# Task 002 session state

- Base: Task 001 report-bearing commit `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`
  (tree `88d2c23aafbd2b3a40a195755c01494de9ffad75`), stacked because PR #1 is unmerged.
- Working branch: `task/002-machine-foundation`.
- Highest passing gate: Gate 6.
- Current gate: Gate 7, in progress; no Gate 7 acceptance checks have run.
- Current failure: none; synchronous-trap implementation is starting after clean
  Gate 6 focused, cumulative, and legacy acceptance.
- Latest clean passing implementation: `179ef541e7cfa53235322610222a01ccdf9364cd`
  (tree `9ff742607b5b1d73924928bf147dabada037f406`).
- Report-bearing revision: later/unassigned; do not confuse it with tested source.
- Next executable action: implement the separately versioned structured trap entry,
  full integer context preservation, compiled dispatch, authorized ECALL/EBREAK
  return, fatal/double-fault paths, and target register/canary/denied-RAM tests for
  Gate 7. Continue through Gates 8--11 after each prerequisite passes.

## Gate 0 historical checkpoint

Executed against clean `b8e9c593...` source on 2026-10-08:

```text
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 expected rejections, 23 fresh QEMU boots
```

Historical aggregate SHA-256:
`3a3cb9244b4a84b1a93ff869843aa3619622719ef6f431067e5502cbefc58a7c`.

## Gate 1 historical and cumulative checkpoint

Gate 1 first passed against clean implementation `8878d2c...` (tree
`a110453f...`) with 2 controls, 12 mutants, 3 intended source rejections, 7 audit
regressions, 24 fresh QEMU boots, and 12/12 verified behavioral mismatches. Its first
aggregate SHA-256 was
`a3fd012ad0dac0d20e16321c32c7006502b8c22921499517bab1468b669bf50c`.

The same complete Gate 1 checks were rerun in the cumulative clean Gates 1-2 command
at `687ee7e...`. The current Gate 1 aggregate is
`build/foundation/gates1-2-clean/gate1/gate1-results.json`, SHA-256
`b09cfaa81a8e1d567f3afe492570bd04112c86cec9378cb9cfab987e64a9bffe`.
All 14 control/mutant provenance records name that commit and are clean.

## Gate 2 commands and observed results

Executed against clean source `687ee7e...` on 2026-10-08:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 20 jobs
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 86/86 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 rejections, 23 fresh QEMU boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-2-clean --clean --timeout 300 --qemu-timeout 10
  exit 0; GATES 1-2 PASS; Gate 1: 24 boots; Gate 2: 136 boots
```

Gate 2 recorded 37 genuine elaborated roots, 1,024 distinct cases/profile, 61 valid
and 7 negative boots/profile, 1,024 direct-source/model matches, 2,048
source/model/target profile matches, five metamorphic pairs, and 327,680 exhaustive
UInt8 direct/model comparisons. O0 and O2 retain a real audited ten-argument RV64
call with narrow ninth/tenth arguments, a 32-byte 16-aligned caller frame, and exact
LP64 extension attributes.

Evidence identities:

- cumulative Gates 1-2:
  `45ba122a148518e76062512f7358d536c16924f1bd881380d69c4819da02a158`;
- Gate 2:
  `6b3e775f3f7ffeb17ed5b9d781d8ae38815afea07944d3e7fc45de21beb3b5cc`;
- cumulative Task 001 regression:
  `30a4b52daf4703df172137eef828a5b6d4052efa42b7cc6c95b099edf05361fe`.

## Gate 3 commands and observed results

Executed against clean committed source `9519adcc...` on 2026-10-08:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 26 jobs; 29 compile-time CFG validator checks
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 125/125 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 rejections, 23 fresh QEMU boots
git status --short --branch && nix develop --no-write-lock-file --command \
  ./scripts/check-foundation.sh --phase 3 \
  --work-dir build/foundation/gate3-clean-9519adc --clean --timeout 180 --qemu-timeout 5
  exit 0; clean status `## task/002-machine-foundation`; Gate 3 PASS;
  44 roots, 708 cases/profile, 88 fresh QEMU boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-3-clean-9519adc --clean --timeout 300 --qemu-timeout 10
  exit 0; GATES 1-3 PASS; Gate 1: 24 boots; Gate 2: 136 boots; Gate 3: 88 boots
