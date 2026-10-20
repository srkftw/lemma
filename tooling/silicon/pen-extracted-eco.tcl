# SPDX-License-Identifier: Apache-2.0
# One bounded physical ECO against the retained actual nominal route SPEF.
# All clock/IO/uncertainty/library limits come from the unchanged original SDC.
set_thread_count 4
read_liberty $pdk/lib/sg13g2_stdcell_typ_1p20V_25C.lib
read_liberty $macro_lib
if {[info exists prepared_physical_db]} {
    # The old actual-SPEF baseline is reported in a separate unchanged database.
    # Never attach its old loads to this newly connected launch net.
    read_db $prepared_physical_db
} else {
    read_db $prior/routed.odb
}
set power_grid_state NOT_IMPLEMENTED
if {[info exists group_button_bus] && $group_button_bus == 1} {
    source $button_pin_script
    lemma_check_button_pins
}
read_sdc $prior/routed.sdc
set validation_group [[ord::get_db_block] findGroup pen_validation_middle]
if {$validation_group != "NULL"} {source $validation_region_check_script}
set_layer_rc -layer Metal2 -resistance 2.53519e-03 -capacitance 1.69121e-04
set_layer_rc -layer Metal3 -resistance 1.54329e-03 -capacitance 1.82832e-04
set_layer_rc -layer Metal4 -resistance 6.31424e-04 -capacitance 1.66454e-04
set_layer_rc -layer Metal5 -resistance 6.84051e-04 -capacitance 8.57431e-05
set_wire_rc -signal -layer Metal2
set_wire_rc -clock -layer Metal5
set_propagated_clock [get_clocks core]
# read_db/read_spef do not initialize GRT's net/pin grid objects. Both
# SwapPinsMove and BufferMove dereferenced that absent context in retained
# negative runs. Restore real routing guides through the supported API first;
# the following read_spef still supplies actual loads, not guide estimates.
if {![info exists clock_min_routing_layer]} {set clock_min_routing_layer Metal2}
if {$clock_min_routing_layer ni {Metal2 Metal3}} {error "Unadmitted clock routing floor"}
set_routing_layers -signal Metal2-Metal5 -clock ${clock_min_routing_layer}-Metal5
if {![info exists prepared_physical_db] && (![info exists preserve_routed_netlist] || $preserve_routed_netlist != 1)} {
    read_guides $prior/route.guide
}
if {![info exists prepared_physical_db]} {
    write_verilog $out/pre-eco.v
    write_sdc $out/pre-eco.sdc
    read_spef $prior/nom.spef
    report_worst_slack -max -digits 6 > $out/actual-pre-eco-setup.rpt
    report_worst_slack -min -digits 6 > $out/actual-pre-eco-hold.rpt
    report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $out/actual-pre-eco-electrical.rpt
}
# Unlike the historical flow, these repairs begin from actual extracted loads.
if {[info exists prepared_physical_db]} {
    puts $prepared_physical_question
} elseif {![info exists preserve_routed_netlist] || $preserve_routed_netlist != 1} {
    repair_design -slew_margin 5 -cap_margin 5
    repair_timing -setup -phases WNS_PATH -setup_margin 0.25 -max_passes 2 -max_iterations 50 -max_buffer_percent 20
    repair_timing -hold -hold_margin 0.03 -max_passes 2 -max_iterations 50 -max_buffer_percent 20
    detailed_placement
} else {
    # A new real PG obstacle set is the changed input. Keep the exact already
    # repaired cells/nets and every timing endpoint; this is no additional ECO.
    puts "Retaining exact prior repaired netlist for real core-grid routing"
}
check_placement -verbose
if {[info exists group_button_bus] && $group_button_bus == 1} {lemma_check_button_pins}
if {$validation_group != "NULL"} {source $validation_region_check_script}
write_verilog $out/post-eco-unrouted.v
# Every signal is freshly routed and then independently re-extracted. An old
# detailed wire may not stand in for the connectivity of a changed buffer/net.
foreach net [[ord::get_db_block] getNets] {
    set wire [$net getWire]
    if {$wire != "NULL"} {odb::dbWire_destroy $wire}
}
if {[info exists core_power_grid] && $core_power_grid == 1} {
    source $power_check_script
    set power_bindings_before [lemma_macro_bindings $out/power-macro-before.tsv]
    if {![info exists existing_core_power_grid] || $existing_core_power_grid != 1} {
        source $power_grid_script
    }
    lemma_check_power_grid $power_bindings_before $out before-route
    set power_grid_state CONNECTED_CORE_GRID_ONLY_NO_IR_EM
    write_db $out/power-grid-before-route.odb
    write_def $out/power-grid-before-route.def
    write_verilog -include_pwr_gnd $out/power-connected.v
    if {[info exists power_edge_script]} {
        source $power_edge_script
        set power_edge_clearance [lemma_add_power_edge_clearance $out]
        lemma_check_power_edge_clearance $power_edge_clearance
    }
    if {[info exists power_geometry_script]} {
        source $power_geometry_script
        set power_geometry_clearance [lemma_add_power_geometry_clearance $out $prior/routed.def $pdk/lef/sg13g2_tech.lef]
        lemma_check_power_geometry_clearance $power_geometry_clearance
        write_db $out/power-geometry-before-route.odb
        write_def $out/power-geometry-before-route.def
    }
}
set_routing_layers -signal Metal2-Metal5 -clock ${clock_min_routing_layer}-Metal5
if {[info exists retained_access_guides]} {
    read_guides $retained_access_guides
    file copy $retained_access_guides $out/route.guide
    puts "Retaining exact qualified clock-M3 guides and original baseline pin access"
} else {
    global_route -guide_file $out/route.guide -congestion_iterations 50 -congestion_report_file $out/global-congestion.rpt -verbose
}
write_db $out/global-route.odb
write_def $out/global-route.def
estimate_parasitics -global_routing -spef_file $out/global-route-estimated.spef
report_checks -path_delay max -group_path_count 10 -digits 6 > $out/global-setup.rpt
report_checks -path_delay min -group_path_count 10 -digits 6 > $out/global-hold.rpt
report_worst_slack -max -digits 6 > $out/global-setup-summary.rpt
report_worst_slack -min -digits 6 > $out/global-hold-summary.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $out/global-electrical.rpt
if {![info exists detail_route_iterations]} {set detail_route_iterations 3}
if {$detail_route_iterations ni {3 8}} {error "Unadmitted detailed-route repair bound"}
# Retain real intermediate net/rule markers even when the original hard route
# deadline expires before the final report. Reporting does not extend routing.
set retained_access_route_flags {}
if {[info exists retained_access_guides]} {
    load $retained_access_exporter Lemmaap
    proc lemma_check_retained_access {stage} {
        global out retained_access_metadata
        write_db $out/preferred-$stage.odb
        lemma_ap_export $out/preferred-$stage.odb $out/preferred-$stage.json
        set file [open $retained_access_metadata rb]
        set expected [read $file]
        close $file
        set file [open $out/preferred-$stage.json rb]
        set actual [read $file]
        close $file
        if {$expected ne $actual} {error "Retained original AP metadata/pattern/preference changed"}
    }
    lemma_check_retained_access before-route
    lappend retained_access_route_flags -no_pin_access
    file mkdir $out/route-snapshots
    set_debug_level DRT snapshot 1
    detailed_route_debug -snapshot_dir $out/route-snapshots
    if {[info exists preferred_access_probe_only] && $preferred_access_probe_only == 1} {
        set file [open $out/preferred-prefix-ready.txt w]
        puts $file "EXACT_RETAINED_ACCESS_GUIDES_POWER_PREFIX_NO_DRT"
        close $file
        return
    }
}
detailed_route {*}$retained_access_route_flags -output_drc $out/route.drc -drc_report_iter_step 1 -output_maze $out/route.maze -droute_end_iter $detail_route_iterations -verbose 1
if {[info exists retained_access_guides]} {lemma_check_retained_access after-route}
if {[info exists core_power_grid] && $core_power_grid == 1} {
    global_connect
    lemma_check_power_grid $power_bindings_before $out after-route
    if {[info exists power_edge_clearance]} {lemma_check_power_edge_clearance $power_edge_clearance}
    if {[info exists power_geometry_clearance]} {lemma_check_power_geometry_clearance $power_geometry_clearance}
}
set file [open $out/router-drc-count.txt w]
puts $file [detailed_route_num_drvs]
close $file
estimate_parasitics -global_routing
report_checks -path_delay max -group_path_count 10 -digits 6 > $out/setup.rpt
report_checks -path_delay min -group_path_count 10 -digits 6 > $out/hold.rpt
report_checks -unconstrained -digits 6 > $out/unconstrained.rpt
check_setup -verbose > $out/constraints.rpt
report_worst_slack -max -digits 6 > $out/setup-summary.rpt
report_worst_slack -min -digits 6 > $out/hold-summary.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $out/electrical.rpt
write_db $out/routed.odb
write_def $out/routed.def
write_verilog $out/routed.v
write_sdc $out/routed.sdc
set block [ord::get_db_block]
set cell_area 0.0
foreach inst [$block getInsts] {
    set master [$inst getMaster]
    set cell_area [expr {$cell_area + [$master getWidth] * [$master getHeight]}]
}
set units [$block getDbUnitsPerMicron]
set cell_area [expr {$cell_area / ($units * $units)}]
set core [$block getCoreArea]
set core_area [expr {[$core dx] * [$core dy] / double($units * $units)}]
set file [open $out/layout-summary.json w]
puts $file "{\"cell_area_um2\": $cell_area, \"core_area_um2\": $core_area, \"utilization_percent\": [expr {100.0 * $cell_area / $core_area}], \"instances\": [llength [$block getInsts]], \"clock_period_ns\": 10, \"timing_model\": \"global-route RC estimate after fresh ECO detailed signal routing\", \"power_grid\": \"$power_grid_state\", \"process_drc\": \"NOT_RUN\", \"lvs\": \"NOT_RUN\"}"
close $file
