#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Bounded maintained full-depth SRAM pen route and extracted-RC assessment.

Consumes an actually qualified current check_pen_sram.py --map result. Uses
immutable public process inputs and the independent enclosure adaptation.
Router, simple enclosure, extracted timing, process DRC and LVS are distinct.
"""
import argparse
import json
import re
from pathlib import Path
import resource
import shutil
import sys
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


def require_iteration_drc_reports(paths):
    """Fail before routing if a future timeout would lose its marker identities."""
    for path in paths:
        commands = list(re.finditer(r'(?m)^[ \t]*detailed_route[ \t]+([^\n]*)', path.read_text()))
        require(len(commands) == 1, 'one maintained detailed-route command required: ' + str(path))
        for match in commands:
            arguments = match[1].split()
            require(arguments.count('-drc_report_iter_step') == 1 and
                    arguments[arguments.index('-drc_report_iter_step') + 1:
                              arguments.index('-drc_report_iter_step') + 2] == ['1'] and
                    arguments.count('-output_drc') == 1 and
                    arguments[arguments.index('-output_drc') + 1:
                              arguments.index('-output_drc') + 2] == ['$out/route.drc'],
                    'every detailed route must retain actual per-iteration DRC markers: ' + str(path))


def require_no_capacity_underflow(log):
    require('GRT-0113' not in log and 'Underflow in reduce' not in log,
            'router capacity underflow invalidates all optimistic route results')


def require_fresh_power_recipe(args):
    if args.fresh_core_power_grid:
        require(not (args.selected_implementation or args.routed_eco_from or
                     args.completed_eco_route_from or args.completed_power_grid_route_from or
                     args.preserve_routed_netlist or args.protect_sram_power_edges),
                'fresh mapped grid cannot reuse or relabel a prior physical netlist')
        require(args.protect_sram_power_geometry and not args.defer_global_eco,
                'fresh grid requires actual power geometry and all ordinary resizer phases')


def require_route_iterations(args):
    require(args.detail_route_iterations in (3, 8), 'unsupported detailed-route repair bound')
    if args.detail_route_iterations == 8:
        require(args.acceptance_launch_buffer or args.padded_sram_input_delay_from or args.control_launch_buffer_from or getattr(args, 'capacity_launch_buffer_from', None) or getattr(args, 'slew_launch_buffer_from', None) or getattr(args, 'decode_launch_buffer_from', None) or getattr(args,'well_fill_from',None) or getattr(args,'two_load_launch_from',None) or (args.core_power_grid and args.preserve_routed_netlist and
                args.protect_sram_power_geometry and args.routed_eco_from and
                not args.fresh_core_power_grid and not args.completed_eco_route_from and
                not args.completed_power_grid_route_from and not args.completed_fresh_grid_route_from),
                'eight-iteration repair is scoped to fresh full-PGbody preserved-netlist routing')


def require_launch_recipe(args, *, selected_binding=False):
    if args.acceptance_launch_buffer:
        require(args.routed_eco_from and args.detail_route_iterations == 8 and
                (not args.selected_implementation or selected_binding) and
                not any((args.preserve_routed_netlist,
                         args.fresh_core_power_grid, args.vss_clock_grid_source,
                         args.protect_sram_power_edges, args.protect_sram_power_geometry,
                         args.completed_eco_route_from, args.completed_power_grid_route_from,
                         args.completed_fresh_grid_route_from, args.defer_global_eco)),
                'one-buffer launch requires only the exact completed powered46 route and unchanged existing PG geometry')


def require_padded_hold_recipe(args, *, selected_binding=False):
    if args.padded_sram_input_delay_from:
        require(args.routed_eco_from and args.detail_route_iterations == 8 and
                (not args.selected_implementation or selected_binding) and
                not any((args.acceptance_launch_buffer,
                         getattr(args, 'control_launch_buffer_from', None),
                         getattr(args, 'capacity_launch_buffer_from', None),
                         args.preserve_routed_netlist, args.fresh_core_power_grid,
                         args.vss_clock_grid_source, args.protect_sram_power_edges,
                         args.protect_sram_power_geometry, args.completed_eco_route_from,
                         args.completed_power_grid_route_from, args.completed_fresh_grid_route_from,
                         args.defer_global_eco, args.center_validation_cones, args.group_button_bus)),
                'padded SRAM input delays require exact completed geometry, original powered115 baseline, and fresh8 routing only')


def require_control_launch_recipe(args):
    if args.control_launch_buffer_from:
        require(args.routed_eco_from and args.detail_route_iterations == 8 and
                not any((args.selected_implementation, args.acceptance_launch_buffer,
                         args.padded_sram_input_delay_from, getattr(args, 'capacity_launch_buffer_from', None), args.preserve_routed_netlist,
                         args.fresh_core_power_grid, args.vss_clock_grid_source,
                         args.protect_sram_power_edges, args.protect_sram_power_geometry,
                         args.completed_eco_route_from, args.completed_power_grid_route_from,
                         args.completed_fresh_grid_route_from, args.defer_global_eco,
                         args.center_validation_cones, args.group_button_bus)),
                'three control launches require exact finite-qualified geometry, original padded30 baseline and fresh8 routing only')


def require_capacity_launch_recipe(args, *, selected_binding=False):
    if args.capacity_launch_buffer_from:
        require(args.routed_eco_from and args.detail_route_iterations == 8 and
                (not args.selected_implementation or selected_binding) and
                not any((args.acceptance_launch_buffer,
                         args.padded_sram_input_delay_from, args.control_launch_buffer_from,
                         args.preserve_routed_netlist, args.fresh_core_power_grid,
                         args.vss_clock_grid_source, args.protect_sram_power_edges,
                         args.protect_sram_power_geometry, args.completed_eco_route_from,
                         args.completed_power_grid_route_from, args.completed_fresh_grid_route_from,
                         args.defer_global_eco, args.center_validation_cones, args.group_button_bus)),
                'capacity launches require exact finite-qualified327 geometry, actual104 baseline and fresh8 routing only')


def require_clock_layer_recipe(args, *, selected_binding=False):
    require(args.clock_min_routing_layer in ('Metal2', 'Metal3'), 'unknown clock minimum layer')
    if args.clock_min_routing_layer == 'Metal3':
        require((args.capacity_launch_buffer_from or getattr(args,'slew_launch_buffer_from',None) or getattr(args,'decode_launch_buffer_from',None) or getattr(args,'well_fill_from',None) or getattr(args,'two_load_launch_from',None)) and args.routed_eco_from and
                args.detail_route_iterations == 8 and
                (not args.selected_implementation or selected_binding),
                'clockMetal3 is scoped to the exact327 source-qualified pilot or selected binding')


def qualified_clock_layer_inputs(args):
    if args.clock_min_routing_layer == 'Metal2':
        return []
    pilot = ROOT / 'build/silicon/task009-capacity-clock3-grt-preflight-a1'
    closure = ROOT / 'build/silicon/task009-capacity-clock3-completed-closure-a2/result.json'
    require(sha(closure) == '065ded893c82b26b7c60b37bdb14a40e5e33b0088b2a6bd08e05a438182702bd' and
            sha(pilot / 'result.json') == '5c671f754ddbc200bf727dec0224eca70cb8efb36f28c3ec710d3788f8e01622',
            'exact reviewed clockM3 pilot and separate complete source assessment required')
    assessment = json.loads(closure.read_text())
    require(assessment['status'] == 'PASS_SEPARATE_COMPLETED_CLOCK3_SOURCE_CLOSURE_AND_ORIGINAL_CONSTRAINTS'
            and assessment['source_seal_equal'], 'sealed clockM3 source assessment required')
    require(sha(pilot / 'route.guide') == assessment['source_inputs'][str(pilot / 'route.guide')],
            'reviewed clockM3 guide bytes differ')
    # Historical source identities stay in their exact archive. They are not
    # silently reinterpreted as this successor's explicit clock-layer argument.
    inputs = [closure, pilot / 'result.json', pilot / 'route.guide']
    for original, entry in assessment['archived_inputs'].items():
        path = ROOT / entry['path']
        require(sha(path) == entry['sha256'] == assessment['source_inputs'][original],
                'reviewed clockM3 source archive differs: ' + original)
        inputs.append(path)
    return inputs


def qualified_vss_grid_source(args):
    original = ROOT / 'tooling/silicon/pen-power-grid.tcl'
    if args.vss_clock_grid_source is None:
        return original
    require(args.selected_implementation and args.core_power_grid and
            args.preserve_routed_netlist and args.protect_sram_power_geometry and
            args.detail_route_iterations == 8 and args.routed_eco_from and
            not args.fresh_core_power_grid and not args.completed_eco_route_from and
            not args.completed_power_grid_route_from and not args.completed_fresh_grid_route_from,
            'VSS clock-channel source requires the scoped fresh8 full-PGbody preserved-netlist recipe')
    candidate = args.vss_clock_grid_source.resolve()
    require(candidate.is_relative_to(ROOT / 'build') and candidate.is_file() and
            candidate.stat().st_size <= 16384, 'bounded explicit ignored PG candidate required')
    line = 'add_pdn_stripe -grid pen_core -layer Metal5 -width 2.5 -pitch 80 -offset 10 -nets {VDDlogic VDDARRAY VSS}'
    source = original.read_text()
    replacement = '\n'.join(f'add_pdn_stripe -grid pen_core -layer Metal5 -width 2.5 -pitch 80 -offset {offset} -nets {{{net}}}'
        for net, offset in [('VDDlogic', '10'), ('VDDARRAY', '36.665'), ('VSS', '65.330')])
    require(source.count(line) == 1 and candidate.read_text() == source.replace(line, replacement),
            'PG candidate changes more than the explicit VSS phase and equivalent one-net definitions')
    require(sha(candidate) == 'b6a3315d233f16e01a6d7a30279867964cdece162a1839b6bed3e01b735fb38e',
            'PG candidate differs from the source-qualified actual-grid pilot')
    return candidate


def host_memory_budget(args):
    require(args.host_memory_gib in (4, 6), 'unsupported bounded host-memory profile')
    require(args.host_memory_gib == 6 or args.fresh_core_power_grid,
            '4GiB host budget is scoped to the separately admitted fresh-grid candidate')
    return args.host_memory_gib << 30, (args.host_memory_gib + 2) << 30


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mapping', type=Path, required=True)
    p.add_argument('--pdk', type=Path, required=True)
    clock = p.add_mutually_exclusive_group()
    clock.add_argument('--automatic-clock-wire-length', dest='automatic_clock_wire_length', action='store_true', default=True, help='Use actual pinned RC/driver wire optimum (default); all timing/electrical constraints remain')
    clock.add_argument('--historical-clock-wire-length', dest='automatic_clock_wire_length', action='store_false', help='Reproduce the historical100um clock-repair optimization bound')
    p.add_argument('--center-validation-cones', action='store_true', help='Fence real range-validation cones/collectors in the open middle macro channel; preserve all timing and macro OBS')
    p.add_argument('--group-button-bus', action='store_true', help='Place all64 raw button inputs contiguously on the original top-edge Metal2 tracks; preserve every input delay/bit and verify actual geometry')
    p.add_argument('--defer-global-eco', action='store_true', help='Keep placement/clock repairs and every constraint, but defer the failing global-RC ECO optimization until actual routed extraction; fresh timing failures remain failures')
    p.add_argument('--question',default='Do independent timestamp/counter arithmetic and bounded clock clusters remove observed defects at unchanged100MHz/full256 FIFO?',help='Prospective engineering question for this changed-input run')
    p.add_argument('--completed-eco-route-from', type=Path, help='Independently assess a source-sealed completed ECO route rejected only by the timestamp-sensitive SDC observer; never reroutes it')
    p.add_argument('--completed-power-grid-route-from', type=Path, help='Independently assess completed grid geometry rejected only by the exact-byte observer seeing the three required physical PG ports; never reroutes it')
    p.add_argument('--completed-fresh-grid-route-from', type=Path, help='Independently validate/finalize sealed fresh-grid geometry rejected after completed detail routing by the historical exact SRAM input-net-name guard; original-Lib buffered endpoint proof and actual PG/port checks remain mandatory; no reroute')
    p.add_argument('--completed-well-fill-route-from',type=Path,help='Separately assess exact completed zero-marker well/spacer route rejected by old byte guard; strict original-CDL serialization, fresh3RC/corners, no routing or oldproducerPASS')
    p.add_argument('--routed-eco-from', type=Path, help='Repair the exact sealed routed nominal-SPEF producer, then route and extract the changed physical netlist afresh')
    p.add_argument('--core-power-grid', action='store_true', help='Add the real separate VDDlogic/VDDARRAY/VSS core grid after actual-SPEF repair and before fresh signal routing; requires a prior route without PG geometry')
    p.add_argument('--fresh-core-power-grid', action='store_true', help='Integrate a fresh qualified mapped candidate, all normal placement/clock/resizer phases and three-supply grid before first GRT; requires full PG geometry protection, no prior netlist or deferred ECO')
    p.add_argument('--acceptance-launch-buffer', action='store_true', help='Source-bound one-buf8 ECO on the exact completed46 powered route; preserve all existing grid/OBS/ports and old cells, then freshly route/extract every signal at unchanged constraints')
    p.add_argument('--padded-sram-input-delay-from', type=Path, help='Consume exact qualified completed original-padding geometry with33 original delaycells on31 SRAM inputs; no repeated legalization/resizer, fresh signal routing/extraction and all original constraints')
    p.add_argument('--control-launch-buffer-from', type=Path, help='Explicit unselected finite-qualified three-original-buf8 geometry on padded30 baseline; all old cells/33delays/PG/OBS/padding preserved, fresh routing/extraction only')
    p.add_argument('--capacity-launch-buffer-from', type=Path, help='Explicit unselected finite-qualified327 original buf8 launches from actual104 nominal maxcap inventory; all old sites/33delays/3controls/PG/OBS/ports preserved, fresh routing/extraction only')
    p.add_argument('--slew-launch-buffer-from',type=Path,help='Exact finite-qualified three originalbuf8 launches on zero-router/native420 geometry; old placements/PG/OBS/delays/padding preserved, fresh GRT/PA/3RC')
    p.add_argument('--decode-launch-buffer-from',type=Path,help='Exact finite-qualified three originalbuf8 launches on selected0.6 NOR3/BUF2/A21OI decodeoutputs; all old geometry/output ports preserved, fresh GRT/PA/3RC')
    p.add_argument('--well-fill-from',type=Path,help='Exact32-site well repair plus40247 original spacers on selected0.6; no functional changes or old signal wires, fresh GRT/PA/DRT/3RC at original constraints')
    p.add_argument('--two-load-launch-from',type=Path,help='Exact two originalbuf8 launches plus40241 updatedspacers on completedwellroute; preserve all old functional sites/fullSDC and freshly route/extract')
    p.add_argument('--power-margin-from',type=Path,help='Exact qualified actual327 VSS+2um/conservative275nm M2 routing precursor; independent native420nm guard required, fresh GRT/PA/route at unchanged constraints')
    p.add_argument('--preferred-access-from', type=Path, help='Exact separately sealed two-instance preferredAP1->existingAP4 on unselected327 clockM3 baseline; reuse original guides/PA with -no_pin_access, no GRT or geometry regeneration')
    p.add_argument('--preferred-access-preflight-only', action='store_true', help='Bounded30s/2GiB actual retained-guide/AP/power prefix; stop before detailed routing, no closure claim')
    p.add_argument('--clock-min-routing-layer', choices=('Metal2', 'Metal3'), default='Metal2', help='Legacy clockMetal2 unchanged; explicitMetal3 only on exact327-source GRT-qualified candidate, preserving every original clock/SDC/pin obligation')
    p.add_argument('--vss-clock-grid-source', type=Path, help='Explicit source-qualified VSS-only+2um clock-channel grid candidate under build/; allpositive rails and declared constraints stay exact, no selection or closure implied')
    p.add_argument('--detail-route-iterations', type=int, choices=(3, 8), default=3, help='Bounded detailed-route repair input; legacy3 unchanged, explicit8 only for fresh full-PGbody preserved-netlist routing at unchanged900/1200-second limits')
    p.add_argument('--host-memory-gib', type=int, choices=(4, 6), default=6, help='Hard host AS budget; legacy6GiB/floor8GiB unchanged. Explicit4GiB/floor6GiB is scoped to the separately source-bound fresh-grid candidate; failure never extends the budget')
    p.add_argument('--core-power-grid-reroute', dest='preserve_routed_netlist', action='store_true', help='For the core-grid question only, retain the exact already repaired logical netlist/placement and reroute against new real power geometry; no further resizer repair claim')
    p.add_argument('--selected-implementation', action='store_true', help='Consume the existing physical-lock selected powered pen configuration; requires its repaired signal-route predecessor and a current qualified mapping')
    p.add_argument('--protect-sram-power-edges', action='store_true', help='Physical-only changed candidate: preserve PG pins and add original Metal4 spacing clearance for signals at real macro PG boundaries')
    p.add_argument('--protect-sram-power-geometry', action='store_true', help='Physical-only candidate: protect full actual PG pin bodies and special-wire/via metal using unchanged original process/CTS spacing')
    p.add_argument('--work-dir', type=Path, required=True)
    args = p.parse_args()
    require_fresh_power_recipe(args)
    require_launch_recipe(args)
    require_padded_hold_recipe(args)
    require_control_launch_recipe(args)
    require_capacity_launch_recipe(args)
    require_clock_layer_recipe(args)
    from silicon_preferred_route import require_recipe as require_preferred_recipe, PrefixComplete
    require_preferred_recipe(args)
    from silicon_power_margin_route import require_recipe as require_margin_recipe
    require_margin_recipe(args)
    from silicon_slew_launch import require_recipe as require_slew_recipe
    require_slew_recipe(args)
    from silicon_decode_launch import require_recipe as require_decode_recipe
    require_decode_recipe(args)
    from silicon_well_fill_route import require_recipe as require_well_recipe
    require_well_recipe(args)
    from silicon_two_load_launch import require_recipe as require_two_load_recipe
    require_two_load_recipe(args)
    if args.completed_well_fill_route_from:
        require(args.well_fill_from and not args.completed_eco_route_from,'completed well assessment requires its exact well-source recipe only')
        args.completed_eco_route_from=args.completed_well_fill_route_from
    host_as_bytes, host_available_floor = host_memory_budget(args)
    if args.fresh_core_power_grid or args.acceptance_launch_buffer or args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
        args.core_power_grid = True
    if args.preferred_access_preflight_only:
        host_as_bytes, host_available_floor = 2 << 30, 4 << 30
    selected = None
    if args.selected_implementation:
        selected = json.loads((ROOT / 'tooling/silicon/physical-lock.json').read_text())['selected_pen_implementation']
        if selected['version'] == 'lemma-pen-sg13g2-slew-native-margin-grid/1':
            from silicon_slew_launch import bind_selected
            bind_selected(args,selected)
            require_clock_layer_recipe(args,selected_binding=True)
        elif selected['version'] == 'lemma-pen-sg13g2-native-margin-grid/1':
            from silicon_power_margin_route import bind_selected
            bind_selected(args,selected)
            require_capacity_launch_recipe(args,selected_binding=True)
            require_clock_layer_recipe(args,selected_binding=True)
        elif selected['version'] == 'lemma-pen-sg13g2-core-grid/1':
            require(selected['launch']['flags'] == ['--core-power-grid', '--core-power-grid-reroute'], 'unknown historical selected grid recipe')
            args.core_power_grid, args.preserve_routed_netlist = True, True
        else:
            require(selected['version'] in ('lemma-pen-sg13g2-launch-grid/1',
                                            'lemma-pen-sg13g2-padded-sram-grid/1'),
                    'unknown selected powered physical recipe')
            predecessor = selected['launch']['predecessor']
            prior = ROOT / predecessor['path']
            require(sha(prior / 'result.json') == predecessor['receipt_sha256'] and
                    sha(prior / 'routed.odb') == predecessor['routed_odb_sha256'], 'selected powered predecessor differs')
            require(args.routed_eco_from is None or args.routed_eco_from.resolve() == prior.resolve(),
                    'selected launch uses its exact declared completed powered predecessor')
            args.routed_eco_from = prior
            args.core_power_grid = True
            args.detail_route_iterations = 8
            entry = selected['launch']['source']
            require(sha(ROOT / entry['path']) == entry['sha256'], 'selected launch source differs')
            entry = selected['launch']['Liberty']
            require(sha(args.pdk.resolve() / entry['path']) == entry['sha256'], 'selected original PDK Liberty differs')
            if selected['version'] == 'lemma-pen-sg13g2-launch-grid/1':
                require(selected['launch']['flags'] == ['--acceptance-launch-buffer', '--detail-route-iterations', '8'],
                        'unknown selected launch flags')
                args.acceptance_launch_buffer = True
                require_launch_recipe(args, selected_binding=True)
            else:
                prepared = selected['launch']['prepared_geometry']
                geometry = ROOT / prepared['path']
                require(selected['launch']['flags'] == ['--padded-sram-input-delay-from',
                        str(geometry.parent.relative_to(ROOT)), '--detail-route-iterations', '8'] and
                        sha(geometry) == prepared['sha256'], 'selected completed padded geometry differs')
                require(args.padded_sram_input_delay_from is None or
                        args.padded_sram_input_delay_from.resolve() == geometry.parent,
                        'selected padded source differs')
                args.padded_sram_input_delay_from = geometry.parent
                require_padded_hold_recipe(args, selected_binding=True)
        for entry in (selected['rtl'], selected['power_grid']['source'], selected['power_grid']['connectivity_check']):
            require(sha(ROOT / entry['path']) == entry['sha256'], 'selected physical source differs: ' + entry['path'])
        require(not args.completed_eco_route_from and not args.completed_power_grid_route_from, 'selected implementation launches new geometry; retained observer assessments keep original source identities')
    out, mapping, pdk = (v.resolve() for v in (args.work_dir, args.mapping, args.pdk))
    require(not out.exists() and out.is_relative_to(ROOT / 'build'), 'unused ignored output required')
    out.mkdir(parents=True)
    start = time.monotonic()
    report = {'schema': 'lemma-pen-physical/3', 'status': 'FAIL', 'scope': __doc__,
              'commands': [], 'bounds': {'whole_seconds': 600 if args.completed_well_fill_route_from else 30 if args.preferred_access_preflight_only else 240 if args.completed_fresh_grid_route_from else 1200, 'route_seconds': 0 if args.completed_well_fill_route_from or args.preferred_access_preflight_only or args.completed_fresh_grid_route_from else 900,
              'extraction_each_seconds': 60, 'AS_bytes': host_as_bytes,
              'launch_available_bytes': host_available_floor, 'file_bytes': 1 << 30,
              'output_budget_bytes': 12 << 30},
              'physical_closure': 'UNVERIFIED',
              'derived_routing_capacity': 'NOT_ADMITTED: future adaptations require actual non-increase and blocked-zero/edge/interior plus underflow/increase negative controls',
              'validation_cone_placement': 'open-middle-channel' if args.center_validation_cones else 'unconstrained',
              'button_bus_pin_placement': 'FULL64_ORDERED_TOP_EDGE' if args.group_button_bus else 'UNCONSTRAINED',
              'global_rc_optimization': 'DEFERRED_UNTIL_ACTUAL_EXTRACTION' if args.defer_global_eco else 'ENABLED',
              'clock_wire_repair': 'pinned-driver-RC-optimum' if args.automatic_clock_wire_length else 'historical100um', 'power_grid': 'NOT_IMPLEMENTED',
              'detail_route_iterations': args.detail_route_iterations,
              'clock_routing_layers': args.clock_min_routing_layer + '-Metal5',
              'process_drc': 'NOT_RUN', 'lvs': 'NOT_RUN',
              'remaining': ['power grid and power/test-pin connectivity',
                 'process DRC and transistor LVS', 'matched-temperature fast stdcell/SRAM timing pair',
                 'pad/package/board and full-SoC physical design',
                 'mixed-signal/power/safety/physical qualification']}
    resource.setrlimit(resource.RLIMIT_AS, (host_as_bytes, host_as_bytes))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    def invoke(argv, name, seconds):
        try:
            record = run(argv, out / (name + '.log'), min(start + report['bounds']['whole_seconds'], time.monotonic() + seconds))
        except CommandFailure as error:
            report['commands'].append(error.record)
            raise
        report['commands'].append(record)

    try:
        require(not args.completed_fresh_grid_route_from or args.fresh_core_power_grid,
                'completed fresh-grid assessment requires its separately named fresh mapping path')
        require(not (args.center_validation_cones and args.routed_eco_from), 'initial cone placement and retained-route ECO are separate questions')
        require(not args.defer_global_eco or (args.center_validation_cones and not args.routed_eco_from), 'deferred optimization is scoped to the aligned validation-placement question')
        require(not args.group_button_bus or not args.routed_eco_from, 'a new input-pin placement requires a fresh initial physical implementation')
        require(not args.core_power_grid or args.completed_well_fill_route_from or args.fresh_core_power_grid or (args.routed_eco_from and not args.completed_eco_route_from), 'new power-grid integration requires its actual source mapping or route')
        require(not args.preserve_routed_netlist or args.core_power_grid, 'preserved-netlist rerouting is scoped only to real new power-grid integration')
        require(not args.completed_power_grid_route_from or (args.core_power_grid and args.preserve_routed_netlist and not args.completed_eco_route_from), 'completed grid assessment requires the exact core-grid interface question')
        require(not args.protect_sram_power_edges or (args.core_power_grid and args.preserve_routed_netlist and not args.completed_power_grid_route_from), 'PG edge clearance requires fresh routing against the actual preserved-netlist grid')
        require(not args.protect_sram_power_geometry or (args.core_power_grid and (args.preserve_routed_netlist or args.fresh_core_power_grid) and not args.protect_sram_power_edges and not args.completed_power_grid_route_from), 'full PG geometry is a separate fresh routing question')
        require_route_iterations(args)
        grid_source = qualified_vss_grid_source(args)
        clock_layer_inputs = qualified_clock_layer_inputs(args)
        available = next(int(x.split()[1]) * 1024 for x in Path('/proc/meminfo').read_text().splitlines()
                         if x.startswith('MemAvailable:'))
        require(available >= host_available_floor, 'launch memory floor')
        require(shutil.disk_usage(out).free >= 12 << 30, 'output disk floor')
        report['available_bytes_at_launch'] = available
        if args.host_memory_gib == 4:
            report['host_resource_profile'] = 'fresh-grid-host-budget/1: hard4GiBAS/floor6GiB, based retained1.38GiB route peak plus5% mapped cells; original chip/clock constraints unchanged; no deadline/AS extension'
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
        report['enclosure_preflight'] = prepare(pdk, out / 'enclosure', True, min(60, start + report['bounds']['whole_seconds'] - time.monotonic()))
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
                  ROOT / 'tooling/silicon/pen-floorplan.tcl', ROOT / 'tooling/silicon/pen-validation-region.tcl', ROOT / 'tooling/silicon/pen-validation-check.tcl', ROOT / 'tooling/silicon/pen-button-pins.tcl', mapping / 'candidate.sv',
                  mapping / 'mapped.v', mapping / 'result.json', openroad]
        inputs += clock_layer_inputs
        if clock_layer_inputs:
            report['clock_layer_pilot'] = {'version': 'lemma-pen-clock-route-floor/1',
                'scope': 'Unselected327-source clockM3pilot, same312clock/9388signalguide identities, target172.8umM2trunk removed; otherlongM2obligations remain. Separate archived source assessment adds originally omitted helper/Lib/tool without rerunning GRT.',
                'completed_source_assessment': str(clock_layer_inputs[0]),
                'sha256': sha(clock_layer_inputs[0])}
        if selected:
            inputs += [ROOT / 'tooling/silicon/physical-lock.json']
            report['selected_implementation'] = {'version': selected['version'], 'source': 'tooling/silicon/physical-lock.json',
                'scope': 'Powered selected recipe; original retained producers keep their original source identities'}
        if args.vss_clock_grid_source is not None:
            inputs.append(grid_source)
            report['power_grid_variant'] = {'version': 'lemma-pen-core-vss-clock-clearance/1', 'source': str(grid_source), 'sha256': sha(grid_source), 'scope': 'Unselected actual pilot-qualified VSS-only2um phase shift; original core widths/pitch/positive geometry/PG bindings and constraints retained'}
        if args.fresh_core_power_grid:
            inputs += [ROOT / name for name in ('tooling/silicon/pen-power-grid.tcl',
                'tooling/silicon/pen-power-check.tcl', 'tooling/silicon/pen-fresh-power.tcl',
                'tooling/silicon/pen-power-edge.tcl', 'scripts/silicon_power_ports.py', 'scripts/silicon_buffered_pins.py')]
            inputs += [std / 'lef/sg13g2_tech.lef']
            report['power_grid_routing_question'] = 'Fresh qualified mapped source, normal resizer phases, actual grid and full PG geometry before first GRT; no historical netlist'
            report['PG_edge_clearance'] = 'CANDIDATE_ACTUAL_FULL_PG_GEOMETRY_ORIGINAL_PROCESS_CTS_0.42UM'
        if args.completed_fresh_grid_route_from:
            completed = args.completed_fresh_grid_route_from.resolve()
            producer = json.loads((completed / 'result.json').read_text())
            require(producer['status'] == 'FAIL' and producer['source_seal_equal'] and producer.get('candidate_only') and
                    producer['mapping_receipt']['sha256'] == sha(mapping / 'result.json') and
                    producer.get('power_grid_routing_question', '').startswith('Fresh qualified mapped source'),
                    'sealed source-specific fresh-grid failure required')
            log = (completed / 'layout.log').read_text()
            require('Complete detail routing.' in log and re.search(r'Error:.*SRAM signal/test binding changed: pen_sram_lane\d \{A_(?:DIN|ADDR|MEN|WEN)', log),
                    'only completed geometry rejected by the exact functional input-net guard may continue')
            require_no_capacity_underflow(log)
            for name, digest in producer['source_inputs'].items():
                source = Path(name)
                relative = source.relative_to(ROOT) if source.is_relative_to(ROOT) else Path('external') / source.name
                archived = completed / 'source-archive' / relative
                require(sha(archived) == digest, 'original failed producer archive differs')
                inputs.append(archived)
            retained = ('failed-layout.odb', 'failed-layout.def', 'route.drc', 'route.guide', 'layout.log',
                        'power-grid-before-route.json', 'power-macro-before-route.tsv',
                        'pre-power/routed.odb', 'pre-power/routed.v', 'pre-power/routed.sdc', 'pre-power/routed.def',
                        'post-power/routed.odb', 'post-power/routed.v')
            inputs += [completed / 'result.json'] + [completed / name for name in retained]
            for name in retained:
                target = out / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(completed / name, target)
            count = len(re.findall(r'^violation type:', (completed / 'route.drc').read_text(), re.M))
            counts = re.findall(r'Number of violations = (\d+)\.', log)
            require(counts and int(counts[-1]) == count, 'actual final router report/count differs')
            (out / 'router-drc-count.txt').write_text(str(count) + '\n')
            report['reused_completed_route'] = {'path': str(completed), 'receipt_sha256': sha(completed / 'result.json'),
                'scope': 'Original failed detail routing retained; actual failed ODB finalized without placement/resizer/routing. New original-Lib endpoint/PG/port assessment and fresh3RC only.'}
        if args.routed_eco_from:
            prior = args.routed_eco_from.resolve()
            previous = json.loads((prior / 'result.json').read_text())
            require(previous['status'] == 'ASSESSED_PHYSICAL_CLOSURE_UNVERIFIED' and previous['source_seal_equal'], 'sealed actual route producer required')
            if previous['mapping_receipt']['sha256'] != sha(mapping / 'result.json'):
                # Versioning the physical selection invalidates the mapping
                # receipt's lock input, even when actual mapped bytes and every
                # design/tool/collateral input are unchanged. Require a fresh
                # current mapping and retain the old receipt independently.
                old_path = Path(previous['mapping_receipt']['path'])
                require((selected or args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from)) and sha(old_path) == previous['mapping_receipt']['sha256'], 'ECO mapping producer differs')
                old = json.loads(old_path.read_text())
                lock_name = 'tooling/silicon/physical-lock.json'
                require({k:v for k,v in old['source_inputs'].items() if k != lock_name} ==
                        {k:v for k,v in admitted['source_inputs'].items() if k != lock_name} and
                        old['collateral'] == admitted['collateral'] and old['tools'] == admitted['tools'] and
                        old['mapping'] == admitted['mapping'] and
                        sha(old_path.parent / 'mapped.v') == sha(mapping / 'mapped.v'),
                        'new selected mapping changes an actual design/tool/collateral input')
                inputs += [old_path, old_path.parent / 'mapped.v']
                report['mapping_metadata_transition'] = {'original': previous['mapping_receipt'],
                    'current': report['mapping_receipt'], 'scope': 'Fresh mapping after physical-lock selection only; actual mapped bytes and all other source/tool/collateral identities equal'}
            if (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
                from importlib import import_module
                launch_module=import_module('silicon_two_load_launch'if args.two_load_launch_from else'silicon_well_fill_route'if args.well_fill_from else'silicon_decode_launch'if args.decode_launch_buffer_from else'silicon_slew_launch')
                admit,SOURCE_SHA=launch_module.admit,launch_module.SOURCE_SHA
                prepared_geometry,geometry_assessment,geometry_inputs=admit((args.two_load_launch_from or args.well_fill_from or args.slew_launch_buffer_from or args.decode_launch_buffer_from))
                if args.well_fill_from: inputs.append(std/'cdl/sg13g2_stdcell.cdl')
                require(previous.get('power_grid')=='CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                        sha(prior/'routed.odb')==SOURCE_SHA and previous['router_drc']['violations']==0 and
                        previous['native_power_margin']['actual_final_relation']['status']=='PASS_ACTUAL_NATIVE420NM_RECTANGLE_SUBSET_ONLY',
                        'slew launches require the exact completedzero/native420 source')
                inputs += geometry_inputs+[geometry_assessment,prepared_geometry,ROOT/('scripts/silicon_two_load_launch.py'if args.two_load_launch_from else'scripts/silicon_well_fill_route.py'if args.well_fill_from else'scripts/silicon_decode_launch.py'if args.decode_launch_buffer_from else'scripts/silicon_slew_launch.py'),
                    ROOT/'scripts/silicon_sram_input_hold.py',ROOT/'scripts/silicon_acceptance_launch.py',
                    ROOT/'scripts/silicon_buffered_pins.py',ROOT/'scripts/silicon_power_clearance.py',
                    ROOT/'scripts/silicon_power_ports.py',ROOT/'tooling/silicon/pen-power-check.tcl']
                report['prepared_two_load_geometry'if args.two_load_launch_from else'prepared_well_fill_geometry'if args.well_fill_from else'prepared_slew_geometry']={'path':str(prepared_geometry),'sha256':sha(prepared_geometry),
                    'assessment':str(geometry_assessment),'assessment_sha256':sha(geometry_assessment),
                    'scope':'Two originalbuf8 measuredwireload launches;9037oldfunctional/macro sites fixed,40247→40241sourcequalifiedspacers only2rows; all960padding/33delays/nativePG/OBS/ports/BIST preserved, no inheritedsignalroute.'if args.two_load_launch_from else'Exact32 one-site functional moves,40247 originalphysicalspacers,960nmfunctionalpadding/33delays/PG/OBS/ports/BIST preserved; zero inheritedsignalroute; originalNWelltable0, inheritedconservativeMetal1finding remains.'if args.well_fill_from else'Three originalbuf8 on exact measuredNOR3_2/BUF2/A21OI2 addressdecode outputs; zero9034oldmoves/full668ports/33delays/327capacitybuffers/nativePG/OBS/960nmpadding preserved.'if args.decode_launch_buffer_from else'Three originalbuf8 on actualselectedNOR4_2/NOR4_1/INV1 slowoutputs; zero9031oldmoves,668ports/33delays/327capacitybuffers/nativePG/OBS/960nmpadding preserved.'}
                report['native_power_margin']={'version':'lemma-native420-conservative-M2-and-VSS-grid/1',
                    'scope':'Inherited exact native420-qualified PG/OBS from source; final independent actualwire/via/patch margin mandatory, never inferred from oldroute.'}
                report['PG_edge_clearance']='ORIGINAL_NATIVE420NM_RECTANGLE_WITH_CONSERVATIVE_M2_ROUTER275_REPRESENTATION'
                report['power_grid_routing_question']='Exactcompletedwellroute5c43:2originalbuf8 on NAND2_2/NOR4_2 wireloaded outputs plus40241updatedspacers;9037oldsites/full10ns/668ports/PG/test/padding fixed; freshGRT/PA/DRT/3RC/all9'if args.two_load_launch_from else'Exactselected0.6:32 source-proved site moves+40247originalspacers; freshGRT/PA/DRT/3RC/all9corners/10ns; originalPG/OBS/668ports/33delays/BIST retained'if args.well_fill_from else'Exact9037cells: actualselected0.6zero-route grid plus3 originalbuf8 on measuredaddressdecode drivers; freshGRT/PA/DRT/3RC, all10ns/ports/PG/test/padding preserved'if args.decode_launch_buffer_from else'Exact9034cells: actualselectedzero-route grid plus3 originalbuf8 on measuredslowdrivers; freshGRT/PA/DRT/3RC, all10ns/ports/PG/test/padding preserved'
                report['global_rc_optimization']='EXACT_TWO_MEASURED_LOAD_BUF8_UPDATED_SPACERS_NO_RESIZER_OR_OLD_SPEF'if args.two_load_launch_from else'EXACT32_WELL_SITE_REPAIR_ORIGINAL_SPACERS_NO_RESIZER_OR_OLD_SPEF'if args.well_fill_from else'EXACT_THREE_MEASURED_SLEW_BUF8_GEOMETRY_NO_RESIZER_OR_OLD_SPEF'
            elif args.capacity_launch_buffer_from:
                from silicon_capacity_launch import admit, SOURCE_SHA
                prepared_geometry, geometry_assessment, geometry_inputs = admit(args.capacity_launch_buffer_from)
                require(previous.get('power_grid') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                        sha(prior / 'routed.odb') == SOURCE_SHA and previous['router_drc']['violations'] == 104,
                        'capacity launch candidate requires exact completed104 baseline')
                inputs += geometry_inputs + [geometry_assessment, prepared_geometry,
                    ROOT / 'scripts/silicon_capacity_launch.py', ROOT / 'scripts/silicon_sram_input_hold.py',
                    ROOT / 'scripts/silicon_acceptance_launch.py', ROOT / 'scripts/silicon_buffered_pins.py',
                    ROOT / 'scripts/silicon_power_ports.py', ROOT / 'tooling/silicon/pen-power-check.tcl']
                report['prepared_capacity_geometry'] = {'path': str(prepared_geometry), 'sha256': sha(prepared_geometry),
                    'assessment': str(geometry_assessment), 'assessment_sha256': sha(geometry_assessment),
                    'scope': 'Unselected327 original buf8 launches from nominal actualmaxcap;37 excluded obligations and54 extra all-corner pins remain. Old placements/33delays/3controls/ports/nativePG/OBS/padding exact; no oldSPEF on changed nets.'}
                report['power_grid_routing_question'] = 'Exact existing104 geometry with327 original buf8 launches on source-qualified nonclock/nonreset/nontest/nonpad internal drivers; full original constraints and excluded obligations retained'
                report['global_rc_optimization'] = 'EXACT327_ORIGINAL_BUF8_ACTUAL_CAPACITY_LAUNCH_GEOMETRY'
                if args.power_margin_from:
                    from silicon_power_margin_route import admit as admit_margin
                    prepared_geometry,margin_receipt,margin_inputs=admit_margin(args.power_margin_from)
                    inputs += margin_inputs+[margin_receipt,prepared_geometry,ROOT/'scripts/silicon_power_margin.py',ROOT/'scripts/silicon_power_margin_route.py',ROOT/'scripts/silicon_power_clearance.py']
                    report['native_power_margin']={'version':'lemma-native420-conservative-M2-and-VSS-grid/1','receipt':str(margin_receipt),'receipt_sha256':sha(margin_receipt),'geometry_sha256':sha(prepared_geometry),
                        'scope':'Original420nm native rectangular margin retained; M2 routing representation275 plus original>=210 Euclidean spacing; source-qualified VSS-only2um shift. Fresh GRT/PA; no old-guide or final margin claim.'}
                    report['power_grid_routing_question']='Exact9031-cell327-buffer geometry with source-qualifiedVSS+2um and conservativeM2OBS275; independent native420nm final wire/via/patch guard, original10ns/fullports/PG/padding/test maintained'
                    report['PG_edge_clearance']='ORIGINAL_NATIVE420NM_RECTANGLE_WITH_CONSERVATIVE_M2_ROUTER275_REPRESENTATION'
                if args.preferred_access_from:
                    from silicon_preferred_route import admit as admit_preferred, require_tcl, CORE_SHA
                    preferred = admit_preferred(args.preferred_access_from)
                    require(sha(openroad.parent / '.openroad-wrapped') == CORE_SHA, 'exact AP exporter core ABI required')
                    require_tcl((ROOT / 'tooling/silicon/pen-extracted-eco.tcl').read_text())
                    prepared_base_geometry = prepared_geometry
                    prepared_geometry = preferred['geometry']
                    inputs += preferred['inputs'] + [ROOT / 'scripts/silicon_preferred_route.py', ROOT / 'scripts/silicon_access_writer.py']
                    report['retained_preferred_access'] = {'source': str(prepared_geometry), 'sha256': sha(prepared_geometry),
                        'seal': str(preferred['seal']), 'seal_sha256': sha(preferred['seal']),
                        'guides_sha256': sha(preferred['guides']),
                        'scope': 'Unselected327 clock-M3 actual baseline PA; exactly2 original preferred refs1->existing4. No new GRT/PA/resizer/DPL/grid generation, selected30 unchanged.'}
                    report['global_rc_optimization'] = 'RETAINED_EXACT_GRT_GUIDES_AND_TWO_INSTANCE_PREFERENCES_NO_NEW_GRT'

            elif args.control_launch_buffer_from:
                from silicon_control_launch import admit, SOURCE_SHA
                prepared_geometry, geometry_assessment, geometry_inputs = admit(args.control_launch_buffer_from)
                require(previous.get('power_grid') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                        sha(prior / 'routed.odb') == SOURCE_SHA and previous['router_drc']['violations'] == 30,
                        'control launch candidate requires its exact completed padded30 baseline')
                inputs += geometry_inputs + [geometry_assessment, prepared_geometry,
                    ROOT / 'scripts/silicon_control_launch.py', ROOT / 'scripts/silicon_sram_input_hold.py',
                    ROOT / 'scripts/silicon_acceptance_launch.py', ROOT / 'scripts/silicon_buffered_pins.py',
                    ROOT / 'scripts/silicon_power_ports.py', ROOT / 'tooling/silicon/pen-power-check.tcl']
                report['prepared_control_geometry'] = {'path': str(prepared_geometry), 'sha256': sha(prepared_geometry),
                    'assessment': str(geometry_assessment), 'assessment_sha256': sha(geometry_assessment),
                    'scope': 'Unselected actual finite-qualified three buf8 geometry; zero old-cell moves,33 SRAM delays/nativePG/OBS/originalpadding exact. No repeated DPL/resizer or old SPEF on changed nets.'}
                report['power_grid_routing_question'] = 'Exact existing padded30 with only three original buf8 control launches; old cells/33 delays/nativePG/OBS/ports/originalpadding unchanged'
                report['global_rc_optimization'] = 'EXACT_THREE_ORIGINAL_BUF8_CONTROL_LAUNCH_GEOMETRY'
            elif args.padded_sram_input_delay_from:
                from silicon_sram_input_hold import admit, SOURCE_ODB_SHA
                prepared_geometry, geometry_assessment, geometry_inputs = admit(args.padded_sram_input_delay_from)
                require(previous.get('power_grid') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                        sha(prior / 'routed.odb') == SOURCE_ODB_SHA and previous['router_drc']['violations'] == 115,
                        'padded hold candidate requires its exact completed powered115 baseline')
                inputs += geometry_inputs + [geometry_assessment, prepared_geometry,
                    ROOT / 'scripts/silicon_sram_input_hold.py', ROOT / 'scripts/silicon_acceptance_launch.py',
                    ROOT / 'scripts/silicon_buffered_pins.py', ROOT / 'scripts/silicon_power_ports.py',
                    ROOT / 'tooling/silicon/pen-power-check.tcl']
                report['prepared_padded_geometry'] = {'path': str(prepared_geometry), 'sha256': sha(prepared_geometry),
                    'assessment': str(geometry_assessment), 'assessment_sha256': sha(geometry_assessment),
                    'scope': 'Actual completed original1/1padding legalization:243 old cells moved,33 input delays. No repeated DPL/resizer, old SPEF only on separate unchanged baseline.'}
                report['power_grid_routing_question'] = 'Exact existing powered115 PG/OBS, full original placement padding and33 original noninverting SRAM input delays; no grid regeneration or resizer'
                report['global_rc_optimization'] = 'EXACT_COMPLETED_PADDED33_INPUT_DELAY_GEOMETRY'
            elif args.acceptance_launch_buffer:
                require(previous.get('power_grid') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                        sha(prior / 'routed.odb') == '92c0e300a753a500d79ea4799e30953887bb98baf5b8972863a7580505be95bc' and
                        previous['router_drc']['violations'] == 46,
                        'launch ECO requires the reviewed completed46 powered layout, not an incomplete VSS route')
                inputs += [ROOT / 'scripts/silicon_acceptance_launch.py', ROOT / 'scripts/silicon_buffered_pins.py',
                           ROOT / 'scripts/silicon_power_ports.py', ROOT / 'tooling/silicon/pen-power-check.tcl']
                report['power_grid_routing_question'] = 'Exact existing powered46 PG/OBS with only one original-Lib buf8 launch; no grid regeneration or unrelated resizer moves'
                report['global_rc_optimization'] = 'EXPLICIT_SINGLE_BUFFER_FROM_ACTUAL_ROUTED_PATH'
            elif args.core_power_grid:
                require(previous.get('power_grid') == 'NOT_IMPLEMENTED', 'this first grid integration requires a prior route without PG geometry')
                inputs += [ROOT / 'tooling/silicon/pen-power-grid.tcl', ROOT / 'tooling/silicon/pen-power-check.tcl', ROOT / 'scripts/silicon_power_ports.py']
                if args.protect_sram_power_edges or args.protect_sram_power_geometry:
                    inputs += [ROOT / 'tooling/silicon/pen-power-edge.tcl']
                    report['PG_edge_clearance'] = ('CANDIDATE_ACTUAL_FULL_PG_GEOMETRY_ORIGINAL_PROCESS_CTS_0.42UM' if args.protect_sram_power_geometry else 'CANDIDATE_ORIGINAL_METAL4_0.24UM_SIGNAL_ONLY')
                    if args.protect_sram_power_geometry:
                        inputs += [std / 'lef/sg13g2_tech.lef']
                report['power_grid_routing_question'] = 'Exact retained repaired signal netlist with new grid obstacles; no further ECO' if args.preserve_routed_netlist else 'New actual-SPEF ECO and new grid obstacles'
            require(sha(prior / 'routed.def') == previous['route_enclosure']['routed_def_sha256'], 'original route DEF differs')
            require(sha(prior / 'nom.spef') == previous['extracted_rc']['nom']['spef_sha256'], 'original nominal SPEF differs')
            if not args.two_load_launch_from:
                require((prior / 'route.guide').is_file() and (prior / 'route.guide').stat().st_size > 1000, 'real prior routing guides required to initialize GRT net/grid context')
            report['button_bus_pin_placement'] = previous.get('button_bus_pin_placement', 'UNCONSTRAINED')
            report['routed_eco_from'] = {'path': str(prior), 'receipt_sha256': sha(prior / 'result.json'), 'guides_sha256': None if args.two_load_launch_from else sha(prior / 'route.guide'), 'guide_scope': 'Newly source-bound real prior guide input initializes net/grid context; timing remains original actual SPEF, not guide estimates'}
            if args.preserve_routed_netlist:
                report['routed_eco_from']['guide_scope'] = 'Retained prior source identity only; fresh global routing does not import old guides or run another resizer ECO'
            predecessor_files=('result.json','routed.odb','routed.def','routed.v','routed.sdc','nom.spef')
            if not args.two_load_launch_from: predecessor_files+=('route.guide',)
            else:
                report['predecessor_guides']='Not consumed: exact newpreparedgeometry performs freshGRT. Completedpredecessor has no retainedguidecopy and no oldguide/PA is imported.'
                report['routed_eco_from']['guide_scope']=report['predecessor_guides']
            inputs += [ROOT / 'tooling/silicon/pen-extracted-eco.tcl'] + [prior / name for name in predecessor_files]
        if args.completed_eco_route_from:
            require(args.routed_eco_from is not None, 'completed ECO requires its original source route')
            completed = args.completed_eco_route_from.resolve()
            producer = json.loads((completed / 'result.json').read_text())
            if args.completed_well_fill_route_from:
                from silicon_well_fill_route import completed_route_inputs
                relation,closed_inputs,historical=completed_route_inputs(completed)
                inputs+=closed_inputs
                report['completed_well_serialization_relation']=relation
                report['padded_hold_preparation']=producer['padded_hold_preparation']
                report['master_geometry_scope']='Pinned inputODB+originalGDSmasterbinding; final names/transformedITerms/PG/ports only. IndependentfullfinaldbMasterbody/propertyseal andfullLVS remain unfinished.'
                report['original_observer_archive_binding']=historical
            else:
                require(producer['status'] == 'FAIL' and producer['source_seal_equal'] and
                        producer.get('error') == "GeometryError('ECO changed admitted timing constraints')", 'only the retained timestamp observer failure may continue')
            require(producer['mapping_receipt']['sha256'] == sha(mapping / 'result.json') and
                    producer['routed_eco_from']['receipt_sha256'] == sha(prior / 'result.json'), 'completed ECO producer differs')
            require(sdc_commands(completed / 'pre-eco.sdc') == sdc_commands(completed / 'routed.sdc') == sdc_commands(prior / 'routed.sdc'), 'actual ECO timing commands differ')
            retained = ('routed.odb', 'routed.def', 'routed.v', 'routed.sdc', 'pre-eco.v', 'pre-eco.sdc',
                        'post-eco-unrouted.v', 'layout-summary.json', 'router-drc-count.txt', 'setup-summary.rpt',
                        'hold-summary.rpt', 'actual-pre-eco-setup.rpt', 'actual-pre-eco-hold.rpt')
            if args.completed_well_fill_route_from:
                retained+=tuple(name for name in('setup.rpt','hold.rpt','unconstrained.rpt','constraints.rpt','electrical.rpt',
                    'global-setup.rpt','global-hold.rpt','global-setup-summary.rpt','global-hold-summary.rpt','global-electrical.rpt',
                    'power-grid-before-route.json','power-grid-after-route.json','power-connected.v',
                    'power-all-terminals-before-route.tsv','power-all-terminals-after-route.tsv',
                    'power-macro-before-route.tsv','power-macro-after-route.tsv')if name not in retained)
            inputs += [completed / 'result.json'] + [completed / name for name in retained]
            for name in retained:
                shutil.copyfile(completed / name, out / name)
            report['reused_completed_route'] = {'path': str(completed), 'receipt_sha256': sha(completed / 'result.json'),
                                              'scope': 'Original failed producer remains FAIL; completed routing/global estimates reused. Current source-aware observer, fresh actual3RC and available corners are separate; no reroute.'}
        if args.completed_power_grid_route_from:
            completed = args.completed_power_grid_route_from.resolve()
            producer = json.loads((completed / 'result.json').read_text())
            require(producer['status'] == 'FAIL' and producer['source_seal_equal'] and
                    producer.get('error') == "GeometryError('power-grid rerouting changed the retained signal netlist')",
                    'only the retained three-PG-port observer failure may continue')
            require(producer['mapping_receipt']['sha256'] == sha(mapping / 'result.json') and
                    producer['routed_eco_from']['receipt_sha256'] == sha(prior / 'result.json') and
                    producer.get('power_grid') == 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' and
                    producer.get('router_capacity_underflow') == 'NOT_OBSERVED_IN_THIS_EXECUTION', 'completed grid source differs')
            retained = ('routed.odb', 'routed.def', 'routed.v', 'routed.sdc', 'pre-eco.v', 'pre-eco.sdc',
                        'post-eco-unrouted.v', 'layout-summary.json', 'router-drc-count.txt', 'route.drc', 'route.guide',
                        'setup-summary.rpt', 'hold-summary.rpt', 'actual-pre-eco-setup.rpt', 'actual-pre-eco-hold.rpt',
                        'power-connected.v', 'power-grid-before-route.json', 'power-grid-after-route.json')
            inputs += [completed / 'result.json'] + [completed / name for name in retained]
            for name in retained:
                shutil.copyfile(completed / name, out / name)
            report['reused_completed_route'] = {'path': str(completed), 'receipt_sha256': sha(completed / 'result.json'),
                'scope': 'Exact completed grid routing reused; new required-PG-port observation and fresh3RC extraction, not fresh routing'}
        inputs += [std / 'lib/sg13g2_stdcell_typ_1p20V_25C.lib', macro / 'lib' / (MACRO+'_typ_1p20V_25C.lib')]
        require_unmodified_routing_resources([path for path in inputs if path.suffix == '.tcl'])
        # Historical source archives keep their original report behavior. This
        # guard binds the maintained scripts used by a new route, not a newly
        # invented requirement for already completed retained geometry.
        require_iteration_drc_reports([ROOT / 'tooling/silicon/layout.tcl',
                                       ROOT / 'tooling/silicon/pen-extracted-eco.tcl'])
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
        if (args.acceptance_launch_buffer or args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from)) and not args.completed_well_fill_route_from:
            if args.acceptance_launch_buffer:
                proof = out / 'launch-prepare.py'
                proof.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom silicon_acceptance_launch import prepare\nprepare(Path({str(prior/"routed.odb")!r}), Path({str(std/"lib/sg13g2_stdcell_typ_1p20V_25C.lib")!r}), Path({str(out/"launch")!r}))\n')
                invoke([str(openroad), '-python', '-exit', str(proof)], 'launch-prepare', 20)
                report['launch_preparation'] = json.loads((out / 'launch/result.json').read_text())
                prepared_geometry = out / 'launch/unrouted.odb'
                prepared_def = out / 'launch/unrouted.def'
            else:
                module = ('silicon_two_load_launch'if args.two_load_launch_from else'silicon_well_fill_route'if args.well_fill_from else'silicon_decode_launch' if args.decode_launch_buffer_from else 'silicon_slew_launch' if (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from) else 'silicon_power_margin_route' if args.power_margin_from else 'silicon_capacity_launch' if args.capacity_launch_buffer_from else
                          'silicon_control_launch' if args.control_launch_buffer_from else 'silicon_sram_input_hold')
                proof = out / 'padded-hold-prepare.py'
                proof.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom {module} import assess\nassess(Path({str(prior/"routed.odb")!r}), Path({str(prepared_geometry)!r}), Path({str(std/"lib/sg13g2_stdcell_typ_1p20V_25C.lib")!r}), Path({str(out/"padded-hold-preparation.json")!r}))\n')
                invoke([str(openroad), '-python', '-exit', str(proof)], 'padded-hold-prepare', 40 if args.two_load_launch_from else 30 if args.well_fill_from else 20)
                report['padded_hold_preparation'] = json.loads((out / 'padded-hold-preparation.json').read_text())
                prepared_def = (prepared_base_geometry if args.preferred_access_from else prepared_geometry).with_suffix('.def')
            report['launch_pre_route_vias'] = audit(out / 'enclosure/repaired-original.lef', prepared_def, allow_generated=True)
            require(report['launch_pre_route_vias']['status'].startswith('PASS_'), 'launch pre-route fixed/generated via geometry fails')
            baseline = out / 'launch-baseline.tcl'
            baseline.write_text(f'''set_thread_count 1
read_liberty {{{std/'lib/sg13g2_stdcell_typ_1p20V_25C.lib'}}}
read_liberty {{{macro/'lib'/(MACRO+'_typ_1p20V_25C.lib')}}}
read_db {{{prior/'routed.odb'}}}
read_sdc {{{prior/'routed.sdc'}}}
set_propagated_clock [get_clocks core]
read_spef {{{prior/'nom.spef'}}}
write_verilog {{{out/'pre-eco.v'}}}
write_sdc {{{out/'pre-eco.sdc'}}}
report_worst_slack -max -digits 6 > {{{out/'actual-pre-eco-setup.rpt'}}}
report_worst_slack -min -digits 6 > {{{out/'actual-pre-eco-hold.rpt'}}}
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > {{{out/'actual-pre-eco-electrical.rpt'}}}
''')
            invoke([str(openroad), '-no_init', '-exit', str(baseline)], 'launch-baseline', 15)
            from silicon_power_ports import signal_bytes
            # read_db reclassifies the existing PG BTerms; the default logical
            # export then omits exactly their three declarations/header names.
            # Actual all668 physical ports/PG geometry are checked separately.
            expected_baseline = ((prior / 'routed.v').read_text() if (args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from))
                                 else signal_bytes((prior / 'routed.v').read_text()))
            require((out / 'pre-eco.v').read_text() == expected_baseline,
                    'powered source export changed more than the exact three PG declarations')
            require(sdc_commands(out / 'pre-eco.sdc') == sdc_commands(prior / 'routed.sdc'),
                    'launch baseline changed an original timing command')
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
set group_button_bus {1 if report['button_bus_pin_placement'] == 'FULL64_ORDERED_TOP_EDGE' else 0}
set button_pin_script {{{ROOT/"tooling/silicon/pen-button-pins.tcl"}}}
set defer_global_eco {1 if args.defer_global_eco else 0}
set validation_region_script {{{ROOT/"tooling/silicon/pen-validation-region.tcl"}}}
set validation_region_check_script {{{ROOT/"tooling/silicon/pen-validation-check.tcl"}}}
source {{{ROOT/'tooling/silicon/layout.tcl'}}}
''')
        if args.routed_eco_from:
            script.write_text(f'set prior {{{prior}}}\nset out {{{out}}}\nset pdk {{{std}}}\nset macro_lib {{{macro/"lib"/(MACRO+"_typ_1p20V_25C.lib")}}}\nset validation_region_check_script {{{ROOT/"tooling/silicon/pen-validation-check.tcl"}}}\nset group_button_bus {1 if report['button_bus_pin_placement'] == 'FULL64_ORDERED_TOP_EDGE' else 0}\nset button_pin_script {{{ROOT/"tooling/silicon/pen-button-pins.tcl"}}}\nsource {{{ROOT/"tooling/silicon/pen-extracted-eco.tcl"}}}\n')
            script.write_text(f'set clock_min_routing_layer {args.clock_min_routing_layer}\n' + script.read_text())
            if args.preferred_access_from:
                script.write_text(f'set retained_access_guides {{{preferred["guides"]}}}\nset retained_access_metadata {{{preferred["metadata"]}}}\nset retained_access_exporter {{{preferred["exporter"]}}}\nset retained_access_writer_check {{{ROOT/"scripts/silicon_access_writer.py"}}}\nset retained_access_python {{{sys.executable}}}\nset preferred_access_probe_only {1 if args.preferred_access_preflight_only else 0}\n' + script.read_text())
            if args.power_margin_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
                script.write_text('set power_margin_prepared 1\n'+script.read_text())
            if args.core_power_grid:
                script.write_text(f'set core_power_grid 1\nset preserve_routed_netlist {1 if args.preserve_routed_netlist else 0}\nset power_grid_script {{{grid_source}}}\nset power_check_script {{{ROOT/"tooling/silicon/pen-power-check.tcl"}}}\n' + script.read_text())
            if args.acceptance_launch_buffer or args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
                script.write_text(f'set prepared_physical_db {{{prepared_geometry}}}\nset existing_core_power_grid 1\nset prepared_physical_question {{{report["power_grid_routing_question"]}}}\n' + script.read_text())
        if args.protect_sram_power_edges:
            script.write_text(f'set power_edge_script {{{ROOT/"tooling/silicon/pen-power-edge.tcl"}}}\n' + script.read_text())
        if args.protect_sram_power_geometry:
            script.write_text(f'set power_geometry_script {{{ROOT/"tooling/silicon/pen-power-edge.tcl"}}}\n' + script.read_text())
        if args.fresh_core_power_grid:
            script.write_text(f'set fresh_power_script {{{ROOT/"tooling/silicon/pen-fresh-power.tcl"}}}\nset power_grid_script {{{grid_source}}}\nset power_check_script {{{ROOT/"tooling/silicon/pen-power-check.tcl"}}}\n' + script.read_text())
        # Preserve the real failed database, including GRT's stored overflow
        # grid, before Tcl propagates an implementation error. A snapshot is
        # diagnostic state only and never a completed routed layout.
        if args.routed_eco_from:
            script.write_text(f'set detail_route_iterations {args.detail_route_iterations}\n' + script.read_text())
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
        if args.completed_fresh_grid_route_from:
            finalize = out / 'finalize-completed.tcl'
            finalize.write_text(f'''set_thread_count 1
read_liberty {{{std/'lib/sg13g2_stdcell_typ_1p20V_25C.lib'}}}
read_liberty {{{macro/'lib'/(MACRO+'_typ_1p20V_25C.lib')}}}
read_db {{{out/'failed-layout.odb'}}}
read_sdc {{{out/'pre-power/routed.sdc'}}}
write_db {{{out/'routed.odb'}}}
write_def {{{out/'routed.def'}}}
write_verilog {{{out/'routed.v'}}}
write_verilog -include_pwr_gnd {{{out/'power-connected.v'}}}
write_sdc {{{out/'routed.sdc'}}}
''')
            invoke([str(openroad), '-no_init', '-exit', str(finalize)], 'finalize-completed', 15)
        if not (args.completed_eco_route_from or args.completed_power_grid_route_from or args.completed_fresh_grid_route_from):
            invoke([str(openroad), '-no_init', '-exit', str(script)], 'layout', 900)
            if args.preferred_access_preflight_only:
                require((out / 'preferred-prefix-ready.txt').read_text().strip() == 'EXACT_RETAINED_ACCESS_GUIDES_POWER_PREFIX_NO_DRT', 'actual retained prefix did not finish')
                require((out / 'preferred-before-route.json').read_bytes() == preferred['metadata'].read_bytes(), 'actual loaded AP metadata differs')
                require(not (out / 'router-drc-count.txt').exists(), 'prefix unexpectedly entered detailed routing')
                raise PrefixComplete()
        if not (args.completed_eco_route_from or args.completed_power_grid_route_from or args.completed_fresh_grid_route_from):
            require_no_capacity_underflow((out / 'layout.log').read_text())
        require((out / 'routed.def').is_file(), 'no completed route')
        if args.fresh_core_power_grid:
            proof = out / 'buffered-endpoints.py'
            proof.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom silicon_buffered_pins import assess\nassess(Path({str(out/"post-power/routed.odb")!r}), Path({str(out/"routed.odb")!r}), Path({str(std/"lib/sg13g2_stdcell_typ_1p20V_25C.lib")!r}), Path({str(out/"buffered-endpoints.json")!r}))\n')
            invoke([str(openroad), '-python', '-exit', str(proof)], 'buffered-endpoints', 15)
            report['buffered_endpoints'] = json.loads((out / 'buffered-endpoints.json').read_text())
            pg = out / 'final-power-grid.tcl'
            pg.write_text(f'''set_thread_count 1
read_liberty {{{std/'lib/sg13g2_stdcell_typ_1p20V_25C.lib'}}}
read_liberty {{{macro/'lib'/(MACRO+'_typ_1p20V_25C.lib')}}}
read_db {{{out/'routed.odb'}}}
set out {{{out}}}
source {{{ROOT/'tooling/silicon/pen-power-check.tcl'}}}
# Every original endpoint/BIST/PG identity has already passed the independent
# source-Lib buffered-input proof. Check actual final three-net geometry now.
set qualified_bindings [lemma_macro_bindings $out/power-final-qualified-bindings.tsv]
lemma_check_power_grid $qualified_bindings $out after-route
''')
            invoke([str(openroad), '-no_init', '-exit', str(pg)], 'final-power-grid', 15)
            observer = out / 'power-interface.py'
            observer.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom silicon_power_ports import assess\nassess(Path({str(out/"pre-power")!r}), Path({str(out/"post-power")!r}), Path({str(out/"power-interface.json")!r}))\n')
            invoke([str(openroad), '-python', '-exit', str(observer)], 'power-interface', 15)
            report['power_interface'] = json.loads((out / 'power-interface.json').read_text())
            report['power_interface']['stage'] = 'Exact fresh placement immediately before/after PG addition; final endpoint geometry independently checked in Tcl, normal subsequent resizer changes retained'
            require(sdc_commands(out / 'pre-power/routed.sdc') == sdc_commands(out / 'routed.sdc'), 'fresh grid changed original timing commands')
        if args.routed_eco_from:
            if args.acceptance_launch_buffer or args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
                from silicon_power_ports import signal_bytes
                expected_baseline = ((prior / 'routed.v').read_text() if (args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from))
                                     else signal_bytes((prior / 'routed.v').read_text()))
                require((out / 'pre-eco.v').read_text() == expected_baseline,
                        'launch baseline changed source logical netlist')
            else:
                require(sha(out / 'pre-eco.v') == sha(prior / 'routed.v'), 'ECO database logical netlist differs from declared source route')
            if args.acceptance_launch_buffer:
                proof = out / 'launch-endpoints.py'
                proof.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom silicon_acceptance_launch import assess\nassess(Path({str(prior/"routed.odb")!r}), Path({str(out/"routed.odb")!r}), Path({str(std/"lib/sg13g2_stdcell_typ_1p20V_25C.lib")!r}), Path({str(out/"launch-endpoints.json")!r}))\n')
                invoke([str(openroad), '-python', '-exit', str(proof)], 'launch-endpoints', 15)
                report['launch_endpoints'] = json.loads((out / 'launch-endpoints.json').read_text())
                require(sha(out / 'pre-eco.v') != sha(out / 'post-eco-unrouted.v') and
                        sha(out / 'post-eco-unrouted.v') == sha(out / 'routed.v'), 'launch route changed another logical cell/net')
            elif args.padded_sram_input_delay_from or args.control_launch_buffer_from or args.capacity_launch_buffer_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
                module = ('silicon_two_load_launch'if args.two_load_launch_from else'silicon_well_fill_route'if args.well_fill_from else'silicon_decode_launch' if args.decode_launch_buffer_from else 'silicon_slew_launch' if (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from) else 'silicon_power_margin_route' if args.power_margin_from else 'silicon_capacity_launch' if args.capacity_launch_buffer_from else
                          'silicon_control_launch' if args.control_launch_buffer_from else 'silicon_sram_input_hold')
                proof = out / 'padded-hold-endpoints.py'
                proof.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom {module} import assess\nassess(Path({str(prior/"routed.odb")!r}), Path({str(out/"routed.odb")!r}), Path({str(std/"lib/sg13g2_stdcell_typ_1p20V_25C.lib")!r}), Path({str(out/"padded-hold-endpoints.json")!r}), fixed_geometry=Path({str(prepared_base_geometry if args.preferred_access_from else prepared_geometry)!r}))\n')
                if args.completed_well_fill_route_from:
                    report['padded_hold_endpoints']=producer['padded_hold_endpoints']
                    report['padded_hold_endpoint_scope']='Original24.404s actual pins/PG/port/functionalpadding component reused on exactsame5c43routedODB; no fresh native execution or fullmasterbodyseal'
                else:
                    invoke([str(openroad), '-python', '-exit', str(proof)], 'padded-hold-endpoints', 40 if args.two_load_launch_from else 30 if args.well_fill_from else 20)
                    report['padded_hold_endpoints'] = json.loads((out / 'padded-hold-endpoints.json').read_text())
                if args.well_fill_from:
                    from silicon_well_fill_route import spacer_serialization
                    cdl=std/'cdl/sg13g2_stdcell.cdl'
                    report['well_spacer_serialization']=spacer_serialization((out/'pre-eco.v').read_text(),
                        (out/'post-eco-unrouted.v').read_text(),json.loads((args.well_fill_from/'row-plan.json').read_text()),cdl.read_text())
                    require(sha(out/'post-eco-unrouted.v')==sha(out/'routed.v'),'routing changed physical/functional source netlist')
                else:
                    require(sha(out / 'pre-eco.v') != sha(out / 'post-eco-unrouted.v') and
                        sha(out / 'post-eco-unrouted.v') == sha(out / 'routed.v'), 'padded hold routing changed another cell/net')
            elif args.preserve_routed_netlist:
                require(sha(out / 'pre-eco.v') == sha(out / 'post-eco-unrouted.v'), 'power-grid integration changed prior repaired cells/nets')
                observer = out / 'power-interface.py'
                observer.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0, {str(ROOT/"scripts")!r})\nfrom silicon_power_ports import assess\nassess(Path({str(prior)!r}), Path({str(out)!r}), Path({str(out/"power-interface.json")!r}))\n')
                invoke([str(openroad), '-python', '-exit', str(observer)], 'power-interface', 15)
                report['power_interface'] = json.loads((out / 'power-interface.json').read_text())
            else:
                require(sha(out / 'pre-eco.v') != sha(out / 'post-eco-unrouted.v'), 'ECO made no physical netlist change')
            require(sdc_commands(out / 'pre-eco.sdc') == sdc_commands(out / 'routed.sdc') == sdc_commands(prior / 'routed.sdc'), 'ECO changed admitted timing commands')
            report['eco_netlist'] = {name: sha(out / name) for name in ('pre-eco.v', 'post-eco-unrouted.v', 'routed.v', 'pre-eco.sdc', 'routed.sdc')}
            report['eco_netlist']['pre_setup'] = (out / 'actual-pre-eco-setup.rpt').read_text().strip()
            report['eco_netlist']['pre_hold'] = (out / 'actual-pre-eco-hold.rpt').read_text().strip()
        if args.preferred_access_from:
            from silicon_preferred_route import check_final_access
            report['retained_preferred_access']['actual_final_relation'] = check_final_access(out, preferred)
        if args.power_margin_from or (args.slew_launch_buffer_from or args.decode_launch_buffer_from or args.well_fill_from or args.two_load_launch_from):
            guard=out/'native-power-margin.py'
            guard.write_text(f'import sys\nfrom pathlib import Path\nsys.path.insert(0,{str(ROOT/"scripts")!r})\nfrom silicon_power_clearance import check\ncheck(Path({str(out/"routed.odb")!r}),Path({str(out/"enclosure/repaired-original.lef")!r}),Path({str(out/"native-power-margin.json")!r}))\n')
            invoke([str(openroad),'-python','-exit',str(guard)],'native-power-margin',45)
            report['native_power_margin']['actual_final_relation']=json.loads((out/'native-power-margin.json').read_text())
            require(report['native_power_margin']['actual_final_relation']['status']in ('PASS_ACTUAL_NATIVE420NM_RECTANGLE_SUBSET_ONLY','FAIL_NATIVE420NM_RECTANGLE_MARGIN'),'native margin observer did not complete; physical failures remain recorded while actual PEX continues')
        report['router_drc'] = router_drc((out / 'router-drc-count.txt').read_text())
        report['global_rc_after_route'] = ({'status': 'NOT_ASSESSED', 'scope': 'Original producer failed its endpoint observer after detailed routing; no post-route global RC report was retained. Fresh actual extracted RC follows.'}
            if args.completed_fresh_grid_route_from else layout_reports(out))
        if args.preferred_access_from:
            report['global_rc_after_route'] = {'status': 'UNADMITTED_IMPORTED_GUIDES_RC_OBSERVER',
                'scope': 'read_guides preserves actual DRT guide/AP inputs but does not reconstruct every GRT-estimator terminal route. Raw reports retained; no fresh global-RC timing claim. Actual routed extraction follows.',
                'missing_terminal_route_warnings': (out / 'layout.log').read_text().count('EST-0026'),
                'raw_unadmitted_reports': report['global_rc_after_route']}
        report['route_enclosure'] = audit(out / 'enclosure/repaired-original.lef', out / 'routed.def', allow_generated=args.core_power_grid)
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
    except PrefixComplete:
        report.update(status='PASS_RETAINED_ORIGINAL_GUIDES_AP_POWER_PREFIX_ONLY_NO_DRT', prefix_only=True)
    except BaseException as error:
        report.update(status='FAIL', error=repr(error))
    finally:
        grid_reports = {}
        for stage in ('before-route', 'after-route'):
            path = out / ('power-grid-' + stage + '.json')
            if path.is_file():
                try:
                    grid_reports[stage] = json.loads(path.read_text())
                except (OSError, ValueError) as error:
                    report.update(status='FAIL', power_grid_report_error=repr(error))
        if grid_reports:
            report['core_power_grid'] = grid_reports
            report['power_grid'] = 'CONNECTED_CORE_GRID_ONLY_NO_IR_EM' if 'after-route' in grid_reports else 'GRID_CONNECTED_BEFORE_ROUTE_ONLY'
            report['power_grid_limits'] = ['provisional widths/pitch require real current/IR/EM closure',
                'no chip ring: original5um margin cannot fit three supplies',
                'BIST bindings preserved but still tiedoff, no usable manufacturing test path',
                'independent simple geometry checks do not establish full process DRC/LVS',
                'no power sequencing, power gating, pads/package/board qualification']
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
    if args.preferred_access_preflight_only:
        return 0 if report['status'] == 'PASS_RETAINED_ORIGINAL_GUIDES_AP_POWER_PREFIX_ONLY_NO_DRT' and report['source_seal_equal'] else 1
    return 0 if (report.get('router_drc', {}).get('violations') == 0 and
                 (not args.power_margin_from or report.get('native_power_margin',{}).get('actual_final_relation',{}).get('status')=='PASS_ACTUAL_NATIVE420NM_RECTANGLE_SUBSET_ONLY') and
                 report.get('route_enclosure', {}).get('status', '').startswith('PASS_') and
                 report.get('physical_closure') == 'QUALIFIED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