```

Gate 3 recorded 44 genuine elaborated roots and 47 checked functions under the new
`core0-v0.2` profile. Per O0/O2 profile, 708 distinct cases ran in 44 target boots;
direct source/model agreed 708/708 and source/model/target agreed 1,416/1,416 across
both profiles. The run retained 15 notation/direct metamorphic pairs, 18 pinned Lean
source probes, 13 unchanged `core0-v0.1` rejections, 8 new-profile rejections, one
unsupported-profile probe, eight checked scalar lemmas, six detected CFG mutants,
and one detected profile-version mutant.

Focused Gate 3 report:
`build/foundation/gate3-clean-9519adc/gate3-results.json`, SHA-256
`82bc01be3efd4f4da1f88eb20e61f36035c4499a2c100ec08bfbed2d7ae2fb6c`.
The clean cumulative Gates 1-3 aggregate is
`build/foundation/gates1-3-clean-9519adc/all-results.json`, SHA-256
`023ed2f602194dbf376de335fc8a507a0b496727b85498dde2ce0049915dea34`;
its Gate 1, Gate 2, and Gate 3 child hashes are respectively
`d9535b416a3a7889fd3bb3262d0e4d3b1c3d1170ffcddd0b9a473d4982777b46`,
`b8ee9c7f1e6f1bfe69481885e0adc31000acb388a51c76d3e6192a3f145b91bf`, and
`707315b5875d12f2a0c1dd33276ff35f143d0aafae0ad20ce44b8a8e315df4a6`.
The same-source legacy report is `build/core0/check/check-results.json`, SHA-256
`a8812a1ea1b2b1c2794d088d25a1fb5f8e878bfd022bd93a71159f04f46e0daa`.

## Gate 4 commands and observed results

Executed against clean committed source `16e7461e...` on 2026-10-08:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 29 jobs; 36 compile-time CFG validator checks
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 142/142 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 rejections, 23 fresh QEMU boots
git status --short --branch && nix develop --no-write-lock-file --command \
  ./scripts/check-foundation.sh --phase 4 \
  --work-dir build/foundation/gate4-clean-16e7461 \
  --clean --timeout 180 --qemu-timeout 10
  exit 0; clean status `## task/002-machine-foundation`; Gate 4 PASS;
  7 roots, 112 cases/profile, 14 fresh QEMU boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-4-clean-16e7461 \
  --clean --timeout 300 --qemu-timeout 10
  exit 0; GATES 1-4 PASS; Gate 1: 24 boots; Gate 2: 136 boots;
  Gate 3: 88 boots; Gate 4: 14 boots
