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

# Full-conductor successor to the failed boundary-band experiment. Read native
# PG via metal boxes, including local lower-layer stacks, without flattening
# cuts into metal or approximating a via by its whole multilayer bounding box.
proc lemma_power_geometry_box {block layer x1 y1 x2 y2 records_name} {
    upvar 1 $records_name records
    set name [$layer getName]
    if {$name ni {Metal2 Metal3 Metal4 Metal5}} {return}
    if {min($x2-$x1,$y2-$y1) <= 0 || min($x2-$x1,$y2-$y1) >= 10000} {error "PG geometry outside original spacing-table domain"}
    set box [list [expr {$x1-420}] [expr {$y1-420}] [expr {$x2+420}] [expr {$y2+420}]]
    lassign $box a b c d
    set die [$block getDieArea]
    if {$a < [$die xMin] || $b < [$die yMin] || $c > [$die xMax] || $d > [$die yMax]} {error "PG body clearance outside die"}
    foreach value $box {if {$value % 5 != 0} {error "PG body clearance off original5nm grid"}}
    set obs [odb::dbObstruction_create $block $layer {*}$box]
    $obs setExceptPGNetsObstruction
    if {![$obs isExceptPGNetsObstruction]} {error "PG body clearance blocks power"}
    lappend records [linsert $box 0 $name]
}

proc lemma_add_power_geometry_clearance {out prior standard_tech} {
    set block [ord::get_db_block]
    if {[$block getDbUnitsPerMicron] != 1000 || [llength [$block getObstructions]] != 0} {error "Unexpected original PG geometry context"}
    set f [open $prior/routed.def r]
    set data [read $f]
    close $f
    if {![regexp {NONDEFAULTRULES 2 ;(.*?)END NONDEFAULTRULES} $data all ndr]} {error "Missing original CTS rules"}
    foreach layer {Metal2 Metal3 Metal4 Metal5} {
        if {[regexp -all "LAYER $layer WIDTH 200 SPACING 420" $ndr] != 2} {error "Changed original CTS spacing"}
    }
    set f [open $standard_tech r]
    set data [read $f]
    close $f
    foreach layer {Metal2 Metal3 Metal4 Metal5} {
        if {![regexp "LAYER ${layer}(.*?)END ${layer}" $data all card] ||
            [string first {WIDTH 0.39        0.21    0.24    0.24} $card] < 0 ||
            [string first {WIDTH 10.0        0.21    0.24    0.60} $card] < 0} {error "Changed original process spacing table"}
    }
    set records [list]
    foreach name {pen_sram_lane0 pen_sram_lane1 pen_sram_lane2} {
        set inst [$block findInst $name]
        if {$inst == "NULL" || [[$inst getMaster] getName] != "RM_IHPSG13_1P_256x64_c2_bm_bist"} {error "Missing original SRAM"}
        foreach pin {VSS! VDD! VDDARRAY!} {
            set term [$inst findITerm $pin]
            if {$term == "NULL" || [$term getNet] == "NULL"} {error "Missing original PG pin"}
            foreach geometry [$term getGeometries] {
                lassign $geometry layer rect
                if {[$layer getName] != "Metal4"} {error "Changed original SRAM PG layer"}
                lemma_power_geometry_box $block $layer [$rect xMin] [$rect yMin] [$rect xMax] [$rect yMax] records
            }
        }
    }
    foreach name {VDDlogic VDDARRAY VSS} {
        set net [$block findNet $name]
        if {$net == "NULL"} {error "Missing real PG net"}
        foreach wire [$net getSWires] {
            foreach shape [$wire getWires] {
                if {[$shape isVia]} {
                    lassign [$shape getViaXY] x y
                    set via [$shape getBlockVia]
                    if {$via == "NULL"} {set via [$shape getTechVia]}
                    if {$via == "NULL"} {error "Unbound actual PG via"}
                    foreach metal [$via getBoxes] {
                        lemma_power_geometry_box $block [$metal getTechLayer] [expr {[$metal xMin]+$x}] [expr {[$metal yMin]+$y}] [expr {[$metal xMax]+$x}] [expr {[$metal yMax]+$y}] records
                    }
                } else {
                    lemma_power_geometry_box $block [$shape getTechLayer] [$shape xMin] [$shape yMin] [$shape xMax] [$shape yMax] records
                }
            }
        }
    }
    if {[llength $records] != 18718 || [llength [$block getObstructions]] != 18718} {error "Incomplete actual PG geometry inventory"}
    set f [open $out/power-geometry-boxes.tsv w]
    foreach record $records {puts $f [join $record \t]}
    close $f
    set f [open $out/power-geometry-clearance.json w]
    puts $f {{"status":"ADDED_ACTUAL_FULL_PG_GEOMETRY_NOT_ROUTED_QUALIFICATION","added_obstructions":18718,"clearance_um":0.42,"source":"max(original_process_spacing,original_CTS_NDR)","power_geometry_and_pins_preserved":true}}
    close $f
    return $records
}

proc lemma_check_power_geometry_clearance {expected} {
    set observed [list]
    foreach obs [[ord::get_db_block] getObstructions] {
        if {![$obs isExceptPGNetsObstruction]} {error "Changed actual PG body exception"}
        set box [$obs getBBox]
        lappend observed [list [[$box getTechLayer] getName] [$box xMin] [$box yMin] [$box xMax] [$box yMax]]
    }
    if {[lsort $observed] != [lsort $expected]} {error "Actual PG body/via clearance changed"}
}
