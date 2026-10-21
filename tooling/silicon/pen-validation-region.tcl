# SPDX-License-Identifier: Apache-2.0
# Keep the actual range-validation cones and their immediate collectors in the
# open middle channel. This changes placement, not logic, timing or macro OBS.
set block [ord::get_db_block]
set invalid_nets [get_nets {physical_validation.ranges.invalid*}]
if {[llength $invalid_nets] != 6} {error "Expected six real pen validation outputs"}
set members [dict create]
foreach cell [get_fanin -to $invalid_nets -flat -only_cells -trace_arcs all] {
    set name [get_full_name $cell]
    # OpenSTA also returns its logical top instance, which owns no placement.
    if {$name == ""} {continue}
    set instance [$block findInst $name]
    if {$instance == "NULL"} {error "No real validation cone instance $name"}
    dict set members $name $instance
}
foreach net $invalid_nets {
    set physical_net [$block findNet [get_full_name $net]]
    if {$physical_net == "NULL"} {error "No real validation output net"}
    foreach pin [$physical_net getITerms] {
        if {[$pin getIoType] == "INPUT"} {
            set instance [$pin getInst]
            dict set members [$instance getName] $instance
        }
    }
}
if {[dict size $members] < 1 || [dict size $members] > 512} {error "Invalid validation region membership"}
set region [odb::dbRegion_create $block pen_validation_middle]
$region setRegionType EXCLUSIVE
set group [odb::dbGroup_create $block pen_validation_middle]
$group setType PHYSICAL_CLUSTER
$region addGroup $group
set units [$block getDbUnitsPerMicron]
odb::dbBox_create $region [expr {round(500.16*$units)}] [expr {round(476.28*$units)}] [expr {round(700.80*$units)}] [expr {round(589.68*$units)}]
set file [open $out/validation-region.tsv w]
puts $file "# Actual OpenDB EXCLUSIVE region; micrometre bbox500.16,476.28,700.80,589.68; aligned real0.48um sites/3.78um rows; no macro geometry changes"
dict for {name instance} $members {
    $region addInst $instance
    $group addInst $instance
    puts $file "$name\t[[$instance getMaster] getName]"
}
close $file
if {[$group getRegion] != $region || [llength [$group getInsts]] != [dict size $members]} {error "Missing placement-group binding"}
puts "Validation middle-channel physical members: [dict size $members]"