```

Gate 4 added the explicitly selected `core0-v0.3` profile and only the recognized
`Lemma.Core0.Bounded.boundedFoldU32` construct. Its canonical literal budget is in
`0..256`; its callback is a direct safe, total, monomorphic top-level
`UInt32 -> UInt32 -> UInt32` declaration; and its runtime count and accumulator are
`UInt32`. In-budget execution visits zero-based indices in ascending order and
returns the final accumulator zero-extended to `UInt64`. Exhaustion executes no
callback and returns bit 63 OR the unchanged initial accumulator, with bits 62..32
zero. Semantic exhaustion remains distinct from model traversal fuel and host/QEMU
timeouts.

The seven roots have a 14-function checked closure and eight pre-optimization LLVM
loop sites. In both O0 and O2, all seven positive-budget loop functions retain
exactly one direct callback call and a machine backedge. The zero-budget site remains
part of the checked IR catalog but does not require a runtime backedge. The audit
found no dynamic stack adjustment and measured acyclic optimized-LLVM direct-call
graphs using object `.stack_sizes`: worst summed chains are 1,856 bytes at O0 and
176 bytes at O2, both below 64 KiB. This is not a reconstruction of every possible
machine call edge; the disassembly audit separately establishes the direct callback
calls and backedges.

Direct Lean evaluation, the checked Core0 model, and the independent Python model
agreed on all 112 cases. Each target profile matched all 112 results, giving 224
source/model/target profile matches. A changed callback-body witness produced six
distinct successful result pairs across 16 identical inputs. The negative matrix
detected nine LLVM loop mutations, four manifest mutations, one profile-version
mutation, and all 11 frontend rejections. Three local bounded-semantics lemmas were
checked; their only recorded dependencies are standard `propext` and `Quot.sound`.
O2's 23 inferred `or disjoint` instructions were all inventoried and justified: 7
exhaustion-tag sites and 16 low-nibble/ASCII-`0x30` formatting sites; pre-optimization
IR contains none.

Focused Gate 4 report:
`build/foundation/gate4-clean-16e7461/gate4-results.json`, SHA-256
`a88ad21498f64b3bc69305ca70603c2c14057c36d48ba812e3a772cc284f611a`.
The clean cumulative Gates 1-4 aggregate is
`build/foundation/gates1-4-clean-16e7461/all-results.json`, SHA-256
`19f507b7317afcf318a4e4c1c3297f5dec421fc92c2aa2062ce61108bad1055e`;
its Gate 1, Gate 2, Gate 3, and Gate 4 child hashes are respectively
`455c3604a118d7498a94fce557dfd9cef831eb688dddd20059cf4fd3ff72d52e`,
`13e765d2d25d35b2b3e699d9fe76c840ac098a32e60007600d06a4086f4c7de4`,
`ed73878b77a820d8953e72fe9172f14778727c1bd76d5d8526de7b4a7a632059`, and
`6883d1089ae7167192320785ed1a060659178edbc515ef035dc73a4eb71ffbf7`.
The same-source legacy report is `build/core0/check/check-results.json`, SHA-256
`36ca3fd1b5e04c243322bda4fc8597fc2d29378493cf6fcbe05048d7c5606404`.

## Gate 5 commands and observed results

Verified for implementation source `ff8ef0f...` on 2026-10-08. Build/unit suites
ran on the final tree immediately before commit; the focused, cumulative, and legacy
artifact checks ran afterward from the clean commit:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 37 jobs; 40 compile-time CFG validator checks
python3 scripts/check_scaffold.py
  exit 0; metadata PASS (7 gates, 56 software units, 6 physical units)
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 21/21 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 196/196 PASS
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  exit 0; 10 cases/profile, 13 rejections, 23 fresh QEMU boots
git status --short --branch
  exit 0; clean status `## task/002-machine-foundation`
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 5 \
  --work-dir build/foundation/gate5-clean-ff8ef0f --clean --timeout 300 --qemu-timeout 15
  exit 0; Gate 5 PASS;
  26 roots, 52 cases/profile, 104 fresh QEMU boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-5-clean-ff8ef0f --clean --timeout 300 --qemu-timeout 15
  exit 0; GATES 1-5 PASS; Gate 1: 24 boots; Gate 2: 136 boots;
  Gate 3: 88 boots; Gate 4: 14 boots; Gate 5: 104 boots
