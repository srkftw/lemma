#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Consume the qualified whole-GRT component of the exact fresh97 pen.

The original incremental route and pilot whole remain failed. This path does
not repeat placement, resizer or GRT. Its new result requires actual detailed
routing, native geometry checks and fresh extraction; no closure is implied.
"""
import ast
import json
import math
import re
from pathlib import Path
import resource
import shutil
import sys
import time

from silicon_enclosure import require
from silicon_synth import ROOT, CommandFailure, router_drc, run, sha

SOURCE = ROOT / 'build/silicon/task009-head-bypass-full-GRT-pilot-a2'
COMPLETED = ROOT / 'build/silicon/task009-head-bypass-full-GRT-completed-a2'
FAILED = ROOT / 'build/silicon/task009-head-bypass-fresh-route-a3'
MAPPING = ROOT / 'build/silicon/task009-head-bypass-standard-mapping-a2/mapping'
MACRO = 'RM_IHPSG13_1P_256x64_c2_bm_bist'
CORE = Path('/nix/store/52lmb0xv2vfcjybjnq3bjfmhkg8w1ign-openroad-26Q2/bin/openroad')
# Exact completed producer/component identities, added below with the source.
PINS = {
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/result.json": "115716cf9ae569e965c9b62cb9908ab51b322ac379597cb995235956486a1ad0",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/global.odb": "d0653265adc0e4939a53ac35454b7df047e9985030da361ca7032d27bac8f1e3",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/global.def": "260287e691acdd2cb90c7cb238f7eb0600ec8a59d334be37544aa28f23ecd99b",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/global.sdc": "fe0fe5db49dda32483914c2237d250c214e497e8fcf09f5b987af43e6f0e230f",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/global.v": "3fc1c82fd2c40ab2f3fd3d4505883239470efb6f8f2a16ac65411468ca7939f8",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/global-estimated.spef": "10e72bbcc502a8391e89c4c608c379d37cf7da82a7b60f5cfd8eec26374a99a6",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/route.guide": "62c24f4a99630892c9d3169ae75e8f4e21e3040e4ebc9c4b9d70eae8f9b925e2",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/pilot.log": "5c51a01ac13578a9ce3df73e9843501ba3b889d2ccdb092dffaf1a17ebec70ad",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/pilot.tcl": "1bee7d8c973e94bc62089e62967feb84c3f9dbe19bd1114da4f82fa75d6524a3",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/congestion.rpt": "ddc47885cb6218a3727d76e5930f45b0026d25c647b6c46f70e4e54419ef3371",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/native-preflight.json": "ad1fa4e71114d8befa8e277892d4f2cee52caad33ea7f328770097d145209a76",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/native-final.json": "78eb1d52ad2c540a4f4c0c7cf1f8a779e34afaf8b39c215add74fd94c704b9a2",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/PGconnect-only.json": "0b7bb6b97a433b4a2e02d7cde9a6bad4a01cb4c41e516530379fada8893fba76",
    "build/silicon/task009-head-bypass-full-GRT-pilot-a2/buffered-endpoints.json": "20ca6ac0964369b2be1d2cf032fe5cd2505225ea8550fa0b64e9dde9e1040abe",
    "build/silicon/task009-head-bypass-full-GRT-completed-a2/result.json": "8083995821c414124c12fd2687d4895ec23eab242fd4f61ff35b754a1de896bb",
    "build/silicon/task009-head-bypass-full-GRT-completed-a2/native.json": "6917675c6084acf4bbed455326f960cee9d8a0405ce82309e4bff0ef6679fca1",
    "build/silicon/task009-head-bypass-full-GRT-completed-a2/failedincremental-whole-raw-map.json": "2baf9f0b34003fef7398568b46f3a52e3070b09c93520f5114d25e93651f0b5b",
    "build/silicon/task009-head-bypass-full-GRT-completed-a2/completedfullGRT-whole-raw-map.json": "b56ffb31da2eeb997570e1ffd75268a5376f1f860fecb093a6dfba70b3d4eed9",
    "build/silicon/task009-head-bypass-fresh-route-a3/result.json": "2a7b17f6564623a7c45067ff98cb5fe0b9bea10d49c8f8c63d86986d55373bb3",
    "build/silicon/task009-head-bypass-fresh-route-a3/failed-layout.odb": "7da5c558bc13cc21c9541a0b9c4e7c19fa6178c542ff0ba7c8105ab461daabd2",
    "build/silicon/task009-head-bypass-fresh-route-a3/pre-power/routed.sdc": "35ac0e377ef4f29cf9a72e3b737879d1c352d613071ee34deb8db8394431dd0b",
    "build/silicon/task009-head-bypass-fresh-route-a3/post-power/routed.odb": "869c1b5ecce3bc772f37241b8fdca127aeaa937f44ef2e051c6752e16762bd24",
    "build/silicon/task009-head-bypass-fresh-route-a3/enclosure/repaired-original.lef": "fb6f0aa5647efc822ad6551a11b57002a278d7d3f98ac20a12cb9f7a65e81d2d",
    "build/silicon/task009-head-bypass-fresh-route-a3/source-archive/scripts/silicon_pen_physical.py": "6f91cb15692411b29e45b805124346699f5e27bfb34a0bad190a0eb7691c89fe",
    "build/silicon/task009-head-bypass-standard-mapping-a2/mapping/result.json": "8a7f111d3c40d55ee6f3703bd3206b163e13c77d182b5406b1f37fdf9a07894a",
    "build/silicon/task009-head-bypass-standard-mapping-a2/mapping/candidate.sv": "97b077796078558fdc84ebcb36bcd7cffc70fd2056653a1269478d250dbedded",
    "build/silicon/task009-head-bypass-standard-mapping-a2/mapping/mapped.v": "87de577e9d8d40e3ecbc9a9c540a4b3b9ae1f68b019f313a4fea9a97e2f11584",
    "build/silicon/task009-head-bypass-standard-mapping-a2/mapping/mapped.json": "be1b857a52e01f96c5d416d8cce9135a71bc03dbf2947691fee1c89120df05ca",
    "/nix/store/pi9m3br8ni97dfybd24lldfa185py07x-source/src/grt/src/fastroute/src/utility.cpp": "db5358d6988e1f9c3ed842659780d03502e33cd50e9e11ca8148333edfffdbba",
    "/nix/store/pi9m3br8ni97dfybd24lldfa185py07x-source/src/grt/src/GlobalRouter.cpp": "a35f9aedbc04b7a382c23af19e3893497d5e72951782f2444eecc1fd8c1a3d67",
    "/nix/store/pi9m3br8ni97dfybd24lldfa185py07x-source/src/grt/src/fastroute/src/FastRoute.cpp": "5e6f9bd3509984d56aeb490050dbc88fa5b05c72a635e645d68081764e0eba0f"
}


def raw_relation(old, new):
    """Whole native maps, retaining the tool's blocked-capacity semantics."""
    require(set(old) == set(new) == {'x_grid_DBU', 'y_grid_DBU', 'schema', 'data'},
            'closed native GCell schema required')
    require(old['x_grid_DBU'] == new['x_grid_DBU'] and
            old['y_grid_DBU'] == new['y_grid_DBU'] and old['schema'] == new['schema'],
            'native grid/units/schema changed')
    for value in (old, new):
        for axis in ('x_grid_DBU', 'y_grid_DBU'):
            require(all(type(v) is int for v in value[axis]) and
                    all(a < b for a, b in zip(value[axis], value[axis][1:])),
                    'native coordinates must be ordered literal integer DBU')
    require(len(old['data']) == len(new['data']) == 68440, 'complete four-layer raw maps required')
    require(len(old['x_grid_DBU']) * len(old['y_grid_DBU']) * 4 == 68440,
            'raw grid dimensions do not cover the complete map')
    excess = []
    seen = set()
    for before, after in zip(old['data'], new['data']):
        require(len(before) == len(after) == 5 and before[:4] == after[:4],
                'native layer/index/capacity changed')
        require(before[0] in ('Metal2', 'Metal3', 'Metal4', 'Metal5') and
                all(type(v) is int and v >= 0 for v in [*before[1:3], *after[1:3]]) and
                all(type(v) in (int, float) and math.isfinite(v) and v >= 0
                    for v in [*before[3:], *after[3:]]), 'untyped or invalid raw native field')
        key = tuple(before[:3])
        require(key not in seen and key[1] < len(old['x_grid_DBU']) and
                key[2] < len(old['y_grid_DBU']), 'duplicate or out-of-range native grid entry')
        seen.add(key)
        if before[4] > before[3]:
            excess.append(before)
        require(after[4] <= after[3], 'completed native map still exceeds raw capacity')
    require(excess == [['Metal3', 125, 56, 18.0, 19.0]], 'original single raw excess changed')
    return {'raw_cells': 68440, 'capacities_identical': True,
            'original_raw_excess': excess, 'completed_raw_excess': [],
            'scope': 'Raw capacity includes reductions; usage includes blockage. Not free-track or process-DRC qualification.'}


