#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded process DRC/transistor LVS on actual routed three-SRAM pen geometry.

Imports original standard-cell and SRAM GDS and original process deck. Missing
or partial geometry, unconnected power, and comparison failures never pass.
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
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--route', type=Path, required=True)
    p.add_argument('--mapping', type=Path, required=True)
    p.add_argument('--pdk', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    p.add_argument('--continue-from-drc-attempt', type=Path,
                   help='Retain a source-matched failed DRC attempt and independently continue GDS extraction/LVS')
    args = p.parse_args()
    out, route, mapping, pdk = (v.resolve() for v in (args.work_dir, args.route, args.mapping, args.pdk))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 << 20, 512 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    report = {'schema': 'lemma-pen-process/1', 'status': 'FAIL', 'scope': __doc__,
              'commands': [], 'process_drc': 'NOT_RUN', 'transistor_extraction': 'NOT_RUN',
              'lvs': 'NOT_RUN', 'power_grid': 'NOT_IMPLEMENTED',
              'bounds': {'whole_seconds': 240, 'process_seconds': 90, 'extraction_seconds': 90,
                         'lvs_seconds': 45, 'AS_bytes': 4 << 30, 'file_bytes': 512 << 20}}

    def invoke(argv, name, seconds, stdin=None):
        try:
            record = run(argv, out / (name + '.log'), min(started + 240, time.monotonic() + seconds), stdin)
        except CommandFailure as error:
            report['commands'].append(error.record)
            raise
        report['commands'].append(record)

    try:
        macro = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
        std = pdk / 'ihp-sg13g2/libs.ref/sg13g2_stdcell'
        sram = mapping / 'pdk/ihp-sg13g2/libs.ref/sg13g2_sram'
        macro_gds, macro_cdl = sram / 'gds' / (macro + '.gds'), sram / 'cdl' / (macro + '.cdl')
        admitted = json.loads((mapping / 'result.json').read_text())
        require(admitted['status'].startswith('PASS_MAINTAINED_'), 'real SRAM mapping required')
        for path in (macro_gds, macro_cdl):
            name = str(path.relative_to(mapping / 'pdk'))
            require(sha(path) == admitted['collateral'][name]['sha256'], 'SRAM process input differs')
        magic, netgen = (Path(shutil.which(v) or '').resolve() for v in ('magic', 'netgen'))
        require(magic.is_file() and netgen.is_file(), 'actual Magic/Netgen required')
        rc = pdk / 'ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc'
        inputs = [Path(__file__).resolve(), ROOT / 'scripts/silicon_synth.py',
                  ROOT / 'tooling/silicon/process.tcl', ROOT / 'tooling/silicon/extract.tcl',
                  route / 'routed.def', route / 'routed.v', macro_gds, macro_cdl,
                  std / 'gds/sg13g2_stdcell.gds', std / 'cdl/sg13g2_stdcell.cdl', rc, magic, netgen]
        report['source_inputs'] = {str(path): sha(path) for path in inputs}
        shutil.copyfile(route / 'routed.def', out / 'routed.def')
        # Use the actual derived via geometry too. Standard LEF is otherwise
        # immutable; the process rule deck and both transistor GDS stay original.
        process = (ROOT / 'tooling/silicon/process.tcl').read_text()
        # Batch import must not run the default background incremental DRC.
        # The explicit drc(full) phase below owns its separate budget.
        process = process.replace('    gds readonly true', '    drc off\n    gds readonly true', 1)
        process = process.replace('gds read $pdk/libs.ref/sg13g2_stdcell/gds/sg13g2_stdcell.gds',
            'gds read $pdk/libs.ref/sg13g2_stdcell/gds/sg13g2_stdcell.gds\n' +
            f'    gds read {{{macro_gds}}}')
        process = process.replace('lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef',
            f'lef read {{{route / "enclosure/repaired-original.lef"}}}')
        process = process.replace('lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef',
            'lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef\n' +
            f'    lef read {{{sram / "lef" / (macro + ".lef")}}}')
        header = f'set pdk {{{pdk/"ihp-sg13g2"}}}\nset out {{{out}}}\nset top lemma_pen\n'
        (out / 'process.tcl').write_text(header + process)
        report['status'] = 'RUNNING'
        (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')
        if args.continue_from_drc_attempt:
            prior = args.continue_from_drc_attempt.resolve()
            previous = json.loads((prior / 'result.json').read_text())
            # Initial observer retained RUNNING in its terminal JSON despite
            # a real timed-out command and exit1. Admit only that explicit
            # terminal signature; an ordinary live RUNNING job cannot resume.
            terminal_failure = previous['status'] == 'FAIL' or (
                previous['status'] == 'RUNNING' and previous.get('error') and
                previous.get('commands') and previous['commands'][-1].get('timed_out') is True)
            require(terminal_failure and previous['source_seal_equal'], 'actual sealed failed DRC attempt required')
            require(all(previous['source_inputs'][str(path)] == sha(path)
                        for path in (route / 'routed.def', route / 'routed.v', macro_gds, macro_cdl)),
                    'prior DRC source/geometry differs')
            report['process_drc'] = {'status': 'REUSED_FAILURE', 'receipt': str(prior / 'result.json'),
                                     'sha256': sha(prior / 'result.json')}
            report['source_inputs'][str(prior / 'result.json')] = sha(prior / 'result.json')
            # The old flow wrote GDS only after finishing DRC, preventing an
            # independent extraction when DRC exceeded its own bound. Import
            # the same original geometry and stream it without repeating DRC.
            import_only = process[:process.index('    drc style drc(full)')] + '''    gds write $out/layout.gds
} failure]} {
    puts stderr "Geometry import failed: $failure"
    exit 1
}
quit -noprompt
'''
            (out / 'import-only.tcl').write_text(header + import_only)
            invoke([str(magic), '-dnull', '-noconsole', '-rcfile', str(rc)], 'import', 30, out / 'import-only.tcl')
            count = None
        else:
            invoke([str(magic), '-dnull', '-noconsole', '-rcfile', str(rc)], 'process', 90, out / 'process.tcl')
            count = int((out / 'process-drc-count.txt').read_text().strip())
            report['process_drc'] = {'status': 'PASS' if count == 0 else 'FAIL', 'violations': count,
                'report_sha256': sha(out / 'process-drc.rpt'), 'deck': 'original public beta SG13G2 drc(full)'}
        extract = out / 'extract.tcl'
        extract.write_text(header + (ROOT / 'tooling/silicon/extract.tcl').read_text())
        invoke([str(magic), '-dnull', '-noconsole', '-rcfile', str(rc)], 'extract', 90, extract)
        require((out / 'extracted.spice').stat().st_size > 1000, 'empty transistor extraction')
        report['transistor_extraction'] = {'status': 'EXTRACTED', 'sha256': sha(out / 'extracted.spice')}
        compare = out / 'lvs.tcl'
        compare.write_text(f'''set reference [readnet spice {{{std/'cdl/sg13g2_stdcell.cdl'}}}]
readnet spice {{{macro_cdl}}} $reference
readnet verilog {{{route/'routed.v'}}} $reference
lvs {{{out/'extracted.spice'} lemma_pen}} [list lemma_pen $reference] {{{pdk/'ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl'}}} {{{out/'lvs.rpt'}}} -json
''')
        invoke([str(netgen), '-batch', 'source', str(compare)], 'lvs', 45)
        match = lvs_matches((out / 'lvs.rpt').read_text())
        report['lvs'] = {'status': 'PASS' if match else 'FAIL', 'report_sha256': sha(out / 'lvs.rpt')}
        require(count == 0 and match, 'actual process DRC/LVS failed')
        # Even a local comparison cannot establish the absent power grid.
        report['status'] = 'PASS_SCOPED_PROCESS_DRC_LVS_POWER_UNIMPLEMENTED'
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
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
