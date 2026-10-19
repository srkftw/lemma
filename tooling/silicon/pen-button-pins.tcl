# SPDX-License-Identifier: Apache-2.0
# Keep every raw button-validation bit. Unconstrained placement scattered the
# bus around the die and produced two >1.4mm single-load reduction nets.
set button_bus_names {}
for {set bit 0} {$bit < 64} {incr bit} {
    set name [format {sample_buttons[%d]} $bit]
    set port [[ord::get_db_block] findBTerm $name]
    if {$port == "NULL" || [$port getIoType] != "INPUT"} {error "Missing full64 button input $name"}
    lappend button_bus_names $name
}
set_io_pin_constraint -group -order -pin_names $button_bus_names -region top:*

proc lemma_check_button_pins {} {
    global button_bus_names out
    set block [ord::get_db_block]
    set die [$block getDieArea]
    set units [$block getDbUnitsPerMicron]
    set previous_x -1
    set first_x -1
    set file [open $out/button-bus-pins.tsv w]
    puts $file "name\tlayer\txmin_dbu\tymin_dbu\txmax_dbu\tymax_dbu"
    foreach name $button_bus_names {
        set port [$block findBTerm $name]
        set pins [$port getBPins]
        if {[llength $pins] != 1} {error "Button input shape missing or duplicated: $name"}
        set boxes [[lindex $pins 0] getBoxes]
        if {[llength $boxes] != 1} {error "Unexpected button input geometry: $name"}
        set box [lindex $boxes 0]
        set layer [[$box getTechLayer] getName]
        if {$layer != "Metal2" || [$box yMax] != [$die yMax] ||
            [$box yMin] < [$die yMax] - $units || [$box xMin] <= $previous_x ||
            [$box xMin] < [$die xMin] || [$box xMax] > [$die xMax]} {
            error "Full64 ordered button bus escaped its actual top-edge geometry: $name"
        }
        if {$first_x < 0} {set first_x [$box xMin]}
        set previous_x [$box xMin]
        puts $file "$name\t$layer\t[$box xMin]\t[$box yMin]\t[$box xMax]\t[$box yMax]"
    }
    close $file
    if {[llength $button_bus_names] != 64 || $previous_x - $first_x > 128 * $units} {
        error "Missing or dispersed full64 button bus"
    }
    puts "Validated all64 raw button inputs, ordered and compact on original top-edge Metal2 tracks"
}