def admit(source, mapping):
    require(source.resolve() == SOURCE and mapping.resolve() == MAPPING,
            'exact independently qualified fresh97 source and mapping required')
    require(PINS and all((ROOT / name).is_file() and sha(ROOT / name) == digest
                         for name, digest in PINS.items()), 'completed source/component identity differs')
    pilot = json.loads((source / 'result.json').read_text())
    require(pilot['status'] == 'FAIL' and
            pilot['error'] == "AssertionError('actualwholeGRTstillcongested')" and
            pilot['source_seal_equal'] and pilot['owned_processes_reaped'] and
            pilot['original_deadline_met'] and len(pilot['commands']) == 1 and
            pilot['commands'][0]['exit_code'] == 0, 'original whole failure/components differ')
    historical = {}
    for name, digest in pilot['source_inputs'].items():
        path = Path(name)
        if path.is_file() and sha(path) == digest:
            continue
        # The new additive CLI is deliberately a new host consumer. Preserve
        # and verify the exact historical producer rather than relabeling it.
        require(path.resolve() == ROOT / 'scripts/silicon_pen_physical.py',
                'an original consumed source changed: ' + name)
        archived = FAILED / 'source-archive/scripts/silicon_pen_physical.py'
        require(sha(archived) == digest, 'historical physical producer bytes missing')
        historical[name] = {'original_sha256': digest, 'archive': str(archived),
                            'current_consumer_sha256': sha(path)}
    completed = json.loads((COMPLETED / 'result.json').read_text())
    require(completed['status'] == 'OBSERVED_COMPLETED_ARTIFACT_NATIVE_CONGESTION_METADATA_NO_NEW_GRT'
            and completed['source_seal_equal'] and completed['owned_processes_reaped']
            and completed['original_deadline_met'], 'completed raw-map observation did not seal')
    relation = raw_relation(*[json.loads((COMPLETED / (name + '-whole-raw-map.json')).read_text())
                             for name in ('failedincremental', 'completedfullGRT')])
    native = json.loads((COMPLETED / 'native.json').read_text())
    require(native['cases'][0]['literal_category_markers'] ==
            native['cases'][1]['literal_category_markers'] and
            len(native['cases'][1]['literal_category_markers']) == 1,
            'literal inherited marker context differs')
    for name in ('native-preflight.json', 'native-final.json'):
        require(json.loads((source / name).read_text())['status'] ==
                'PASS_FRESH_MAPPED_NATIVE_PG_PADDING_PIN_PRECURSOR_NOT_ROUTED',
                'actual full-GRT native component differs')
    endpoints = json.loads((source / 'buffered-endpoints.json').read_text())
    require(endpoints['status'] == 'PASS_ORIGINAL_LIB_BUFFERED_INPUTS_ALL668_PORTS_AND_ACTUAL_NEGATIVES'
            and endpoints['source_seal_equal'] and any(
                v['case'] == 'read_enable_driver_swap' and v['result'] == 'REJECTED'
                for v in endpoints['negative_cases']), 'actual REN-aware endpoint proof required')
    return {'status': 'QUALIFIED_COMPLETED_FULL_GRT_COMPONENT_ORIGINAL_WHOLE_FAIL_RETAINED',
            'raw_relation': relation, 'historical_source': historical,
            'scope': 'No new GRT. Imported stale category remains unchanged; no marker deletion or routing waiver.'}


