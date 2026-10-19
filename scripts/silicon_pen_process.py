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
    p.add_argument('--process-seconds', type=int, default=90)
    p.add_argument('--import-seconds', type=int, default=30)
    p.add_argument('--extraction-seconds', type=int, default=90)
    p.add_argument('--whole-seconds', type=int, default=240)
    p.add_argument('--question', default='Can the bounded original process deck complete on the declared real three-SRAM routed geometry?')
    p.add_argument('--direct-import-extraction', action='store_true', help='After a retained failed process attempt, extract original GDS+actual DEF directly without repeating the failed GDS re-stream')
    p.add_argument('--continue-from-drc-attempt', type=Path,
                   help='Retain a source-matched failed DRC attempt and independently continue GDS extraction/LVS')
    args = p.parse_args()
    out, route, mapping, pdk = (v.resolve() for v in (args.work_dir, args.route, args.mapping, args.pdk))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    require(1 <= args.process_seconds <= 600 and 1 <= args.import_seconds <= 120 and
            1 <= args.extraction_seconds <= 600 and 1 <= args.whole_seconds <= 1500 and
            1 <= len(args.question) <= 1024, 'invalid prospective process budget/question')
    resource.setrlimit(resource.RLIMIT_AS, (4 << 30, 4 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (512 << 20, 512 << 20))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic()
    report = {'schema': 'lemma-pen-process/1', 'status': 'FAIL', 'scope': __doc__,
              'commands': [], 'process_drc': 'NOT_RUN', 'transistor_extraction': 'NOT_RUN',
              'lvs': 'NOT_RUN', 'power_grid': 'NOT_IMPLEMENTED',
              'question': args.question,
              'bounds': {'whole_seconds': args.whole_seconds, 'process_seconds': args.process_seconds, 'import_seconds': args.import_seconds, 'extraction_seconds': args.extraction_seconds,
                         'lvs_seconds': 45, 'AS_bytes': 4 << 30, 'file_bytes': 512 << 20}}

    def invoke(argv, name, seconds, stdin=None):
        phase = {'process': 'process_drc', 'extract': 'transistor_extraction', 'lvs': 'lvs'}.get(name)
        if phase:
            report[phase] = {'status': 'RUNNING'}
        try:
            record = run(argv, out / (name + '.log'), min(started + args.whole_seconds, time.monotonic() + seconds), stdin)
        except CommandFailure as error:
            if phase:
                report[phase] = {'status': 'FAIL', 'error': repr(error)}
            report['commands'].append(error.record)
            raise
        report['commands'].append(record)

    try:
        macro = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
        std = pdk / 'ihp-sg13g2/libs.ref/sg13g2_stdcell'
        sram = mapping / 'pdk/ihp-sg13g2/libs.ref/sg13g2_sram'
        macro_gds, macro_cdl = sram / 'gds' / (macro + '.gds'), sram / 'cdl' / (macro + '.cdl')
        admitted = json.loads((mapping / 'result.json').read_text())
        require(admitted['status'].startswith(('PASS_MAINTAINED_', 'PASS_ISOLATED_CANDIDATE_')), 'real SRAM mapping required')
        report['candidate_only'] = admitted.get('candidate_only', False)
        report['mapping_receipt'] = {'path': str(mapping / 'result.json'), 'sha256': sha(mapping / 'result.json')}
        require(report['candidate_only'] == admitted['status'].startswith('PASS_ISOLATED_CANDIDATE_'), 'mapping candidate scope differs')
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
        inputs += [std / 'lef/sg13g2_tech.lef', std / 'lef/sg13g2_stdcell.lef',
                   route / 'enclosure/repaired-original.lef', sram / 'lef' / (macro+'.lef'),
                   pdk / 'ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl']
        inputs += sorted(path for path in rc.parent.rglob('*') if path.is_file())
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
            import_only = process[:process.index('    drc style drc(full)')] + '''} failure]} {
    puts stderr "Geometry import failed: $failure"
    exit 1
}
quit -noprompt
'''
            (out / 'import-only.tcl').write_text(header + import_only)
            if not args.direct_import_extraction:
                invoke([str(magic), '-dnull', '-noconsole', '-rcfile', str(rc)], 'import', args.import_seconds, out / 'import-only.tcl')
            count = None
        else:
            try:
                invoke([str(magic), '-dnull', '-noconsole', '-rcfile', str(rc)], 'process', args.process_seconds, out / 'process.tcl')
                count = int((out / 'process-drc-count.txt').read_text().strip())
                report['process_drc'] = {'status': 'PASS' if count == 0 else 'FAIL', 'violations': count,
                    'report_sha256': sha(out / 'process-drc.rpt'), 'deck': 'original public beta SG13G2 drc(full)'}
            except CommandFailure as error:
                # Geometry is written and closed before starting DRC. Retain
                # this failed command and continue only the independent check.
                count = None
                report['process_drc'] = {'status': 'FAIL', 'error': repr(error),
                                        'deck': 'original public beta SG13G2 drc(full)'}
        geometry = out / 'layout.gds'
        if not args.direct_import_extraction:
            require(geometry.is_file() and geometry.stat().st_size > 1000 and
                geometry.read_bytes()[-4:] == bytes((0, 4, 4, 0)), 'no complete source GDS for independent extraction')
            report['imported_geometry'] = {'sha256': sha(geometry), 'bytes': geometry.stat().st_size, 'complete_ENDLIB': True}
        else:
            require(args.continue_from_drc_attempt is not None, 'direct extraction requires retained failed process observation')
            report['imported_geometry'] = {'mode': 'direct original transistor GDS plus actual routed DEF', 'source_DEF_sha256': sha(route / 'routed.def'), 're_streamed_GDS': False}
        extract = out / 'extract.tcl'
        extraction = (ROOT / 'tooling/silicon/extract.tcl').read_text()
        if args.direct_import_extraction:
            # Retain the exact original transistor layouts, LEFs and DEF import.
            # No drc(full) selection precedes extraction in this fresh process.
            body = process[:process.index('    gds write $out/layout.gds')]
            extraction = body + extraction[extraction.index('    extract path $out'):]
        extract.write_text(header + extraction)
        invoke([str(magic), '-dnull', '-noconsole', '-rcfile', str(rc)], 'extract', args.extraction_seconds, extract)
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
