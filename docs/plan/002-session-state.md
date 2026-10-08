# Task 002 session state

- Base: Task 001 report-bearing commit `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`
  (tree `88d2c23aafbd2b3a40a195755c01494de9ffad75`), stacked because PR #1 is unmerged.
- Working branch: `task/002-machine-foundation`.
- Highest passing gate: Gate 4.
- Current gate: Gate 5, not started.
- Current failure: none.
- Latest clean passing implementation: `16e7461e009e09390c0e9682d5800cae9fdd90d3`
  (tree `ee8840a642aa3acc03a8759242cc477a7b8c2eb2`).
- Next executable action: begin Gate 5 by specifying the checked fixed-region memory
  interface, overflow-safe range/alignment checks, explicit effects, finite memory/event
  model, and 8/32/64-bit target operations before implementing buffer algorithms.

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
  run names clean `9519adc...` source; the earlier Gate 2 checkpoint remains
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
- Gates 0-4 advance Stage I only. Later M-mode work cannot by itself mark Stage II
  Unit 2.1 or 2.2 passed, and neither G1 nor G2 is complete.

Machine-readable status is in `docs/plan/002-gates.json`.
