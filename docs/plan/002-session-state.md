# Task 002 session state

- Base: Task 001 report-bearing commit `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`
  (tree `88d2c23aafbd2b3a40a195755c01494de9ffad75`), stacked because PR #1 is unmerged.
- Working branch: `task/002-machine-foundation`.
- Highest passing gate: Gate 7.
- Current gate: Gate 8, actual pinned-machine hardware timer implementation in progress;
  no Gate 8 acceptance exists.
- Current acceptance work: Gate 8's frozen development matrix passed; commit
  this implementation and rerun from exact clean committed source. Clean
  focused Gate 7 passed 32 boots and both live restore mutants; cumulative
  Gates 1--7 passed 426 boots, legacy passed 23 boots.
- Latest clean passing implementation: `6c1b6a8ded1e94a822cff9977578b7c292075f75`
  (tree `5c53acabde200edd2ef7061ba65830c7c00b5b5b`).
- Gate 7 report-bearing revision: `530fb1ec80687569e5f5def5ac870153b3256227`;
  do not confuse it with tested implementation source.
- Next executable action: commit the frozen Gate 8 implementation, then run
  `./scripts/check-foundation.sh --all --work-dir
  build/foundation/gates1-8-clean --clean --timeout 300 --qemu-timeout 20`
  and the legacy checker inside the pinned Nix environment. The focused phase
  has passed on the uncommitted source, not yet from a clean implementation commit.
  Continue through Gates 9--11 after Gate 8 acceptance; do not restart its existing
  implementation or credit the development runs below as clean acceptance.
- Publication: Task 002 has not been pushed or submitted as a PR; no publication
  attempt or new actual CI result is claimed. PR #1 remains open/draft/unmerged.

## Gate 8 work in progress (not accepted)

Uncommitted additive `core0-v0.7` work now includes the seven closed timer/MIE
Actions, checked effects/IR/lowering, structured MTIMER/CSR/probe primitives,
compiled timer policy and event-ring source, exporter, strict host runner,
checker, source rejections/probes, and machine audit. The tree remains on the
same Task 002 branch; there has been no Task 002 push or PR.

Actual development results, separately from the accepted Gate 7 evidence:

- The final frozen focused command `./scripts/check-foundation.sh --phase 8
  --work-dir build/foundation/gate8-integration-final --clean --timeout 300
  --qemu-timeout 20` passed: 30 fresh QEMU boots, six positives and five semantic
  rejections per profile, 1,474 actual positive-corpus hardware entries, two
  restored-register mutants and two disabled-arming mutants detected, four
  frontend rejections, 26 direct policy probes, six finite model probes and six
  conditional lemmas. All 339 foundation host tests, 32 legacy host tests,
  18 scaffold tests and metadata checks passed. This is dirty-source development
  evidence until a clean committed rerun completes.
- The earlier `build/foundation/gate8-integration` attempt failed closed on a
  changed `scripts/audit_core0.py` source hash during concurrent audit development.
  Its failure report is retained; no behavioral mutant credit is attributed to
  that source-binding failure. Source was frozen for the later passing matrix.
- Full Lean build passed 52 jobs, including 52 CFG validator checks. Genuine
  combined timer frontend/lowering passed with 40 Action functions, 40 scalar
  functions and all seven timer operations. Gate 8 source rejection fixtures
  passed 4/4 intended diagnostics; Gate 7 frontend/regression fixtures passed.
- Root scaffold metadata and 18 scaffold tests passed; legacy Core0 host tests
  passed 32/32. The first combined foundation-host run passed 312 tests before
  subsequent audit/binding regressions were added. Later final counts must come
  from a fresh complete run, not this historical count.
- `TimerPolicyProbes.lean` passed 26 direct policy predicates, six finite model
  examples, and six conditional lemma axiom reports. One lemma has no axioms;
  the other five use only `propext`. These do not simulate hardware delivery or
  prove the compiler/UInt64 implementation.
- Genuine O0 image `86b3df55da352176d9246bc70b8956e3e029b8feed58243084c1140c8804b7f8`
  and O2 image `e7a4700e2bee1ef5ba1b5857642aad68b170ddca8f5a91400267640edaa7ea33`
  each completed six manual QEMU positive cases with 737 actual timer entries,
  visible overflow and interleaved ring wrap, zero reported context/guard masks,
  and nonzero useful foreground work in the stress cases. The independent host
  oracle revalidated all twelve raw transcripts. These were explicitly
  non-acceptance diagnostics with incomplete/stale audit provenance, retained at
  `build/foundation/gate8-manual-diagnostic/`.
- Both O0 development mutants booted and produced their exact guest failures:
  wrong S3 restore returned status 20/mask `0x40000`; disabled arming returned
  status 21/value zero. Raw artifacts are at
  `build/foundation/gate8-manual-mutants/`. No timeout or compile/audit failure
  counted as behavioral detection.
- An intermediate full central O0 audit passed at
  `build/foundation/gate8-audit-final-dev/O0`; a strict bound runner then passed
  one 256-entry overflow case at `build/foundation/gate8-strict-binding-smoke/O0`.
  Review subsequently strengthened provenance, final-body hashes, unknown/system
  instruction checks, local-label/body boundaries and call-graph roles. These
  intermediate records do not qualify the later source or replace the full
  fresh O0/O2 acceptance matrix.

Next acceptance must preserve genuine hardware entry, bounded masked/pending,
overflow/catch-up/shutdown and both valid-image mutant outcomes. Gate 9's
interactive monitor, Gate 10 detached-worktree/cumulative qualification and CI,
and Gate 11 publication remain unrun for this revision.

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
at `687ee7e...`. That historical Gate 1 aggregate is
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
the legacy aggregate at that checkpoint is
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

