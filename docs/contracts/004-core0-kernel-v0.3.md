# Core0 kernel v0.3: LemmaSim device boundary

This additive kernel-only profile preserves all older source-language profiles.
It admits exactly four new checked scalar operations: `lemmasim.device-read32`,
`device-write32`, `device-read64`, and `device-write64`. Each elaborates a real
Lean Action declaration. Loads/stores are volatile, little endian, require natural
alignment and a whole-width in-range access, and have an I/O fence before and
after the access. Writes reject values outside the selected register width.

32-bit ranges: modern VirtIO-MMIO registers `[0x10001000,0x10001200)`,
PLIC priorities `[0x0c000004,0x0c000038)`, supervisor-context enables
`[0x0c002080,0x0c002084)`, and context1 threshold/claim-complete
`[0x0c201000,0x0c201008)`. 64-bit ranges: project paper and pen windows
`[0x10010000,0x10012000)`. These are a separate device catalog; ordinary physical
RAM operations do not grant MMIO authority. User-v0.1 cannot express these
operations. Kernel-v0.1/v0.2 reject them even when externally forged into an IR.

Only the explicit LemmaSim configuration selects v0.3 and its extra PMP/map
boundary. LLVM20.1.8 RV64IM LP64 remains the backend and ABI. The profile extends
neither managed Lean support nor arbitrary foreign-code linkage. Compiler fixture
`tests/lemmasim/CompilerDevices.lean` checks genuine elaboration, rejection under
old profiles, access widths, volatile operations, and fences. This local check is
not compiler correctness or a whole-machine execution certificate.

The pinned optimizer may replace declared scalar arithmetic with
`llvm.usub.sat.i64` (unsigned subtraction clamped to zero) and `llvm.fshl.i64`
(concatenated unsigned funnel shift modulo 64). The compiled notebook's observed
funnel shift has equal input words and therefore rotates its value. The artifact
auditor admits these two optimizer intrinsics only for the closed LemmaSim
configurations, together with historical min/max intrinsics. They lower to
ordinary RV64IM integer instructions and introduce no runtime helper or target
source-language operation. Undefined symbols, generated instructions, literal
tables, ownership and stack accounting remain independently checked. This is
accounting for pinned optimized artifacts, not a claim of general LLVM or Lean
compiler correctness.
