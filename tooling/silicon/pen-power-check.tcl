# SPDX-License-Identifier: Apache-2.0
proc lemma_macro_bindings {file} {
    set bindings [dict create]
    set f [open $file w]
    foreach name {pen_sram_lane0 pen_sram_lane1 pen_sram_lane2} {
        set inst [[ord::get_db_block] findInst $name]
        if {$inst == "NULL"} {error "Missing real SRAM $name"}
        foreach iterm [$inst getITerms] {
            set mterm [$iterm getMTerm]
            set net [$iterm getNet]
            set n NULL
            if {$net != "NULL"} {set n [$net getName]}
            set value [list [$mterm getSigType] $n]
            dict set bindings [list $name [$mterm getName]] $value
            puts $f "$name\t[$mterm getName]\t[join $value \t]"
        }
    }
    close $f
    return $bindings
}

proc lemma_check_power_grid {before out stage} {
    set after [lemma_macro_bindings $out/power-macro-$stage.tsv]
    if {[lsort [dict keys $before]] != [lsort [dict keys $after]] || [dict size $after] != 1047} {
        error "Actual SRAM signal/test/power terminal inventory changed"
    }
    set pg [dict create VDD! VDDlogic VDDARRAY! VDDARRAY VSS! VSS]
    set bist 0
    set power 0
    dict for {key value} $after {
        set pin [lindex $key 1]
        if {[dict exists $pg $pin]} {
            if {[lindex $value 1] != [dict get $pg $pin]} {error "SRAM supply binding differs: $key"}
            incr power
        } else {
            if {$value != [dict get $before $key]} {error "SRAM signal/test binding changed: $key"}
            if {[string match A_BIST_* $pin]} {incr bist}
        }
    }
    if {$power != 9 || $bist != 423} {error "Incomplete actual SRAM power/test coverage"}
    # Bind every stdcell PG terminal too. PSM below must require actual terminal
    # connectivity; do not use floorplanning/dont_require_terminals shortcuts.
    set f [open $out/power-all-terminals-$stage.tsv w]
    set all_power 0
    foreach inst [[ord::get_db_block] getInsts] {
        foreach iterm [$inst getITerms] {
            set mterm [$iterm getMTerm]
            if {[$mterm getSigType] ni {POWER GROUND}} {continue}
            set net [$iterm getNet]
            if {$net == "NULL" || [$net getName] ni {VDDlogic VDDARRAY VSS}} {
                error "Unconnected/unknown supply terminal [$inst getName]/[$mterm getName]"
            }
            incr all_power
            puts $f "[$inst getName]\t[$mterm getName]\t[$net getName]"
        }
    }
    close $f
    foreach net {VDDlogic VDDARRAY VSS} {
        check_power_grid -net $net -error_file $out/$net-$stage-connectivity.rpt
    }
    set f [open $out/power-grid-$stage.json w]
    puts $f "{\"status\":\"CONNECTED_CORE_GRID_ONLY_NO_IR_EM\",\"macro_power_pins\":$power,\"preserved_BIST_pins\":$bist,\"all_power_terminals\":$all_power,\"voltages_V\":{\"VDDlogic\":1.20,\"VDDARRAY\":1.20,\"VSS\":0}}"
    close $f
}
