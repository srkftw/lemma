#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded original SG13G2 row-filler correction on selected0.6 routed geometry.

This adds physical CORE SPACERs only. Functional cells, all signal wires and
the native power grid stay fixed. Original process/LVS/RC checks remain separate.
"""
import argparse
import json
import os
from pathlib import Path
import resource
import shutil
import tarfile
import threading
import time

from silicon_filler_source import all_row_plan, lef_masters, SELECTED_PLAN_SHA, SELECTED_SOURCE_ODB
from silicon_geometry_export import require
from silicon_pen_process import OwnedProcessStop
from silicon_synth import ROOT, CommandFailure, run, sha

OWNED_RSS = 1 << 30
HOST_RESERVE = int(6.5*(1 << 30))
HOST_INPUTS = ('silicon_row_filler.py', 'silicon_filler_source.py', 'silicon_gds_geometry.py',
               'silicon_geometry_export.py', 'silicon_pen_process.py', 'silicon_synth.py',
               'silicon_acceptance_launch.py', 'silicon_buffered_pins.py', 'silicon_enclosure.py',
               'silicon_power_ports.py', 'silicon_lvs_alias.py')


def require_reserve(available, owned_cap=OWNED_RSS, host_reserve=HOST_RESERVE):
    require(all(type(value) is int and value > 0 for value in (available, owned_cap, host_reserve)) and
            available >= owned_cap+host_reserve, 'fresh owned-cap plus host-reserve proof')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native-descriptor', required=True, type=Path)
    parser.add_argument('--openroad', required=True, type=Path)
    parser.add_argument('--work-dir', required=True, type=Path)
    args = parser.parse_args()
    out = args.work_dir.resolve(); basis = args.native_descriptor.resolve(); tool = args.openroad.resolve()
    require(not out.exists() and out.is_relative_to(ROOT/'build'), 'unused ignored row-fill output required')
    out.mkdir(parents=True)
    started = time.monotonic(); deadline = started+40
    resource.setrlimit(resource.RLIMIT_AS, (3 << 30, 3 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 << 20, 128 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    report = {'schema': 'lemma-original-row-filler/1', 'status': 'FAIL', 'scope': __doc__,
              'bounds': {'whole_seconds': 40, 'tool_seconds': 30, 'AS_bytes': 3 << 30,
                         'combined_RSS_bytes': OWNED_RSS, 'host_reserve_bytes': HOST_RESERVE,
                         'output_bytes': 128 << 20}, 'source_inputs': {}, 'commands': [], 'peak_RSS_bytes': 0}
    stopped = threading.Event(); failures = []; stopper = OwnedProcessStop()
    def monitor():
        while not stopped.wait(.05):
            queue = [os.getpid()]; seen = set(); rss = 0
            while queue:
                pid = queue.pop()
                if pid in seen: continue
                seen.add(pid)
                try:
                    rss += int(Path(f'/proc/{pid}/statm').read_text().split()[1])*os.sysconf('SC_PAGE_SIZE')
                    queue.extend(map(int, Path(f'/proc/{pid}/task/{pid}/children').read_text().split()))
                except (OSError, ValueError, IndexError): pass
            report['peak_RSS_bytes'] = max(report['peak_RSS_bytes'], rss)
            available = next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                             if line.startswith('MemAvailable:'))
            output = sum(path.stat().st_size for path in out.rglob('*') if path.is_file())
            if (rss > OWNED_RSS or available < HOST_RESERVE or output > 128 << 20 or
                    time.monotonic() >= deadline-1) and not failures:
                failures.append({'owned_RSS_bytes': rss, 'available_bytes': available,
                                 'output_bytes': output, 'elapsed_seconds': time.monotonic()-started})
            if failures: stopper.stop(seen-{os.getpid()})
    thread = threading.Thread(target=monitor, daemon=True)
    try:
        available = next(int(line.split()[1])*1024 for line in Path('/proc/meminfo').read_text().splitlines()
                         if line.startswith('MemAvailable:'))
        require_reserve(available); require(shutil.disk_usage(out).free >= 1 << 30, 'free output floor')
        report['launch_available_bytes'] = available
        config = json.loads(basis.read_text()); source = Path(config['source_odb'])
        inputs = [basis, source, Path(config['native_instances']), Path(config['routed_def']),
                  *map(Path, config['lef_files'][1:]), tool, tool.parent/'.openroad-wrapped']
        require(sha(source) == SELECTED_SOURCE_ODB and
                all(config['source_inputs'][str(path)] == sha(path) for path in inputs[1:-2]),
                'original native route/instance/DEF/LEF closure differs')
        require(sha(tool) == '2d49fb4cc8b03f39d089090015e24b8a783d08949491200e119048b158b6649d' and
                sha(tool.parent/'.openroad-wrapped') == 'ada97e26cd2f192265ed3b217fa00c67b5e009c4ea23b1f7b38f69beacccaaca',
                'exact pinned native OpenDB core required')
        masters = {}
        for name in config['lef_files'][1:]:
            actual = lef_masters(Path(name).read_text())
            require(not set(masters) & set(actual), 'ambiguous original source master')
            masters.update(actual)
        plan = all_row_plan(Path(config['routed_def']).read_text(),
                            json.loads(Path(config['native_instances']).read_text()), masters)
        plan_path = out/'row-plan.json'; plan_path.write_text(json.dumps(plan, indent=2)+'\n')
        require(sha(plan_path) == SELECTED_PLAN_SHA, 'source-bound selected row plan differs')
        driver = out/'insert.py'
        driver.write_text('import sys\nfrom pathlib import Path\nsys.path.insert(0,'+repr(str(ROOT/'scripts'))+')\n'
                          'from silicon_filler_source import insert_original_fillers\n'
                          'insert_original_fillers(Path('+repr(str(source))+'),Path('+repr(str(plan_path))+'),'
                          'Path('+repr(str(out/'candidate'))+'))\n')
        inputs += [ROOT/'scripts'/name for name in HOST_INPUTS]+[driver, plan_path]
        report['source_inputs'] = {str(path): sha(path) for path in dict.fromkeys(inputs)}
        with tarfile.open(out/'source-closure.tar.gz', 'x:gz') as archive:
            for index, path in enumerate(dict.fromkeys(inputs)):
                if path.suffix in ('.py', '.json', '.lef'):
                    archive.add(path, arcname=f'inputs/{index:03d}-{path.name}')
        report['source_archive_sha256'] = sha(out/'source-closure.tar.gz')
        (out/'plan.json').write_text(json.dumps(report, indent=2)+'\n')
        thread.start()
        report['commands'].append(run([str(tool), '-python', '-exit', str(driver)], out/'insertion.log',
                                      min(deadline-8, time.monotonic()+30)))
        result = json.loads((out/'candidate/insertion.json').read_text())
        require(result['status'] == 'PASS_ORIGINAL_ALLROW_FILLER_NATIVE_PLACEMENT_PG_OVERLAP_SIGNALS_UNCHANGED_NOT_PROCESS_DRC'
                and not failures, 'actual native filler correction failed')
        report.update(status='PASS_SOURCE_BOUND_ORIGINAL_ALLROW_FILLER_INSERTION_AND_SIGNALS_NOT_PROCESS_DRC', geometry=result)
    except BaseException as error:
        report['error'] = repr(error)
        if isinstance(error, CommandFailure): report['commands'].append(error.record)
    finally:
        stopped.set()
        if thread.is_alive(): thread.join()
        report.update(seconds=time.monotonic()-started, original_whole_deadline_met=time.monotonic() <= deadline,
                      resource_errors=failures,
                      source_seal_equal=all(sha(name) == digest for name, digest in report['source_inputs'].items()))
        if failures or not report['source_seal_equal'] or not report['original_whole_deadline_met']:
            report['status'] = 'FAIL'
        (out/'result.json').write_text(json.dumps(report, indent=2)+'\n')
        print(report['status'], report.get('error'), report['seconds'], flush=True)
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__': raise SystemExit(main())
