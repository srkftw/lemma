# SPDX-License-Identifier: Apache-2.0
# Extract actual streamed geometry in a fresh Magic process. Selecting
# drc(full) and subsequently extracting crashes the pinned tool on the
# original public inverter; full-rule DRC is attempted separately in process.tcl.
cd $out
if {[catch {
    gds readonly true
    gds read $out/layout.gds
    load $top
    select top cell
    # expand changes only the UI view; hierarchical DRC/extract all owns geometry.
    extract path $out
    # Original public CDL uses primitive M devices, while ngspice() emits
    # undefined subcircuit placeholders in this explicit CDL comparison.
    # The supplied primitive style passes width/bulk negative preflights;
    # it differs from the PDK README's ordinary Magic/Netgen recommendation.
    extract style ngspice(lvs)
    extract all
    ext2spice lvs
    ext2spice -o $out/extracted.spice $top
} failure]} {
    puts stderr "Transistor extraction Tcl failure: $failure"
    exit 1
}
quit -noprompt
