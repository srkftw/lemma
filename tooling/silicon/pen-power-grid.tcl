# SPDX-License-Identifier: Apache-2.0
# Source-bound SG13G2 core mesh, OpenROAD26Q2 PDN/PSM supported API.
# Original SRAM Liberty voltage_map: VDD1.20V, VDDARRAY1.20V, VSS0V.
# No IR/EM, power sequencing, pad/package or full process signoff claim.
# Core-block mesh only: original5um die margin cannot hold the3rail chip ring.
# A reserved chip power/pad band remains a separate physical predecessor.
# Actual always-on three-rail pen grid. Both positive rails are1.20V in the
# original macro Liberty; keep support logic and array supplies separate.
add_global_connection -net VDDlogic -pin_pattern {^VDD$} -power
add_global_connection -net VDDlogic -pin_pattern {^VDD!$} -power
add_global_connection -net VDDARRAY -pin_pattern {^VDDARRAY!$} -power
add_global_connection -net VSS -pin_pattern {^VSS!?$} -ground
global_connect
set_voltage_domain -name Core -power VDDlogic -ground VSS -secondary_power VDDARRAY
define_pdn_grid -name pen_core -voltage_domains Core -pins TopMetal2 -starts_with POWER
# Use explicit0.33um full row rail rather than the inferred0.165um width.
# Width must be a multiple of0.010um, twice the unchanged0.005um grid.
add_pdn_stripe -grid pen_core -layer Metal1 -width 0.33 -followpins -nets {VDDlogic VSS}
# Preserve lower-layer signal-pin access: continuousM2straps covered620
# actualM1/M2signalpinrectangles; M4straps/localizedstacks covernone.
add_pdn_stripe -grid pen_core -layer Metal4 -width 1.2 -pitch 60 -offset 10 -nets {VDDlogic VSS}
add_pdn_stripe -grid pen_core -layer Metal5 -width 2.5 -pitch 80 -offset 10 -nets {VDDlogic VDDARRAY VSS}
add_pdn_stripe -grid pen_core -layer TopMetal1 -width 4 -pitch 120 -offset 20 -nets {VDDlogic VDDARRAY VSS}
add_pdn_stripe -grid pen_core -layer TopMetal2 -width 4 -pitch 120 -offset 20 -nets {VDDlogic VDDARRAY VSS}
# Default PDN emitted410nm Via1 pitch despite the original generator's480nm.
# Request its original480nm pitch explicitly; independent DEF checks retain
# cut-size/pitch/every-cut enclosure validation, including all power shapes.
add_pdn_connect -grid pen_core -layers {Metal1 Metal4} -cut_pitch 0.48
add_pdn_connect -grid pen_core -layers {Metal4 Metal5}
add_pdn_connect -grid pen_core -layers {Metal5 TopMetal1}
add_pdn_connect -grid pen_core -layers {TopMetal1 TopMetal2}
define_pdn_grid -macro -name pen_sram -cells RM_IHPSG13_1P_256x64_c2_bm_bist -orient {R0 MX} -grid_over_pg_pins -voltage_domains Core
add_pdn_stripe -grid pen_sram -layer Metal5 -width 2.5 -pitch 24 -offset 8 -nets {VDDlogic VDDARRAY VSS}
add_pdn_connect -grid pen_sram -layers {Metal4 Metal5}
add_pdn_connect -grid pen_sram -layers {Metal5 TopMetal1}
pdngen -failed_via_report $out/failed-vias.rpt
