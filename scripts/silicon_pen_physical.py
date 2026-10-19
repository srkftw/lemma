#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded maintained full-depth SRAM pen route and extracted-RC assessment.

Consumes an actually qualified current check_pen_sram.py --map result. Uses
immutable public process inputs and the independent enclosure adaptation.
Router, simple enclosure, extracted timing, process DRC and LVS are distinct.
"""
import argparse
import json
from pathlib import Path
import resource
import shutil
import time
from silicon_enclosure import prepare, require
from silicon_route_enclosure import audit
from silicon_synth import ROOT, CommandFailure, layout_reports, router_drc, run, sha

MACRO = 'RM_IHPSG13_1P_256x64_c2_bm_bist'


def sdc_commands(path):
    # write_sdc adds a timestamp comment. Ignore only whole comment/blank lines;
    # every command, endpoint, value and exception must remain byte-identical.
    return '\n'.join(line for line in path.read_text().splitlines()
                     if line.strip() and not line.lstrip().startswith('#'))


def require_unmodified_routing_resources(paths):
    # No derived capacity adaptation is admitted by this flow. Any future
    # adaptation must first prove non-increase against actual before/after
    # resources and blocked-zero/edge/interior geometry, with underflow and
    # increased-capacity negative controls. Nominal route success is not proof.
    for path in paths:
        for line in path.read_text().splitlines():
            if line.lstrip().startswith('#'):
                continue
            require(not any(name in line for name in
                    ('set_global_routing_region_adjustment', 'set_global_routing_layer_adjustment',
                     'set_global_routing_random', '-infinite_cap', '-allow_congestion')),
                    'unadmitted derived routing resources or congestion bypass in ' + str(path))


def require_no_capacity_underflow(log):
    require('GRT-0113' not in log and 'Underflow in reduce' not in log,
            'router capacity underflow invalidates all optimistic route results')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mapping', type=Path, required=True)
    p.add_argument('--pdk', type=Path, required=True)
    clock = p.add_mutually_exclusive_group()
    clock.add_argument('--automatic-clock-wire-length', dest='automatic_clock_wire_length', action='store_true', default=True, help='Use actual pinned RC/driver wire optimum (default); all timing/electrical constraints remain')
    clock.add_argument('--historical-clock-wire-length', dest='automatic_clock_wire_length', action='store_false', help='Reproduce the historical100um clock-repair optimization bound')
    p.add_argument('--center-validation-cones', action='store_true', help='Fence real range-validation cones/collectors in the open middle macro channel; preserve all timing and macro OBS')
    p.add_argument('--defer-global-eco', action='store_true', help='Keep placement/clock repairs and every constraint, but defer the failing global-RC ECO optimization until actual routed extraction; fresh timing failures remain failures')
    p.add_argument('--question',default='Do independent timestamp/counter arithmetic and bounded clock clusters remove observed defects at unchanged100MHz/full256 FIFO?',help='Prospective engineering question for this changed-input run')
    p.add_argument('--completed-eco-route-from', type=Path, help='Independently assess a source-sealed completed ECO route rejected only by the timestamp-sensitive SDC observer; never reroutes it')
    p.add_argument('--routed-eco-from', type=Path, help='Repair the exact sealed routed nominal-SPEF producer, then route and extract the changed physical netlist afresh')
    p.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    out, mapping, pdk = (v.resolve() for v in (args.work_dir, args.mapping, args.pdk))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'schema': 'lemma-pen-physical/3', 'status': 'FAIL', 'scope': __doc__,
              'commands': [], 'bounds': {'whole_seconds': 1200, 'route_seconds': 900,
              'extraction_each_seconds': 60, 'AS_bytes': 6 << 30,
              'launch_available_bytes': 8 << 30, 'file_bytes': 1 << 30,
              'output_budget_bytes': 12 << 30},
              'physical_closure': 'UNVERIFIED',
              'derived_routing_capacity': 'NOT_ADMITTED: future adaptations require actual non-increase and blocked-zero/edge/interior plus underflow/increase negative controls',
              'validation_cone_placement': 'open-middle-channel' if args.center_validation_cones else 'unconstrained',
              'global_rc_optimization': 'DEFERRED_UNTIL_ACTUAL_EXTRACTION' if args.defer_global_eco else 'ENABLED',
              'clock_wire_repair': 'pinned-driver-RC-optimum' if args.automatic_clock_wire_length else 'historical100um', 'power_grid': 'NOT_IMPLEMENTED',
              'process_drc': 'NOT_RUN', 'lvs': 'NOT_RUN',
              'remaining': ['power grid and power/test-pin connectivity',
                 'process DRC and transistor LVS', 'matched-temperature fast stdcell/SRAM timing pair',
                 'pad/package/board and full-SoC physical design',
                 'mixed-signal/power/safety/physical qualification']}
    resource.setrlimit(resource.RLIMIT_AS, (6 << 30, 6 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def invoke(argv, name, seconds):
        try:
            record = run(argv, out / (name + '.log'), min(start + 1200, time.monotonic() + seconds))
        except CommandFailure as error:
            report['commands'].append(error.record)
            raise
        report['commands'].append(record)

    try:
        require(not (args.center_validation_cones and args.routed_eco_from), 'initial cone placement and retained-route ECO are separate questions')
        require(not args.defer_global_eco or (args.center_validation_cones and not args.routed_eco_from), 'deferred optimization is scoped to the aligned validation-placement question')
        available = next(int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines()
                         if x.startswith('MemAvailable:'))
        require(available >= 8 << 30, 'launch memory floor')
        require(shutil.disk_usage(out).free >= 12 << 30, 'output disk floor')
        report['available_bytes_at_launch'] = available
        admitted = json.loads((mapping / 'result.json').read_text())
        require(admitted['status'] in ('PASS_MAINTAINED_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING',
                'PASS_ISOLATED_CANDIDATE_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING'),
                'actual full256 protocol/mapping admission required')
        report['candidate_only']=admitted.get('candidate_only',False)
        require(isinstance(args.question,str) and 1<=len(args.question)<=1024,'bounded engineering question required')
        require(all(sha(ROOT / name) == digest for name, digest in admitted['source_inputs'].items()),
                'mapped producer source differs from current implementation')
        require(sha(mapping / 'mapped.v') == admitted['mapping']['mapped_verilog_sha256'], 'mapped bytes differ')
        for name, value in admitted['collateral'].items():
            require(sha(mapping / 'pdk' / name) == value['sha256'], 'mapped collateral differs')
        std = pdk / 'ihp-sg13g2/libs.ref/sg13g2_stdcell'
        macro = mapping / 'pdk/ihp-sg13g2/libs.ref/sg13g2_sram'
        openroad = Path(shutil.which('openroad') or '').resolve()
        require(openroad.is_file(), 'actual OpenROAD required')
        report['mapping_receipt'] = {'path': str(mapping / 'result.json'), 'sha256': sha(mapping / 'result.json')}
        report['enclosure_preflight'] = prepare(pdk, out / 'enclosure', True, 60)
        require(report['enclosure_preflight']['status'].startswith('PASS_'), 'enclosure preflight failed')
        raw = (mapping / 'mapped.v').read_text()
        adapted = raw
        for lane in range(3):
            name = '\\' + f'physical_storage.field_bank[{lane}].memory '
            require(adapted.count(name) == 1, 'actual SRAM instance missing')
            adapted = adapted.replace(name, f'pen_sram_lane{lane} ')
        (out / 'mapped.v').write_text(adapted)
        inputs = [Path(__file__).resolve(), ROOT / 'scripts/silicon_enclosure.py',
                  ROOT / 'scripts/silicon_route_enclosure.py', ROOT / 'tooling/silicon/layout.tcl',
                  ROOT / 'scripts/silicon_synth.py', ROOT / 'tooling/silicon/eda.nix',
                  ROOT / 'tooling/silicon/pen-floorplan.tcl', ROOT / 'tooling/silicon/pen-validation-region.tcl', ROOT / 'tooling/silicon/pen-validation-check.tcl', mapping / 'candidate.sv',
                  mapping / 'mapped.v', mapping / 'result.json', openroad]
        if args.routed_eco_from:
            prior = args.routed_eco_from.resolve()
            previous = json.loads((prior / 'result.json').read_text())
            require(previous['status'] == 'ASSESSED_PHYSICAL_CLOSURE_UNVERIFIED' and previous['source_seal_equal'], 'sealed actual route producer required')
            require(previous['mapping_receipt']['sha256'] == sha(mapping / 'result.json'), 'ECO mapping producer differs')
            require(sha(prior / 'routed.def') == previous['route_enclosure']['routed_def_sha256'], 'original route DEF differs')
            require(sha(prior / 'nom.spef') == previous['extracted_rc']['nom']['spef_sha256'], 'original nominal SPEF differs')
            report['routed_eco_from'] = {'path': str(prior), 'receipt_sha256': sha(prior / 'result.json')}
            inputs += [ROOT / 'tooling/silicon/pen-extracted-eco.tcl'] + [prior / name for name in ('result.json', 'routed.odb', 'routed.def', 'routed.v', 'routed.sdc', 'nom.spef')]
        if args.completed_eco_route_from:
            require(args.routed_eco_from is not None, 'completed ECO requires its original source route')
            completed = args.completed_eco_route_from.resolve()
            producer = json.loads((completed / 'result.json').read_text())
            require(producer['status'] == 'FAIL' and producer['source_seal_equal'] and
                    producer.get('error') == "GeometryError('ECO changed admitted timing constraints')", 'only the retained timestamp observer failure may continue')
            require(producer['mapping_receipt']['sha256'] == sha(mapping / 'result.json') and
                    producer['routed_eco_from']['receipt_sha256'] == sha(prior / 'result.json'), 'completed ECO producer differs')
            require(sdc_commands(completed / 'pre-eco.sdc') == sdc_commands(completed / 'routed.sdc') == sdc_commands(prior / 'routed.sdc'), 'actual ECO timing commands differ')
            retained = ('routed.odb', 'routed.def', 'routed.v', 'routed.sdc', 'pre-eco.v', 'pre-eco.sdc',
                        'post-eco-unrouted.v', 'layout-summary.json', 'router-drc-count.txt', 'setup-summary.rpt',
                        'hold-summary.rpt', 'actual-pre-eco-setup.rpt', 'actual-pre-eco-hold.rpt')
            inputs += [completed / 'result.json'] + [completed / name for name in retained]
            for name in retained:
                shutil.copyfile(completed / name, out / name)
            report['reused_completed_route'] = {'path': str(completed), 'receipt_sha256': sha(completed / 'result.json'),
                                              'scope': 'actual completed routing reused; this observer performs new extraction only'}
        inputs += [std / 'lib/sg13g2_stdcell_typ_1p20V_25C.lib', macro / 'lib' / (MACRO+'_typ_1p20V_25C.lib')]
        require_unmodified_routing_resources([path for path in inputs if path.suffix == '.tcl'])
        report['source_inputs'] = {str(v): sha(v) for v in inputs}
        archive = out / 'source-archive'
        archive.mkdir()
        archived = {}
        for source in inputs:
            relative = source.relative_to(ROOT) if source.is_relative_to(ROOT) else Path('external') / source.name
            target = archive / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            require(sha(target) == report['source_inputs'][str(source)], 'archived source differs')
            archived[str(relative)] = sha(target)
        (archive / 'manifest.json').write_text(json.dumps(archived, indent=2) + '\n')
        script = out / 'layout.tcl'
        script.write_text(f'''set pdk {{{std}}}
set macro_lef {{{macro/'lef'/ (MACRO+'.lef')}}}
set macro_lib {{{macro/'lib'/ (MACRO+'_typ_1p20V_25C.lib')}}}
set tech_lef {{{out/'enclosure/repaired-original.lef'}}}
set pen_sram {{{ROOT/'tooling/silicon/pen-floorplan.tcl'}}}
set out {{{out}}}
set top lemma_pen
set clock_ns 10
set clock_port clk
set automatic_clock_wire_length {1 if args.automatic_clock_wire_length else 0}
set center_validation_cones {1 if args.center_validation_cones else 0}
set defer_global_eco {1 if args.defer_global_eco else 0}
set validation_region_script {{{ROOT/"tooling/silicon/pen-validation-region.tcl"}}}
set validation_region_check_script {{{ROOT/"tooling/silicon/pen-validation-check.tcl"}}}
source {{{ROOT/'tooling/silicon/layout.tcl'}}}
''')
        if args.routed_eco_from:
            script.write_text(f'set prior {{{prior}}}\nset out {{{out}}}\nset pdk {{{std}}}\nset macro_lib {{{macro/"lib"/(MACRO+"_typ_1p20V_25C.lib")}}}\nset validation_region_check_script {{{ROOT/"tooling/silicon/pen-validation-check.tcl"}}}\nsource {{{ROOT/"tooling/silicon/pen-extracted-eco.tcl"}}}\n')
        # Preserve the real failed database, including GRT's stored overflow
        # grid, before Tcl propagates an implementation error. A snapshot is
        # diagnostic state only and never a completed routed layout.
        recipe = script.read_text()
        script.write_text('if {[catch {\n' + recipe + r"""
} failure options]} {
    set snapshot_errors {}
    if {[catch {write_db $out/failed-layout.odb} reason]} {lappend snapshot_errors $reason}
    if {[catch {write_def $out/failed-layout.def} reason]} {lappend snapshot_errors $reason}
    set file [open $out/failed-layout.txt w]
    puts $file $failure
    puts $file "Snapshot errors: $snapshot_errors"
    close $file
    return -options $options $failure
}
""")
        report['question'] = args.question
        report['status'] = 'RUNNING'
        (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')
        if not args.completed_eco_route_from:
            invoke([str(openroad), '-no_init', '-exit', str(script)], 'layout', 900)
        if not args.completed_eco_route_from:
            require_no_capacity_underflow((out / 'layout.log').read_text())
        require((out / 'routed.def').is_file(), 'no completed route')
        if args.routed_eco_from:
            require(sha(out / 'pre-eco.v') == sha(prior / 'routed.v'), 'ECO database logical netlist differs from declared source route')
            require(sha(out / 'pre-eco.v') != sha(out / 'post-eco-unrouted.v'), 'ECO made no physical netlist change')
            require(sdc_commands(out / 'pre-eco.sdc') == sdc_commands(out / 'routed.sdc') == sdc_commands(prior / 'routed.sdc'), 'ECO changed admitted timing commands')
            report['eco_netlist'] = {name: sha(out / name) for name in ('pre-eco.v', 'post-eco-unrouted.v', 'routed.v', 'pre-eco.sdc', 'routed.sdc')}
            report['eco_netlist']['pre_setup'] = (out / 'actual-pre-eco-setup.rpt').read_text().strip()
            report['eco_netlist']['pre_hold'] = (out / 'actual-pre-eco-hold.rpt').read_text().strip()
        report['router_drc'] = router_drc((out / 'router-drc-count.txt').read_text())
        report['global_rc_after_route'] = layout_reports(out)
        report['route_enclosure'] = audit(out / 'enclosure/repaired-original.lef', out / 'routed.def')
        (out / 'route-enclosure.json').write_text(json.dumps(report['route_enclosure'], indent=2) + '\n')
        # Extract actual route shapes using all public RC decks. Liberty stays
        # typical: RC-min/max are not new transistor/process/PVT corners.
        report['extracted_rc'] = {}
        for corner in ('min', 'nom', 'max'):
            rules = pdk / ('ihp-sg13g2/libs.tech/librelane/openrcx/ihp-sg13g2.' + corner + '.magic.rules')
            require(rules.is_file(), 'missing actual public RC model ' + corner)
            extract = out / ('extract-' + corner + '.tcl')
            extract.write_text(f'''set_thread_count 2
read_liberty {{{std/'lib/sg13g2_stdcell_typ_1p20V_25C.lib'}}}
read_liberty {{{macro/'lib'/ (MACRO+'_typ_1p20V_25C.lib')}}}
read_db {{{out/'routed.odb'}}}
read_sdc {{{out/'routed.sdc'}}}
define_process_corner -ext_model_index 0 {corner}
extract_parasitics -ext_model_file {{{rules}}}
write_spef {{{out/(corner+'.spef')}}}
read_spef {{{out/(corner+'.spef')}}}
report_checks -path_delay max -group_path_count 5 -digits 6 > {{{out/(corner+'-setup.rpt')}}}
report_checks -path_delay min -group_path_count 5 -digits 6 > {{{out/(corner+'-hold.rpt')}}}
report_worst_slack -max -digits 6 > {{{out/(corner+'-setup-summary.rpt')}}}
report_worst_slack -min -digits 6 > {{{out/(corner+'-hold-summary.rpt')}}}
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > {{{out/(corner+'-electrical.rpt')}}}
''')
            try:
                invoke([str(openroad), '-no_init', '-exit', str(extract)], 'extract-' + corner, 60)
                require((out / (corner + '.spef')).stat().st_size > 1000, 'empty extracted SPEF')
                report['extracted_rc'][corner] = {'status': 'EXTRACTED', 'model_sha256': sha(rules),
                    'spef_sha256': sha(out / (corner + '.spef')),
                    'setup': (out / (corner + '-setup-summary.rpt')).read_text().strip(),
                    'hold': (out / (corner + '-hold-summary.rpt')).read_text().strip(),
                    'electrical_violations': (out / (corner + '-electrical.rpt')).read_text().count('(VIOLATED)')}
            except (RuntimeError, ValueError, OSError) as error:
                report['extracted_rc'][corner] = {'status': 'FAIL', 'error': repr(error), 'model_sha256': sha(rules)}
        report['status'] = 'ASSESSED_PHYSICAL_CLOSURE_UNVERIFIED'
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        if (out / 'layout.log').is_file():
            try:
                require_no_capacity_underflow((out / 'layout.log').read_text())
                report['router_capacity_underflow'] = 'NOT_OBSERVED_IN_THIS_EXECUTION'
            except ValueError as error:
                report.update(status='FAIL', router_capacity_underflow='REJECTED', capacity_error=repr(error))
        snapshots = [out / name for name in ('failed-layout.odb', 'failed-layout.def', 'failed-layout.txt') if (out / name).is_file()]
        if snapshots:
            report['failed_layout_snapshots'] = {str(path): sha(path) for path in snapshots}
            report['failed_layout_scope'] = 'Diagnostic failed database/placement and stored congestion only; not a completed routed layout'
        report['seconds'] = time.monotonic() - start
        report['source_seal_equal'] = all(sha(Path(v)) == digest for v, digest in report.get('source_inputs', {}).items())
        if not report['source_seal_equal']:
            report.update(status='FAIL', source_drift=True)
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'], flush=True)
    # Assessment is not acceptance: any physical defect keeps failure status.
    return 0 if (report.get('router_drc', {}).get('violations') == 0 and
                 report.get('route_enclosure', {}).get('status', '').startswith('PASS_') and
                 report.get('physical_closure') == 'QUALIFIED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
