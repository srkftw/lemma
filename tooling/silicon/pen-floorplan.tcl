# SPDX-License-Identifier: Apache-2.0
# The full256-entry pen: three original 784.48x118.78um process macros.
# Keep the compact source geometry: a widened1400x1100 trial reduced original
# short/spacing markers but increased wire RC and exposed counter/control
# timing. The maintained arithmetic repair now uses compact placement with
# cell padding, preserving all original macro routing obstructions.
initialize_floorplan -die_area {0 0 1050 850} -core_area {5 5 1045 845} -site CoreSite
foreach {name x y orient} {
    pen_sram_lane0 120 100 R0
    pen_sram_lane1 120 350 R0
    pen_sram_lane2 120 600 MX
} {
    place_macro -macro_name $name -location [list $x $y] -orientation $orient -exact
}
# A first stricter M3/M4 interior reservation plus global macro extension
# failed actual GRT-0116: that coarse reservation also blocks required pin
# escape resources. Preserve that failed run; do not waive original LEF OBS.
set_placement_padding -global -left 1 -right 1

if {[info exists center_validation_cones] && $center_validation_cones == 1} {
    source $validation_region_script
}
