#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compile the small read-only host geometry adapter against admitted OpenROAD.

Reuses the exact original public-header/compiler/core ABI component receipt;
never rebuilds OpenROAD, fetches a substitute, or implements target behavior.
The original larger producer's whole deadline failure remains a failure.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import resource
import shlex
import shutil
import signal
import threading
import time

from silicon_synth import ROOT, CommandFailure, run, sha

COMPILER_COMPONENT_SHA = '78268e97e4ae26440c3537e3e5c2b0ce77057b52ec5f10b117dd3dee2c3abdef'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(data):
    require(set(data) == {'schema', 'db_units_per_micron', 'top', 'nets', 'ports'} and
            data['schema'] == 'lemma-opendb-native-geometry/1' and
            type(data['db_units_per_micron']) is int and data['db_units_per_micron'] == 1000,
            'exact native geometry schema/units required')
    names = set()
    layers, kinds = Counter(), Counter()
    rectangles = vias = 0
    for net in data['nets']:
        require(set(net) == {'name', 'type', 'iterms', 'bterms', 'shapes', 'wire_shape_count',
                            'wire_via_count', 'RECT_count', 'special_box_count'}, 'net schema')
        require(type(net['name']) is str and net['name'] not in names, 'duplicate/invalid net')
        names.add(net['name'])
        require(net['type'] in ('SIGNAL', 'CLOCK', 'POWER', 'GROUND', 'RESET', 'SCAN', 'TIEOFF'),
                'unqualified signal type')
        for key in ('wire_shape_count', 'wire_via_count', 'RECT_count', 'special_box_count'):
            require(type(net[key]) is int and net[key] >= 0, 'noninteger native count')
        require(all(type(t) is list and len(t) == 2 and all(type(v) is str for v in t)
                    for t in net['iterms']) and len({tuple(t) for t in net['iterms']}) == len(net['iterms']),
                'invalid/duplicate native instance terminal')
        require(all(type(t) is str for t in net['bterms']) and
                len(set(net['bterms'])) == len(net['bterms']), 'invalid/duplicate native block terminal')
        actual = Counter()
        witnesses = Counter()
        for box in net['shapes']:
            validate_shape(box)
            key = (box['layer'], tuple(box['rect_nm']))
            if box['kind'] == 'decoder_rect_witness':
                witnesses[key] += 1
            else:
                layers[box['layer']] += 1
                kinds[box['kind']] += 1
                if box['kind'] == 'signal_wire_or_rect':
                    actual[key] += 1
        require(not witnesses - actual and sum(witnesses.values()) == net['RECT_count'],
                'full decoder RECT dimensions differ from native shape iterator')
        require(sum(actual.values()) == net['wire_shape_count'], 'native wire count mismatch')
        rectangles += net['RECT_count']; vias += net['wire_via_count']
    ports = set()
    for port in data['ports']:
        require(set(port) == {'terminal', 'net', 'shapes'} and type(port['terminal']) is str and
                port['net'] in names and port['shapes'], 'unbound native port')
        ports.add(port['terminal'])
        for box in port['shapes']:
            validate_shape(box)
            require(box['kind'] == 'port', 'nonport block shape')
    require(rectangles > 0 and vias > 0 and kinds['special_via'] > 0 and kinds['special_wire'] > 0,
            'real routed signal/patch/via/PG geometry required')
    return {'nets': len(names), 'ports': len(ports), 'native_RECT_dimensions_bound': rectangles,
            'signal_vias': vias, 'shape_kinds': dict(kinds), 'layers': dict(layers)}


