# SPDX-License-Identifier: Apache-2.0
# Pinned OpenROAD bounded setup-repair journal sensitivity reproducer.
set root [file normalize [file join [file dirname [info script]] ../..]]
set pdk $root/build/silicon/deps/ihp-open-pdk/ihp-sg13g2/libs.ref/sg13g2_stdcell
set_thread_count 1
read_lef $pdk/lef/sg13g2_tech.lef
read_lef $pdk/lef/sg13g2_stdcell.lef
read_liberty $pdk/lib/sg13g2_stdcell_typ_1p20V_25C.lib
read_verilog $root/tooling/silicon/journal-repro.v
link_design journal_minimal
initialize_floorplan -utilization 20 -aspect_ratio 1 -core_space 5 -site CoreSite
foreach layer {Metal1 Metal2 Metal3 Metal4 Metal5} {
 make_tracks $layer -x_offset 0.0 -x_pitch 0.48 -y_offset 0.0 -y_pitch 0.42
}
create_clock -name core -period 0.5 [get_ports clk]
set_input_delay 0.1 -clock core [get_ports data_in]
set_output_delay 0.1 -clock core [get_ports data_out]
set_driving_cell -lib_cell sg13g2_buf_4 -pin X [get_ports data_in]
set_load 0.006 [get_ports data_out]
set_wire_rc -resistance 0.00253519 -capacitance 0.000169121
place_pins -hor_layers Metal3 -ver_layers Metal2
global_placement -density 0.35
estimate_parasitics -placement
report_worst_slack -max
set_debug_level RSZ journal 1
set phase [expr {[info exists env(LEMMA_JOURNAL_PHASE)] ? $env(LEMMA_JOURNAL_PHASE) : "LEGACY"}]
if {$phase ni {LEGACY WNS_PATH}} {error "Unknown journal reproducer phase"}
repair_timing -setup -phases $phase -max_passes 1 -max_iterations 1 -max_buffer_percent 100
report_worst_slack -max
