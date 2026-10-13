<!--
# Core0 kernel v0.4: Power-v1 PLIC priority

This successor preserves the language, primitive operations, ABI, alignment,
whole-access bounds, volatile accesses and fences of
[kernel v0.3](004-core0-kernel-v0.3.md). Its only device-range change extends
the exclusive end of the 32-bit PLIC priority interval from `0x0c000038` to
`0x0c00003c`. Source14's four-byte priority register at `0x0c000038` is thereby
admitted. Source15, unaligned accesses and accesses crossing the interval remain
rejected. All other memory and device ranges are identical.

Only `lemmasim-silicon-power-initialize`, `lemmasim-silicon-power-notebook` and
`lemmasim-silicon-power-probe`, selected by machine profile
`lemma-silicon-dev/0.3.0`, use this compiler contract. Historical configurations
continue to use their previous contract and priority bound. User software gains
no raw MMIO operation or new compiler operation.

`tests/lemmasim/CompilerPowerBoundary.lean` genuinely elaborates the relevant
declarations through checked lowering. `scripts/check_power_compiler.py` executes
their emitted O0/O2 guards against an independently mapped host-only register
page, checking both contracts, alignment, widths, boundary addresses and rejected
values. This focused guard evidence is separate from RV64 guest execution,
compiler correctness, whole-machine equivalence and physical qualification.

-->
