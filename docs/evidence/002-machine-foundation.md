# Task 002 machine-foundation evidence

This is a living evidence record for the highest passing prefix of Task 002. Gates 0
through 4 have passed. Gate 5 and every later gate remain open. This record does not
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
- Gate 3 implementation checkpoint:
  `9519adcc1f72fbf06a5f888e387e561df9f1604a`, tree
  `ef80a9cdf95e150606344ee84551128231092937`.
- Gate 4 implementation and current cumulative clean verification source:
  `16e7461e009e09390c0e9682d5800cae9fdd90d3`, tree
  `ee8840a642aa3acc03a8759242cc477a7b8c2eb2`.
- Branch: `task/002-machine-foundation`, stacked on Task 001.

The historical Gate 0 clean aggregate was `build/core0/check/check-results.json`,
SHA-256 `3a3cb9244b4a84b1a93ff869843aa3619622719ef6f431067e5502cbefc58a7c`.
Gate 1 first passed at `8878d2c...`; it was then rerun as part of the cumulative clean
Gates 1-2 command at `687ee7e...`. All 14 current Gate 1 control/mutant provenance
records, both Gate 2 profiles, and the current Task 001 O0/O2 release records name the
full `687ee7e...` commit and record `dirty_tree: false`.

The current cumulative clean run repeated Gates 1-4 at `16e7461...`. Its Gate 1
records and all Gate 2, Gate 3, and Gate 4 profiles name that full commit and record
`dirty_tree: false`; the earlier per-gate identities remain historical checkpoints
rather than being overwritten.

Generated build output remains ignored. The durable identities of the cumulative
clean records are:

| Record | SHA-256 |
|---|---|
| `build/foundation/gates1-2-clean/all-results.json` | `45ba122a148518e76062512f7358d536c16924f1bd881380d69c4819da02a158` |
| `build/foundation/gates1-2-clean/gate1/gate1-results.json` | `b09cfaa81a8e1d567f3afe492570bd04112c86cec9378cb9cfab987e64a9bffe` |
| `build/foundation/gates1-2-clean/gate2/gate2-results.json` | `6b3e775f3f7ffeb17ed5b9d781d8ae38815afea07944d3e7fc45de21beb3b5cc` |
| `build/foundation/gate3-clean-9519adc/gate3-results.json` (authoritative focused Gate 3 report) | `82bc01be3efd4f4da1f88eb20e61f36035c4499a2c100ec08bfbed2d7ae2fb6c` |
| `build/foundation/gates1-3-clean-9519adc/all-results.json` | `023ed2f602194dbf376de335fc8a507a0b496727b85498dde2ce0049915dea34` |
| `build/foundation/gates1-3-clean-9519adc/gate1/gate1-results.json` | `d9535b416a3a7889fd3bb3262d0e4d3b1c3d1170ffcddd0b9a473d4982777b46` |
| `build/foundation/gates1-3-clean-9519adc/gate2/gate2-results.json` | `b8ee9c7f1e6f1bfe69481885e0adc31000acb388a51c76d3e6192a3f145b91bf` |
| `build/foundation/gates1-3-clean-9519adc/gate3/gate3-results.json` | `707315b5875d12f2a0c1dd33276ff35f143d0aafae0ad20ce44b8a8e315df4a6` |
| `build/foundation/gate4-clean-16e7461/gate4-results.json` (authoritative focused Gate 4 report) | `a88ad21498f64b3bc69305ca70603c2c14057c36d48ba812e3a772cc284f611a` |
| `build/foundation/gates1-4-clean-16e7461/all-results.json` | `19f507b7317afcf318a4e4c1c3297f5dec421fc92c2aa2062ce61108bad1055e` |
| `build/foundation/gates1-4-clean-16e7461/gate1/gate1-results.json` | `455c3604a118d7498a94fce557dfd9cef831eb688dddd20059cf4fd3ff72d52e` |
| `build/foundation/gates1-4-clean-16e7461/gate2/gate2-results.json` | `13e765d2d25d35b2b3e699d9fe76c840ac098a32e60007600d06a4086f4c7de4` |
| `build/foundation/gates1-4-clean-16e7461/gate3/gate3-results.json` | `ed73878b77a820d8953e72fe9172f14778727c1bd76d5d8526de7b4a7a632059` |
| `build/foundation/gates1-4-clean-16e7461/gate4/gate4-results.json` | `6883d1089ae7167192320785ed1a060659178edbc515ef035dc73a4eb71ffbf7` |
| `build/core0/check/check-results.json` (same-source legacy regression) | `36ca3fd1b5e04c243322bda4fc8597fc2d29378493cf6fcbe05048d7c5606404` |

