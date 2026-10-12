# SPDX-License-Identifier: Apache-2.0
# Import original transistor-level standard-cell layouts before signal DEF.
# This is an attempted public-PDK check, not foundry signoff.
cd $out
if {[catch {
    gds readonly true
    gds read $pdk/libs.ref/sg13g2_stdcell/gds/sg13g2_stdcell.gds
    lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_tech.lef
    lef read $pdk/libs.ref/sg13g2_stdcell/lef/sg13g2_stdcell.lef
    def read $out/routed.def
    load $top
    select top cell
    expand
    drc style drc(full)
    drc on
    drc check
    drc catchup
    set count [drc list count total]
    set file [open $out/process-drc-count.txt w]
    puts $file $count
    close $file
    set file [open $out/process-drc.rpt w]
    puts $file [drc listall why]
    close $file
    gds write $out/layout.gds
} failure]} {
    puts stderr "Process check Tcl failure: $failure"
    exit 1
}
quit -noprompt
