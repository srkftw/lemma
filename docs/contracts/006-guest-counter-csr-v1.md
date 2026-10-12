# Fixed machine counter operations: core0-firmware-v0.2

This additive development firmware profile preserves every historical Core0
profile and adds nine fixed, M-mode machine-state operations. Ordinary Lean
source is genuinely elaborated, checked as Action IR, lowered through LLVM,
and linked with the structured hardware boundary. ELF preload remains explicit
development boot. This contract is not product boot, a complete ISA audit,
or fast/RTL processor timing parity.

The scalar language, bounded folds, fixed firmware RAM interval and existing
firmware operations are inherited from core0-firmware-v0.1. Action.loop remains
rejected. The new profile does not admit arbitrary CSR numbers, new memory
intervals, generic extern calls, hosted target runtimes or a counter emulator.

| Source operation | CSR | Meaningful UInt64 arguments | Result |
| --- | --- | --- | --- |
| readMisa | misa, 0x301 | 0 | Actual CSR word |
| readMachineCycle | mcycle, 0xb00 | 0 | Actual CSR word |
| writeMachineCycle | mcycle, 0xb00 | 1 | Zero after normal write |
| readMachineRetired | minstret, 0xb02 | 0 | Actual CSR word |
| writeMachineRetired | minstret, 0xb02 | 1 | Zero after normal write |
| readMachineInhibit | mcountinhibit, 0x320 | 0 | Actual CSR word |
| writeMachineInhibit | mcountinhibit, 0x320 | 1 | Zero after normal write |
| readMachineCounterEnable | mcounteren, 0x306 | 0 | Actual CSR word |
| writeMachineCounterEnable | mcounteren, 0x306 | 1 | Zero after normal write |

All six source operand slots remain present in Action.platform. The unused
slots must be literal zero. Each operation has only machine-state effects;
its fixed CSR access is not physical RAM, MMIO, allocator or privilege policy.
The read body is CSRRS a0,csr,x0 followed by return; write is CSRRW x0,csr,a0,
sets the ABI result to zero and returns. A fault does not reach that normal
return. The emitted instruction bytes, CSR identity, ABI and complete executable
closure are audited independently. Legacy profiles reject the new operations.

For lemma-silicon-dev/0.3.0, the reference RTL reports RV64IM with S/U
misa=0x8000000000141100. Its mcountinhibit admits CY(bit0) and IR(bit2),
mcounteren admits CY/TM/IR(bits0..2), and other bits read zero after all-one
writes. Counter-enable controls lower-privilege access, not incrementing;
MTIME continues independently of mcountinhibit. Counter writes replace the
selected 64-bit value, and uninhibited counters wrap modulo 2^64. These are
profile obligations checked by actual guest instructions, not debugger writes.
No exact instruction-retirement/cycle relation is imposed on a fast backend.

The first qualification scope is M-mode reads/writes, masks, independent
inhibition, resume, modulo wrap and reset from active inhibition. It selects an
actual compiled-source PC boundary with both counters inhibited, snapshots
without hidden drain/fence/reset, restores an isolated fork, and compares the
applicable exact native RTL suffix and guest records. This finite state is
not cached-translation/instruction-visibility coverage. S/U access admission,
trap priority/values, unadmitted extensions, Sv39/PMP/fences/WFI and arbitrary
cached-state continuation remain separate, unfinished obligations.

Primary ISA basis: [Machine ISA 1.13](https://docs.riscv.org/reference/isa/v20240411/priv/machine.html)
and [Zicsr 2.0](https://docs.riscv.org/reference/isa/v20240411/unpriv/zicsr.html).
Pinned circuitry/tool identities and observed failures belong in the emitted
source/tool-bound receipt. A successful source/admission fixture is distinct
from an observed RV64 run.

Run the narrow compiled guest qualification using a prepared immutable native
bundle containing the canonical RTL and pinned fast binaries:

```sh
nix develop --no-write-lock-file --command lake env lean tests/kernel/CounterExecutionCompile.lean
nix develop --no-write-lock-file --command python3 scripts/check_guest_counters.py \
  --work-dir build/silicon/guest-counters-new \
  --native-bundle build/native/task006-arithmetic-a3 --fast
```

Use an unused output directory. The receipt records actual compiler/source,
primitive bytes, linked objects, stack bound, runtime identities and guest RAM.
The first observed run is in `docs/evidence/006-guest-counters.json`: 3,257 RTL
cycles, 1,488 retired instructions at completion; a snapshot at cycle840 has an
exact same-backend suffix. Those values describe this finite workload and impose
no fast/RTL timing equivalence or broader cache-state continuation claim.
