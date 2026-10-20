#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded process DRC/transistor LVS on actual routed three-SRAM pen geometry.

Imports original standard-cell and SRAM GDS and original process deck. Missing
or partial geometry, unconnected power, and comparison failures never pass.
"""
import argparse
import json
import os
from pathlib import Path
import resource
import re
import shutil
import tarfile
import time
from silicon_enclosure import require
from silicon_power_ports import signal_bytes
from silicon_lvs_alias import cdl_alias, verilog_alias, require_originals
from silicon_synth import CommandFailure, ROOT, lvs_matches, run, sha


def power_reference_script(route, out, standard_liberty, sram_liberty):
    """Export both references in the actual producer's Liberty-aware context."""
    return f'''read_liberty {{{standard_liberty}}}
read_liberty {{{sram_liberty}}}
read_db {{{route/'routed.odb'}}}
write_verilog {{{out/'observed-signal.v'}}}
write_verilog -include_pwr_gnd {{{out/'observed-power.v'}}}
'''


def connected_reference_signal_bytes(text):
    """Admit the two exact OpenROAD physical-PG serializations only.

    A route exported before its database reload puts the three PG ports last;
    a later read_db export puts them before the vector ports. All remaining
    bytes, including every cell's power and signal connections, stay intact.
    """
    try:
        return signal_bytes(text)
    except ValueError:
        return signal_bytes(text, reloaded_power=True)


