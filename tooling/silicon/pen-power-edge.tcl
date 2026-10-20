# SPDX-License-Identifier: Apache-2.0
# Physical-only candidate: preserve actual SRAM PG geometry and exclude signals
# from its boundary clearance on Metal4. Original SG13G2 Metal4 spacing table:
# width>=0.39um and <10um, PRL>=1um =>0.24um. Actual PG rails are2.81um wide.
# No macro pin, existing OBS, clock, endpoint, or routing-capacity override.
proc lemma_add_power_edge_clearance {out} {
    set block [ord::get_db_block]
    set units [$block getDbUnitsPerMicron]
    if {$units != 1000} {error "Unadmitted PG edge database units"}
    set clearance 240
    set layer [[ord::get_db_tech] findLayer Metal4]
    set die [$block getDieArea]
    set original [llength [$block getObstructions]]
    set added [list]
    foreach name {pen_sram_lane0 pen_sram_lane1 pen_sram_lane2} {
        set inst [$block findInst $name]
        if {$inst == "NULL" || [[$inst getMaster] getName] != "RM_IHPSG13_1P_256x64_c2_bm_bist"} {error "Missing original PG macro $name"}
        set bbox [$inst getBBox]
        foreach pin {VSS! VDD! VDDARRAY!} {
            set term [$inst findITerm $pin]
            if {$term == "NULL" || [$term getNet] == "NULL"} {error "Missing connected original PG pin"}
            foreach geometry [$term getGeometries] {
                lassign $geometry pin_layer rect
                if {[$pin_layer getName] != "Metal4"} {error "Unexpected original PG layer"}
                if {[$rect dx] < 390 || [$rect dx] >= 10000} {error "PG width outside original0.24um spacing domain"}
                foreach side {bottom top} {
                    if {$side == "bottom"} {
                        set edge [$bbox yMin]
                        if {[$rect yMin] != $edge} {continue}
                    } else {
                        set edge [$bbox yMax]
                        if {[$rect yMax] != $edge} {continue}
                    }
                    set box [list [expr {[$rect xMin]-$clearance}] [expr {$edge-$clearance}] [expr {[$rect xMax]+$clearance}] [expr {$edge+$clearance}]]
                    lassign $box x1 y1 x2 y2
                    if {$x1 < [$die xMin] || $y1 < [$die yMin] || $x2 > [$die xMax] || $y2 > [$die yMax]} {error "PG edge clearance outside die"}
                    foreach value $box {if {$value % 5 != 0} {error "PG edge clearance off original5nm grid"}}
                    set obs [odb::dbObstruction_create $block $layer {*}$box]
                    $obs setExceptPGNetsObstruction
                    if {![$obs isExceptPGNetsObstruction]} {error "PG geometry incorrectly excluded"}
                    lappend added $box
                }
            }
        }
    }
    if {[llength $added] != 816 || [llength [$block getObstructions]] != $original+816} {error "Incomplete or changed original PG edge inventory"}
    set file [open $out/power-edge-clearance.json w]
    puts $file "{\"status\":\"ADDED_SIGNAL_ONLY_CLEARANCE_NOT_ROUTED_QUALIFICATION\",\"layer\":\"Metal4\",\"clearance_um\":0.24,\"added_obstructions\":816,\"original_obstructions\":$original,\"original_PG_pins_preserved\":true}"
    close $file
    return $added
}

proc lemma_check_power_edge_clearance {expected} {
    set observed [list]
    foreach obs [[ord::get_db_block] getObstructions] {
        set box [$obs getBBox]
        if {[[$box getTechLayer] getName] != "Metal4" || ![$obs isExceptPGNetsObstruction]} {continue}
        lappend observed [list [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
    }
    if {[lsort $observed] != [lsort $expected]} {error "PG edge clearance changed during routing"}
}
