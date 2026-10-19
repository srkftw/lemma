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


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mapping', type=Path, required=True)
    p.add_argument('--pdk', type=Path, required=True)
    p.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    out, mapping, pdk = (v.resolve() for v in (args.work_dir, args.mapping, args.pdk))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'schema': 'lemma-pen-physical/2', 'status': 'FAIL', 'scope': __doc__,
              'commands': [], 'bounds': {'whole_seconds': 1200, 'route_seconds': 900,
              'extraction_each_seconds': 60, 'AS_bytes': 6 << 30,
              'launch_available_bytes': 8 << 30, 'file_bytes': 1 << 30,
              'output_budget_bytes': 12 << 30},
              'physical_closure': 'UNVERIFIED', 'power_grid': 'NOT_IMPLEMENTED',
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
        available = next(int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines()
                         if x.startswith('MemAvailable:'))
        require(available >= 8 << 30, 'launch memory floor')
        require(shutil.disk_usage(out).free >= 12 << 30, 'output disk floor')
        report['available_bytes_at_launch'] = available
        admitted = json.loads((mapping / 'result.json').read_text())
        require(admitted['status'] == 'PASS_MAINTAINED_PEN_PROTOCOL_AND_THREE_REAL_SRAM_MAPPING',
                'actual full256 protocol/mapping admission required')
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
                  ROOT / 'tooling/silicon/pen-floorplan.tcl', mapping / 'candidate.sv',
                  mapping / 'mapped.v', mapping / 'result.json', openroad]
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
source {{{ROOT/'tooling/silicon/layout.tcl'}}}
''')
        report['question'] = 'Do independent timestamp/counter arithmetic and bounded clock clusters remove observed defects at unchanged100MHz/full256 FIFO?'
        report['status'] = 'RUNNING'
        (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')
        invoke([str(openroad), '-no_init', '-exit', str(script)], 'layout', 900)
        require((out / 'routed.def').is_file(), 'no completed route')
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
