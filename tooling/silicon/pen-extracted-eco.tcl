# SPDX-License-Identifier: Apache-2.0
# One bounded physical ECO against the retained actual nominal route SPEF.
# All clock/IO/uncertainty/library limits come from the unchanged original SDC.
set_thread_count 4
read_liberty $pdk/lib/sg13g2_stdcell_typ_1p20V_25C.lib
read_liberty $macro_lib
read_db $prior/routed.odb
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
write_verilog $out/pre-eco.v
write_sdc $out/pre-eco.sdc
read_spef $prior/nom.spef
report_worst_slack -max -digits 6 > $out/actual-pre-eco-setup.rpt
report_worst_slack -min -digits 6 > $out/actual-pre-eco-hold.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $out/actual-pre-eco-electrical.rpt
# Unlike the historical flow, these repairs begin from actual extracted loads.
repair_design -slew_margin 5 -cap_margin 5
repair_timing -setup -phases WNS_PATH -setup_margin 0.25 -max_passes 2 -max_iterations 50 -max_buffer_percent 20
repair_timing -hold -hold_margin 0.03 -max_passes 2 -max_iterations 50 -max_buffer_percent 20
detailed_placement
check_placement -verbose
if {$validation_group != "NULL"} {source $validation_region_check_script}
write_verilog $out/post-eco-unrouted.v
# Every signal is freshly routed and then independently re-extracted. An old
# detailed wire may not stand in for the connectivity of a changed buffer/net.
foreach net [[ord::get_db_block] getNets] {
    set wire [$net getWire]
    if {$wire != "NULL"} {odb::dbWire_destroy $wire}
}
set_routing_layers -signal Metal2-Metal5 -clock Metal2-Metal5
global_route -guide_file $out/route.guide -congestion_iterations 50 -congestion_report_file $out/global-congestion.rpt -verbose
write_db $out/global-route.odb
write_def $out/global-route.def
estimate_parasitics -global_routing -spef_file $out/global-route-estimated.spef
report_checks -path_delay max -group_path_count 10 -digits 6 > $out/global-setup.rpt
report_checks -path_delay min -group_path_count 10 -digits 6 > $out/global-hold.rpt
report_worst_slack -max -digits 6 > $out/global-setup-summary.rpt
report_worst_slack -min -digits 6 > $out/global-hold-summary.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $out/global-electrical.rpt
detailed_route -output_drc $out/route.drc -output_maze $out/route.maze -droute_end_iter 3 -verbose 1
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
puts $file "{\"cell_area_um2\": $cell_area, \"core_area_um2\": $core_area, \"utilization_percent\": [expr {100.0 * $cell_area / $core_area}], \"instances\": [llength [$block getInsts]], \"clock_period_ns\": 10, \"timing_model\": \"global-route RC estimate after fresh ECO detailed signal routing\", \"power_grid\": \"NOT_IMPLEMENTED\", \"process_drc\": \"NOT_RUN\", \"lvs\": \"NOT_RUN\"}"
close $file