## Commands actually executed at the current clean source

| Command | Exit | Actual result |
|---|---:|---|
| `nix develop --no-write-lock-file --command lake build` | 0 | 29 jobs; complete Lean library build; 36 compile-time CFG validator checks |
| `python3 scripts/check_scaffold.py` | 0 | metadata valid: 7 gates, 56 software units, 6 physical units |
| `python3 -m unittest discover -s tests/scaffold -v` | 0 | 18/18 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v` | 0 | 21/21 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v` | 0 | 142/142 passed |
| `nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean` | 0 | 10 cases/profile, 13 intended rejections, 23 fresh QEMU boots |
| `git status --short --branch && nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 4 --work-dir build/foundation/gate4-clean-16e7461 --clean --timeout 180 --qemu-timeout 10` | 0 | Clean status `## task/002-machine-foundation`; Gate 4 passed: 7 roots, 112 cases/profile, 14 fresh QEMU boots |
| `nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all --work-dir build/foundation/gates1-4-clean-16e7461 --clean --timeout 300 --qemu-timeout 10` | 0 | Gates 1-4 passed: Gate 1 used 24 boots, Gate 2 used 136, Gate 3 used 88, Gate 4 used 14 |

All commands in this table ran after the implementation was committed, from clean
source `16e7461...`. The focused Gate 4 report is the detailed authority for Gate 4;
the cumulative report separately proves that Gates 1-4 still pass together. The
legacy Core0 report also binds both O0/O2 audits to `16e7461...` with
`dirty_tree: false`.

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

## Gate 3: structured control flow and total scalar operations

Gate 3 introduces the explicit `core0-v0.2` profile without changing
`core0-v0.1`. The new checked IR and lowering support structured basic blocks,
conditional branches, merge values, fixed-width complement, left and logical-right
shifts, and unsigned division/remainder for UInt8, UInt32, and UInt64. Signed
arithmetic was not added. The 44 roots lower to 47 checked functions and retain 49
used primitive identities; source conditionals lower through branches and phi nodes,
not eager evaluation through `select`.

The deterministic corpus uses suite ID `0xb15c8d071a8dc520`, source seed
`0x4c454d4d41333033`, runtime seed `0x52554e54494d4533`, and `SplitMix64-v1`
with fixed scalar/CFG boundary pools. Its 708 distinct cases/profile cover all 44
roots in 44 batches/profile. Direct source and checked model agreed on all 708 cases;
both have result SHA-256
`eabc0c7033b47f1d96c2df0164195e10221886447989b4152287fa65f858b4a9`.
O0 and O2 each ran all 708 cases in 44 QEMU boots and matched the same result digest,
for 1,416 source/model/target profile matches and 88 target boots total. Fifteen
notation/direct metamorphic pairs cover complement, shift, division, and remainder
at all three widths.

### Pinned source semantics and profile compatibility

The run executed
`lake env lean examples/foundation/ScalarV2PinnedSemantics.lean` and retained 18
direct-source probes: complement, divide-by-zero, remainder-by-zero, shift-by-width,
shift-by-width-plus-one, and right-shift-by-maximum-count at each of UInt8, UInt32,
and UInt64. The observed contract is:

- complement is fixed-width;
- shift counts reduce modulo the operand width;
- unsigned division by zero returns zero; and
- unsigned remainder by zero returns the dividend.

The probe source SHA-256 is
`2d45bfa0bd410c3bbfb0f4694c50191e06e4a7f60060851ae4fb34d13a710e82`;
its stdout SHA-256 is
`f6f6edc79d777fef3d6df66d721df9f91876d41e78877366a2118fae308a067e`.
The inspected pinned Lean UInt source has SHA-256
`d0f463c78f6c92585caffef53154cadd3c3e0f3b1681584f19e85d8e5da15c94`.

Compatibility was tested rather than inferred: all 13 legacy rejection fixtures
still rejected under `core0-v0.1`; eight new `core0-v0.2` fixtures rejected custom
division, remainder, left-shift, right-shift, and complement instances, signed
division, UInt16, and a branch-hidden arbitrary extern; and a separate probe rejected
unsupported `core0-v0.3` in the parser and reference model. Every suite/ABI manifest
records its exact profile.

### CFG and dangerous-operation audit

