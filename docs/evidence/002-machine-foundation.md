# Task 002 machine-foundation evidence

This is a living evidence record for the highest passing prefix of Task 002. Gates 0
and 1 have passed. Gate 2 and every later gate remain open. This record does not claim
completion of G1, G2, the full compiler-conformance unit, or the Task 002 machine
foundation.

## Source identity

- Task 001 base: `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85` (unmerged PR #1).
- Gate 0 checkpoint: `27033e434337e7b0af9ae428688fee242b499005`.
- Gate 1 implementation and clean verification source:
  `8878d2c65a6d76bc94ef0e8a9e036404bc76582c`, tree
  `a110453f7d92b342f193cd36e889db9a370d3232`.
- Branch: `task/002-machine-foundation`, stacked on Task 001.
- All 14 Gate 1 control/mutant provenance records name the full Gate 1 commit and
  record `dirty_tree: false`.

The clean aggregate is `build/foundation/check/gate1-results.json`, SHA-256
`a3fd012ad0dac0d20e16321c32c7006502b8c22921499517bab1468b669bf50c`.
Generated build output remains ignored; this report, the compact summary, and the hash
inventory retain its identity.

## Commands actually executed at the clean Gate 1 source

| Command | Exit | Actual result |
|---|---:|---|
| `nix develop --no-write-lock-file --command lake build` | 0 | 15 jobs; complete Lean library build |
| `python3 scripts/check_scaffold.py` | 0 | metadata valid: 7 gates, 56 software units, 6 physical units |
| `python3 -m unittest discover -s tests/scaffold -v` | 0 | 18/18 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v` | 0 | 21/21 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v` | 0 | 19/19 passed |
| `nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean` | 0 | 10 cases at O0/O2, 13 intended rejections, 23 fresh QEMU boots |
| `nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 1 --clean` | 0 | 2 controls, 12 mutants, 3 intended rejections, 7 audit regressions, 24 fresh QEMU boots |

The cumulative Task 001 regression record at this source is
`build/core0/check/check-results.json`, SHA-256
`690732e4a97a29bc25cf168c46d9f8f857667d432c5c6271463bde1fdaff4f18`.
Its O0 and O2 release provenance is schema 2, category `release`, source commit
`8878d2c...`, and clean.

## Gate 1 construction

The immutable source declarations live in `examples/foundation/CompilerFaults.lean`.
Lean elaborates them to a recorded `.olean`; the genuine Core0 frontend checks the
transitive closure; the ordinary structured lowering runs; and only then may the
test-only exporter apply one closed transform. The production exporter imports no
mutation module and the production build CLI exposes no mutation/category selector.

The test categories are explicit:

- `test-compiler-control` uses the unmodified lowering;
- `test-compiler-mutant` requires `compiler-mutation.json` and its hash bindings;
- `release` rejects either test category and all mutation metadata.

Every mutant audit repeats the normal IR, object, relocation, dependency, ELF, ISA,
layout, startup, and final-closure checks. It also audits its clean control, requires
the source manifest/normalized form/symbol map/startup/layout/linker script to be
byte-identical, reverses the reported instruction replacement, and requires the
resulting pre-optimization IR to be byte-identical to the control. Thus the reported
replacement is the sole pre-optimization IR delta.

The imported source was elaborated with:

```text
lake env lean -o .lake/build/lib/lean/examples/foundation/CompilerFaults.olean \
  examples/foundation/CompilerFaults.lean
```

Source SHA-256 is
`e757146e213b9e265dc1b074abbb113efed38ca49554fe2845fb8082504d8274`;
the clean `.olean` SHA-256 is
`b299c8b87db79d4665959632c4b1a5c2e377ca1f674f6c23dec0a5c7b3c65a1e`.
Each schema-2 provenance record hashes both and retains the exact elaboration command.

## Behavioral matrix

The checked-Core0 executable semantics supplied the unchanged oracle. Each clean
control ran all six inputs under O0 and O2 (12 boots). Each fault then produced a
separate valid O0 and O2 image, passed its audit, booted, emitted exactly one valid
UART frame, and returned the specific wrong result below (12 more boots).

| Closed fault | Distinguishing input `(selector, x, y)` | Oracle/control | O0 mutant | O2 mutant |
|---|---|---:|---:|---:|
| `ult-as-ule` | `(0, 7, 7)` | `0x22` | `0x11` | `0x11` |
| `ult-as-slt` | `(1, 0x8000000000000000, 0)` | `0x44` | `0x33` | `0x33` |
| `add-as-sub` | `(2, 9, 4)` | `0x0d` | `0x05` | `0x05` |
| `zext-as-sext` | `(3, 0x0000000080000001, 0)` | `0x0000000080000001` | `0xffffffff80000001` | `0xffffffff80000001` |
| `trunc-high-half` | `(4, 0x1122334455667788, 0)` | `0x0000000055667788` | `0x0000000011223344` | `0x0000000011223344` |
| `swap-call-args` | `(5, 9, 4)` | `0x05` | `0xfffffffffffffffb` | `0xfffffffffffffffb` |

Only `verified-behavioral-mismatch` counts. Compile/link failures, missing artifacts,
audit/provenance rejection, timeout, process failure, malformed protocol, a result
equal to the oracle, and an unexpected wrong value have separate fail-closed
categories.

## Negative and adversarial results

Three elaborated Lean rejection fixtures failed for their required diagnostics:
unknown fault ID, zero matching instructions, and two matching instructions. An
unrelated nonzero diagnostic cannot satisfy these checks.

Seven artifact-level audit regressions also passed by producing their intended
rejection:

1. release audit rejects a mutant;
2. mutant audit rejects a clean control as a mutant;
3. forged `production_selectable: true` manifest;
4. incomplete manifest;
5. stale manifest from a different closed mutant;
6. tampered before/after description even after updating its manifest hash;
7. tampered `program.ll` detected by its provenance hash.

Host tests additionally establish that a valid-looking PASS frame followed by a
nonzero QEMU exit is a process failure, not a mutant detection.

## Stage mapping and limits

Gate 1 directly advances Unit 1.8 by supplying the previously open deliberately
defective-lowering evidence. Its artifact categories and closure checks also add
evidence for Units 1.1, 1.5, and 1.7. All remain `partial`: six seeded defects and
finite inputs are not a compiler-correctness proof, Gate 2's direct elaborated-source
comparison and broad typed ABI matrix are not implemented, and later scalar, loop,
memory, device, trap, timer, monitor, and qualification gates remain open.

No Stage II unit is marked passed. In particular, the later Task 002 M-mode work does
not by itself satisfy Unit 2.1's supervisor-entry requirement. G1 and G2 remain
incomplete.
