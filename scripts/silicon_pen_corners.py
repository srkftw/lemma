#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Assess actual routed SPEF with the available original public timing corners.

Typical25C and slow125C are matched stdcell/SRAM PVT pairs. Public fast
libraries use stdcell-40C/SRAM-55C: report that mixed-temperature diagnostic
separately; it is not a matched fast-corner signoff result.
"""
import argparse
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import time
from silicon_enclosure import require
from silicon_synth import CommandFailure, ROOT, run, sha

REVISION = '5e6d592e4002946a4616f798c357f0f3c06cf3b6'
MACRO = 'RM_IHPSG13_1P_256x64_c2_bm_bist'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--route', type=Path, required=True)
    p.add_argument('--pdk', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    out, route, pdk = (v.resolve() for v in (args.work_dir, args.route, args.pdk))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (3 << 30, 3 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (256 << 20, 256 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    report = {'schema': 'lemma-pen-extracted-timing-corners/1', 'status': 'FAIL',
              'scope': __doc__, 'process_revision': REVISION, 'commands': [], 'cases': [],
              'bounds': {'whole_seconds': 300, 'each_seconds': 30, 'AS_bytes': 3 << 30}}
    try:
        openroad = Path(shutil.which('openroad') or '').resolve()
        require(openroad.is_file(), 'actual OpenROAD required')
        inputs = [Path(__file__).resolve(), ROOT / 'scripts/silicon_synth.py', openroad,
                  route / 'routed.odb', route / 'routed.sdc', *[route / (v + '.spef') for v in ('min', 'nom', 'max')]]
        report['source_inputs'] = {str(path): sha(path) for path in inputs}
        for corner, std_suffix, sram_suffix, matched in (
            ('typical', 'typ_1p20V_25C', 'typ_1p20V_25C', True),
            ('slow', 'slow_1p08V_125C', 'slow_1p08V_125C', True),
            ('fast_mixed_temperature', 'fast_1p32V_m40C', 'fast_1p32V_m55C', False)):
            stdname = 'ihp-sg13g2/libs.ref/sg13g2_stdcell/lib/sg13g2_stdcell_' + std_suffix + '.lib'
            sramname = 'ihp-sg13g2/libs.ref/sg13g2_sram/lib/' + MACRO + '_' + sram_suffix + '.lib'
            libraries = []
            for name in (stdname, sramname):
                target = out / Path(name).name
                target.write_bytes(subprocess.check_output(['git', '-C', str(pdk), 'show', REVISION + ':' + name], timeout=10))
                libraries.append(target)
                report.setdefault('libraries', {})[name] = sha(target)
            for rc in ('min', 'nom', 'max'):
                name = corner + '_' + rc
                script = out / (name + '.tcl')
                script.write_text(f'''read_liberty {{{libraries[0]}}}
read_liberty {{{libraries[1]}}}
read_db {{{route/'routed.odb'}}}
read_sdc {{{route/'routed.sdc'}}}
read_spef {{{route/(rc+'.spef')}}}
report_checks -path_delay max -group_path_count 5 -digits 6 > {{{out/(name+'-setup.rpt')}}}
report_checks -path_delay min -group_path_count 5 -digits 6 > {{{out/(name+'-hold.rpt')}}}
report_worst_slack -max -digits 6 > {{{out/(name+'-setup-summary.rpt')}}}
report_worst_slack -min -digits 6 > {{{out/(name+'-hold-summary.rpt')}}}
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > {{{out/(name+'-electrical.rpt')}}}
''')
                try:
                    record = run([str(openroad), '-no_init', '-exit', str(script)], out / (name + '.log'),
                                 min(started + 300, time.monotonic() + 30))
                except CommandFailure as error:
                    report['commands'].append(error.record)
                    raise
                report['commands'].append(record)
                setup = float(re.search(r'worst slack max ([-\d.]+)', (out / (name + '-setup-summary.rpt')).read_text())[1])
                hold = float(re.search(r'worst slack min ([-\d.]+)', (out / (name + '-hold-summary.rpt')).read_text())[1])
                electrical = (out / (name + '-electrical.rpt')).read_text().count('(VIOLATED)')
                report['cases'].append({'corner': corner, 'matched_PVT': matched, 'RC': rc,
                    'setup_ns': setup, 'hold_ns': hold, 'electrical_violations': electrical,
                    'log_sha256': sha(out / (name + '.log')),
                    'status': 'PASS_SCOPED_TIMING' if setup >= 0 and hold >= 0 and electrical == 0 else 'FAIL'})
        require(all(v['status'].startswith('PASS_') for v in report['cases'] if v['matched_PVT']),
                'actual matched-corner timing/electrical failures')
        report['status'] = 'PASS_AVAILABLE_MATCHED_CORNERS_FAST_TEMPERATURE_GAP'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['source_seal_equal'] = all(sha(Path(path)) == digest for path, digest in report.get('source_inputs', {}).items())
        if not report['source_seal_equal']:
            report.update(status='FAIL', source_drift=True)
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
