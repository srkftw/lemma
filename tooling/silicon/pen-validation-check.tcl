# SPDX-License-Identifier: Apache-2.0
# Pinned placers do not enforce bare dbRegion component tags. Admit this
# candidate only when the physical placement group actually stays in bounds.
set block [ord::get_db_block]
set validation_group [$block findGroup pen_validation_middle]
if {$validation_group == "NULL"} {error "Missing real validation placement group"}
set validation_region [$validation_group getRegion]
if {$validation_region == "NULL"} {error "Missing validation group region"}
set bounds [$validation_region getBoundaries]
if {[llength $bounds] != 1} {error "Unknown validation region geometry"}
set boundary [lindex $bounds 0]
set members [$validation_group getInsts]
if {[llength $members] < 1 || [llength $members] > 512} {error "Missing bounded validation group members"}
foreach instance $members {
    set box [$instance getBBox]
    if {[$box xMin] < [$boundary xMin] || [$box yMin] < [$boundary yMin] ||
        [$box xMax] > [$boundary xMax] || [$box yMax] > [$boundary yMax]} {
        error "Validation group placement escaped its actual region: [$instance getName]"
    }
}
puts "Validated real middle-channel containment of [llength $members] cells"
