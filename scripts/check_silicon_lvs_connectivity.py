#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Qualify the explicit connectivity-only Magic adapter on real process geometry.

Original inverter W/L and bulk terminals must match its original CDL. Deliberate
width and bulk mutations must fail. This is not a whole-design DRC/LVS result.
"""
import argparse
import json
from pathlib import Path
import resource
import shutil
import time

from silicon_enclosure import require
from silicon_synth import CommandFailure, ROOT, lvs_matches, run, sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdk', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    args = parser.parse_args()
    out, pdk = args.work_dir.resolve(), args.pdk.resolve() / 'ihp-sg13g2'
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    started = time.monotonic()
    resource.setrlimit(resource.RLIMIT_AS, (2 << 30, 2 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64 << 20, 64 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report = {'schema': 'lemma-connectivity-only-extraction-preflight/1', 'status': 'FAIL',
              'scope': __doc__, 'commands': [], 'cases': [],
              'bounds': {'whole_seconds': 90, 'each_seconds': 20, 'AS_bytes': 2 << 30}}
    try:
        magic, netgen = (Path(shutil.which(name) or '').resolve() for name in ('magic', 'netgen'))
        require(magic.is_file() and netgen.is_file(), 'actual Magic and Netgen required')
        std = pdk / 'libs.ref/sg13g2_stdcell'
        setup = pdk / 'libs.tech/netgen/ihp-sg13g2_setup.tcl'
        inputs = [Path(__file__).resolve(), ROOT / 'scripts/silicon_synth.py',
                  ROOT / 'tooling/silicon/extract.tcl', magic, netgen,
                  std / 'gds/sg13g2_stdcell.gds', std / 'cdl/sg13g2_stdcell.cdl', setup]
        inputs += sorted(path for path in (pdk / 'libs.tech/magic').rglob('*') if path.is_file())
        report['source_inputs'] = {str(path): sha(path) for path in inputs}

        def invoke(argv, name, stdin=None):
            try:
                record = run(argv, out / (name + '.log'),
                             min(started + 90, time.monotonic() + 20), stdin)
            except CommandFailure as error:
                report['commands'].append(error.record)
                raise
            report['commands'].append(record)

        recipe = (ROOT / 'tooling/silicon/extract.tcl').read_text().replace(
            '    gds read $out/layout.gds', f'    gds read {{{std / "gds/sg13g2_stdcell.gds"}}}')
        script = out / 'extract.tcl'
        script.write_text(f'set out {{{out}}}\nset top sg13g2_inv_1\nset connectivity_only_extraction 1\n' + recipe)
        invoke([str(magic), '-dnull', '-noconsole', '-rcfile',
                str(pdk / 'libs.tech/magic/ihp-sg13g2.magicrc')], 'extract', script)
        original = (out / 'extracted.spice').read_text()
        for name, before, after, expected in (
                ('original', '', '', True),
                ('wrong-width', 'w=0.74u', 'w=0.37u', False),
                ('wrong-bulk', 'M1000 Y A VDD VDD', 'M1000 Y A VDD VSS', False)):
            require(not before or original.count(before) == 1, 'mutation no longer targets real device')
            data = out / (name + '.spice')
            data.write_text(original.replace(before, after) if before else original)
            comparison = out / (name + '.tcl')
            comparison.write_text(f'''set reference [readnet spice {{{std / 'cdl/sg13g2_stdcell.cdl'}}}]
lvs {{{data} sg13g2_inv_1}} [list sg13g2_inv_1 $reference] {{{setup}}} {{{out / (name + '.rpt')}}} -json
''')
            invoke([str(netgen), '-batch', 'source', str(comparison)], name)
            matches = lvs_matches((out / (name + '.rpt')).read_text())
            report['cases'].append({'name': name, 'matches': matches, 'expected': expected,
                                    'report_sha256': sha(out / (name + '.rpt'))})
            require(matches == expected, 'original/device negative comparison differs')
        report['status'] = 'PASS_TRANSISTOR_GEOMETRY_AND_BULK_CONTROLS_ONLY'
    except BaseException as error:
        report['error'] = repr(error)
    finally:
        report['source_seal_equal'] = all(sha(Path(path)) == digest
                                         for path, digest in report.get('source_inputs', {}).items())
        if not report['source_seal_equal']:
            report['status'] = 'FAIL'
        report['seconds'] = time.monotonic() - started
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'])
    return 0 if report['status'].startswith('PASS_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
