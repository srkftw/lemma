# SPDX-License-Identifier: Apache-2.0
# Signal-routing feasibility only, typical standard-cell corner.
# No SRAM, pad ring, power-grid closure, GDS, process DRC or LVS claim.
set_thread_count 4
read_lef $pdk/lef/sg13g2_tech.lef
read_lef $pdk/lef/sg13g2_stdcell.lef
read_liberty $pdk/lib/sg13g2_stdcell_typ_1p20V_25C.lib
read_verilog $out/mapped.v
link_design $top
# OpenSTA creates logical one_/zero_ nets for unused Verilog don't-care
# aliases. TritonRoute rejects these POWER/GROUND nets even with no pins.
# Remove only proven unconnected aliases; a connected constant needs a real
# tie-cell implementation and must fail instead of being silently deleted.
foreach name {zero_ one_} {
    set net [[ord::get_db_block] findNet $name]
    if {$net != "NULL" && [$net getSigType] in {POWER GROUND}} {
        if {[llength [$net getITerms]] || [llength [$net getBTerms]]} {
            error "Connected logical constant $name requires a physical tie cell"
        }
        puts "Removing unconnected logical constant alias $name"
        odb::dbNet_destroy $net
    }
}
initialize_floorplan -utilization 25 -aspect_ratio 1 -core_space 5 -site CoreSite
foreach layer {Metal1 Metal2 Metal3 Metal4 Metal5} {
    make_tracks $layer -x_offset 0.0 -x_pitch 0.48 -y_offset 0.0 -y_pitch 0.42
}
make_tracks TopMetal1 -x_offset 1.64 -x_pitch 3.28 -y_offset 1.64 -y_pitch 3.28
make_tracks TopMetal2 -x_offset 2.0 -x_pitch 4.0 -y_offset 2.0 -y_pitch 4.0
create_clock -name core -period $clock_ns [get_ports $clock_port]
set data_inputs [lsearch -all -inline -not -exact [all_inputs] [get_ports $clock_port]]
set_input_delay 2 -clock core $data_inputs
set_output_delay 2 -clock core [all_outputs]
set_driving_cell -lib_cell sg13g2_buf_4 -pin X $data_inputs
set_load 0.006 [all_outputs]
set_clock_uncertainty 0.25 [get_clocks core]
set_clock_transition 0.15 [get_clocks core]
# RC values copied from the exact PDK's public librelane/config.tcl.
set_layer_rc -layer Metal2 -resistance 2.53519e-03 -capacitance 1.69121e-04
set_layer_rc -layer Metal3 -resistance 1.54329e-03 -capacitance 1.82832e-04
set_layer_rc -layer Metal4 -resistance 6.31424e-04 -capacitance 1.66454e-04
set_layer_rc -layer Metal5 -resistance 6.84051e-04 -capacitance 8.57431e-05
set_wire_rc -signal -layer Metal2
set_wire_rc -clock -layer Metal5
place_pins -hor_layers Metal3 -ver_layers Metal2
global_placement -density 0.35
estimate_parasitics -placement
repair_design
detailed_placement
check_placement -verbose
clock_tree_synthesis -root_buf sg13g2_buf_16 -buf_list {sg13g2_buf_8 sg13g2_buf_4 sg13g2_buf_2}
set_propagated_clock [get_clocks core]
detailed_placement
check_placement -verbose
set_routing_layers -signal Metal2-Metal5 -clock Metal2-Metal5
global_route -guide_file $out/route.guide -congestion_iterations 50
# Persist completed global routing before bounded detailed-route refinement.
write_db $out/global-route.odb
write_def $out/global-route.def
estimate_parasitics -global_routing
report_checks -path_delay max -group_path_count 10 > $out/global-setup.rpt
report_checks -path_delay min -group_path_count 10 > $out/global-hold.rpt
report_checks -unconstrained > $out/global-unconstrained.rpt
report_worst_slack -max > $out/global-setup-summary.rpt
report_worst_slack -min > $out/global-hold-summary.rpt
check_setup -verbose > $out/global-constraints.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators > $out/global-electrical.rpt
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
set file [open $out/global-route-summary.json w]
puts $file "{\"cell_area_um2\": $cell_area, \"core_area_um2\": $core_area, \"utilization_percent\": [expr {100.0 * $cell_area / $core_area}], \"instances\": [llength [$block getInsts]], \"clock_period_ns\": $clock_ns, \"timing_model\": \"global-route RC estimate before detailed signal routing\", \"power_grid\": \"NOT_IMPLEMENTED\", \"process_drc\": \"NOT_RUN\", \"lvs\": \"NOT_RUN\"}"
close $file
detailed_route -output_drc $out/route.drc -output_maze $out/route.maze -droute_end_iter 3 -verbose 1
set route_violations [detailed_route_num_drvs]
set drv_file [open $out/router-drc-count.txt w]
puts $drv_file $route_violations
close $drv_file
estimate_parasitics -global_routing
# These are global-route RC timing estimates after detailed signal routing,
# not extracted post-route timing or foundry signoff.
report_checks -path_delay max -group_path_count 10 > $out/setup.rpt
report_checks -path_delay min -group_path_count 10 > $out/hold.rpt
report_checks -unconstrained > $out/unconstrained.rpt
check_setup -verbose > $out/constraints.rpt
report_worst_slack -max > $out/setup-summary.rpt
report_worst_slack -min > $out/hold-summary.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators > $out/electrical.rpt
write_db $out/routed.odb
write_def $out/routed.def
write_verilog $out/routed.v
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
puts $file "{\"cell_area_um2\": $cell_area, \"core_area_um2\": $core_area, \"utilization_percent\": [expr {100.0 * $cell_area / $core_area}], \"instances\": [llength [$block getInsts]], \"clock_period_ns\": $clock_ns, \"timing_model\": \"global-route RC estimate after detailed signal routing\", \"power_grid\": \"NOT_IMPLEMENTED\", \"process_drc\": \"NOT_RUN\", \"lvs\": \"NOT_RUN\"}"
close $file