## Gate 7 development checkpoint

The uncommitted implementation based on `2797373` passed the following real
commands on 2026-10-08; these are development results, not clean-source evidence:

```text
nix develop --no-write-lock-file --command lake build
  exit 0; 48 jobs; 52 compile-time CFG checks
python3 scripts/check_scaffold.py
  exit 0; metadata 7 gates/56 software/6 physical
python3 -m unittest discover -s tests/scaffold -v
  exit 0; 18/18 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
  exit 0; 32/32 PASS
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
  exit 0; 281/281 PASS
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 7 \
  --work-dir build/foundation/gate7-integration-matrix --clean --timeout 300 --qemu-timeout 20
  exit 0; 32 fresh boots; 8 positive/6 negative cases per profile;
  288 resumable traps/profile; 14 checked denials/positive case;
  2 live restore mutants detected; 4 frontend rejections;
  20 direct policy probes; 2 local conditional policy lemmas
```

Development aggregate SHA-256:
`3b0351c889ae22d4e7570c30b9b7ce1b76a5813f3628fbdf13f2451d6141d602`.
The final machine audit closes four UART sites/eight fence calls, full vector/probe
register slots, eleven vector CSR operations, and zero compiled privileged
instructions. O0's full foreground chain is 3,536/65,520 bytes and compiled
dispatcher chain 1,312/16,048 bytes. Early integration failures (export typing and
a missing audit import) were fixed before this matrix; they did not count as
mutant detection. Formal acceptance must rebuild rather than reuse these dirty
development artifacts.

## Gate 7 clean checkpoint

Verified committed implementation `6c1b6a8...` on 2026-10-08. Final precommit build
48 jobs/52 compile-time CFG checks; metadata valid; scaffold 18/18, Core0 host
32/32, foundation host 281/281 passed. The commands below then ran from exact clean
committed source, all exit zero:

```text
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 7 \
  --work-dir build/foundation/gate7-clean-6c1b6a8 --clean --timeout 300 --qemu-timeout 20
  Gate 7 PASS: 32 boots, 288 positive-corpus resumptions/profile,
  14 software denials/positive case, 2 behavioral restore mutants detected,
  4 exact frontend rejections, 20 policy probes, 2 conditional local lemmas
nix develop --no-write-lock-file --command ./scripts/check-core0.sh \
  --work-dir build/core0/task002-gate7-clean --clean
  legacy PASS: 10 cases/profile, 13 intended rejections, 23 boots
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-7-clean-6c1b6a8 --clean --timeout 300 --qemu-timeout 20
  Gates 1--7 PASS: 24+136+88+14+104+28+32 = 426 fresh boots
```

All 33 cumulative provenance records name full clean `6c1b6a8...`; focused and
legacy build records do likewise. Focused aggregate SHA-256:
`34e27a775b18d06195133e8c05e3d048e78dc849b06188447d2d849638aad7c5`;
cumulative aggregate:
`12837b1bf0d38df75ad9744a120da5702c3651b1bfff22234092721e3d182339`;
its Gate 7 child:
`0f2ab68547526cd8c2d370d98d58495b0388b8b75c55f91f895622b26500667b`;
legacy aggregate:
`f118ffe7ed2646657bf614dcf1081b7e156d6b602e99f5427ecd472637e78bf2`.

The additive synchronous profile is `core0-v0.6`, ABI `lemma-sync-trap-test-v1`.
Two elaborated roots lower through 21 Action/26 scalar functions. Save/restore
covers all 31 integer registers, five CSRs, a 288-byte frame, and six canary pairs.
Only exact ECALL/EBREAK site/continuation pairs resume. Unauthorized ECALL/illegal
instruction exit 18 with checked diagnostics; nested compiled-dispatch ECALL exits
19. The sole test-only wrong S3 restore slot boots and returns mask `0x40000`,
status/exit 20 in both profiles. The 576 positive-corpus resumptions are separate
from extra clean-control/mutant completions and fatal/nested entries.

Machine audit finds four ordered UART accesses/eight fences, eleven vector CSR
operations, and zero privileged instructions in 48 compiled functions. O0/O2
foreground frame chains are 3,536/288 bytes against 65,520 usable; dispatcher
chains 1,312/272 against 16,048. Entry/return-tail fixed aligned RAM/CSR accesses,
MPRV clear, approved M-mode state, and no NMI remain explicit premises. This is
synchronous pinned-QEMU evidence, not interrupts, isolation, a compiler proof,
physical hardware, detached-worktree qualification, actual CI, or G1/G2 completion.

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
  share byte-identical checked suite/ABI/source artifacts. The historical cumulative
  Gate 6 run names clean `179ef54...` source; the current Gates 1--7 run names
  clean `6c1b6a8...`; the earlier Gate 2 checkpoint remains
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
- Gate 7 adds partial early Stage II 2.1/2.2 evidence only: no supervisor entry
  or timer interrupts. Their construction-backlog statuses remain planned.
- Preserve `core0-v0.6` as synchronous and non-nested. Gate 8 needs a separately
  versioned timer/interrupt and single-hart synchronization contract; do not
  retroactively attribute timer behavior or later source changes to Gate 7.
- Inventoried tested-source paths are hashes from `git show 6c1b6a8...:<path>`;
  later guidance/evidence files are report-bearing changes, not clean-source
  requalification. Gate 10's separate detached worktree and Gate 11 publication
  and actual CI inspection remain open.

Machine-readable status is in `docs/plan/002-gates.json`.