```

Gate 5 added the explicitly selected `core0-v0.4` Action profile. Its closed fixed
table separates four ordinary 4 KiB regions from reserved image/stack regions and
UART/finisher devices. It implements 8/32/64-bit checked loads/stores, range
preflight, subtraction-first bounds, fixed alignment and permissions, a two-word
checked result, transitive RAM effects, and runtime-counted Action folds. MMIO remains
denied by the ordinary RAM interface.

The deterministic suite ID is `0xa20c6fd4108dbf27`; source and runtime seeds are
`0x4c454d4d41353035` and `0x52554e54494d4535`. The 26 roots cover 52 cases/profile.
O0 and O2 each matched all 52 independent-model outcomes and all 52 complete
16,384-byte ordinary-memory post-states. Across 104 boots, 1,703,936 region bytes and
1,040 boundary-canary values were checked. Scalar-result and post-state aggregate
digests are respectively
`66aef0a96804cba0e71f1c17d5e2cab272a3cc448b7abdf7a5caa752d2c71d19`
and `4b508bee3b64f17c8548a7db1dc6cbb11b6afc1514e440a8ce214db8eb06d544`.

The audit found 37 successful physical access sites and eight range sites/profile.
All 51 mutations rejected: 19 manifest/effect/closure and 32 LLVM mutations,
including changed store value, offset selection, region selection/branch routing,
guard/order/address defects, access duplication, and ABI corruption. All 14 frontend
fixtures rejected, five local model lemmas had no forbidden proof dependencies, and
18 pinned Lean model probes passed. The optimized call graph is acyclic; maximum
frame chains were 1,568 bytes at O0 and 240 bytes at O2 against the 64 KiB stack.

Evidence identities:

- focused Gate 5:
  `build/foundation/gate5-clean-ff8ef0f/gate5-results.json`, SHA-256
  `fa670e195ce2b4f8988850f8b1e2f10c3dc9eda7cb993b5f0dcf09f20cbe25d7`;
- cumulative Gates 1-5:
  `build/foundation/gates1-5-clean-ff8ef0f/all-results.json`, SHA-256
  `635c1ca0c7d3a4647297a978b109ce5b42d015a6ab46de676d8791b66261b863`;
- same-source legacy Core0:
  `build/core0/check/check-results.json`, SHA-256
  `ab160eebccc519922a537c181c83900c2838f690bd15c7ca49ba8906283b1c8f`.

## Gate 6 clean checkpoint

Verified implementation `179ef54...` on 2026-10-08. The final build/unit checks ran
on its tree immediately before commit: Lean build 44 jobs and 52 compile-time CFG
checks; metadata 7 gates/56 software/6 physical; scaffold 18/18, Core0 32/32, and
foundation 239/239 tests passed. The following commands then ran against the clean
implementation commit, all exit 0:

```text
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 6 \
  --work-dir build/foundation/gate6-clean-readback --clean --timeout 300 --qemu-timeout 20
  Gate 6 PASS: 14 scenarios/profile, 28 fresh boots, 16 runtime requests
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-6-clean-readback --clean --timeout 300 --qemu-timeout 20
  Gates 1--6 PASS: 24+136+88+14+104+28 = 394 fresh boots
nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean
  legacy PASS: 10 cases/profile, 13 intended rejections, 23 fresh boots
