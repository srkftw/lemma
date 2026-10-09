# Target ABI — G1 proposal

Status: Task 001 validates the scalar RV64/LP64 bootstrap profile against the pinned
compiler and emitted ELF; the managed Lean ABI remains future work.

| Field | Proposal |
| --- | --- |
| Triple | `riscv64-unknown-elf`, subject to exact LLVM target spelling |
| Application machine | RV64GC-capable, little endian |
| G1 generated code | Integer-only RV64 subset, no F/D/vector operations |
| G1 calling convention | Standard integer LP64; do not silently mix with LP64D objects |
| Pointer and word width | 64 bits |
| Stack | 16-byte alignment at call boundaries; fixed reserved area initially |
| ELF | Static RV64 ELF, explicit entry, no interpreter/dynamic dependencies |
| Initial privilege | M-mode for the first slice |
| Later privilege | M-mode platform services, S-mode OS, U-mode isolated processes |

Choosing the integer ABI for G1 is a scoped bootstrap choice, not a claim that the
managed Lean ABI has been ported. Record all changes before linking objects from another profile.

## Entry and layout

Generate the minimal entry sequence from reviewed Lean-authored primitive definitions.
It must establish a valid stack before any code with a compiler-generated prologue executes,
preserve/document boot inputs, clear required zero-initialized storage, and handle `gp` /
relaxation deliberately. No assumptions about a C runtime having prepared the environment.

Reserve text, readonly data, writable data, zero-initialized storage, stack and any runtime
test-input region in one machine-readable layout. Verify alignment, bounds and non-overlap.
Record ELF entry, load segments, target features, relocations and a linker map. No implied
heap or process environment. Any required compiler helper must be Lean-authored and audited
or the operation must be rejected. Prefer explicit LLVM/LLD tools over a driver that links
hosted startup/default libraries implicitly.

## Provenance

Every linked input has a path, source identity, SHA-256, generation command and purpose.
Track symbols/sections back to Lean source or an explicitly declared generated primitive.
Inspect pre-optimization and optimized IR, as well as object and final image closure.
No unresolved symbols is not enough: known, statically linked unwanted libraries also fail.

Consult the RISC-V psABI and LLVM manuals listed in `docs/SOURCES.md`; freeze the exact
versions and relevant rules in task 001's audit report.
