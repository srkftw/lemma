# Task 002 machine-foundation evidence

This is a living evidence record for the highest passing prefix of Task 002. Gates 0,
1, and 2 have passed. Gate 3 and every later gate remain open. This record does not
claim completion of G1, G2, the full compiler-conformance construction unit, or the
Task 002 machine foundation.

## Source identity and checkpoint lineage

- Task 001 base: `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`, tree
  `88d2c23aafbd2b3a40a195755c01494de9ffad75` (unmerged PR #1).
- Gate 0 checkpoint: `27033e434337e7b0af9ae428688fee242b499005`.
- Gate 1 implementation checkpoint: `8878d2c65a6d76bc94ef0e8a9e036404bc76582c`,
  tree `a110453f7d92b342f193cd36e889db9a370d3232`; its evidence checkpoint is
  `4258375`.
- Gate 2 implementation and cumulative clean verification source:
  `687ee7e292b7a049f8fd35fcf17097c80c3d5665`, tree
  `9b3a8e06a0ce683b887a75ee9c615eb856965a1c`.
- Branch: `task/002-machine-foundation`, stacked on Task 001.

The historical Gate 0 clean aggregate was `build/core0/check/check-results.json`,
SHA-256 `3a3cb9244b4a84b1a93ff869843aa3619622719ef6f431067e5502cbefc58a7c`.
Gate 1 first passed at `8878d2c...`; it was then rerun as part of the cumulative clean
Gates 1-2 command at `687ee7e...`. All 14 current Gate 1 control/mutant provenance
records, both Gate 2 profiles, and the current Task 001 O0/O2 release records name the
full `687ee7e...` commit and record `dirty_tree: false`.

Generated build output remains ignored. The durable identities of the cumulative
clean records are:

| Record | SHA-256 |
|---|---|
| `build/foundation/gates1-2-clean/all-results.json` | `45ba122a148518e76062512f7358d536c16924f1bd881380d69c4819da02a158` |
| `build/foundation/gates1-2-clean/gate1/gate1-results.json` | `b09cfaa81a8e1d567f3afe492570bd04112c86cec9378cb9cfab987e64a9bffe` |
| `build/foundation/gates1-2-clean/gate2/gate2-results.json` | `6b3e775f3f7ffeb17ed5b9d781d8ae38815afea07944d3e7fc45de21beb3b5cc` |
| `build/core0/check/check-results.json` | `30a4b52daf4703df172137eef828a5b6d4052efa42b7cc6c95b099edf05361fe` |

## Commands actually executed at the cumulative clean source

| Command | Exit | Actual result |
|---|---:|---|
| `nix develop --no-write-lock-file --command lake build` | 0 | 20 jobs; complete Lean library build |
| `python3 scripts/check_scaffold.py` | 0 | metadata valid: 7 gates, 56 software units, 6 physical units |
| `python3 -m unittest discover -s tests/scaffold -v` | 0 | 18/18 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v` | 0 | 21/21 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v` | 0 | 86/86 passed |
| `nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean` | 0 | 10 cases/profile, 13 intended rejections, 23 fresh QEMU boots |
| `nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all --work-dir build/foundation/gates1-2-clean --clean --timeout 300 --qemu-timeout 10` | 0 | Gates 1-2 passed: Gate 1 used 24 fresh boots; Gate 2 used 136 fresh boots |

## Gate 1: incorrect-compiler detection

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
categories. The cumulative run retained 2 controls, 12 mutants, 12/12 verified
behavioral mismatches, 3 intended source rejections, and 7 artifact-level audit
regressions.

## Gate 2: genuine multi-root frontend conformance

Gate 2 preserves the Task 001 fixed-entry runner and adds the test-only
`test-frontend-suite` category. The new route starts from 37 genuine elaborated Lean
roots. `checkAndLowerSuite` checks every root and its dependency closure before the
structured LLVM exporter emits one O0 or O2 image containing the complete suite.

The roots span `Bool`, `UInt8`, `UInt32`, and `UInt64`; a zero-argument constant;
nested lets and conditionals; direct, cross-module, and shared-diamond calls;
mixed-width signatures; all six admitted casts; and every admitted arithmetic,
bitwise, equality, and unsigned-comparison primitive. The manifest records 34 used
primitive identities. Five paired roots test alpha-renaming, helper extraction,
equivalent let nesting, module reorganization, and an unreachable host-only import.
Each pair used the same four inputs and produced equal results.

### Three comparison routes and deterministic corpus

The corpus uses suite ID `0x7812482420151ea4`, source seed
`0x4c454d4d41323032`, runtime seed `0x52554e54494d4532`, and
`SplitMix64-v1` with fixed typed boundary pools. Its file is
`build/foundation/gates1-2-clean/gate2/corpus/gate2-cases.json`, SHA-256
`b035b7aec0218e3132e93c8ec34a2b45e46e992880f4894b28c0f7d311804d1d`.
It contains exactly 1,024 distinct `(root, arguments)` cases per profile, distributed
over all 37 roots and packed into 61 valid batches per profile.

The three routes were:

1. direct evaluation of the original elaborated declarations, from a driver that
   imports the conformance declarations but neither the Core0 checker nor evaluator;
2. one genuine `checkAndLower` per root followed by the checked-Core0 evaluator;
3. compiled freestanding RV64 execution in the audited O0 and O2 images under QEMU.

Direct source and model matched all 1,024 cases and produced the same canonical result
digest, `54aca4404cf28f441ae6d83ba3b4fad0dfc3618ff89fd2414bcae8bfba531933`.
Each target profile independently matched that same digest for all 1,024 cases, for
2,048 source/model/target profile comparisons. No target case was replaced by a host
simulation.

The target matrix used 61 valid boots plus 7 negative typed-input boots in each
profile: 68/profile and 136 total. The negative matrix required exact guest failure
for inconsistent suite identity, excess argument count, a tag mismatch, invalid Bool
encoding, pre-truncation UInt8 and UInt32 overflow, and a nonzero unused slot. A
separate elaborated fixture rejected a 17-argument suite root with the required
`lemma-scalar-test-v1 maximum is 16` diagnostic.

### Versioned typed ABI and real call boundary

`lemma-scalar-test-v1` uses a 128-byte little-endian header and 136-byte records
containing a case ID plus sixteen UInt64 transport slots. Type tags are Bool=1,
UInt8=2, UInt32=3, UInt64=4; Bool must be 0/1, narrow arguments are range-checked
before truncation, unused slots must be zero, and narrow results are explicitly
extended to the transport word. The guest emits the versioned `LEMMA_SCALAR/1`
batch/result/end grammar. Both host descriptors and the image-bound manifest identify
the exact root and signature.

The dedicated ten-argument caller and callee use the signature
`(u64,u8,u32,bool,u64,u8,u32,bool,u8,u32) -> u64`. Pre-optimization LLVM contains a
non-tail real call and exact LP64 attributes at both definitions and the call site:
UInt8/Bool use `zeroext`, UInt32 uses `signext`, and UInt64 has no extension attribute.
Both O0 and O2 audits identify caller `core0_user_31`, callee `core0_user_30`, a
32-byte caller frame aligned to 16 bytes, outgoing stack argument offsets 0 and 8,
and a retained real call. The callee's audited stack-load offsets are 64/72 at O0 and
0/8 at O2. Thus the ninth and tenth, deliberately narrow, arguments cross the actual
RV64 stack boundary rather than an inlined or silently widened surrogate.

| Profile | Audit SHA-256 | Image SHA-256 |
|---|---|---|
| O0 | `26fccf1bafee4b03e24a95ba7b32df3765dd985bc09fa370f4df8c73f32de2c0` | `84ad3a6e5c0397d460bb272ebbfe64c1e3d94e5c0d8fe06907e254ba96b35d48` |
| O2 | `c29900d25bffdf71e0543cd58fd93dc3a6a3a5eb246c5d45657c6f667d000efc` | `6ea70385af020d53edf40e19bb7b0f74a9eca4cb2890b7e0b8bfed5d6c7c0cb9` |

The two profiles have byte-identical checked suite manifest
(`ec99b7c526af8bce080a0bdeac8a12c7b136d226012add83af3859dd1b8951cd`),
normalized suite
(`a3ebd6ecbc3e2ebaab387e5b8d499cb5954f1bfaff801b4e84f6c6b0c13ea5b4`),
typed ABI
(`ad68695a7820051d319e8ac914018e89272837ca77756be4b4e88a6d099148aa`),
symbol map
(`ced6e5edd52d6d1126234a0a68b8225e1f678cbf737e504a8e168e618362763c`),
and pre-optimization `program.ll`
(`07b37f40e8dccfbeb93be2412b2160252fe2932fb22db2a57c57f6ca8887f658`).
Their schema-2 provenance agrees on artifact category, source commit, clean-tree state,
compiler route, target, source and elaborated inputs, and export configuration. This
binds both optimized profiles to the same checked source while retaining their
distinct optimized IR, object, image, and audit identities.

### Exhaustive UInt8 anchor

The direct-source and checked-model routes exhaustively enumerated all 65,536 ordered
`(x,y)` pairs, in x-major order, for five named roots: UInt8 add, subtract, less-than,
less-or-equal, and equality. That is 327,680 exact comparisons. Each route emitted a
327,680-byte result artifact; both have SHA-256
`fd1b65ef4cff910a3e0179670516b2a9d176d7fefb931027b47cff76ab8b25dd`.
The recorded exhaustive phase completed in 5.888941 seconds and records per-root
offsets, pair counts, and hashes rather than only an aggregate claim.

## Shared assumptions, stage mapping, and limits

The direct and checked-model routes are deliberately separate computations, but both
share the pinned Lean 4 host elaborator and type checker. They are not three
absolutely independent proof systems; the third route also consumes the same checked
source before LLVM lowering. The exhaustive UInt8 comparison, 1,024-case wider-type
matrix, and metamorphic checks are strong finite evidence, not a compiler-correctness
or semantic-preservation proof. No separate kernel-reduction or mathematical-lemma
anchor was added, and the exact ABI audit covers one deliberate ten-argument shape,
not every possible RISC-V ABI signature.

Gates 1 and 2 directly advance Unit 1.8. Gate 2 also adds evidence for Units 1.1,
1.3, 1.4, 1.5, and 1.7 through its versioned ABI, multi-root membership checks,
executable model comparison, exact lowering/ABI audit, and source-bound freestanding
images. Every listed construction unit remains `partial`: Gate 3 scalar/control-flow
work and all later loop, memory, device, trap, timer, monitor, and qualification gates
remain open. The suite deliberately remains `core0-v0.1` and introduces no managed
Lean runtime.

No Stage II unit is marked passed. In particular, later Task 002 M-mode work will not
by itself satisfy Unit 2.1's supervisor-entry requirement. G1 and G2 remain
incomplete, and Task 002 is not complete.