The validated pre-optimization module has 47 checked functions, 44 roots, and 51
audited call sites. Its structured audit records 18 guarded division/remainder sites,
18 exact same-block shift-mask sites, eight source functions containing branches,
and zero source `select`s. The divisor nonzero block must be the unique false
successor of an exact zero guard, must not be reachable from the zero successor, and
must have no alternate predecessor. Shift counts must come from the exact source
count masked by 7, 31, or 63 in the same block. O0 and O2 machine code contains
native unsigned divide/remainder and shift instructions; post-optimization flags are
audited separately so optimizer-inferred O2 flags are not attributed to the emitter.

All seven fail-closed audit mutations were detected:

| Mutation | Kind | Mutant IR SHA-256 | Required diagnostic |
|---|---|---|---|
| `wrong-divisor-guard-operand` | wrong guard | `f842cdeec0f3d67bd9dda9781717372e03e6d71b967c14cdf4d6eed7313c9058` | `not the unique false successor` |
| `inverted-divisor-guard-edges` | wrong guard | `7cfa67adca6f0072bee9e6efa7cc809e7eb3c9a40e608b91f50390c5ecd4dfa9` | `not the unique false successor` |
| `zero-edge-reaches-dangerous-block` | wrong guard | `f7d14d3032903698fba215517c458b7dfbbc1c61a7c6fd3f66f83b66c6895773` | `reachable from the divisor-zero successor` |
| `unguarded-dangerous-block-predecessor` | wrong guard | `86b81cb40b018fcca5e58df810ea0385b2d06b153b3970a3f5e0659a28b6039b` | `unguarded predecessor set` |
| `wrong-shift-count-mask` | wrong count handling | `839e6f54ba4b23aaeeacf48a08d615e1dacc933ee5fee632e478745e427e6daf` | `same-block source-count` |
| `wrong-shift-count-source` | wrong count handling | `e5f182911f2c9764b74d393c0da96d25a2a845fb3f321c7b4cc842616d8dd71c` | `same-block source-count` |
| `unsupported-contract-version` | profile version | manifest mutation, no IR artifact | `unsupported Core0 contract` |

The two profiles use byte-identical checked source artifacts and the same
pre-optimization IR:

| Shared checked artifact | SHA-256 |
|---|---|
| `scalar-suite-manifest.json` | `0b6ab4f9051c9f688236e771a8d5b3dc24baf09500b3807f804f50eefb068b62` |
| `scalar-suite-normalized.txt` | `804b3bc0cd5e7608e0f613d2736c9dc36e6ed54c2cd533cabc62b831fc530836` |
| `scalar-test-abi.json` | `b1beaa206470404f55c6a1b1fec8efb1fd26d7967495671034a113eed06fa515` |
| `symbols.txt` | `ac4ab5a6da285c70ba30617c2a57114674336bdf780dddd27e6aa0b17cff6cc4` |
| `program.ll` | `9e3053f7dbceb2c4cd423e3e29056afaf0710431ca848f8aab43aa9fed18cf2b` |

Their profile-specific retained artifacts are:

| Profile | Audit SHA-256 | Optimized IR SHA-256 | Image SHA-256 |
|---|---|---|---|
| O0 | `9d41571fe1667da1e05f5f05af556bde3408495d100c896829256d96e621761a` | `0414c988cd850b7a9e4bd892767562797be9b0719de1744c52800073024311c7` | `48c3c1b04a5532d8cb441a824b8aa68532598c6eeea8c234cdccf07a34ebb2c0` |
| O2 | `03fa90658dc63a483007860a424f4af20c6b980ca071a5c541f13e4686d030f5` | `06f09dcca3ce1df8afc4e2fc56e13e8231a59d45e482c4cc3980b419afa59e85` | `4e14cae828732613cbaa427905bdffc508a5060a78b7118d3e439472de8ab7f1` |

### Local mathematical lemmas and their limits

The run checked eight named scalar lemmas and recorded their exact axiom
dependencies:

| Theorem | Recorded axioms |
|---|---|
| `fixedWidthNormalize_lt` | none |
| `fixedWidthNormalize_idempotent` | `propext` |
| `maskedShiftCount_lt` | none |
| `shiftCountMask_eq_mod` | `propext`, `Classical.choice`, `Quot.sound` |
| `shiftCountMask_lt` | `propext`, `Classical.choice`, `Quot.sound` |
| `u8ToU32ToU8` | `propext` |
| `u8ToU64ToU8` | `propext` |
| `u32ToU64ToU32` | `propext` |

