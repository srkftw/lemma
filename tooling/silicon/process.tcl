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
    # expand changes only the UI view; hierarchical DRC/extract all owns geometry.
    # Publish complete imported geometry before independent DRC. A DRC timeout
    # must not discard a finished input for separately bounded extraction.
    gds write $out/layout.gds
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
} failure]} {
    puts stderr "Process check Tcl failure: $failure"
    exit 1
}
quit -noprompt