def native_script(before, current, output, liberty):
    return f'''import sys
from pathlib import Path
sys.path.insert(0,{str(ROOT/'scripts')!r})
from silicon_power_margin import load
from silicon_acceptance_launch import snapshot
from silicon_fresh_margin import assess
from silicon_buffered_pins import assess as endpoints
a,b=load(Path({str(before)!r}));d,nb=load(Path({str(current)!r}))
assert snapshot(b)==snapshot(nb),'DRT changed source cells/pins/ports/PG/OBS'
assess(Path({str(current)!r}),Path({str(liberty)!r}),Path({str(output)!r}))
endpoints(Path({str(FAILED/'post-power/routed.odb')!r}),Path({str(current)!r}),Path({str(liberty)!r}),Path({str(output.with_name(output.stem+'-endpoints.json'))!r}))
'''


def main(args):
    """Normal physical entry delegates here only for this explicit handoff."""
    from silicon_pen_physical import sdc_commands
    from silicon_route_enclosure import audit
    out, pdk = args.work_dir.resolve(), args.pdk.resolve()
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    require(args.fresh_native_margin_grid and args.fresh_core_power_grid and
            args.protect_sram_power_geometry and args.group_button_bus and
            args.clock_min_routing_layer == 'Metal3' and args.detail_route_iterations == 8,
            'complete original fresh97 physical recipe required')
    out.mkdir(parents=True)
    resource.setrlimit(resource.RLIMIT_AS, (6 << 30, 6 << 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    started = time.monotonic(); deadline = started + 1200
    report = {'schema': 'lemma-pen-completed-fresh-global/1', 'status': 'FAIL',
              'candidate_only': True, 'selected': False, 'commands': [],
              'bounds': {'whole_seconds': 1200, 'route_seconds': 900,
                         'AS_bytes': 6 << 30, 'file_bytes': 1 << 30},
              'question': args.question, 'physical_closure': 'UNVERIFIED',
              'process_drc': 'NOT_RUN', 'lvs': 'NOT_RUN'}
    def invoke(argv, name, seconds):
        try:
            result = run(argv, out / (name + '.log'), min(deadline, time.monotonic() + seconds))
        except CommandFailure as error:
            report['commands'].append(error.record)
            raise
        report['commands'].append(result)
    try:
        report['completed_global_component'] = admit(args.completed_fresh_global_from, args.mapping)
        require(isinstance(args.question, str) and 1 <= len(args.question) <= 1024,
                'bounded actual engineering question required')
        require(CORE.is_file() and Path(shutil.which('openroad') or '').resolve() == CORE,
                'original pinned OpenROAD required')
        std = pdk / 'ihp-sg13g2/libs.ref/sg13g2_stdcell'
        macro = MAPPING / 'pdk/ihp-sg13g2/libs.ref/sg13g2_sram'
        liberty = std / 'lib/sg13g2_stdcell_typ_1p20V_25C.lib'
        macro_lib = macro / 'lib' / (MACRO + '_typ_1p20V_25C.lib')
        tech = FAILED / 'enclosure/repaired-original.lef'
        inputs = [ROOT / name for name in PINS]
        inputs += [liberty, macro_lib, tech, CORE, CORE.with_name('.openroad-wrapped')]
        inputs += [pdk / ('ihp-sg13g2/libs.tech/librelane/openrcx/ihp-sg13g2.' + rc + '.magic.rules')
                   for rc in ('min', 'nom', 'max')]
        pending = ['silicon_fresh_global', 'silicon_pen_physical']; seen = set()
        while pending:
            name = pending.pop()
            if name in seen:
                continue
            seen.add(name); path = ROOT / 'scripts' / (name + '.py'); inputs.append(path)
            for node in ast.walk(ast.parse(path.read_text())):
                names = ([node.module] if isinstance(node, ast.ImportFrom) else
                         [n.name for n in node.names] if isinstance(node, ast.Import) else [])
                pending += [n for n in names if n and n.startswith('silicon_') and
                            (ROOT / 'scripts' / (n + '.py')).is_file()]
        report['source_inputs'] = {str(p): sha(p) for p in dict.fromkeys(inputs)}
        archive = out / 'source-archive'; archive.mkdir()
        for index, path in enumerate(dict.fromkeys(inputs)):
            if path.suffix in ('.py', '.json', '.tcl', '.lib', '.lef', '.rules'):
                shutil.copyfile(path, archive / (str(index) + '-' + path.name))
        pre = out / 'native-prefix.py'; final = out / 'native-final.py'
        pre.write_text(native_script(SOURCE / 'global.odb', out / 'before-DRT.odb', out / 'native-prefix.json', liberty))
        final.write_text(native_script(SOURCE / 'global.odb', out / 'routed.odb', out / 'native-final.json', liberty))
        script = out / 'detail.tcl'
        script.write_text(f'''set_thread_count 4
read_liberty {{{liberty}}}
read_liberty {{{macro_lib}}}
read_db {{{SOURCE/'global.odb'}}}
read_sdc {{{SOURCE/'global.sdc'}}}
set out {{{out}}}
set_routing_layers -signal Metal2-Metal5 -clock Metal3-Metal5
read_guides {{{SOURCE/'route.guide'}}}
global_connect
write_db $out/before-DRT.odb
write_def $out/before-DRT.def
write_verilog $out/before-DRT.v
exec {CORE} -python -exit {{{pre}}} > $out/native-prefix.log 2>@1
detailed_route -output_drc $out/route.drc -drc_report_iter_step 1 -output_maze $out/route.maze -droute_end_iter 8 -verbose 1
global_connect
set f [open $out/router-drc-count.txt w]
puts $f [detailed_route_num_drvs]
close $f
write_db $out/routed.odb
write_def $out/routed.def
write_verilog $out/routed.v
write_verilog -include_pwr_gnd $out/power-connected.v
write_sdc $out/routed.sdc
''')
        report['status'] = 'RUNNING'
        (out / 'plan.json').write_text(json.dumps(report, indent=2) + '\n')
        invoke([str(CORE), '-no_init', '-exit', str(script)], 'detail', 900)
        require((out / 'before-DRT.v').read_bytes() == (SOURCE / 'global.v').read_bytes() ==
                (out / 'routed.v').read_bytes(), 'DRT changed exact consumed logical netlist')
        require(sdc_commands(SOURCE / 'global.sdc') == sdc_commands(out / 'routed.sdc'),
                'DRT changed an original timing command')
        report['native_prefix'] = json.loads((out / 'native-prefix.json').read_text())
        invoke([str(CORE), '-python', '-exit', str(final)], 'native-final', 30)
        report['native_final'] = json.loads((out / 'native-final.json').read_text())
        power = out / 'power.tcl'
        power.write_text(f'''set_thread_count 1
read_liberty {{{liberty}}}
read_liberty {{{macro_lib}}}
read_db {{{out/'routed.odb'}}}
set out {{{out}}}
source {{{ROOT/'tooling/silicon/pen-power-check.tcl'}}}
set bindings [lemma_macro_bindings $out/qualified-macro-bindings.tsv]
lemma_check_power_grid $bindings $out final
''')
        invoke([str(CORE), '-no_init', '-exit', str(power)], 'power', 15)
        report['power'] = json.loads((out / 'power-grid-final.json').read_text())
        guard = out / 'native-margin.py'
        guard.write_text(f'''import sys
from pathlib import Path
sys.path.insert(0,{str(ROOT/'scripts')!r})
from silicon_power_clearance import check
check(Path({str(out/'routed.odb')!r}),Path({str(tech)!r}),Path({str(out/'native-margin.json')!r}))
''')
        invoke([str(CORE), '-python', '-exit', str(guard)], 'native-margin', 45)
        report['native_margin'] = json.loads((out / 'native-margin.json').read_text())
        require(report['native_margin']['status'] in ('PASS_ACTUAL_NATIVE420NM_RECTANGLE_SUBSET_ONLY',
                'FAIL_NATIVE420NM_RECTANGLE_MARGIN'), 'native geometry observer did not complete')
        report['router_drc'] = router_drc((out / 'router-drc-count.txt').read_text())
        report['route_enclosure'] = audit(tech, out / 'routed.def', allow_generated=True)
        report['extracted_rc'] = {}
        for rc in ('min', 'nom', 'max'):
            rules = pdk / ('ihp-sg13g2/libs.tech/librelane/openrcx/ihp-sg13g2.' + rc + '.magic.rules')
            extract = out / ('extract-' + rc + '.tcl')
            extract.write_text(f'''set_thread_count 2
read_liberty {{{liberty}}}
read_liberty {{{macro_lib}}}
read_db {{{out/'routed.odb'}}}
read_sdc {{{out/'routed.sdc'}}}
define_process_corner -ext_model_index 0 {rc}
extract_parasitics -ext_model_file {{{rules}}}
write_spef {{{out/(rc+'.spef')}}}
read_spef {{{out/(rc+'.spef')}}}
report_checks -path_delay max -group_path_count 5 -digits 6 > {{{out/(rc+'-setup.rpt')}}}
report_checks -path_delay min -group_path_count 5 -digits 6 > {{{out/(rc+'-hold.rpt')}}}
report_worst_slack -max -digits 6 > {{{out/(rc+'-setup-summary.rpt')}}}
report_worst_slack -min -digits 6 > {{{out/(rc+'-hold-summary.rpt')}}}
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > {{{out/(rc+'-electrical.rpt')}}}
''')
            invoke([str(CORE), '-no_init', '-exit', str(extract)], 'extract-' + rc, 60)
            require((out / (rc + '.spef')).stat().st_size > 1000, 'empty actual SPEF')
            report['extracted_rc'][rc] = {'status': 'EXTRACTED', 'model_sha256': sha(rules),
                'spef_sha256': sha(out / (rc + '.spef')),
                'setup_ns': float(re.fullmatch(r'worst slack max ([-+\d.]+)\s*',
                    (out / (rc + '-setup-summary.rpt')).read_text())[1]),
                'hold_ns': float(re.fullmatch(r'worst slack min ([-+\d.]+)\s*',
                    (out / (rc + '-hold-summary.rpt')).read_text())[1]),
                'electrical_violations': (out / (rc + '-electrical.rpt')).read_text().count('(VIOLATED)')}
        report['status'] = 'ASSESSED_COMPLETED_FRESH_GLOBAL_DRT_3RC_CLOSURE_UNVERIFIED'
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        report['seconds'] = time.monotonic() - started
        report['source_seal_equal'] = all(Path(p).is_file() and sha(Path(p)) == digest
                                          for p, digest in report.get('source_inputs', {}).items())
        if not report['source_seal_equal'] or time.monotonic() > deadline:
            report['status'] = 'FAIL_SOURCE_OR_ORIGINAL_DEADLINE'
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(report['status'], report.get('error'), report['seconds'], flush=True)
    # Assessment remains distinct from timing/process acceptance.
    return 0 if (report['status'].startswith('ASSESSED_') and report['router_drc']['violations'] == 0
        and report['native_margin']['status'] == 'PASS_ACTUAL_NATIVE420NM_RECTANGLE_SUBSET_ONLY'
        and report['route_enclosure']['status'].startswith('PASS_') and all(
            case['setup_ns'] >= 0 and case['hold_ns'] >= 0 and case['electrical_violations'] == 0
            for case in report['extracted_rc'].values())) else 1