`Lemma/Core0/ScalarLemmas.lean` has SHA-256
`6fa63d2d99f94092eb96942c294deaef7b5f0d17e2e0c5ce5989a3847a459497`.
The dependency-probe source and stdout SHA-256 values are respectively
`c0978395ea7deb6aa254e705cec63c9096f2c0c82a273e71e031db869ea0562d` and
`f7b2ebfe4a7eeafdb60b823a29fffc05da67b9f3b2780932b9107e37e10adfd8`.
These are local normalization, shift-mask, and conversion-round-trip invariants.
They do not prove the frontend, CFG lowering, LLVM optimizer, code generator, audit,
or whole compiler correct.

### Pinned tools and machine contract

The Gate 3 report binds `tooling/toolchain-lock.json`, SHA-256
`314fa2842766f300308c8a703581a1f07f12eb2332f9e63bb2e96e7c58230872`.

| Tool | Exact pin |
|---|---|
| nixpkgs | revision `7dd199b0e2993e37b4775ed66b1c291699608c9f` |
| Lean / Lake | Lean 4.34.1, Lake 5.0.0-src; ref `v4.34.1`; revision `5045d0056413266e57c625dcd7c365b10e377c52`; binary `--githash` unavailable, so the Nix source identity is authoritative |
| LLVM `opt`/`llc`, Clang, LLD | 20.1.8; ref `llvmorg-20.1.8`; revision `87f0227cb60147a26a1eeb4fb06e3b505e9c7261`; tag object `023ec9011c9a92cfa8922030eb266d66a10f78f8` |
| QEMU | 11.1.1; ref `v11.1.1`; revision `c3d48b7d1e89604920e5b81b91140c2ad39a1943`; tag object `5e35f26695645b20931e10d8567c7e0169e62c07` |
| DTC / Python / jq / Nix | 1.8.1 / 3.14.7 / 1.8.2 / 2.31.2 |

The target remains `riscv64-unknown-elf`, integer/soft-float LP64,
`rv64im_zicsr_zifencei`, QEMU `virt`, one hart, 128 MiB RAM, no firmware, and no
compressed instructions. Gate 3 did not add a managed Lean runtime.

## Gate 4: bounded iteration

Gate 4 introduces the explicitly selected, additive `core0-v0.3` profile while
preserving the `core0-v0.1` and `core0-v0.2` contracts and rejection behavior. It
admits exactly one higher-order-looking compiler-recognized source identity:

```lean
Lemma.Core0.Bounded.boundedFoldU32
  (budget : Nat)
  (step : UInt32 -> UInt32 -> UInt32)
  (count initial : UInt32) : UInt64
```

The budget must be a canonical standard `Nat` literal in `0..256`. The callback must
be a direct safe, total, monomorphic top-level declaration with exactly the displayed
type; its ordinary helpers are checked as transitive Core0 dependencies. The budget
and callback identity are compile-time data. They do not become a guest `Nat`,
closure, environment, function pointer, or higher-order dispatch mechanism.

`count` and `initial` are runtime `UInt32` values. If `count.toNat <= budget`, the
callback receives `(index, accumulator)` for ascending zero-based indices through
`count - 1`, and the final accumulator is zero-extended to `UInt64`. If
`count.toNat > budget`, no callback executes and the result is
`0x8000000000000000 ||| initial.toUInt64`. Bit 63 identifies exhaustion, bits 62
through 32 are zero, and the low 32 bits retain the unchanged initial value. This
semantic budget exhaustion is distinct from a checked-model expression/call
traversal-fuel diagnostic and from host or QEMU timeout enforcement.

### Genuine checked loop lowering and target execution

The seven genuine elaborated roots are `sumFold`, `sumFoldChanged`, `bitMixFold`,
`nestedFold`, `helperFold`, `zeroBudgetFold`, and `maxBudgetFold`. Their transitive
closure contains 14 checked functions and eight bounded-fold sites; the nested root
accounts for two sites. Checked structured lowering emits an unsigned runtime budget
guard, scalar `i32` index and accumulator phi nodes, one direct callback call on the
body edge, a plain wrapping index increment, an actual backedge, a zero-extension on
success, and a tagged `i64` exhaustion edge. Iteration uses fixed call frames rather
than recursive calls, and the exhaustion path cannot reach the callback.