def validate_shape(box):
    require(set(box) == {'kind', 'layer', 'rect_nm'} and type(box['layer']) is str and
            box['kind'] in ('signal_wire_or_rect', 'signal_via', 'decoder_rect_witness',
                            'special_wire', 'special_via', 'port'), 'shape schema')
    r = box['rect_nm']
    require(type(r) is list and len(r) == 4 and all(type(v) is int and -(1 << 31) <= v < 1 << 31 for v in r)
            and r[0] < r[2] and r[1] < r[3], 'native mask rectangle')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler-receipt', required=True, type=Path)
    p.add_argument('--input-odb', required=True, type=Path)
    p.add_argument('--work-dir', required=True, type=Path)
    args = p.parse_args()
    source = ROOT / 'tooling/silicon/opendb-geometry-export.cpp'
    basis, odb, out = (x.resolve() for x in (args.compiler_receipt, args.input_odb, args.work_dir))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    started = time.monotonic(); deadline = started + 180
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    r = {'schema': 'lemma-native-geometry-host-adapter/1', 'status': 'FAIL', 'scope': __doc__,
         'bounds': {'whole_seconds': 180, 'compile_seconds': 120, 'export_seconds': 40,
                    'AS_bytes': 2 << 30, 'export_AS_bytes': 1 << 30, 'combined_RSS_bytes': 2 << 30,
                    'export_combined_RSS_bytes': 1 << 30, 'host_available_floor_bytes': 6 << 30,
         'output_bytes': 1 << 30}, 'commands': [], 'source_inputs': {}, 'peak_RSS_bytes': 0}
    def interrupted(number, frame):
        raise InterruptedError('Owned host adapter cancelled')
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    stopped = threading.Event(); violation = []; active_cap = [2 << 30]
    def monitor():
        while not stopped.wait(.1):
            ps = {}
            for proc in Path('/proc').iterdir():
                if not proc.name.isdigit(): continue
                try:
                    fields = (proc/'stat').read_text().rsplit(') ', 1)[1].split()
                    ps[int(proc.name)] = (int(fields[1]), int(fields[21])*os.sysconf('SC_PAGE_SIZE'))
                except (OSError, ValueError, IndexError): pass
            ids = {os.getpid()}
            for _ in range(12): ids |= {pid for pid, (parent, _) in ps.items() if parent in ids}
            rss = sum(ps.get(pid, (0, 0))[1] for pid in ids)
            r['peak_RSS_bytes'] = max(r['peak_RSS_bytes'], rss)
            available = next(int(row.split()[1])*1024 for row in Path('/proc/meminfo').read_text().splitlines()
                             if row.startswith('MemAvailable:'))
            if rss > active_cap[0] or available < 6 << 30:
                violation.append({'RSS_bytes': rss, 'available_bytes': available})
                os.kill(os.getpid(), signal.SIGTERM); return
    def invoke(argv, name, seconds, expected_failure=False):
        try: record = run(argv, out/(name+'.log'), min(deadline, time.monotonic()+seconds))
        except CommandFailure as e:
            r['commands'].append(e.record)
            require(expected_failure and not e.record['timed_out'] and e.record['exit_code'] != 0,
                    'unexpected owned command failure: '+name)
            return
        r['commands'].append(record)
        require(not expected_failure, 'negative accepted: '+name)
    try:
        r['launch_available_bytes'] = next(int(row.split()[1])*1024
            for row in Path('/proc/meminfo').read_text().splitlines() if row.startswith('MemAvailable:'))
        require(r['launch_available_bytes'] >= 6 << 30, 'fresh host available floor')
        require(shutil.disk_usage(out).free >= 1 << 30, 'free output floor')
        require(sha(basis) == COMPILER_COMPONENT_SHA, 'exact original compiler/header/core component required')
        old = json.loads(basis.read_text())
        require(old['status'] == 'PASS_FRESH_HOST_MODULE_COMPILE_NOT_LOADED_OR_QUALIFIED' and old['source_seal_equal'] and
                all(sha(Path(name)) == digest for name, digest in old['source_inputs'].items()),
                'original compile component source closure changed')
        r['source_inputs'] = {str(q): sha(q) for q in (Path(__file__).resolve(), source, basis, odb)}
        argv = old['commands'][0]['argv'][:]
        old_source = str(ROOT/'tooling/silicon/opendb-access-export.cpp')
        require(argv.count(old_source) == 1 and argv[-2] == '-o', 'qualified compiler invocation shape')
        argv[argv.index(old_source)] = str(source); argv[-1] = str(out/'lemma_geometry_export.so')
        (out/'source.cpp').write_bytes(source.read_bytes())
        threading.Thread(target=monitor, daemon=True).start()
        # Discover every original/new transitive header before the sole compile.
        invoke(argv[:-2]+['-M', '-MF', str(out/'headers.d'), '-MT', 'geometry'], 'headers', 15)
        dep_text = (out/'headers.d').read_text().replace('\\\n', ' ')
        headers = [Path(name) for name in shlex.split(dep_text.split(':', 1)[1])]
        require(headers and all(q.is_absolute() and q.is_file() for q in headers), 'complete public header closure')
        r['source_inputs'].update(old['source_inputs'])
        r['source_inputs'].update({str(q): sha(q) for q in headers})
        r['compile_argv'] = argv
        (out/'plan.json').write_text(json.dumps(r, indent=2)+'\n')
        invoke(argv, 'compile', 120)
        require(not violation, 'owned resource guard')
        active_cap[0] = 1 << 30
        resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
        tool = next(Path(q) for q in old['source_inputs'] if q.endswith('/bin/.openroad-wrapped'))
        wrapper = tool.parent/'openroad'
        r['source_inputs'][str(wrapper)] = sha(wrapper)
        def script(name, input_path, output_path, roundtrip=None):
            path = out/(name+'.tcl')
            text = f'load {{{out/"lemma_geometry_export.so"}}} Lemmageometry\nlemma_geometry_export {{{input_path}}} {{{output_path}}}'
            if roundtrip: text += f' {{{roundtrip}}}'
            path.write_text(text+'\n'); return path
        invoke([str(wrapper), '-no_init', '-exit', str(script('export', odb, out/'native.json', out/'roundtrip.odb'))], 'export', 40)
        require(sha(out/'roundtrip.odb') == sha(odb), 'original database roundtrip not byte-identical')
        data = json.loads((out/'native.json').read_text()); r['geometry'] = validate(data)
        # Actual module rejects overwrite and malformed original input; source
        # ODB is immutable and no source queue/layout mutation occurs.
        invoke([str(wrapper), '-no_init', '-exit', str(script('overwrite-negative', odb, out/'native.json'))], 'overwrite-negative', 5, True)
        (out/'truncated.odb').write_bytes(odb.read_bytes()[:64])
        invoke([str(wrapper), '-no_init', '-exit', str(script('truncated-negative', out/'truncated.odb', out/'bad-native.json'))], 'truncated-negative', 5, True)
        require(not (out/'bad-native.json').exists(), 'malformed input produced native geometry')
        r.update(status='PASS_READ_ONLY_NATIVE_WIRE_RECT_CUT_POWER_PORT_EXPORT_NOT_LVS_OR_PROCESS_DRC',
                 module_sha256=sha(out/'lemma_geometry_export.so'), native_sha256=sha(out/'native.json'),
                 byte_identical_original_roundtrip=True,
                 negatives=['existing_output_rejected', 'actual_truncated_ODB_rejected'])
    except BaseException as e:
        r['error'] = repr(e)
    finally:
        stopped.set()
        signal.signal(signal.SIGTERM, previous_term)
        r.update(seconds=time.monotonic()-started, resource_failures=violation,
                 source_seal_equal=all(sha(Path(name)) == digest for name, digest in r['source_inputs'].items()))
        require(sum(q.stat().st_size for q in out.rglob('*') if q.is_file()) <= 1 << 30, 'output budget exceeded')
        (out/'result.json').write_text(json.dumps(r, indent=2)+'\n')
        print(r['status'], r.get('error'), r['seconds'], flush=True)
    return 0 if r['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