def process_tiling_script(process, step_microns):
    """Change checker tiling only; leave original halo and every rule intact."""
    if step_microns is None:
        return process
    require(step_microns == 600, 'only finite-qualified600um process step admitted')
    anchor = '    drc style drc(full)\n'
    require(process.count(anchor) == 1 and
            not re.search(r'(?m)^\s*drc\s+(?:ignore\b|\*halo\s+\S)', process),
            'one original full-rule style with no halo/rule waiver required')
    return process.replace(anchor, anchor + '''    puts "LEMMA_TILING original-halo"
    drc *halo
    puts "LEMMA_TILING original-step"
    drc *stepsize
    puts "LEMMA_TILING microns-per-unit [cif scale out]"
    drc printrules $out/process-rules-before-step.txt
    drc *stepsize 600um
    puts "LEMMA_TILING retained-halo"
    drc *halo
    puts "LEMMA_TILING selected-step"
    drc *stepsize
    drc printrules $out/process-rules-after-step.txt
    set before_file [open $out/process-rules-before-step.txt r]
    set after_file [open $out/process-rules-after-step.txt r]
    set before_rules [read $before_file]
    set after_rules [read $after_file]
    close $before_file
    close $after_file
    if {$before_rules ne $after_rules} {error "Checker step changed original rule table"}
    puts "LEMMA_TILING original-rule-table-identical"
''', 1)


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
    p.add_argument('--process-drc-only', action='store_true', help='Run original drc(full) directly on original GDS+actual DEF; skip only redundant GDS re-stream, with no extraction/LVS claim')
    p.add_argument('--drc-step-microns', type=int, choices=(600,), help='Explicit finite-qualified600um checker tiling only for full original-deck DRC; no halo/rule reduction or timing/process pass implied')
    p.add_argument('--direct-import-extraction', action='store_true', help='Independently extract original GDS+actual DEF without GDS re-stream; process DRC remains separate and NOT_RUN unless an exact prior failure is bound')
    p.add_argument('--connectivity-only-extraction', action='store_true', help='LVS-only: disable parasitic capacitance/coupling, preserving transistor devices, geometry and terminal connectivity; never timing extraction')
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
              'lvs': 'NOT_RUN', 'power_grid': 'NOT_IMPLEMENTED', 'physical_closure': 'UNVERIFIED',
              'question': args.question,
              'extraction_mode': 'TRANSISTOR_CONNECTIVITY_NO_PARASITIC_C' if args.connectivity_only_extraction else 'FULL_DEFAULT_PARASITICS',
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
            # Magic may publish its interrupted database in the owned Nix
            # temporary directory. Preserve that observed file before shell
            # cleanup; never let retention replace the primary failed result.
            if name == 'process':
                try:
                    text = (out / 'process.log').read_text()
                    found = re.search(r'^Created database crash recovery file (/tmp/(?:nix-shell-[^/]+/)?MAG[0-9]+\.[A-Za-z0-9]+)$', text, re.M)
                    if found:
                        recovery = Path(found[1])
                        if (recovery.is_file() and not recovery.is_symlink() and
                                recovery.stat().st_uid == os.getuid() and recovery.stat().st_size <= 64 << 20):
                            retained = out / 'interrupted-magic-database'
                            shutil.copyfile(recovery, retained)
                            report['interrupted_database'] = {'path': str(retained), 'sha256': sha(retained),
                                                              'scope': 'Failed owned process recovery file, not completed geometry or DRC'}
                except (OSError, UnicodeError) as retention_error:
                    report['recovery_retention_error'] = repr(retention_error)
            raise
        report['commands'].append(record)

    try:
        require(not args.process_drc_only or not (args.direct_import_extraction or args.continue_from_drc_attempt or args.connectivity_only_extraction), 'independent full DRC and extraction are separate questions')
        require(args.drc_step_microns is None or args.process_drc_only,
                'changed checker tiling is scoped only to original full-process DRC')
        macro = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
        std = pdk / 'ihp-sg13g2/libs.ref/sg13g2_stdcell'
        sram = mapping / 'pdk/ihp-sg13g2/libs.ref/sg13g2_sram'
        macro_gds, macro_cdl = sram / 'gds' / (macro + '.gds'), sram / 'cdl' / (macro + '.cdl')
        admitted = json.loads((mapping / 'result.json').read_text())
        require(admitted['status'].startswith(('PASS_MAINTAINED_', 'PASS_ISOLATED_CANDIDATE_')), 'real SRAM mapping required')
        report['candidate_only'] = admitted.get('candidate_only', False)
        report['mapping_receipt'] = {'path': str(mapping / 'result.json'), 'sha256': sha(mapping / 'result.json')}
        producer = json.loads((route / 'result.json').read_text())
        require(producer.get('source_seal_equal') is True, 'actual source-sealed route required')
        require(producer['mapping_receipt']['sha256'] == report['mapping_receipt']['sha256'], 'route mapping producer differs')
        require(producer['route_enclosure']['routed_def_sha256'] == sha(route / 'routed.def'), 'actual routed geometry differs')
        report['route_receipt'] = {'path': str(route / 'result.json'), 'sha256': sha(route / 'result.json')}
        reference_netlist = route / 'routed.v'
        core_grid = producer.get('power_grid') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM'
        if core_grid:
            connected = producer.get('core_power_grid', {}).get('after-route', {})
            require(connected.get('status') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                    connected.get('macro_power_pins') == 9 and connected.get('preserved_BIST_pins') == 423,
                    'actual after-route three-supply/test terminal assessment required')
            reference_netlist = route / 'power-connected.v'
            require(reference_netlist.is_file() and (route / 'routed.odb').is_file(), 'actual connected PG netlist/database required')
            report['power_grid'] = 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM'
            report['power_grid_scope'] = 'Actual three-supply terminal connectivity only; no IR/EM, pad/package, sequencing or full power qualification'
        require(report['candidate_only'] == admitted['status'].startswith('PASS_ISOLATED_CANDIDATE_'), 'mapping candidate scope differs')
        for path in (macro_gds, macro_cdl):
            name = str(path.relative_to(mapping / 'pdk'))
            require(sha(path) == admitted['collateral'][name]['sha256'], 'SRAM process input differs')
        magic, netgen = (Path(shutil.which(v) or '').resolve() for v in ('magic', 'netgen'))
        require(magic.is_file() and netgen.is_file(), 'actual Magic/Netgen required')
        rc = pdk / 'ihp-sg13g2/libs.tech/magic/ihp-sg13g2.magicrc'
        inputs = [Path(__file__).resolve(), ROOT / 'scripts/silicon_power_ports.py', ROOT / 'scripts/silicon_lvs_alias.py', ROOT / 'scripts/silicon_synth.py',
                  ROOT / 'tooling/silicon/process.tcl', ROOT / 'tooling/silicon/extract.tcl',
                  route / 'result.json', mapping / 'result.json', route / 'routed.def', route / 'routed.v', macro_gds, macro_cdl,
                  std / 'gds/sg13g2_stdcell.gds', std / 'cdl/sg13g2_stdcell.cdl', rc, magic, netgen]
        inputs += [std / 'lef/sg13g2_tech.lef', std / 'lef/sg13g2_stdcell.lef',
                   route / 'enclosure/repaired-original.lef', sram / 'lef' / (macro+'.lef'),
                   pdk / 'ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl']
        inputs += sorted(path for path in rc.parent.rglob('*') if path.is_file())
        if args.drc_step_microns is not None:
            control = ROOT / 'build/silicon/task009-full-drc-tiling-controls-a1/result.json'
            require(sha(control) == '34ccb415c6b3188fcf16916ec3ecc0e6237a0e8dbd82476f599d325c0767bda3',
                    'exact original-deck default/600um control producer required')
            qualification = json.loads(control.read_text())
            require(qualification['status'] == 'PASS_ORIGINAL_FULL_DECK_TILING_RULE_IDENTITY_AND_INVERTER_VIA_NEGATIVE_CONTROLS_NOT_CONTROLLER'
                    and qualification['source_seal_equal'] and
                    all(sha(Path(name)) == digest for name, digest in qualification['source_inputs'].items()),
                    'actual source-sealed inverter/badVia1/repairedVia1 controls required')
            inputs += [control] + [Path(name) for name in qualification['source_inputs']]
            report['checker_tiling'] = {'version': 'lemma-original-full-drc-step/1',
                'microns': 600, 'control_receipt': str(control), 'sha256': sha(control),
                'scope': 'Checker work partition only; original full-rule deck/halo/geometry unchanged, no full-controller result inferred from small-cell controls'}
        if core_grid:
            openroad = Path(shutil.which('openroad') or '').resolve()
            require(openroad.is_file(), 'actual OpenROAD required for connected PG reference comparison')
            inputs += [reference_netlist, route / 'routed.odb', route / 'power-grid-after-route.json', openroad,
                       std / 'lib/sg13g2_stdcell_typ_1p20V_25C.lib',
                       sram / 'lib' / (macro + '_typ_1p20V_25C.lib')]
        report['source_inputs'] = {str(path): sha(path) for path in inputs}
        # A source hash alone cannot recover an uncommitted adapter after a
        # later fix. Retain exact caller, recipe, tool and process input bytes
        # before starting any expensive phase; original inputs stay immutable.
        archive = out / 'source-closure.tar.gz'
        with tarfile.open(archive, 'x:gz') as capsule:
            for index, path in enumerate(dict.fromkeys(inputs)):
                capsule.add(path, arcname=f'inputs/{index:04d}-{path.name}')
        require(archive.stat().st_size <= 128 << 20, 'process source archive budget')
        report['source_archive'] = {'path': str(archive), 'sha256': sha(archive),
                                    'scope': 'Exact launch-time input bytes; index follows source_inputs order'}
        shutil.copyfile(route / 'routed.def', out / 'routed.def')
        # Use the actual derived via geometry too. Standard LEF is otherwise
        # immutable; the process rule deck and both transistor GDS stay original.
        process = (ROOT / 'tooling/silicon/process.tcl').read_text()
        # Batch import must not run the default background incremental DRC.
        # The explicit drc(full) phase below owns its separate budget.
        process = process.replace('    gds readonly true', '    drc off\n    gds readonly true', 1)
        process = process.replace('gds read $pdk/libs.ref/sg13g2_stdcell/gds/sg13g2_stdcell.gds',
            'gds read $pdk/libs.ref/sg13g2_stdcell/gds/sg13g2_stdcell.gds\n' +
            f'    source {{{pdk / "ihp-sg13g2/libs.tech/magic/read_sram_gds.tcl"}}}\n' +
            f'    gds read {{{macro_gds}}}')
        report['SRAM_import'] = {'original_helper': str(pdk / 'ihp-sg13g2/libs.tech/magic/read_sram_gds.tcl'),
            'scope': 'Original recommended six flatten patterns before SRAM GDS import; retains devices, geometry, bulk and net-breaker connectivity. Generic ideal resistor versus CDL lvsres model remains an explicit unresolved comparison.'}
        process = process.replace('lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef',
            f'lef read {{{route / "enclosure/repaired-original.lef"}}}')
        process = process.replace('lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef',
            'lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef\n' +
            f'    lef read {{{sram / "lef" / (macro + ".lef")}}}')
        if args.process_drc_only:
            process = process.replace('    gds write $out/layout.gds', '    # Direct full DRC on the same imported original GDS and actual routed DEF; no re-stream.')
            report['geometry_mode'] = 'DIRECT_ORIGINAL_GDS_AND_ACTUAL_DEF_NO_RESTREAM'
        process = process_tiling_script(process, args.drc_step_microns)
        header = f'set connectivity_only_extraction {1 if args.connectivity_only_extraction else 0}\nset pdk {{{pdk/"ihp-sg13g2"}}}\nset out {{{out}}}\nset top lemma_pen\n'
        (out / 'process.tcl').write_text(header + process)
        report['status'] = 'RUNNING'
        (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')
        if core_grid:
            # Bind the archived PG reference to the actual final database. The
            # ordinary signal netlist must also be byte-identical; PG handling
            # cannot silently change an endpoint or hide a different circuit.
            check = out / 'power-reference.tcl'
            # Default read_db exports omit physical PG ports; explicit power
            # exports move exactly those three ports before the vector ports.
            # Compare the exact remaining bytes, including all PG connections.
            check.write_text(power_reference_script(route, out,
                std/'lib/sg13g2_stdcell_typ_1p20V_25C.lib',
                sram/'lib'/(macro+'_typ_1p20V_25C.lib')))
            invoke([str(openroad), '-no_init', '-exit', str(check)], 'power-reference', 10)
            observed_signal = (out / 'observed-signal.v').read_text()
            original_signal = (route / 'routed.v').read_text()
            # Newer routed exports already omit physical PG ports; older
            # exports retain their exact three-name suffix. Compare bytes
            # directly first, and only normalize the explicit PG interface.
            if observed_signal != original_signal:
                require(observed_signal == connected_reference_signal_bytes(original_signal),
                        'final database signal reference differs')
            require(signal_bytes((out / 'observed-power.v').read_text(), reloaded_power=True) ==
                    connected_reference_signal_bytes(reference_netlist.read_text()), 'final database connected PG reference differs')
            report['connected_reference'] = {'path': str(reference_netlist), 'sha256': sha(reference_netlist),
                'source_ODB_sha256': sha(route / 'routed.odb'), 'scope': 'Actual final database power/test pins retained; signal netlist independently identical'}
        if args.direct_import_extraction and not args.continue_from_drc_attempt:
            count = None
            report['process_drc'] = {'status': 'NOT_RUN', 'scope': 'Independent transistor connectivity extraction; no process DRC result inferred for this geometry'}
        elif args.continue_from_drc_attempt:
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
                        for path in dict.fromkeys((route / 'routed.def', route / 'routed.v', reference_netlist, macro_gds, macro_cdl))),
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
        if args.process_drc_only:
            require(count is not None and count == 0, 'actual original-deck full process DRC failed')
            report['status'] = 'PASS_SCOPED_PROCESS_DRC_ONLY_POWER_AND_LVS_UNQUALIFIED'
        else:
            geometry = out / 'layout.gds'
            if not args.direct_import_extraction:
                require(geometry.is_file() and geometry.stat().st_size > 1000 and
                    geometry.read_bytes()[-4:] == bytes((0, 4, 4, 0)), 'no complete source GDS for independent extraction')
                report['imported_geometry'] = {'sha256': sha(geometry), 'bytes': geometry.stat().st_size, 'complete_ENDLIB': True}
            else:
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
            extraction_log = (out / 'extract.log').read_text(errors='replace')
            report['transistor_extraction']['warnings'] = {
                'cell_error_counts': re.findall(r'^([^\n]+): (\d+) errors?$', extraction_log, re.M),
                'subscript_warning_count': extraction_log.count("Number of subscripts doesn't match"),
                'scope': 'Completed netlist does not establish error-free geometry or LVS; all original warnings retained in extract.log'}
            # The original CDL spells bus bits <n>; Netgen's Verilog reader
            # binds [n], and mishandles escaped ! PG port names. Adapt only
            # reference spelling, with exact original-byte roundtrip guards.
            adapted_cdl = out / 'reference-sram-alias.cdl'
            adapted_verilog = out / 'reference-power-alias.v'
            original_cdl, original_verilog = macro_cdl.read_text(), reference_netlist.read_text()
            adapted_cdl.write_text(cdl_alias(original_cdl))
            adapted_verilog.write_text(verilog_alias(original_verilog, core_grid))
            require_originals(adapted_cdl.read_text(), original_cdl, adapted_verilog.read_text(), original_verilog)
            report['reference_spelling_adapter'] = {'original_CDL_sha256': sha(macro_cdl),
                'original_Verilog_sha256': sha(reference_netlist), 'derived_CDL_sha256': sha(adapted_cdl),
                'derived_Verilog_sha256': sha(adapted_verilog), 'scope': 'Exactly reversible bit/PG-port spelling only; all devices, parameter values, connection arguments and bit identities preserved; lvsres models unchanged'}
            compare = out / 'lvs.tcl'
            compare.write_text(f'''set reference [readnet spice {{{std/'cdl/sg13g2_stdcell.cdl'}}}]
    readnet spice {{{adapted_cdl}}} $reference
    readnet verilog {{{adapted_verilog}}} $reference
    lvs {{{out/'extracted.spice'} lemma_pen}} [list lemma_pen $reference] {{{pdk/'ihp-sg13g2/libs.tech/netgen/ihp-sg13g2_setup.tcl'}}} {{{out/'lvs.rpt'}}} -json
    ''')
            invoke([str(netgen), '-batch', 'source', str(compare)], 'lvs', 45)
            match = lvs_matches((out / 'lvs.rpt').read_text())
            report['lvs'] = {'status': 'PASS' if match else 'FAIL', 'report_sha256': sha(out / 'lvs.rpt')}
            require(count == 0 and match, 'actual process DRC/LVS failed')
            # A connected core mesh still does not establish IR/EM or complete
            # power/pad/package qualification, even if DRC and LVS both pass.
            report['status'] = ('PASS_SCOPED_PROCESS_DRC_LVS_CORE_GRID_IR_EM_UNQUALIFIED' if core_grid
                                else 'PASS_SCOPED_PROCESS_DRC_LVS_POWER_UNIMPLEMENTED')
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