The retained pre-optimization audit binds all eight sites to the exact source budget
and callback catalog and checks their guard, preheader/header/body/latch/exit shape,
phi inputs, callback argument order, increment, success value, and exhaustion edge.
It also preserves the v0.2 audit premises for scalar operations. The machine audit
finds exactly one direct callback call and a backward branch for each of the seven
positive-budget loop functions under both O0 and O2. The zero-budget site remains in
the checked IR catalog but does not require a runtime backedge; O2 removes its dead
callback and loop. Thus the QEMU results come from runtime-counted RV64 loops, not
compiler-side unrolling or a host simulation.

No audited loop function uses a dynamic stack adjustment. The stack report combines
the optimized LLVM direct-call graph with the object's `.stack_sizes` metadata,
requires that graph to be acyclic, and sums the maximum frame chain against the
64 KiB stack limit. The observed maximum is 1,856 bytes at O0 and 176 bytes at O2.
This bound is specifically an optimized-LLVM direct-call graph weighted by object
metadata, not a claim that every possible machine call edge was reconstructed.
Machine disassembly separately establishes the retained direct callback calls and
backedges.

The source emitter asserted no `disjoint`, `nuw`, `nsw`, or `inbounds` premise. O2
inferred 23 `or disjoint` instructions. The fail-closed post-optimization inventory
accepted exactly seven exhaustion-tag ORs whose payloads are zero-extended `UInt32`
values and 16 hexadecimal-formatting ORs combining low nibbles with ASCII `0x30`.
All 23 operands were locally proven disjoint; no other inferred form was accepted.
O0 retained zero `disjoint` instructions.

### Four comparison routes and adversarial evidence

The deterministic corpus uses suite ID `0xb1e51d2902bca153`, source seed
`0x4c454d4d41343034`, runtime seed `0x52554e54494d4534`, and `SplitMix64-v1` with an
exact bounded-count boundary pool. It contains 112 distinct cases over all seven
roots and is split into seven batches/profile. Direct evaluation of the original
Lean declarations, the checked Core0 model, and an independent Python model agreed
on all 112 results, with result SHA-256
`38ad1a02fc9dd60f482b533ea5492b465643cda5231a0ad26883d4026d392f62`.
The Python model shares the documented arithmetic contract, but not the Lean
evaluator implementation. O0 and O2 each executed all 112 cases in seven fresh QEMU
boots and matched the same digest, giving 224 source/model/target profile matches and
14 boots total.

The `sumFold` and `sumFoldChanged` roots use identical inputs but distinct source
callback bodies. Six of the 16 successful comparison inputs produced distinct
results. The first recorded witness has count 1 and initial `0xffffffff`: the
unchanged callback body returns `0x00000000ffffffff`, while the changed body returns
`0x0000000000000000`. This binds target behavior to the source callback body rather
than only to its declaration name.

The audit detected nine structured-LLVM loop mutations: wrong static budget, wrong
budget predicate, index starting at one, stale accumulator phi, swapped callback
arguments, wrong index increment, missing backedge, missing exhaustion tag, and an
exhaustion path reaching the callback. It also detected four manifest mutations for
tampered budget/callback and incomplete site/function closure, plus one unsupported
profile-version mutation. These are audit fixtures, never production compiler inputs.

All 11 exact frontend fixtures rejected: capturing, dynamic, and polymorphic
callbacks; a direct arbitrary extern callback; a forbidden extern hidden behind a
callback helper; a lookalike combinator; a nonliteral budget; budget 257; a recursive
callback; and attempts to use the bounded construct under `core0-v0.1` or
`core0-v0.2`. The last two preserve the older profiles rather than silently widening
them.

Three local source-semantics lemmas were checked with their exact dependency output:

| Theorem | Recorded axioms |
|---|---|
| `executedIterations_le_budget` | `propext` |
| `boundedFoldU32_exhausted` | `propext`, `Quot.sound` |
| `boundedFoldU32_zero` | `propext`, `Quot.sound` |

`Lemma/Core0/Bounded.lean` has SHA-256
`19600082ec9b26ee297e001deca524cebe896e96b03c29f607df5f693b344305`.
The dependency-probe source and stdout SHA-256 values are respectively
`eb2ab935ac6d37273a5741261224c8648e635d1f55fed9725656a84c44935197`
and `4065ac14230bcb6912555b00483ed23fd8cf39055fc0d9fa4239de213339961f`.
These facts constrain the source combinator; they do not prove frontend, lowering,
LLVM, machine-code, or whole-compiler correctness.

### Retained Gate 4 artifacts

The O0 and O2 builds carry the same clean source commit and byte-identical checked
manifest, normalized suite, typed ABI, symbol map, and pre-optimization LLVM:

| Shared checked artifact | SHA-256 |
|---|---|
| `bounded-suite-manifest.json` | `7ce0f74cde332acdb60e14de8edf96fe4ab292654bd3cb3fc61866653c728300` |
| `bounded-suite-normalized.txt` | `7b7a2601b3256df1e976e7702cb7680e93d23cd90ecc205751c30885181b3e10` |
| `scalar-test-abi.json` | `1ef34a43553748f75c897c669d19c0dc7235d28af502a4201df39e96037cd5d7` |
| `symbols.txt` | `fbdf607644c1f0da61e032f70d07724406da0cbfde35f9d1d28117084ca86bea` |
| `program.ll` | `88c9da324e8dcf1629416690a7309173c417c8c2675a6b0488f61ef64a9891fe` |

Their profile-specific retained artifacts are:

| Profile | Audit SHA-256 | Optimized IR SHA-256 | Stack-size report SHA-256 | Image SHA-256 |
|---|---|---|---|---|
| O0 | `74d5fcbe006afde2badeb0e3468cdea511e3384e934ef985ff50db164c9fb259` | `cf400e19dbf948f411186d9a1380e550b8524b5d73421ccf9d4eacbc1f048d06` | `a5930212727612e1edeaf14cc980e33168f988dba0944e82484eb71337a4b90f` | `68a2624214b03d5b05d170fd08e6537cc2284bd2fe1114225e3d9f74b8e42464` |
| O2 | `461492bb14cb911a764ccc8e4e6837ca86e68ffc26c4498cfbe0865b0c35be5f` | `e7840296cdb0a92d3c923b4eb2983ffc90e5033524fab9cf104c454cad0a34a9` | `99ea1b90d7118ac624d57e052fa03de3aa1e30342d4e2f6dd34892210c5d41b1` | `1bb445b821725b8cccf4d5c58d984cceaf7c9f6f8303c7a6209707b80f0d7b6d` |

The focused report records seven pinned source probes, three lemmas, 11 frontend
rejections, nine IR mutants, four manifest mutants, and one profile mutant in
addition to the full comparison matrix. Its SHA-256 is
`a88ad21498f64b3bc69305ca70603c2c14057c36d48ba812e3a772cc284f611a`.
The separate cumulative Gates 1-4 report and all four child identities are listed in
the source-identity table above.

## Shared assumptions, stage mapping, and limits

The direct and checked-model routes are deliberately separate computations, but both
share the pinned Lean 4 host elaborator and type checker. They are not absolutely
independent proof systems; the target route also consumes the same checked source
before LLVM lowering. Gate 4 adds an independent Python computation that shares only
the documented bounded arithmetic contract, but this fourth route is still finite
testing rather than a proof. The exhaustive UInt8 comparison, 1,024-case wider-type
matrix, Gate 3's 708-case matrix, Gate 4's 112-case matrix, and metamorphic/body-change
checks are strong finite evidence, not a compiler-correctness or semantic-preservation
proof. Gates 3 and 4 add local mathematical lemmas with recorded axiom dependencies,
but no whole-compiler proof or separate kernel-reduction comparison. The exact ABI
audit covers one deliberate ten-argument shape, not every possible RISC-V ABI
signature.

Gates 1 and 2 directly advance Unit 1.8. Gate 2 also adds evidence for Units 1.1,
1.3, 1.4, 1.5, and 1.7 through its versioned ABI, multi-root membership checks,
executable model comparison, exact lowering/ABI audit, and source-bound freestanding
images. Gate 3 directly advances Units 1.1, 1.3, 1.4, 1.5, 1.7, and 1.8 through
versioned membership rejection, executable scalar semantics, validated structured
lowering, dangerous-operation audit mutations, and differential target execution.
Gate 4 advances the same partial Stage I units with a versioned bounded construct,
transitive callback checks, validated loop lowering, machine backedge/callback
evidence, stack bounds, mutations, and source/model/Python/target comparison. The
explicit profiles and trust manifests plus source-bound images account for the added
1.1 and 1.7 evidence. Units 1.2 and 1.6 receive regression coverage only; neither
Gate 3 nor Gate 4 adds a new LemmaVM or machine-primitive capability. Every listed
construction unit remains `partial`; checked fixed-region memory, device, trap,
timer, monitor, and qualification gates remain open.

No Stage II unit is marked passed. In particular, later Task 002 M-mode work will not
by itself satisfy Unit 2.1's supervisor-entry requirement. G1 and G2 remain
incomplete, and Task 002 is not complete. Gate 5 checked fixed-region memory is the
next executable gate.
