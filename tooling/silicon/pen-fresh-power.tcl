# SPDX-License-Identifier: Apache-2.0
# Actual fresh-mapping grid integration before the first global route. This
# preserves the mapped candidate, all placement/clock/timing repairs and every
# functional port. It never substitutes a historical repaired netlist.
proc lemma_signal_ports {} {
    set result [dict create]
    foreach term [[ord::get_db_block] getBTerms] {
        if {[$term getName] in {VDDlogic VDDARRAY VSS}} {continue}
        set boxes [list]
        foreach pin [$term getBPins] {
            foreach box [$pin getBoxes] {
                lappend boxes [list [[$box getTechLayer] getName] [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
            }
        }
        dict set result [$term getName] [list [$term getSigType] [$term getIoType] [[$term getNet] getName] [lsort $boxes]]
    }
    return $result
}
proc lemma_check_fresh_power_ports {before} {
    set after [lemma_signal_ports]
    if {[dict size $before] != 665 || [dict size $after] != 665 ||
        [lsort [dict keys $before]] != [lsort [dict keys $after]]} {error "Fresh grid changed functional port inventory"}
    dict for {name value} $before {
        if {$value != [dict get $after $name]} {error "Fresh grid changed functional port $name"}
    }
}
set fresh_power_ports_before [lemma_signal_ports]
file mkdir $out/pre-power $out/post-power
write_db $out/pre-power/routed.odb
write_def $out/pre-power/routed.def
write_verilog $out/pre-power/routed.v
write_sdc $out/pre-power/routed.sdc
source $power_check_script
set power_bindings_before [lemma_macro_bindings $out/power-macro-before.tsv]
source $power_grid_script
lemma_check_power_grid $power_bindings_before $out before-route
lemma_check_fresh_power_ports $fresh_power_ports_before
write_db $out/post-power/routed.odb
write_verilog $out/post-power/routed.v
write_db $out/power-grid-before-route.odb
write_def $out/power-grid-before-route.def
write_verilog -include_pwr_gnd $out/power-connected.v
source $power_geometry_script
set power_geometry_clearance [lemma_add_power_geometry_clearance $out $out/pre-power/routed.def $pdk/lef/sg13g2_tech.lef]
lemma_check_power_geometry_clearance $power_geometry_clearance
write_db $out/power-geometry-before-route.odb
write_def $out/power-geometry-before-route.def
set power_grid_state CONNECTED_CORE_GRID_ONLY_NO_IR_EM