```

All 29 cumulative provenance records name exact clean `179ef54...` source. The
focused report SHA-256 is
`da4726d0c7f312c72295b70651a94cd4eeb69f5e99072dd6ba3f07676acd73a1`;
the cumulative aggregate is
`b82597eced2cd1e23bc9c589142c353e36d6f3414746194cdbb47be00ce3c2de`;
the current legacy aggregate is
`1a0e514c0ff086f6ca25679882c97e992c02f9e9eb6cbfe049e3552c5eaa0e09`.
Earlier legacy hashes above are historical because that output path was reused.

Gate 6's `core0-v0.5` compiles four closed ordered UART operations through one
elaborated root, 22 Action and 19 scalar functions. Both profiles exchange two
runtime requests in each of four interactive sessions; ten further sessions test
defined bounded terminal failures. All 36 audit mutants, five exact frontend
fixtures (including one legacy-profile rejection), twelve pinned-UART probes,
thirteen packet/source-model probes, and four local lemmas passed their checks.
Branch RAM evidence is direct: four target readbacks return `0x5a00` and `0x3c01`,
with the true branch's raw `0xa5` UART marker and preserved `0x3c` RAM sentinel.
Maximum acyclic frame chains are O0 2,736 bytes and O2 288 against a 65,536-byte stack.

This is polling-only pinned-QEMU evidence, not traps, interrupts, physical hardware,
compiler correctness, isolation, or G1/G2 completion. Separate detached-worktree
qualification, publication, and actual CI remain Gate 10/11 obligations.

## Decisions that must survive a resume

- Preserve `core0-v0.1` and its rejection corpus. Gate 3 added the explicitly
  separate `core0-v0.2` profile; do not silently expand either profile.
- Task 001 historical artifacts remain bound to `800d359...`; its clean report-bearing
  verification and GitHub synthetic merge are separately identified in Task 001
  evidence.
- Runtime input bytes are ASCII `LEMMA001`; the loaded little-endian word is
  `0x313030414d4d454c`. The separate Task 001 corpus tag is
  `0x4c454d4d41303031`.
- Gate 1 mutations are test-only Lean transformations, never production inputs. A
  mutant audit requires an audited clean control and proves that the reported
  replacement is the sole pre-optimization IR delta.
- Gate 2's additive typed ABI is `lemma-scalar-test-v1`, suite
  `0x7812482420151ea4`; it does not replace the legacy harness. Source and runtime
  seeds are `0x4c454d4d41323032` and `0x52554e54494d4532`.
- Direct-source and checked-model routes share the pinned Lean elaborator/type checker;
  the direct route does not import or call the Core0 checker/evaluator. Do not describe
  the three comparison routes as absolutely independent proof systems.
- Schema-2 provenance binds exact source and `.olean` inputs. O0/O2 Gate 2 profiles
  share byte-identical checked suite/ABI/source artifacts. The current cumulative
  run names clean `179ef54...` source; the earlier Gate 2 checkpoint remains
  historically bound to `687ee7e...`.
- Gate 3 pins Lean 4.34.1 revision `5045d0056413266e57c625dcd7c365b10e377c52`
  and the inspected `Init/Data/UInt/Basic.lean` SHA-256
  `d0f463c78f6c92585caffef53154cadd3c3e0f3b1681584f19e85d8e5da15c94`.
  Its declared semantics are fixed-width complement, shift counts modulo width,
  division by zero yielding zero, and remainder by zero yielding the dividend.
- Gate 3's eight scalar lemmas establish only local normalization, shift-mask, and
  conversion-round-trip invariants. Their recorded axiom dependencies do not turn
  the finite differential matrix into a compiler-correctness proof.
- The structured audit requires branch/phi source conditionals, exact same-block
  shift masks, and zero-guarded division/remainder with no dangerous alternate
  predecessor. Its six IR mutations and one profile mutation are audit tests, not
  production inputs.
- Gate 4's additive `core0-v0.3` recognizes only `boundedFoldU32`; it does not add
  closures, function pointers, recursive iteration, allocation, or a managed runtime.
  Preserve the semantic-exhaustion tag and its zero-callback behavior independently
  of evaluator fuel and process timeouts.
- Gate 4's stack bound is an optimized LLVM direct-call graph weighted by object
  `.stack_sizes`, while retained machine backedges and callback calls are separate
  disassembly evidence. Do not describe it as a fully reconstructed machine call graph.
- O2 optimizer-inferred `or disjoint` is accepted only for the retained closed
  inventory with local range proofs; the source emitter asserts no such premise.
- Gate 5's additive `core0-v0.4` recognizes only the closed Action/memory interface.
  Preserve lookup/class/permission/width/bounds/alignment order, subtraction-first
  checks, device exclusion, the two-word result ABI, and transitive effects. Complete
  target post-state is observed; model event traces are not separately instrumented
  on target.
- Gate 5's direct source-binding audit covers directly auditable normalized operands;
  computed expressions and Action-bound variables remain subject to generic guard/CFG
  audit and target comparisons, not a general semantic proof.
- Gate 6's additive `core0-v0.5` admits only the four closed UART operations and
  separate `mmioRead`, `mmioWrite`, `ioOrder` effects. Preserve byte access widths,
  per-access full fences, compiled packet/polling logic, bounded terminal statuses,
  transitive checking, and device exclusion from generic RAM. The v0.4 fold budget
  stays 256; only v0.5 admits up to 1,000,000 for bounded device polling.
- Gate 6 target branch readback is now complete; do not repeat the development-only
  RAM-observation gap. Its UART model is finite/scripted, not timing-accurate; local
  proofs and bounded straight-line machine register inference are not full compiler
  or CFG proofs.
- Gates 0--6 advance Stage I only. Later M-mode work cannot by itself mark Stage II
  Unit 2.1 or 2.2 passed, and neither G1 nor G2 is complete.

Machine-readable status is in `docs/plan/002-gates.json`.
