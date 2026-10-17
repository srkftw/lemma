<!--
# Task 002 machine-foundation evidence

Task 002's bounded Gates 0--11 have passed. Repaired source `09c47ba` passed full
cold clean detached local qualification and both actual GitHub push/PR CI runs.
The branch is pushed with an upstream; draft stacked PR #2 remains open and
unmerged. Initial CI failures and earlier local results remain historical evidence.
This does not complete G1, G2, the broader compiler-conformance construction unit,
any Stage II unit, or a general-purpose OS/runtime.

## Gate status and RV64 capability delta

| Gate | Result | Demonstrated scope / remaining work |
|---|---|---|
| 0 | Passed | Reproduced Task 001 baseline. |
| 1 | Passed | Deliberately defective lowerings detected. |
| 2 | Passed | Multi-root scalar/typed-ABI conformance. |
| 3 | Passed | Validated CFG and total fixed-width operations. |
| 4 | Passed | Checked bounded iteration and resource evidence. |
| 5 | Passed | Fixed-region RAM, Actions and transitive effects. |
| 6 | Passed | Compiled bounded UART interaction. |
| 7 | Passed | Real authorized M-mode synchronous traps and context tests. |
| 8 | Passed | Hardware timer IRQs, bounded ring and useful foreground work. |
| 9 | Passed | One coherent post-boot interactive monitor ELF/profile. |
| 10 | Passed locally | Fresh clean detached hosts, cumulative stress, legacy, rebuilds and failure-path qualification. |
| 11 | Passed | Branch/upstream/draft stacked PR published; actual repair push/PR CI, retained artifacts and bounded evidence handoff checked. |

Task 001 executed a bounded scalar program from post-build fixture input.
Task 002 now executes multiple typed scalar roots/ABI shapes, validated CFG with
total fixed-width operations and bounded loops, checked fixed RAM through Action
effects, compiled UART exchange, real M-mode synchronous traps, hardware timer
interrupts with a bounded event ring alongside useful foreground computation,
and one monitor ELF per profile receiving fresh commands after boot. Its parsing,
calculations, buffer algorithms and responses execute on RV64, not in a hosted
guest or host-precomputed image. All claims are profile-bound finite tests/audits;
this is not general Lean support, compiler correctness, isolation, managed runtime,
scheduling, physical hardware, or G1/G2 completion.

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
- Gate 4 implementation checkpoint:
  `16e7461e009e09390c0e9682d5800cae9fdd90d3`, tree
  `ee8840a642aa3acc03a8759242cc477a7b8c2eb2`.
- Gate 5 implementation checkpoint:
  `ff8ef0f871a0c1a3bfdadf95d49d52a828df1e98`, tree
  `c1172034c1dedc0a91375b2eb21dd6fe5fd9b187`.
- Gate 6 implementation and historical cumulative clean verification source:
  `179ef541e7cfa53235322610222a01ccdf9364cd`, tree
  `9ff742607b5b1d73924928bf147dabada037f406`.
- Gate 7 implementation and historical cumulative clean verification source:
  `6c1b6a8ded1e94a822cff9977578b7c292075f75`, tree
  `5c53acabde200edd2ef7061ba65830c7c00b5b5b`.
- Gate 7 report-bearing revision: `530fb1ec80687569e5f5def5ac870153b3256227`.
- Historical accepted cumulative Gates 1--8 implementation checkpoint:
  `42674c1ba773454c36c277620e2acd289539e5a2`, tree
  `f7bea0b4f126275773bbc84e8fb534849ac6bb35`.
- Historical Gate 9 clean focused monitor implementation: `8fd45d8458f4901c7a2d4debcb60ebd71f18a39c`,
  tree `965b550c576f80284a1a24c427d9704b517d160d`.
- Historical successful clean detached/local qualification implementation:
  `e0e1f2188fba1d26fbdd8723f37091001802064d`, tree
  `9660ade13a0b202bb0a76325eb36cf0c2b75a7d4`.
- Current repaired clean detached/local qualification implementation:
  `09c47ba24577da87390f4c693237fe71ab67c965`, tree
  `7051d19087e09a6eede78210fdbe7652105e355d`.
- Branch: `task/002-machine-foundation`, stacked on Task 001.
- Initial post-test report-bearing/published revision:
  `ac2a95ec460d271ef00f92335ae3ea821d1b329d`, tree
  `6e129a2ed43608d2bd728df26d09037d93e72fb9`. This later publication-status edit
  is not self-referenced or claimed to be in that revision. At that initial
  publication tested source was `e0e1f2`; current tested source is the separately
  identified `09c47ba` implementation above.

The historical Gate 0 clean aggregate was `build/core0/check/check-results.json`,
SHA-256 `3a3cb9244b4a84b1a93ff869843aa3619622719ef6f431067e5502cbefc58a7c`.
Gate 1 first passed at `8878d2c...`; it was then rerun as part of the cumulative clean
Gates 1-2 command at `687ee7e...`. All 14 Gate 1 control/mutant provenance records,
both Gate 2 profiles, and the Task 001 O0/O2 release records in that historical
checkpoint name the full `687ee7e...` commit and record `dirty_tree: false`.

The previous cumulative clean run repeated Gates 1--6 at `179ef54...`. All 29
retained cumulative provenance records (24 actual builds and five copied Gate 1
negative-audit records) name that full commit and record
`dirty_tree: false`; the focused Gate 6 and legacy O0/O2 audits do likewise. The
earlier per-gate identities remain historical checkpoints rather than being
overwritten. These are clean committed-source runs in the existing checkout, not
the separate detached-worktree qualification then still required by Gate 10
(and subsequently passed at the later checkpoints below).

The previous cumulative clean run repeated Gates 1--7 at `6c1b6a8...`, with all
33 retained provenance records (28 actual builds and five copied Gate 1
negative-audit records) naming that exact commit and `dirty_tree: false`.
The focused Gate 7 run's four build records and the legacy regression's eight retained
records (seven actual builds and one copied audit) likewise name clean `6c1b6a8...`. Later report/guidance updates and
Gate 8 work are not retroactively covered by those source identities. The source
snapshot in that historical hash inventory uses `git show 6c1b6a8...:<path>`, not the later
worktree; its report-bearing files are explicitly hashed separately.

The historical accepted cumulative Gates 1--8 run names exact `42674c1...` source in
all 39 retained provenance records (34 actual builds and five copied Gate 1
negative-audit records), each with `dirty_tree: false`; all eight legacy
regression provenance records do likewise. Gate 8 acceptance is the complete
checker executed as the cumulative child, not a separate clean focused run.
The historical focused Gate 9 run binds both profiles to exact `8fd45d8...`
with `dirty_tree: false` and 101 source inputs/profile. Current local Gate 10
acceptance is a full clean detached run at `09c47ba...` (successful `e0e1f2` remains historical): 41 retained cumulative
provenance records (36 actual builds plus five copied Gate 1 negative-audit records),
eight retained legacy records (seven actual builds plus one copied negative-audit
record) and two qualifier rebuild records all bind that
exact clean source. Monitor source inputs now number 102/profile. The current
inventory hashes source with `git show 09c47ba...:<path>`, including guidance bytes
as they existed then; later report/root-guidance updates are explicitly separate.

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
| `build/foundation/gate5-clean-ff8ef0f/gate5-results.json` (authoritative focused Gate 5 report) | `fa670e195ce2b4f8988850f8b1e2f10c3dc9eda7cb993b5f0dcf09f20cbe25d7` |
| `build/foundation/gates1-5-clean-ff8ef0f/all-results.json` | `635c1ca0c7d3a4647297a978b109ce5b42d015a6ab46de676d8791b66261b863` |
| `build/foundation/gates1-5-clean-ff8ef0f/gate1/gate1-results.json` | `d2d8abeeb5bb709863074941e13580c5edcd30b76de6d9bb985de1050de8be04` |
| `build/foundation/gates1-5-clean-ff8ef0f/gate2/gate2-results.json` | `24d07cda88c3e318547b0af3fa116d56f30b854cb9ab099a28658c7d53811045` |
| `build/foundation/gates1-5-clean-ff8ef0f/gate3/gate3-results.json` | `dd742d894dabd5714dad387212421fc12e376e23e86acb763d4cfd2a5eb1dbcf` |
| `build/foundation/gates1-5-clean-ff8ef0f/gate4/gate4-results.json` | `60e29f2c73934c0dc2ad761c6df3ab0ab0a10310295b63901bbb9948efde1a4a` |
| `build/foundation/gates1-5-clean-ff8ef0f/gate5/gate5-results.json` | `c331d3f4210d3bdaef88def71c892606d0dc4caa85cee8e07f092092b55de8f6` |
| `build/core0/check/check-results.json` (historical Gate 5 legacy regression; path subsequently reused) | `ab160eebccc519922a537c181c83900c2838f690bd15c7ca49ba8906283b1c8f` |
| `build/foundation/gate6-clean-readback/gate6-results.json` (authoritative focused Gate 6 report) | `da4726d0c7f312c72295b70651a94cd4eeb69f5e99072dd6ba3f07676acd73a1` |
| `build/foundation/gates1-6-clean-readback/all-results.json` | `b82597eced2cd1e23bc9c589142c353e36d6f3414746194cdbb47be00ce3c2de` |
| `build/foundation/gates1-6-clean-readback/gate1/gate1-results.json` | `f5d58aff59e38c7a8f29b86bc87742164c9f5531080d064e17dcd51140c08706` |
| `build/foundation/gates1-6-clean-readback/gate2/gate2-results.json` | `d757326af681a420137f14157fb9609aa1972b9852bb232eee55f874c6528eb0` |
| `build/foundation/gates1-6-clean-readback/gate3/gate3-results.json` | `fedd4428a9831744f51bede8d1ef44ce18c228859ccbd2e5e64a4d463cee3c71` |
| `build/foundation/gates1-6-clean-readback/gate4/gate4-results.json` | `b91564ae709820dbe58e1c58ca8a76bbec90a72c16ecec081c8d28d838cf898a` |
| `build/foundation/gates1-6-clean-readback/gate5/gate5-results.json` | `dcd9e7b34efee45570860f33e9b04e0a7654ed7e14daca8c7641447dbe1ff3e1` |
| `build/foundation/gates1-6-clean-readback/gate6/gate6-results.json` | `bb61dc1c32a2d00440ff71a78ffc040f8efd8a2ec10b0441d529ba820c38e9f2` |
| `build/core0/check/check-results.json` (historical same-source Gate 6 legacy regression) | `1a0e514c0ff086f6ca25679882c97e992c02f9e9eb6cbfe049e3552c5eaa0e09` |
| `build/foundation/gate7-clean-6c1b6a8/gate7-results.json` (authoritative focused Gate 7 report) | `34e27a775b18d06195133e8c05e3d048e78dc849b06188447d2d849638aad7c5` |
| `build/foundation/gates1-7-clean-6c1b6a8/all-results.json` | `12837b1bf0d38df75ad9744a120da5702c3651b1bfff22234092721e3d182339` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate1/gate1-results.json` | `59c9bc9230f7408a1f0d46cd965f9bb3c292c0014f847e1511d7cec5fe074a66` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate2/gate2-results.json` | `d909000e9b529a7b3e6afa035aaf86ccde3040dd009b778690fd72c01e0aed1f` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate3/gate3-results.json` | `2352a9daae79853ca4105d186cddaf717fd56bf00c19120777c5a24de2435ea2` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate4/gate4-results.json` | `a79d624c2259df47681f296ed38990ceb93c795431298ca49ea35df64dec6c27` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate5/gate5-results.json` | `4ba92dc8eb13ec3a12edd8357b2e11ec9b583e336e6f7864f301debd9521e0f1` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate6/gate6-results.json` | `c239b3f9343bf2e34f0efd3c2386c3deedf5b5a00f2abf63ec4d732f5e0468e0` |
| `build/foundation/gates1-7-clean-6c1b6a8/gate7/gate7-results.json` | `0f2ab68547526cd8c2d370d98d58495b0388b8b75c55f91f895622b26500667b` |
| `build/core0/task002-gate7-clean/check-results.json` (historical same-source regression) | `f118ffe7ed2646657bf614dcf1081b7e156d6b602e99f5427ecd472637e78bf2` |
| `build/foundation/gates1-8-clean-42674c1/all-results.json` (historical accepted Gates 1--8 baseline) | `393a2a649e3f804ea7fc332b53d9c88cdd2d789dc34c7ac7357fbdb1d4aca8de` |
| `build/foundation/gates1-8-clean-42674c1/gate8/gate8-results.json` (authoritative clean Gate 8 child) | `09190b5a7ad03d5b3a208aa9514c6aa48dfd64bd2a95890dc7a755c2866bb8e9` |
| `build/core0/task002-gate8-clean/check-results.json` (historical accepted legacy baseline) | `7ba1294f53702fb4b86ef3a8ad65173b4100a9efc0256e11b90a4a72dda89f82` |
| `build/foundation/gate9-clean-8fd45d8/gate9-results.json` (clean focused Gate 9) | `69e37da2266a4c89ddd18243600da1da52300c7edbebe264eae9033bf3841ca6` |
| `build/qualification-worktree.hJDCyB/build/foundation/gates1-9-clean/all-results.json` (historical successful e0e1f2 cumulative stress) | `8d8189b489e07643dcacf5f03bf4c5317fab191a5a69584f57c2c51d1c575f5f` |
| `build/qualification-worktree.hJDCyB/build/foundation/gates1-9-clean/gate9/gate9-results.json` (historical successful e0e1f2 monitor normal/stress) | `cce7d93e6c830015c4952110c6d05d89abe16dd04127d4c019701e46a9b988be` |
| `build/qualification-worktree.hJDCyB/build/core0/qualification-legacy/check-results.json` (historical successful e0e1f2 legacy) | `1878d6d734d118836ddc4840f686098029339f29a164d11d185c34db3a42cafd` |
| `build/qualification-worktree.hJDCyB/build/foundation/qualification/qualification-results.json` (historical successful e0e1f2 qualifier) | `3b7923e051835c2bd2de87b69ac365ced24b95f73d364fcf488fd5373c7284d9` |

## Commands executed for the historical Gate 6 implementation checkpoint

| Command | Exit | Actual result |
|---|---:|---|
| `nix develop --no-write-lock-file --command lake build` | 0 | 44 jobs; complete Lean library build; 52 compile-time CFG validator checks |
| `python3 scripts/check_scaffold.py` | 0 | metadata valid: 7 gates, 56 software units, 6 physical units |
| `python3 -m unittest discover -s tests/scaffold -v` | 0 | 18/18 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v` | 0 | 32/32 passed |
| `nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v` | 0 | 239/239 passed |
| `nix develop --no-write-lock-file --command ./scripts/check-core0.sh --clean` | 0 | 10 cases/profile, 13 intended rejections, 23 fresh QEMU boots |
| `git status --short --branch` | 0 | Before authoritative runs: clean status `## task/002-machine-foundation` |
| `nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 6 --work-dir build/foundation/gate6-clean-readback --clean --timeout 300 --qemu-timeout 20` | 0 | Gate 6 passed: 14 scenarios/profile, 28 fresh QEMU boots, 16 runtime requests |
| `nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all --work-dir build/foundation/gates1-6-clean-readback --clean --timeout 300 --qemu-timeout 20` | 0 | Gates 1--6 passed: boot counts 24, 136, 88, 14, 104, 28 respectively; 394 total |

The build and unit suites ran against the final implementation tree immediately
before its checkpoint commit. The focused Gate 6, cumulative Gates 1--6, and legacy
Core0 commands then ran after the implementation was committed, from clean source
`179ef54...`. Those reports are the source-attributable authorities: the focused
report details Gate 6, the cumulative report proves Gates 1--6 still pass together,
and the legacy Core0 report binds both O0/O2 audits to `179ef54...` with
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

## Gate 5: checked fixed-region memory and explicit effects

Gate 5 adds the explicitly selected, additive `core0-v0.4` profile. It preserves
v0.1--v0.3 and introduces closed `Action` syntax rather than hiding effects behind a
scalar function. The checker resolves continuations, direct Action calls, and
bounded-fold callbacks statically; computes `checkedAccess`, `ramRead`, and
`ramWrite` transitively; and rejects runtime Action values, captures, recursion,
arbitrary externs, lookalikes, unsafe definitions, and Action use under older
profiles. No Action, closure, allocator, exception object, or managed state monad is
present in the target image.

The fixed table contains four 4 KiB ordinary regions: read/write scratch at
`0x80801000`, read-only input at `0x81000000`, read/write output at `0x80803000`,
and width-4/8 event storage at `0x80805000`. Image and stack regions are reserved;
UART and SiFive-test are classified as devices and cannot reach the ordinary-RAM
pointer path. Loads/stores admit 8, 32, and 64 bits as allowed by each table entry.
The exact failure order is lookup, class, permission, width, bounds, alignment.
Bounds are subtraction-first (`offset <= length - width`) after width/interval
validation, so `offset + width` cannot wrap into acceptance. Range checks are pure
preflights. A pointer and one volatile physical access are emitted only on success.

The result is logically `(status : UInt8, value : UInt64)`, physically LLVM
`{ i64, i64 }`, and directly returned in RV64 `a0/a1` with the status zero-extended.
Status codes 0--9 cover success, unknown/reserved/device region, read/write/width
denial, out-of-bounds, misalignment, and iteration-budget exhaustion. Status 4 is
defined but unreachable under this exact table because every ordinary region is
readable and class checks precede permission checks.

### Source/model/target state agreement

The closed suite uses ID `0xa20c6fd4108dbf27`, source seed
`0x4c454d4d41353035`, and runtime seed `0x52554e54494d4535`. It contains 26 genuine
elaborated roots and 52 deterministic cases/profile. The roots exercise each width,
endianness and overlapping loads, last-valid and one-past accesses, misalignment,
maximum offsets, read-only writes, forged IDs, reserved/device denial, range
preflight, selected-branch writes, runtime-counted stores, bounded fill, byte
checksum, non-overlap helper copy, and overlap-aware copy. The source algorithms are
ordinary declarations in `examples/foundation/MemoryConformance.lean`; the host does
not substitute their target implementation.

The independent Python finite-memory transition model records every successful
read/write event and the complete final contents of all four ordinary regions. The
pinned Lean model separately evaluates the original elaborated Action declarations;
18 probes cover outcome/event behavior. Their shared fixture/layout assumptions are
explicit: the Python model imports the runner's frozen catalog and deterministic
initial-region generator, while implementing transitions separately.

Each O0/O2 case used a fresh QEMU boot. After the checked root returned, test glue
emitted the exact 16,384-byte ordinary-region post-state as reversible aligned-word
frames, followed by all ten 16-byte boundary canaries. The runner enforces exact
frame order, IDs, lengths, payload sizes, case/image binding, and terminal framing;
it decodes every word to little-endian bytes. Acceptance reparses the retained raw
UART rather than trusting summary metadata and compares SHA-256 over
`region-id || complete-region-bytes` with the independently recomputed model state.

Both profiles matched all 52 scalar outcomes and all 52 complete post-states. Across
104 boots this is 104 outcome matches, 104 post-state matches, 1,703,936 observed
ordinary-region bytes, and 1,040 exact canary observations. O0, O2, and the model
share scalar-result digest
`66aef0a96804cba0e71f1c17d5e2cab272a3cc448b7abdf7a5caa752d2c71d19`
and post-state aggregate digest
`4b508bee3b64f17c8548a7db1dc6cbb11b6afc1514e440a8ce214db8eb06d544`.
The corpus SHA-256 is
`6051b6f7e38eecb7b95501bbd36296699a3840c8e74c3b6e768051c69b30a6a4`.

### Lowering, mutation, proof, and closure evidence

The pre-optimization audit finds 31 Action functions, 37 successful physical access
sites (18 loads and 19 stores), eight range sites, and five Action-fold sites. It
checks region dispatch; exact class/permission/width metadata; guard order and CFG
dominance; subtraction-first bounds; alignment; pointer construction; volatility;
the direct aggregate ABI; Action-call closure; and source/effect manifests. Its
focused source-binding layer connects stable sites to directly auditable normalized
region, offset, store-value, and range-length operands. Computed expressions and
Action-bound variables remain outside that narrow binding claim; they retain the
generic guard/CFG checks and finite target comparisons.

All 51 audit mutations were rejected: 19 manifest/effect/closure mutations and 32
pre-optimization IR mutations. The latter include nonvolatile/wrong-width/wrong-
alignment/extra accesses; changed source store value, checked offset, region
selection, and branch route; reserved/device inversion; bounds, permission, width,
alignment, range, and address-construction defects; poison-sensitive flags; checked
result corruption; indirect calls; and wrong direct callees. Focused target-state
tests separately show that a wrong stored byte, wrong checked offset, or wrong branch
destination changes the complete-state observation and fails comparison.

All 14 exact frontend fixtures rejected, including three older-profile Action uses.
Five local Lean theorems were checked: fixed-table validity, interval containment,
physical interval containment, and rejected-store preservation of memory and model
events. Their dependency reports contain no `sorryAx`; the allowed dependencies are
only standard `propext`, `Classical.choice`, and `Quot.sound` where present. These are
facts about the finite model, not a compiler-correctness proof or refinement proof
for emitted RV64.

O0 and O2 have byte-identical checked source artifacts and clean provenance at
`ff8ef0f...`:

| Shared checked artifact | SHA-256 |
|---|---|
| `memory-suite-manifest.json` | `3e88850ba609f598d1e8ae52668880bb99e06367bf6dde4b0810e5558400292d` |
| `memory-suite-normalized.txt` | `d254f79b53d115488f5536dc7840072f1e28282edc35f5791307b7242028d7d2` |
| `memory-test-abi.json` | `cb261785b0bf5de2e51c41eb78ad4a511ae9d407cc3b518697230a1516d19ab2` |
| `symbols.txt` | `d630fd5c2a9f86650218cdc1e80a88c25a72fa8755d0f1f1c86c98eed25081d0` |
| `program.ll` | `58cf81fd9781be78de568fbb8a20488dda7d7e39bb4bfd1f6241131fa77ed8e3` |

| Profile | Audit SHA-256 | Optimized IR SHA-256 | Stack-size report SHA-256 | Image SHA-256 |
|---|---|---|---|---|
| O0 | `dc5552bf57556d512aca363c58eafdbada6836d2690e22d9ba6771cc42ceafda` | `6d4b9a7b684f8e47633c15b62e679ef2292eb756ed96d6c2707043842ea0a100` | `98fd3b38a21d3acd3a9757aee979478422b42c5d5b0d93c6974f9b5d19c90494` | `976cceb9dd09346b518067b56a73f98ec93b54dfe597ada7cf5fe1df10e7bfce` |
| O2 | `b3f4a02ff6df0ac0c9973dfe1775d47d332a6687b25cc431b3b62610c10bfd90` | `fea3cb038478e58c16983a421634fac7c8e6b8a0257698f17d8ec746b06caa7f` | `dd0e9652e263356c9fdf7d5fd0dd72f8827cd74622cf749d300ede780941d5bf` | `400e909ae118746a361053e59aad102779a11397907cbfbb061e8ffb56bb4018` |

The optimized direct-call graph is acyclic and has no dynamic allocation. Its
maximum frame chain is 1,568 bytes at O0 and 240 bytes at O2, below the fixed 64 KiB
stack. Pre-optimization IR contains no `disjoint`, `inbounds`, `nsw`, or `nuw`.
O2's closed inventory contains 54 `or disjoint`, five `inbounds`, 85 `nsw`, and 84
`nuw` inferences, each classified by the audit; no such premise is attributed to the
source emitter.

Gate 5 establishes checked ordinary-RAM access inside one trusted M-mode image. It
does not establish protection against arbitrary privileged machine code, MMIO
ordering, a device driver, traps, interrupts, address-space isolation, allocation,
or a managed runtime.

## Gate 6: compiled Lean polling UART and runtime sessions

Gate 6 adds explicitly selected `core0-v0.5`, test ABI
`lemma-device-session-v1`, and artifact category `test-device-suite`. The genuine
elaborated root `Lemma.Examples.Foundation.Device.deviceSession` has a checked
closure of 22 Action and 19 scalar functions. Its four closed device operations are
`uartReadStatus`, `uartReadByte`, `uartWriteByte`, and `uartEnableAndResetFifo`.
Their `mmioRead`, `mmioWrite`, and `ioOrder` effects remain separate from ordinary
RAM effects and propagate through helper calls, selected branches, and bounded
Action folds. Generic RAM access to device regions remains denied. The older
`core0-v0.4` budget stays 256; the new profile permits a literal Action-fold budget
up to 1,000,000 for bounded polling, without adding dynamic closures or recursion.

The compiled source performs UART FIFO initialization, transmit/status/receive
polling, bounded timeouts, packet validation, dispatch, arithmetic, encoding, and
final drain. `DeviceHarness.lean` only invokes the no-argument Action root and
writes the status-coded SiFive-test finisher; its audit finds zero UART accesses.
The legacy Task 001 harness remains separately tested.

### Pinned machine, ordering, and audit scope

The one-hart integer-only machine remains QEMU `virt`, `-bios none`, 128 MiB RAM,
RV64IM with Zicsr/Zifencei, and LP64. QEMU 11.1.1 revision
`c3d48b7d1e89604920e5b81b91140c2ad39a1943` has source archive SHA-256
`079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482`.
The captured DTB SHA-256 is
`c9c27a1a5c9a652c5c9daa8109c5109d651dacf502b2b7c6081d63d99849d73f`.
Its `/soc/serial@10000000` node identifies ns16550a, span `0x100`, clock
3,686,400 Hz, and IRQ 10; this polling gate does not enable that IRQ or use the
clock as a timing oracle. The exact source inspection and model limits are in
[the UART audit](../audits/uart-core0-v05.md).

The selected register-shift-zero interface uses bytes only: RBR/THR at
`0x10000000`, fixed FCR `0x07` at `0x10000002`, and LSR at `0x10000005`.
RBR reads consume receive data; LSR reads clear BI/OE, not every error bit; THR/FCR
writes have the documented transmitter/FIFO side effects. Every source device
operation emits a volatile `i8` access, alignment one, immediately bracketed by
calls to the structured `fence iorw,iorw` primitive. Six physical source sites and
twelve fence calls survive both profiles. The optimized alignment audit admits
only alignment one or the exact constant address's justified low-bit alignment.
It does not attribute LLVM-inferred alignment to the source emitter.

The central audit checks the named two-object closure, ELF/ISA/layout, direct-call
closure, stack metadata, fences, and all inferred UART memory uses. Its register
constant/alias tracking is bounded per-function straight-line inference, not a
general machine CFG proof. O0 has 18 explicitly classified UART-base constants
used only in denied-region metadata; O2 has none. The acyclic optimized-LLVM call
graph weighted by object `.stack_sizes` has maximum chains of 2,736 bytes at O0
and 288 at O2, below the fixed 65,536-byte stack; this is not a complete machine
call-graph proof.

### Actual runtime and failure matrix

Suite ID is `0x4c454d4d41363036`, source seed `0x534f555243453036`, and runtime
seed `0x52554e54494d4536`. The closed corpus SHA-256 is
`dab17f6d43e29ca55787ccbe63862a3d1af35a9bd62126d09f089c200de844df`.
The compiled READY bytes are `LEMMA_DEVICE/1\nREADY\n`. A request has a 16-byte
`LMQ6` header, version 1, command, payload length at most 16, zero flags, and a
little-endian UInt64 ID. A response is exactly 24 bytes: `LMS6`, version, status,
payload length 8, zero flags, echoed ID, and little-endian UInt64 result.

Each profile ran four interactive and ten terminal scenarios: 14 fresh boots,
eight runtime requests, and four single-PID/two-request sessions. Across O0/O2 that
is 28 boots, 16 runtime requests, and eight two-request sessions. ADD64/XOR64
answers, selected branch effects, unsupported-command recovery, and bounded TX
stress all matched the independent host oracle using inputs sent after READY.
An unsupported command returned status 17 and the next valid request succeeded
without restarting or rebuilding the image.

Malformed magic/version/flags and noncanonical branch input terminated with status
14; partial header/payload with 15; invalid lengths with 16; no receive input with
12; and actual serial-backend backpressure with bounded transmit status 11. Each
profile's exit-status histogram is `{0:4, 11:1, 12:1, 14:4, 15:2, 16:2}`. A line-error
outcome is covered by the finite UART probes, not a claimed injected target line
error. Backpressure evidence is specific to QEMU's stdio backend, not a UART latency
measurement. Retained raw bytes, PID/ELF binding, argv, timestamps, status, and
cleanup are checked rather than accepting a banner alone.

The branch command first initializes scratch+64 to `0x3c`. False alone writes
`0x5a`; true alone emits raw UART `0xa5`. Both paths read the byte through checked
RAM and encode `(readback << 8) | selector`. Both profiles returned exactly
`0x5a00` and `0x3c01`, respectively, giving four actual target marker readbacks.
Source bindings and exclusive pre/post-LLVM CFG placement additionally check the
sentinel, selected effect, branch-local load, and encoded result. The earlier
development-only observation gap is closed in this clean checkpoint.

All 18 manifest/effect/branch/pre-IR/post-IR audit mutants per profile rejected
(36 total). They exercise stale/duplicate catalogs, wrong address/width/volatility,
missing/reordered fences, duplicated physical operations, invalid optimized
alignment, and misplaced branch effects. These are audit mutations, not six new
behavioral compiler faults; the Gate 1 behavioral fault matrix remains separate.
All five exact frontend fixtures rejected, including one older-profile rejection
(the latter is a subset, not a sixth fixture). They also cover excessive budget,
stored continuation, hidden arbitrary extern, and a pure result concealing effects.

### Retained transcript, models, and proofs

The focused acceptance command in the command table produced this actual O2
`branch-effects` session, PID 226639, image SHA-256
`34195270cb43289f64754b10b63508ae08fff07974c6c60875c06710c6cd6910`.
The run record and binary streams are under
`build/foundation/gate6-clean-readback/O2/runs/branch-effects/`.

```text
guest READY: LEMMA_DEVICE/1\nREADY\n
host request 0x2001: 4c4d513601030100012000000000000000
guest frame:        4c4d5336010008000120000000000000005a000000000000
decoded: id=0x2001 status=0 marker=0x5a selector=0 value=0x5a00
host request 0x2002: 4c4d513601030100022000000000000001
guest prefix:       a5
guest frame:        4c4d5336010008000220000000000000013c000000000000
decoded: id=0x2002 status=0 marker=0x3c selector=1 value=0x3c01
QEMU exit: 0; both requests used the same PID and ELF
```

Twelve pinned-UART semantics probes and thirteen packet/source-model probes passed.
The finite model scripts receive/transmit availability; it is not a timing-accurate
model of the asynchronous FIFO. Packet probes separately compare original
elaborated source encoders. Four local lemmas were checked:
`empty_write_has_ordered_events`, `fifo_reset_discards_pending_rx`, and
`fifo_reset_is_ordered` have no axiom dependencies; `response_size` depends only on
`propext` and `Quot.sound`. Their exact statements and dependency output are retained
in the focused JSON and `proofs/device-lemmas-axioms.stdout`. They establish model
ordering/reset/frame-size facts, not frontend/lowering refinement, compiler
correctness, or physical UART correctness.

| Profile | Audit SHA-256 | Optimized IR SHA-256 | Image SHA-256 |
|---|---|---|---|
| O0 | `cf5735bd8e7b58de2c9b504430a017a1eb9f1a55cc9c09aef345bb2da5252b4a` | `4bb9b7476f25f15d1e0657bf46e801ddfd3be88f6e4767ca7358d78bbf374259` | `5feef4cb1b5989d5421f07db8df703f5a34352c8ea824b2c2f2e8d53dc40ec80` |
| O2 | `71cf14a9ea62080c9f9fb46ec51b6e96fb827b2313fdb5ae0d94c8784412b565` | `76f76f44ed39897a923c1db0ec6b0d10b68bf55be08acc8f534d4c6966e57ab0` | `34195270cb43289f64754b10b63508ae08fff07974c6c60875c06710c6cd6910` |

O0/O2 have byte-identical checked manifest, normalized source, wire ABI, symbol
map, layout, startup, and pre-optimization IR. The pre-IR SHA-256 is
`06993acef2e38439afc6e49ce682f4f32d2e3d4785a2eaca7a6e7a1057d4504c`.
The full identities are in the machine-readable summary and SHA-256 inventory.
Gate 6 itself adds no traps, interrupts, scheduler, managed runtime, or physical-board
claim. Later Gate 7 synchronous traps and Gate 8 timer acceptance are recorded
below, followed by local Gate 10 detached qualification and Gate 11 publication;
actual CI subsequently failed as recorded under Gate 11.

## Gate 7: synchronous M-mode traps, dispatch, and return

The explicitly selected additive profile is `core0-v0.6`, ABI
`lemma-sync-trap-test-v1`, artifact category `test-trap-suite`. Genuine elaboration
checks two roots, `Lemma.Examples.Foundation.Trap.foreground` and `dispatch`, with
21 Action and 26 scalar functions. Four exact no-address source operations admit
ECALL, EBREAK, an unauthorized ECALL fixture, and an illegal-instruction fixture;
their `sync-trap` and `machine-state` effects propagate through calls, branches,
and bounded folds. Scalar wrappers and older profiles cannot hide these effects.
The finite RAM/UART models explicitly reject trap execution rather than simulating
hardware success.

The machine contract remains one-hart QEMU `virt`, `-bios none`, integer-only
RV64IM/Zicsr/Zifencei, LP64, no compressed/FP/vector/atomic instructions or target
runtime libraries. The privileged reference is the official RISC-V 20240411
Machine ISA 1.13 PDF, SHA-256
`538f3b17e1990ffabde30a6b96aaa2a0111afb63c174a6ef02b55a7aeb0e701d`.
Exact ISA sections and inspected pinned QEMU 11.1.1 source hashes are in the
[trap construction audit](../audits/traps-core0-v06.md); the earlier toolchain pins
above are unchanged. Pinned TCG disables Smrnmi/Smdbltrp, a relevant premise of the
tested software double-fault latch, not a general hardware double-trap claim.

### Clean-source commands and actual results

The final build and unit suites ran on the implementation tree immediately before
commit: Lean build 48 jobs/52 compile-time CFG checks, scaffold metadata valid,
18/18 scaffold, 32/32 Core0 host, and 281/281 foundation host tests passed. The
following commands then ran from exact clean `6c1b6a8...` source; all exited zero:

```sh
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 7 \
  --work-dir build/foundation/gate7-clean-6c1b6a8 --clean --timeout 300 --qemu-timeout 20
nix develop --no-write-lock-file --command ./scripts/check-core0.sh \
  --work-dir build/core0/task002-gate7-clean --clean
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-7-clean-6c1b6a8 --clean --timeout 300 --qemu-timeout 20
```

Focused Gate 7 passed 32 fresh boots: eight positive, six negative, one extra
clean-control, and one behavioral restore-mutant boot per O0/O2 profile. The eight
positive cases use counts 0, 1, 7, and 64 with two distinguishing seeds each. They
observed 288 actual ECALL/EBREAK resumptions per profile, 576 total, separately
from the extra clean-control/mutant completions and fatal/nested entries. Both
profiles' foreground checksums matched the unchanged independent arithmetic oracle
and an interrupt-disabled, trap-free control fold. Every positive case also passed
14 software-denial checks with the vector active: exact error/value, unchanged
trap count, and unchanged scratch guard. Full register/canary masks were zero in
the returning probes. Zero-count cases execute no returning trap.

Unauthorized ECALL and actual illegal instruction each produced five correctly
framed source-encoded diagnostic values and exit 18, with causes 11 and 2,
exact ELF-bound faulting PCs, relevant status/mie checks, and permitted trap values
(observed illegal mtval `0x0b`). An actual ECALL from compiled dispatch hit the
zero-latch stackless nested-fault path and exited 19. Semantic count 65, non-UInt32
count, and invalid scenario terminated with 9, 16, and 14 respectively, without
fabricated normal frames. Protocol errors, timeout, process failure, and malformed
artifact/provenance are distinct failures, not accepted trap outcomes.

The quarantined Lean structured mutation changes exactly
`ld s3,144(sp)` to `ld s3,152(sp)` on restore. In both profiles it compiled, passed
its declared test-only audit, booted, entered compiled dispatch, returned from the
real ECALL, and emitted frame ID `0x71ff`, status 20, mask `0x40000`, before exit 20.
Both outcomes were `verified-behavioral-context-mismatch`; a compilation, audit,
timeout, or protocol failure would not count as detection. The source and compiled
program remain identical to the clean control; production inputs cannot select
the mutation.

All four exact frontend fixtures rejected with their intended reasons. Twenty
direct-source policy probes and the actual transitive frontend/lowering/model-refusal
probe passed. Two conditional local lemmas, `approvedEcallResume` and
`approvedBreakpointResume`, were checked with only `propext` and `Quot.sound`.
They establish the source return-policy facts under the stated status premise, not
entry/return correctness, compiler refinement, or hardware correctness.

The cumulative Gates 1--7 command passed 426 boots
(`24+136+88+14+104+28+32`); all seven fresh child reports passed and all 33 build
provenance records identify clean `6c1b6a8...`. The separate legacy command passed
10 cases/profile, all 13 intended rejections, and 23 fresh boots, with repeat-build,
source mutation, and foreign-object audit checks preserved. These are clean runs
in the existing checkout, not Gate 10's detached-worktree qualification.

### Context/resource and artifact audits

Lean-authored typed machine instructions mask interrupts, initialize the direct
vector and dedicated private stack, save x1--x31 including interrupted SP, capture
five CSRs in an aligned 288-byte frame, and call the nine-word compiled dispatcher
with its ninth argument in a separate 16-byte outgoing frame. Only the exact
four-byte authorized ECALL/EBREAK site/continuation pairs may resume; dispatch
does not blindly increment an arbitrary PC. GP/TP are saved then zeroed for compiled
dispatch, whose emitted code must use neither. MRET's architectural status changes
are accounted for rather than requiring invalid raw pre/post mstatus equality.

Each returning probe initializes all 31 integer sentinels and a valid private SP,
snapshots them before comparison clobbers any register, and checks six canary pairs
covering foreground/trap/probe stacks. The private trap/probe storage grants no
ordinary RAM-region authority. Non-nesting is explicit: dispatch faults are caught
by the zero `mscratch` latch, while fixed aligned RAM/CSR accesses in the entry and
final return tail, MPRV clear, an approved M-mode continuation, and no NMI remain
premises. Interrupt masking alone is not claimed to suppress synchronous faults.

The central audit retains exactly two named linked objects and the closed 17-file
build bundle. It binds exact signatures, effects, normalized source, ABI, platform,
provenance, hashes, LLVM call closure, ELF attributes/layout/sections/relocations,
full vector/probe register-slot sequences, stack adjustments, direct vector/latch
targets, ordered CSR operations, and stackless terminal fatal loops. It finds 48
compiled functions using zero privileged instructions, eleven vector CSR operations,
two approved resume pairs, and the two bounded fatal loops. Checked pre-IR has 24
physical ordinary-RAM sites (16 loads/eight stores) and one range preflight. UART
machine audit finds four exact byte accesses with eight fence calls; denied UART
metadata constants are 24 at O0 and zero at O2. Its alias inference is bounded
straight-line analysis, not a general machine CFG proof.

The optimized LLVM acyclic direct-call graph weighted by object `.stack_sizes`
measures foreground chains O0 3,536 and O2 288 bytes against 65,520 usable bytes;
compiled dispatcher chains are 1,312 and 272 against 16,048 bytes. The separate
288-byte frame plus 16-byte outgoing slot fit the 16,352-byte usable trap stack.
These bounds and observed canaries are complementary evidence, not exhaustive
machine call-graph reconstruction or a compiler proof.

| Profile | Audit SHA-256 | Optimized IR SHA-256 | Image SHA-256 |
|---|---|---|---|
| O0 | `177e94b0080f4f5debd9fe9b7e8e704c18c3f13a8951240d4c37d8f31d5887ab` | `f8b5c6fef9a9cf6585ad6a353c0d4a421abbd1123c54aed547adeaeda5e1df8b` | `3652a3ac62db05112ade80e318c5131ff8ca97371d39e920643ad540a10e626d` |
| O2 | `0abc7f10fe76b9a1900b35b0f1e6f5333fb4b08a6bf3363a7f108846991dbff5` | `3a92c31e0fa8560c4671852fc2a1fee87b2ebd91c8907e60770db4a3a5a712ab` | `6e8d8f630657ff5a61659490eef1317c27d34bdac201ce53a1addd1563e39928` |

The shared pre-optimization IR SHA-256 is
`85a460be25445ef2330d5cb0e144bd62a0126af98683a8cfa4c74386a7ad0ac9`.
O0/O2 checked source artifacts are byte-identical; the summary and full hash
inventory retain their identities and every fresh artifact under the focused,
cumulative, and legacy output directories.

### Retained synchronous-trap transcript and limits

The focused O2 `several-pattern-a` run used PID 246658 and the O2 ELF above. Its
24-byte loader fixture was generated after image binding, with seed
`0x0123456789abcdef`, count 7, and scenario 0. These are runtime loader data, not
interactive UART requests or precomputed target answers. Raw bytes and `run.json`
are under `build/foundation/gate7-clean-6c1b6a8/runs/O2/several-pattern-a/`.

```text
guest READY: LEMMA_DEVICE/1\nREADY\n
guest frame: 4c4d533601000800017100000000000082204bc33116f6d4
decoded: id=0x7101 status=0 checksum=0xd4f61631c34b2082
guest frame: 4c4d53360100080002710000000000000e00000000000000
decoded: id=0x7102 status=0 actual returning trap count=14
guest frame: 4c4d53360100080003710000000000000e00000000000000
decoded: id=0x7103 status=0 software denials=14
guest frame: 4c4d53360100080004710000000000000000000000000000
decoded: id=0x7104 status=0 register/canary mismatch mask=0
QEMU exit: 0; raw UART SHA-256 b4a634d16835a3e42ad7f615962f858020383f66906bedeb9e57e56c991c5c19
```

Gate 7 itself establishes only synchronous, non-nested M-mode trap behavior under
the declared pinned-machine premises. Gate 8's later actual timer acceptance is
recorded below, followed by integrated monitor/local detached qualification and
Gate 11 publication. At the historical Gate 7 checkpoint those later checks and
publication had not yet run; no later success is attributed to Gate 7 source. No scheduler, managed runtime,
privilege transition, hardware isolation, physical-board result, or G1/G2 completion
is claimed.

## Gate 8: actual machine-timer interrupts and useful foreground work

The additive `core0-v0.7` profile, `lemma-timer-test-v1` ABI, and
`test-timer-suite` category compile two elaborated roots with 40 Action and 40
scalar functions. Seven exact Actions admit time/compare/pending observation,
global-MIE save/disable/restore, MTIE control, and an asynchronous full-register
probe. Bool arguments are canonically widened at the closed machine boundary;
no source-selected MMIO address, CSR, handler, arbitrary extern, allocation,
threading runtime, atomics extension, or SBI call is introduced. Transitive
timer/interrupt/machine-state and ordered-IO effects are checked explicitly.

The pinned QEMU source and DTB establish hart-0 MTIMECMP `0x02004000`, MTIME
`0x0200bff8`, 10,000,000-Hz timebase, and cause `0x8000000000000007`.
The [timer audit](../audits/timers-core0-v07.md) records immutable source hashes,
ISA sections, naturally aligned RV64 64-bit access, eventual MTIP update,
possible delayed/spurious observations, and the unchanged no-NMI/non-nesting
entry-tail premises. This is the QEMU CLINT compatibility node backed by ACLINT
MTIMER, not another board's timer or a PLIC/SBI path.

### Executed clean qualification

Final precommit host suites passed: scaffold 18/18, Core0 32/32, foundation
339/339, and scaffold metadata valid. The actual Gate 8 Lean build passed 52 jobs
and 52 CFG checks. After committing `42674c1...`, these commands exited zero:

```sh
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all \
  --work-dir build/foundation/gates1-8-clean-42674c1 --clean --timeout 300 --qemu-timeout 20
nix develop --no-write-lock-file --command ./scripts/check-core0.sh \
  --work-dir build/core0/task002-gate8-clean --clean
```

All eight cumulative children passed: `24+136+88+14+104+28+32+30 = 456` fresh
boots. Gate 8 itself ran 30 boots: six positives, five input rejections, and
two extra clean controls plus two mutants per optimization profile. Its positive
corpus observed 737 real timer entries/profile, 1,474 total; extra control/mutant
entries are not folded into that count. Legacy acceptance passed 10 cases/profile,
13 intended rejections, and 23 boots with its reproducibility/source-mutation/
foreign-object checks. The 39 cumulative and eight legacy provenance records all
identify exact clean `42674c1...`.

There was no separate clean focused Gate 8 run. The earlier dirty development
focused report at `build/foundation/gate8-integration-final/gate8-results.json`
passed 30 boots/1,474 entries, SHA-256
`715fd9346126151aa81f700dc3b0a645edfe84d8e5bc649ab9418e2156852e53`;
it is historical development evidence, not clean acceptance. The first strict
attempt at `build/foundation/gate8-integration/` failed closed when
`audit_core0.py` changed midrun and O0 mutation2 source binding rejected. Its
partial artifacts/check-failure record remain retained; that failure received
no behavioral-mutant detection credit.

### Actual delivery, accounting, and distinguishing failures

| Positive case | O0/O2 real entries | O0/O2 work quanta | O0/O2 overflow | O0/O2 skipped periods |
|---|---:|---:|---:|---:|
| overflow-zero | 256 / 256 | 9,992 / 14,844 | 240 / 240 | 1 / 1 |
| overflow-wrap-seed | 256 / 256 | 10,323 / 16,414 | 240 / 240 | 2 / 0 |
| masked-pending | 1 / 1 | 0 / 0 | 0 / 0 | 0 / 0 |
| forced-catch-up | 32 / 32 | 862 / 1,117 | 16 / 16 | 8 / 5 |
| shutdown | 64 / 64 | 4,639 / 6,831 | 48 / 48 | 0 / 0 |
| interleaved-wrap | 128 / 128 | 4,778 / 4,921 | 0 / 0 | 1 / 1 |

Each work quantum executes 128 wrapping mix steps. The guest recomputes the
foreground result with interrupts disabled, and the independent host oracle
checks it using the observed quantum count. O0/O2 work counts and checksums need
not be identical: QEMU virtual-time delivery is not an instruction-count or
wall-clock oracle. Every stress case performed useful foreground computation;
the one-event masked/pending fixture deliberately needs none. All context/guard
masks were zero. The asynchronous sentinel probe checks all 31 integer registers
within its bounded enable window; checksum/ring checks cover the wider event
stream, not a claim of complete sentinel instrumentation on every entry.

Compiled Lean owns the non-allocating ISR, phase-reset rearming, sixteen-record
ring, drop-on-full accounting, critical sections, validation, and deferred UART
encoding. Masked delivery first observed real MTIP while the entry count stayed
zero, then unmasked inside the sentinel probe. Catch-up performs constant work:
`next = now + period`, recording `(now - oldDeadline) / period` separately from
hardware entries. Periods are 1..1,000,000 and `now <= 0x7fffffffffffffff-period`;
wrap is not silently admitted. Interleaved consumption advanced head/tail to
128 with zero overflow, exercising physical ring wrap. Full-buffer cases visibly
dropped events; final accounting requires `hardware = head + overflow` and a
drained ring. The host checks every retained physical record's sequence/time,
cause, and actual ELF executable PC; the guest validates every consumed record.
The last sixteen records are not a complete interrupt trace.

Shutdown masks global MIE, clears MTIE, parks compare at all ones, marks the
source state inactive, and re-enables global MIE during bounded foreground work.
Before/after hardware counts remained equal, including 512 shutdown quanta in
the dedicated scenario. All ones is far future only within the stated domain,
not a timeless disable mechanism across wrap. Pending state is observed without
assuming immediate architectural deassertion. No host sleep, injected software
tick, or manual ISR call counted as hardware delivery.

Both wrong-S3-slot mutants built, audited, booted, and emitted ID `0x81ff`,
status/exit 20, value `0x40000`. Both disabled-arming mutants changed only the
compare store from `sd a0,0(t0)` to `sd t1,0(t0)`, parking the far-future value;
they emitted the same ID with status/exit 21, value zero. Each had an unchanged
successful clean control. All four were exact behavioral detections, not timeout,
compile/audit rejection, malformed output, or missing-file outcomes. Invalid
zero/excess goal, zero/excess period, and malformed scenario terminated with
16, 16, 22, 22, and 14 respectively in both profiles. Four exact frontend
fixtures rejected; 26 policy predicates, six finite-model examples, and the
actual frontend/effect/lowering probe passed.

Six local Nat-model lemmas establish future/nonwrapping deadlines, one hardware
count per modeled enqueue, separate skipped accounting, capacity preservation,
and exact drop overflow. `valid_nextDeadline_greater` has no axioms; the other
five depend only on `propext`. They do not model hardware delivery, prove the
UInt64 source-to-model correspondence, or prove compiler/hardware correctness.

### Artifact/resource audit and retained transcript

The two-object image closure remains exact. The audit checks seven timer machine
bodies, exact CSR roles and register slots, 64-bit MTIMER/fence sequences, complete
integer preservation, executable PCs, final body hashes, unknown/system instruction
rejection, manifests/effects/provenance, and ordered shared-memory calls. It finds
three fixed MTIMER accesses (startup park, clock load, compare store), no compiled
program MMIO escape, fourteen timer fences, and zero privileged instructions in
80 compiled functions. Named CSR roles include twelve vector operations and sum
to 28 over the complete startup/primitive map. The historical raw report retains
an inherited `machine_csr_operations=11` aggregate; it is stale trap-only metadata,
not the total or an omitted-instruction allowance. The exact named map and all
per-function sequences were checked. Gate 9 development corrects that aggregate
to 28; it does not rewrite the retained clean Gate 8 report. O2's
single `llvm.umin.i64` is restricted to the exact retained-record bound of sixteen;
its sole merged compare call is bound to the mutually exclusive deadline branches.
These optimizer accommodations are explicit checks, not arbitrary intrinsic or
call allowances. The byte/alias inference remains bounded, not a full machine CFG
proof. Foreground stack chains are O0 3,088/O2 512 bytes against 65,520 usable;
dispatcher chains 976/272 against 16,048, separately accounting for the 288-byte
frame and 16-byte outgoing slot.

| Profile | Audit SHA-256 | Image SHA-256 |
|---|---|---|
| O0 | `4b541f578e0ea596683acc4a1dcacfe80b38b9bdfe2a1551f20c3302b8ac95fa` | `86b3df55da352176d9246bc70b8956e3e029b8feed58243084c1140c8804b7f8` |
| O2 | `f67687f2742c23f67c13ab63c2d97f0fa56dbda014f649d72df793868585166e` | `e7a4700e2bee1ef5ba1b5857642aad68b170ddca8f5a91400267640edaa7ea33` |

The actual clean O2 interleaved-wrap transcript (PID 280439) decodes in part as:

```text
runtime fixture: seed=0xa55aa55a5aa55aa5 goal=128 period=10000 scenario=4
guest READY: LEMMA_DEVICE/1\nREADY\n
id=0x8101 status=0 checksum=0xa5727edaab989825
id=0x8102 status=0 foreground quanta=4921
id=0x8103 status=0 hardware IRQs=128
head=tail=128 overflow=0 skipped=1 context_mask=guard_mask=0
shutdown count before=after=128; last record sequence=128 cause=0x8000000000000007
QEMU exit=0
```

Raw frames/fixture/run record are at
`build/foundation/gates1-8-clean-42674c1/gate8/runs/O2/interleaved-wrap/`;
UART SHA-256 is
`31487da4d1f8bf8bedc0fced343ec92ba36d4b8aab3670cc55138fe91612e6cb`.
This uses post-build loader data, not the integrated interactive monitor.
Later Gate 9 monitor and local Gate 10 detached qualification are recorded below;
publication and the later actual CI failure are recorded under Gate 11. No Stage II
unit, G1, G2, scheduler,
managed runtime, isolation, physical board, or hard-real-time claim is completed.

## Gate 9: integrated freestanding diagnostic monitor

The coherent `test-monitor-image`, ABI `lemma-monitor-v1`, reuses `core0-v0.7`
without adding a source-language primitive or machine glue. Genuine elaboration
checks `Lemma.Examples.Foundation.Monitor.foreground` and the nine-word
`Timer.dispatch`, with 85 Action and 54 scalar functions. The exact two linked
objects remain `program.o` and `startup.o`; there is no hosted IO, loader fixture,
managed runtime or host-precomputed guest answer. Parsing, validation, command
dispatch, byte fill/sum, scalar selection, trap/timer lifecycle and formatting are
compiled Lean. [The monitor contract](../audits/monitor-core0-v07.md) records the
wire format and bounded policy in detail.

Clean focused acceptance used implementation `8fd45d8458f4901c7a2d4debcb60ebd71f18a39c`,
tree `965b550c576f80284a1a24c427d9704b517d160d`:

```sh
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 9 \
  --work-dir build/foundation/gate9-clean-8fd45d8 --clean --timeout 300 --qemu-timeout 20
```

Exit 0: 18 fresh boots, 1,598 handled requests, 1,461 actual hardware IRQs,
20 synchronous recoveries and 192 retained records checked. Fifty source policy
probes, the real frontend/lowering probe and four intended source rejections
passed. Both build provenance records name exact clean `8fd45d8...`, each with
101 source inputs. An independent review replayed all 18 retained raw sessions,
hashes, bindings and provenance. Actual Lean build passed 53 jobs with 52 CFG
checks; precommit host suites passed foundation 398, Core0 32 and scaffold 18,
with metadata valid. Earlier dirty `gate9-integration-01` observed 1,465 IRQs;
that is development evidence, not the 1,461-IRQ clean acceptance.

One unchanged ELF per optimization profile serves two differing mixed sessions,
five terminal sessions and two request-budget cases. Inputs are sent only after
compiled `LEMMA_MONITOR/1\nREADY\n`; no rebuilding occurs between streams.
Each mixed session handles 143 requests, including 25 recoverable errors,
five actual synchronous recoveries and 48 checked records. Observed hardware
IRQs were O0 376/356 and O2 373/354 for mixed-zero/mixed-wrap; the active truncated
prefix adds one per profile. Counts may vary with execution, so elapsed time and
an exact inter-IRQ spacing are not correctness oracles.

Requests use a 16-byte `LMQ9` v1 header with command, length, zero flags and
UInt64 ID, followed by at most 32 payload bytes. Responses are fixed 48-byte
`LMS9` frames with echoed ID, status and four UInt64 values. The ten commands are
HELLO, STATUS, EVAL, FILL, CHECKSUM, TRAP_TEST, TIMER_START, TIMER_STOP, TICKS and EXIT.
The 256-request limit allows EXIT as request 256; exhausting it without EXIT
terminates status 9. Bounded malformed headers recover with 14, wrong lengths
with 16, unknown commands with 17, denied intervals with 7. Oversize input
terminates 16, truncated header/payload 15, and missing input 12. Active truncated
input tests cleanup. These expected terminal rejections remain distinct from a
successful EXIT, a process failure or a host timeout.

The logical user buffer is `[0,3840)` at scratch offsets 256--4095, disjoint from
parser bytes 0--47. Preflight uses `offset <= 3840` then
`length <= 3840-offset`; zero length at the end is valid, wrapping/out-of-range
intervals and values above 255 are rejected before writing. The mixed sessions
check full-buffer fill/checksum, both endpoints and denied writes, then reuse the
same image for fresh arithmetic, authorized ECALL/EBREAK, real IRQ-dependent
mixing, visible overflow, record peek/pop and ring wrap, timer restart/stop and
orderly EXIT. Host checksum/mixing validation uses actual response data and
reported useful quanta, not a constant baked into the image.

Monitor TIMER_START deliberately narrows the lower-level deadline domain to
10,000--1,000,000 ticks. A retained development period-one request timed out after
three seconds and QEMU was killed/reaped; sustained pending delivery can starve
foreground progress. Requests below 10,000 now return status 22 without arming.
This is an empirically qualified bounded monitor policy, not worst-case latency
or a real-time guarantee. STOP retains eight useful 128-step quanta through a
volatile private checksum witness; the O2 audit checks its eight ordered unrolled
calls rather than silently accepting optimized-away work. TICKS snapshots/ring
access occur with saved/masked MIE, and UART formatting occurs after restore.

The expanded audit retains exact source/effect/IR closure, volatile memory guards,
UART/fence sequences, fixed machine calls, final ELF/disassembly/relocation checks
and the two-object provenance rule. It records 139 compiled functions with zero
privileged instructions and no GP/TP use, 16 structured startup functions,
28 named CSR operations, three 64-bit timer MMIO sites and six byte-wide UART
sites. Gate 9 correctly reports the total 28; the stale inherited aggregate 11
in the immutable Gate 8 raw report remains a disclosed historical metadata issue.
No optimizer intrinsic appears in either monitor profile. Foreground stack chains
are O0 3,776/O2 720 bytes against 65,520 usable; dispatcher chains 976/272 against
16,048. These are optimized LLVM direct-call graphs weighted by object stack
metadata, not a reconstructed whole-machine CFG or compiler proof.

| Profile | ELF SHA-256 | Audit SHA-256 |
|---|---|---|
| O0 | `b72bf055b3d492989d24043a01b7dbeb25eda6c5161d4c3dc9f5a4c037f53d68` | `32fdeafd007ac98675eb55a4e9d9e5a6596edb4f7bba213fd3f74fdf4ac94a73` |
| O2 | `8b1c19592419c09983a4d2f72731cda9701d48de63b535ad5524be69eee07382` | `bd4ade2153cc67a434f374d708af26a87d3383fd38141ac64417916f91a65145` |

Actual O2 mixed-zero frames (PID 291257), decoded compactly:

```text
id=9000 HELLO -> status=0 [31304e4f4d4d454c,7,1,3ff]
id=9014 FILL(0,3840,90) -> status=0 [3840,345600,0,0]
id=9015 CHECKSUM(0,3840) -> status=0 [345600,3840,0,0]
id=901b FILL(3840,1,0) -> status=7 [0,0,0,0]
id=9021 TRAP_TEST(ECALL) -> status=0 [0,1,0,0]
id=902e TIMER_START(10000) -> status=0 [1,10000,1555875,0]
id=9031 TRAP_TEST(ECALL, timer active) -> status=0 [0,1,5,5]
id=9033 EVAL(IRQ-progress,seed=0,delta=64) -> status=0 [d38c22f10ed34d00,2705,9,73]
id=9036 TICKS(peek,0) -> status=0 [1,1545875,80001afc,8000000000000007]
id=908d STATUS -> status=0 [142,25,5,4d641b9d2b5cdd5a]
id=908e EXIT -> status=0 [143,5,17,0]; QEMU exit=0
```

IDs, checksums, PCs and HELLO tag above are hexadecimal; other numbers are decimal.
Raw sent/received frames, stderr and `run.json` are at
`build/foundation/gate9-clean-8fd45d8/runs/O2/mixed-zero/`; received SHA-256 is
`5aaec282cebb41eeab5c3ddd5dc02b7f17ed9b668323b7037d62f2069295abdc`.
The session driver used by acceptance is `python3 scripts/run_monitor_session.py
--image build/foundation/gate9-clean-8fd45d8/O2/image.elf --output-dir <fresh-dir>
--scenario mixed-zero --timeout 20 --clean`, inside the pinned environment.
Its exact QEMU argv is retained in each run record. This example is decoded guest
output, not a host-emitted success banner.

Gate 9 was the highest passing gate at this focused checkpoint. The historical
accepted cumulative Gates 1--8
and legacy baseline is `42674c1`; neither is silently attributed to `8fd45d8`.
Later clean cumulative/legacy checks at `8fe29c4` passed, but its qualifier failed
as recorded below. Fixed-candidate local Gate 10 acceptance is recorded later;
actual CI remains separate.
Publication had not been attempted at the focused Gate 9 checkpoint; current
publication/CI state is under Gate 11 below. The monitor adds finite integration
tests and audits, not new proof lemmas or any Stage II/G1/G2 completion.

## Gate 10 development and failed first qualification (historical)

At this historical preparation point, Gate 10 was in progress and Gate 9 was the
highest accepted gate. The successful fixed-candidate qualification follows below.
The first qualification candidate `8fe29c4d435ab12841dbc80f09580f580b0e3fc0`, tree
`8bdaf06023726917b25f209613b9ab6d17cd5ad5`, ran in a separate clean detached
worktree at `/home/sreekumaar/Downloads/lemma/build/qualification-worktree.BeCycl`.
It initially had neither `.lake` nor build output; no previous outputs were copied.
Its cold Lean build passed 53 jobs. Fresh hosts passed foundation 433 in 32.102
seconds, Core0 32, scaffold 18 and metadata. Cumulative `--all --stress` passed
482 boots; its monitor child ran 26 boots, handled 2,742 requests and observed
4,374 hardware IRQs, 60 synchronous recoveries and 576 retained records.
The default/stress split is 18/8 boots, 1,598/1,144 requests, 1,466/2,908 IRQs,
20/40 recoveries and 192/384 records. Fresh legacy acceptance passed 23 boots,
ten cases/profile and 13 expected rejections. These clean results remain valid
at `8fe29c4`; the qualifier failure below prevents Gate 10 acceptance.

Root-relative retained report identities (prefix
`build/qualification-worktree.BeCycl/`):

- `build/foundation/gates1-9-clean/all-results.json`:
  `84510c8134fe8dcf9bfc77cc0ef0eff41c1fa44b53c601d061c7b29abfbcb1d5`.
- `build/foundation/gates1-9-clean/gate9/gate9-results.json`:
  `5b3944da77baf639798ed9254dcb8ba8d060f89855935c2e011025a0af4b9a5b`.
- `build/core0/qualification-legacy/check-results.json`:
  `03a7b5bbe7fbc1c7b27659a1a94ddc4c45e658e413968ae5b22045487dc2e1ab`.

The actual qualifier exited 1 during final report validation with
`qualification artifact roles are duplicate`. Canonical PASS is absent;
149 intermediate files, including rebuilds and five failure experiments, remain
retained. Failure report `build/foundation/qualification/qualification-failure.json`
under that prefix hashes to
`50f784c97c1fd53c47763f951c4d7a3d7b2b85ba234446b36df84dcec16c21fd`.
All eight detached host/check logs are retained at `build/qualification-host/`.
A failed final report is not credited as successful qualification even when its
intermediate checks produced useful evidence.

The minimal fix assigns distinct semantic roles to four colliding command-stream
artifacts without changing target semantics or weakening strict 66-artifact and
eight-mandatory-role validation. Actual-callsite/full-catalog regressions passed
15 focused tests; fresh precommit foundation passed 435 in 35.318 seconds,
Core0 32, scaffold 18 and metadata. Logs are at
`build/foundation/gate10-role-fix-host/`. The new committed candidate is
`e0e1f2188fba1d26fbdd8723f37091001802064d`, tree
`9660ade13a0b202bb0a76325eb36cf0c2b75a7d4`, in new detached worktree
`/home/sreekumaar/Downloads/lemma/build/qualification-worktree.hJDCyB`.
That worktree also began without `.lake` or build outputs and copied no prior
outputs. Its fresh cold Lean build passed 53 jobs; metadata and scaffold 18,
Core0 32 and foundation 435 tests (35.382 seconds) passed. These were the completed
checks at the preparatory checkpoint. The later cumulative, legacy and qualifier
all actually passed as recorded below. That successful `e0e1f2` checkpoint and
the failed earlier attempt remain historical; the current inventory now binds
the later fully qualified repair source `09c47ba`.

The earlier development `--all --stress` command at dirty `8fd45d8` passed
482 boots in `build/foundation/gates1-9-stress-dev-01`. The monitor child ran the
18 default plus eight additional deterministic stress sessions (26 boots total),
handling 2,742 requests with 4,389 observed hardware IRQs, 60 synchronous
recoveries and 576 retained records. This run predates review fixes and is
historical development evidence, not clean acceptance. Its aggregate SHA-256 is
`a81a1ece8363d50c8a2eea047d156014c6e7acec99fa03d75d9d0169739c92fc`;
the Gate 9 child is
`57c2cfa6832d207c3a3aa038699d87bca450c6ec51dcb275843ee565b12a77df`.

Independent review closed five host-harness/qualification issues: strict JSON
integers, exact retained schema/QEMU argv/full binding, ELF-derived machine
witnesses, malformed-CLI stale-PASS cleanup, and cold CI host-test build ordering.
Post-fix precommit suites actually passed foundation 433/433 in 32.250 seconds,
Core0 32/32, scaffold 18/18 and metadata; logs remain under
`build/foundation/gate10-host-dev-postfix/`. These host checks do not substitute
for the subsequent clean target qualification or an actual GitHub CI run.

A real malformed CLI probe copied the prior successful aggregate, then supplied
`--timeout not-a-number`. It returned 2, removed the copied `all-results.json`
PASS and wrote `harness-input-failure` / `CLI`; the retained old report hashes to
the development aggregate above. The failure report at
`build/foundation/gate10-malformed-cli-dev.mBxPSQ/check-failure.json` hashes to
`04d6682e4fba6c729bc3f2d7b332837dc43b56f3ade27e1502942e532bdc4d0a`.
This is an observed harness-failure test, not successful guest execution or a
behavioral compiler/timer mutant. The later clean cumulative/legacy passes above
remain distinct from the failed qualifier. No actual CI result or Gate 11 publication is inferred from these development
checks; successful local Gate 10 qualification is recorded separately below.

## Gate 10: historical successful clean detached qualification at e0e1f2

The entire fresh sequential pipeline passed at exact clean implementation
`e0e1f2188fba1d26fbdd8723f37091001802064d`, tree
`9660ade13a0b202bb0a76325eb36cf0c2b75a7d4`, in
`/home/sreekumaar/Downloads/lemma/build/qualification-worktree.hJDCyB`.
It began with no `.lake` or build output, copied no earlier outputs, and remained
clean throughout. Tested implementation and later report-bearing revisions are
separate; this report does not hash or claim its own future commit.

The commands below were actually run inside that detached repository. Relative
paths in commands are relative to it; root-relative retained artifact paths need
the prefix `build/qualification-worktree.hJDCyB/`.

```sh
nix develop --no-write-lock-file --command python3 scripts/check_scaffold.py
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/scaffold -v
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
nix develop --no-write-lock-file --command lake build
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --all --stress \
  --work-dir build/foundation/gates1-9-clean --clean --timeout 300 --qemu-timeout 20
nix develop --no-write-lock-file --command ./scripts/check-core0.sh \
  --work-dir build/core0/qualification-legacy --clean
nix develop --no-write-lock-file --command python3 scripts/qualify_foundation.py \
  --gate9-dir build/foundation/gates1-9-clean/gate9 \
  --work-dir build/foundation/qualification --clean --timeout 300 --qemu-timeout 20
```

All exited 0. Metadata and scaffold 18, cold Lean build 53 jobs (52 CFG checks),
Core0 host 32 and foundation host 435 tests (35.382 seconds) passed. Eight closed
logs are retained at child `build/qualification-host/`. Full cumulative stress
passed 24+136+88+14+104+28+32+30+26 = **482 fresh target boots**. Same-source legacy
separately passed 23 boots, ten cases/profile and 13 expected source rejections,
with reproducibility, changed-source behavior and foreign-object rejection.
The total is 505 target boots; the qualifier replays retained monitor sessions
and is not credited with 26 additional boots.

The monitor normal/stress matrix passed:

| Corpus | Boots | Requests | Actual hardware IRQs | Sync recoveries | Retained records |
|---|---:|---:|---:|---:|---:|
| Default O0/O2 | 18 | 1,598 | 1,417 | 20 | 192 |
| Additional bounded stress | 8 | 1,144 | 2,826 | 40 | 384 |
| Total | 26 | 2,742 | 4,243 | 60 | 576 |

Stress adds four deterministic mixed streams per profile, preserving one ELF per
profile, fresh runtime UART input, bounded useful checksum/mixing work, checked
buffer denial/recovery, actual traps, overflow/wrap and shutdown. IRQ counts differ
from historical runs without implying a failure: useful completed work and actual
observations drive the host oracle; exact elapsed timing is not asserted. Fifty
source policy probes, the genuine frontend/lowering probe and four source rejection
fixtures passed. The strengthened source/binding closure records 102 inputs/profile.
The audit preserves the same two-object runtime closure, full integer state,
fixed timer/UART accesses and 28 named CSR operations; no accepted language or
target primitive was broadened by the qualification-role fix.

The successful qualifier independently revalidated all 26 retained sessions,
including raw-frame hashes, exact QEMU argv, schema/types, source/ELF/ABI binding,
machine-derived executable witnesses, distinct PIDs, protocol replies, useful
computation and terminal outcomes. It rebuilt O0 and O2 independently and compared
16 intended deterministic artifacts/profile byte-for-byte: checked manifests,
normalized source, ABI/symbol/layout/device/startup/linker artifacts, pre/post LLVM,
both objects, ELF/map and DTB/DTS. Reproducibility is within each profile; O0 and O2
are not required to match one another.

Build/audit report directory fields and their referenced provenance digest differ
intentionally. Provenance keeps identical stable source/toolchain/link/target fields
and command structure, while output directories, command elapsed times and observed
stdout/stderr differ. Those differences are retained and enumerated, not deleted
to manufacture matching hashes. The final qualifier validates all 66 artifact paths
and 66 semantic roles as unique, including its eight mandatory-role closure.

Five actual failure-path experiments passed their intended checks:

| Experiment | Observed distinction |
|---|---|
| Seeded stale Gate 9 PASS + invalid finite timeout | Exit 1, `harness-input-failure`; canonical PASS removed. |
| Seeded stale runner PASS + invalid timeout | Exit 1, `image-or-harness-rejection`; failure replaces PASS and retains raw files. |
| Missing `program.o` in isolated artifact copy | Audit exit 1 with missing-artifact diagnostic; no new audit PASS. |
| Tampered pre-optimization LLVM in isolated copy | Audit exit 1 with exact source/LLVM closure rejection. |
| Missing retained `received.bin` | Retained-session validation rejects missing evidence; old PASS quarantined. |

The isolated stale-runner negative `run.json` deliberately retains a bare `NaN`
timeout from the invalid input; that negative child record is not RFC-strict JSON.
The canonical successful qualification report is strict JSON. Consumers must not
assume every negative raw child artifact uses the successful report schema.

Accepted images were not modified. These are harness/audit/evidence failure tests,
not new behavioral compiler-mutant detections or guest successes. Earlier cumulative
gates separately retain their actual distinguishing compiler/context/missing-IRQ
mutants. The previous 8fe29 qualifier failure remains preserved and receives no
successful-qualification credit.

Current O0/O2 ELF hashes remain respectively
`b72bf055b3d492989d24043a01b7dbeb25eda6c5161d4c3dc9f5a4c037f53d68` and
`8b1c19592419c09983a4d2f72731cda9701d48de63b535ad5524be69eee07382`;
source/provenance-bound audit hashes are now
`b87d3fe456de85ea817098921b1dadc30f5260c6f0631a324e53944b5eb37cb8` and
`b4c3425874cbe7d735927f89a3ccd1e022dc5fbdc5ed0d7abbe34544f995b7ea`.

Actual final O2 mixed-zero sample, PID 332603 (IDs/checksums/PCs/tag/capability bitmap hexadecimal;
other numbers decimal):

```text
READY: LEMMA_MONITOR/1\nREADY\n
id=9000 HELLO -> status=0 [31304e4f4d4d454c,7,1,3ff]
id=9014 FILL(0,3840,90) -> status=0 [3840,345600,0,0]
id=9015 CHECKSUM(0,3840) -> status=0 [345600,3840,0,0]
id=901b FILL(3840,1,0) -> status=7 [0,0,0,0]
id=9021 TRAP_TEST(ECALL) -> status=0 [0,1,0,0]
id=902e TIMER_START(10000) -> status=0 [1,10000,885109,0]
id=9031 TRAP_TEST(ECALL, timer active) -> status=0 [0,1,3,3]
id=9033 EVAL(IRQ-progress,seed=0,delta=64) -> status=0 [aae526ec967c9c00,6110,5,69]
id=9036 TICKS(peek,0) -> status=0 [1,875109,80001afc,8000000000000007]
id=908d STATUS -> status=0 [142,25,5,d60eeaddd4ca455a]
id=908e EXIT -> status=0 [143,5,17,0]; QEMU exit=0
```

This session observed 358 hardware IRQs across its timer lifetimes, five synchronous
recoveries, 48 checked records, overflow/wrap and independently validated checksum
work. The final lifetime counter 17 is not confused with the aggregate 358.
Raw files are at child `build/foundation/gates1-9-clean/gate9/runs/O2/mixed-zero/`;
received SHA-256 is
`1a30ecdac0aca89c10a71ba77b999e876846a8e2504cf2349eb41eba1751593d`.
Acceptance used the actual session interface (with a fresh output directory):

```sh
nix develop --no-write-lock-file --command python3 scripts/run_monitor_session.py \
  --image build/foundation/gates1-9-clean/gate9/O2/image.elf \
  --output-dir <fresh-build-directory> --scenario mixed-zero --timeout 20 --clean
```

The cumulative checker invoked that interface; the example does not claim an extra
manual boot. At this historical e0e1f2 checkpoint, local Gate 10 was the highest
passing gate. Gate 11
publication now exists as recorded below. Initial CI later exposed the Gate 3
pinned-source prerequisite; subsequent repaired-source local qualification is
recorded next. The pinned CI workflow and local checks are not themselves
remote CI success evidence. All construction units remain partial; conditional
models/lemmas, artifact audits, finite target tests and physical measurements remain
distinct. No compiler proof, WCET, supervisor/user isolation, managed runtime,
scheduler, physical-board compatibility, G1/G2 or full Task 002 completion is claimed.

## Gate 10: current repaired-source clean qualification at 09c47ba

The minimal host-only repair realizes immutable `pkgs.lean4.src` with
`nix build --no-link --print-out-paths` before checking the pinned UInt source and
hash. It changes no target semantics, accepted language or toolchain pins. Three
focused host regressions and an actual realization probe passed; their development
logs remain separate from the following complete clean run.

All eight commands listed in the historical Gate 10 command block above ran again,
in exactly that order and each via `nix develop --no-write-lock-file --command`,
in a new cold detached worktree:
`/home/sreekumaar/Downloads/lemma/build/qualification-worktree.exc0kN`.
Exact source is `09c47ba24577da87390f4c693237fe71ab67c965`, tree
`7051d19087e09a6eede78210fdbe7652105e355d`. It initially contained no `.lake`/build
outputs, copied no prior outputs and stayed clean throughout. Every command exited 0:
metadata, scaffold 18 (2.696 s), Core0 32 (1.156 s), cold Lean 53 jobs/52 CFG checks,
foundation 438 (24.635 s), cumulative stress, legacy and qualifier. All eight
closed command logs are at child `build/qualification-host/`.

| Fresh local scope | Boots / replays | Result |
|---|---:|---|
| Cumulative Gates 1--9 with stress | 482 boots | 24+136+88+14+104+28+32+30+26; all passed. |
| Same-source legacy Core0 | 23 boots | 10 cases/profile, 13 rejections, mutation/audit/reproducibility passed. |
| Independent qualifier | 26 retained-session replays | Two profiles, 16 byte-identical artifacts/profile, five actual failure experiments, 66 unique paths/roles. |

There are **505 actual target boots**, not 531; qualification adds no target boots.
The complete monitor sessions handled 2,742 requests with **4,229 actual hardware
IRQs**, 60 synchronous recoveries and 576 checked retained records. Default
18 sessions accounted for 1,598 requests/1,414 IRQs/20 recoveries/192 records;
additional eight stress sessions accounted for 1,144/2,815/40/384. These are fresh
observations, not the earlier `e0e1f2` counters. The same-profile reproducibility,
intentional provenance/time/path differences, negative-child `NaN` caveat and
proof/audit/testing limits in the preceding qualification section still apply.

Current report identities (prefix `build/qualification-worktree.exc0kN/`):

- `build/foundation/gates1-9-clean/all-results.json`:
  `205719680253a4287b226f4481e21540014ce71ff6265f218a280ab1f31cdcc0`.
- `build/foundation/gates1-9-clean/gate9/gate9-results.json`:
  `712e4e24a3a7c46893c26b85ff9861f0c8d75bedbdd9a17d09a81476f0a1bc9e`.
- `build/core0/qualification-legacy/check-results.json`:
  `822c33466924cb5b4ff785d64791ded017800eb233c498804f9a7974e7a7b7b9`.
- `build/foundation/qualification/qualification-results.json`:
  `9f8aacd874d9f7c317c9f8573a92ba7b1dfd55892312055066f406ea033e78c1`.

The cumulative 41 retained provenance records are 36 actual builds plus five copied
negative-audit records; legacy eight are seven actual builds plus one copied
negative-audit record. Two qualifier rebuilds are actual builds, not copied records.
The O0/O2 monitor images retain the ELF hashes shown in the earlier qualification;
current source-bound audit hashes are
`60ac99783e9804b6ab0a8539f0bc58c4b07ea4c31a28b38b8e60e28ec7593f31` and
`5ccf622b52e811455f67419d3adf619b449eecdaaf1401794c813ee077db2dca`.
Independent artifact review verified the complete reports, source/ELF/audit bindings,
all 26 raw sessions and their 78 raw streams, exact request/frame counts, actual
machine witnesses and qualifier closure. This is an evidence review, not an extra
QEMU run, additional replay credit or a compiler proof.

Actual latest O2 mixed-zero sample, PID 357202 (IDs/checksums/PCs/tag hexadecimal;
capability bitmap and other counts decimal):

```text
id=9000 HELLO -> status=0 [31304e4f4d4d454c,7,1,1023]
id=9014 FILL(0,3840,90) -> status=0 [3840,345600,0,0]
id=9015 CHECKSUM(0,3840) -> status=0 [345600,3840,0,0]
id=901b FILL(3840,1,0) -> status=7 [0,0,0,0]
id=9021 TRAP_TEST(ECALL) -> status=0 [0,1,0,0]
id=902e TIMER_START(10000) -> status=0 [1,10000,914475,0]
id=9031 TRAP_TEST(ECALL, timer active) -> status=0 [0,1,3,3]
id=9033 EVAL(IRQ-progress,seed=0,delta=64) -> status=0 [3e882f3e44836000,5768,5,69]
id=9036 TICKS(peek,0) -> status=0 [1,904475,80001afc,8000000000000007]
id=908d STATUS -> status=0 [142,25,5,bce3223f72cdbf5a]
id=908e EXIT -> status=0 [143,5,17,0]; QEMU exit=0
```

This one session observed 360 hardware IRQs across timer lifetimes,
five synchronous recoveries, 48 checked records and overflow/wrap, with useful
validated computation. Its final lifetime counter is 17, not the aggregate
IRQ count. Raw run directory is child
`build/foundation/gates1-9-clean/gate9/runs/O2/mixed-zero/`;
received SHA-256 is `fcdfa16d5305fab2fefb025ef48c3350193dca7bbd88d947b3eaef1d22dd1916`.
The cumulative checker used the same actual `run_monitor_session.py` interaction
command shown above, against this child's O2 image, with fresh post-READY UART input.
No extra manual boot is claimed. Detailed latest counts/source/command/report
references are compactly recorded in the summary; the full inventory includes every
retained current artifact and hashes 305 tracked source files from exact
`git show 09c47ba:<path>` bytes. Historical artifacts are not relabeled or removed.
Gate 11 actual repair CI and final bounded evidence closure passed as recorded below.

## Gate 11: publication, retained initial CI failure and repair reverification

Normal publication succeeded after local qualification. Initial report-bearing
commit `ac2a95ec460d271ef00f92335ae3ea821d1b329d` (tree
`6e129a2ed43608d2bd728df26d09037d93e72fb9`) was committed after the tests, then:

```sh
env GIT_TERMINAL_PROMPT=0 git push --set-upstream origin task/002-machine-foundation
```

Exit 0; upstream is `origin/task/002-machine-foundation`. At publication the root
worktree was clean and had no ahead/behind difference. Later evidence/ledger edits
are separate reporting changes, not a claim that the current worktree is unchanged.
No force push or automatic merge was performed.

[Draft PR #2](https://github.com/srkftw/lemma/pull/2) was created at
2026-10-08 18:19:37 UTC and is open, draft and unmerged. It is stacked against
`task/001-core0-freestanding-slice` at
`b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`, because fresh read-only inspection
still found PR #1 open/draft/unmerged. PR #1 was not modified. PR #2's initial published
head was `ac2a95ec460d271ef00f92335ae3ea821d1b329d`; its body was inspected and the
435-test host count corrected. At that initial publication, tested target source
was `e0e1f2`, not this
later report commit or a synthetic PR merge. The later repaired implementation
`09c47ba` is now the latest locally qualified source, as recorded above.

Actual [Lemma pinned acceptance run #4](https://github.com/srkftw/lemma/actions/runs/37823411915)
completed with conclusion **failure**: run ID `37823411915`, attempt 1, event
`pull_request`, head `ac2a95ec...`, updated 2026-10-08 18:25:15 UTC. Full logs
confirm the actual checkout, not merely a candidate: synthetic PR merge
`0755c817d35c5d466875a2df0e7339a681d3cda4`, ref `refs/remotes/pull/2/merge`,
tree `6e129a2ed43608d2bd728df26d09037d93e72fb9`, parents Task 001 base `b8e9c593...`
and published report-bearing head `ac2a95ec...`. This is distinct from the locally
then-locally tested implementation `e0e1f2`.

Metadata job `113469966392` passed: metadata, 18 scaffold, 32 Core0, 53 Lean build
jobs/52 CFG checks and 435 foundation host tests (28.076 seconds). Legacy job
`113469965796` passed: 23 fresh boots, 10 differential cases/profile, 13 expected
source rejections, source-mutation boots and audit/reproducibility checks.
Foundation job `113469965539` passed Gates 1/2 (24/136 fresh boots) before its Gate 3
prerequisite failed. The recorded Gate 1/2 report hashes are respectively
`191b43ad556804f5b1837c5cc4ded627c7658534d18a46c6bc9102e35340e73e` and
`fe21cbda02c10384311926992f56f998d167a4b188cfd0b035a135665ea64733`.
Gate 3 did not reach target acceptance; Gates 4--9 did not run and qualification
was skipped. Evidence upload succeeded.

The actual failure was `pinned-source-semantics-failure[UInt8/UInt32/UInt64]`:

```text
pinned UInt source is missing:
/nix/store/1szlhrxfpn9a2xadknnd18ynp2qxcq7h-source/src/Init/Data/UInt/Basic.lean
```

The assignment-owned Gate 3 driver evaluated `pkgs.lean4.src` but did not realize
its source derivation in the fresh Nix store. The warm local store masked that
prerequisite. This is not external CI unavailability or evidence of a failed RV64
operation. The later code-only repair passed full clean local qualification at `09c47ba`.
Actual repair CI terminal successes are separately recorded below; this failed run
is never relabeled as green.

Full logs for all three jobs, terminal observation, extracted failure record and
earlier partial observations are retained under `build/foundation/gate11-ci/`.
The finalized terminal observation SHA-256 is
`b6fa35b57a1314563c6361b795e8bd2dbc7f8894abe0a71057df82cb6f066e7a`;
`foundation-check-failure.json` is
`1600f4afb91a9a89722d8045d8c9a8674212700cc8618fa17d055495c8a0087e`.
All retained local files and full job-log hashes are in the inventory/summary.
Earlier partial observations remain historical, not the terminal run status.

GitHub retained these artifact archives (reported metadata, not locally downloaded
archive bytes):

- Foundation `11569704127`, `foundation-rv64-37823411915-1`: 3,200,685 bytes,
  1,898 members, digest `sha256:91d590ab60ecf3c5b0e8013c69903e3ebd06adcef00f4daaa83a05ec905a9119`.
- Legacy `11570427723`, `legacy-rv64-37823411915-1`: 391,130 bytes, 341 members,
  digest `sha256:ddb8c446df9dc74dc9d91c8950ff5048c4a2f3d83e9b2e6f991f2de6586fbc7e`.
- Metadata `11570936129`, `metadata-host-suites-37823411915-1`: 25,972 bytes,
  five members, reported digest `sha256:21abd67ba63557783e2e341f188f94a777bed22adaad354cf89718ae22af6083`.

Artifact URLs, creation/expiry times and retained observation hashes are in the
machine-readable summary. No nonexistent local archive/member bytes are inventoried.
Existing local clean artifacts remain intact and independently inventoried.

At the initial failure checkpoint Gate 11 remained unaccepted. Historical local Gate 10 at exact
`e0e1f2` remains valid; latest repaired-source local Gate 10 passed at `09c47ba`.
The remote failure above remains scoped to its confirmed synthetic merge checkout.
Code-only repair candidate
`09c47ba24577da87390f4c693237fe71ab67c965` (tree
`7051d19087e09a6eede78210fdbe7652105e355d`) was normally pushed after the failure.
Three focused host tests and an actual source-realization probe passed in the
root development checkout; their closed logs are retained. Its new cold detached
full rerun at `build/qualification-worktree.exc0kN` passed, as recorded above.
That full run, not the narrow development checks, binds the current tested source.
Both later repair CI runs and final bounded evidence closure passed as recorded below.
### Gate 11 final actual repair CI and evidence closure

Both repair runs finished **success**, all six jobs:
[push run #5, 37825241614](https://github.com/srkftw/lemma/actions/runs/37825241614)
and [PR run #6, 37825247231](https://github.com/srkftw/lemma/actions/runs/37825247231).
Push checkout was exact `09c47ba24577da87390f4c693237fe71ab67c965`; actual PR
checkout was synthetic merge `e292d4359fabbf46d2c18423103333217a58c062`, parents
Task 001 base `b8e9c593...` and repair `09c47ba...`. Logs and the GitHub commit
record confirm both share tree `7051d19087e09a6eede78210fdbe7652105e355d`.
These checkout identities are distinct from the initial report-bearing `ac2a95`
and failed initial synthetic merge `0755c817`; no CI is inferred from a candidate.

Each actual run passed metadata/scaffold 18/Core0 32/cold Lean 53 jobs/52 CFG
checks/foundation 438 hosts; cumulative Gates 1--9 with stress (482 target boots);
legacy Core0 (23 target boots); and qualification (26 retained-session replays,
two profiles/16 byte-identical artifacts each/66 unique paths and roles/five
failure experiments). Push monitor observed 4,348 hardware IRQs, PR monitor 4,445;
local observed 4,229. These separate time-dependent observations are not substituted
for one another. All retain 26 monitor boots/60 synchronous recoveries; request
and record counts remain the same bounded corpus. Gate 3's report records actual
source realization and pinned UInt SHA-256
`d0f463c78f6c92585caffef53154cadd3c3e0f3b1681584f19e85d8e5da15c94`.
The checked subprocess captures realization output; no direct source-cache-copy
line is claimed in the wrapper log.

Six uploaded archives were downloaded and stream-inspected; their zip SHA-256
matched GitHub API digests. Archive bytes were **not retained locally**. IDs/digests,
all six job IDs, actual source/report hashes and detailed inspected member counts
are recorded in the summary and retained terminal observation. Foundation artifacts
are push `11571767094` (29,934,938 bytes) and PR `11572411330` (29,933,650 bytes),
3,819 members each. The full seven closed job logs (six successful plus historical
failed push foundation) and terminal metadata are retained under
`build/foundation/gate11-ci-repair/`; terminal SHA-256 is
`af6af5e23c1d4ad4613d72ff37868961fb00b35e72ebc3313aae829e5f1783f2`.
Initial failed push run #3 (`37823368652`) and PR run #4 remain failures in that
metadata, with their missing-source record and logs retained. No failed run is
rewritten as a pass, and no nonexistent local archive/member bytes are inventoried.

Supplemental final report metadata and scaffold checks passed (18 tests, 1.939 s);
closed logs are in `build/foundation/gate11-final-report-checks/`. These check
later documentation consistency, not new target acceptance. Gate 11 is accepted
for bounded Task 002 publication/CI/evidence handoff. PR #2 stays draft/unmerged;
no force push or automatic merge occurred. G1/G2 and all broader construction
units remain partial/incomplete. Future report-only commit/push identities are
external Git metadata, not invented self-referential hashes; tests remain bound
to the explicit implementation/CI revisions above.

The initial report-bearing commit is identified externally rather than embedded
as its own future hash. The current source inventory still hashes exact tested
`git show 09c47ba:<path>` bytes; later reporting/remote metadata updates do not
silently requalify source or change the historical artifact identities.

## Shared assumptions, stage mapping, and limits

The direct and checked-model routes are deliberately separate computations, but both
share the pinned Lean 4 host elaborator and type checker. They are not absolutely
independent proof systems; the target route also consumes the same checked source
before LLVM lowering. Gates 4 and 5 add independent Python computations that share
their documented contracts and selected fixed fixture/layout definitions, but these
routes are still finite testing rather than proofs. The exhaustive UInt8 comparison, 1,024-case wider-type
matrix, Gate 3's 708-case matrix, Gate 4's 112-case matrix, and metamorphic/body-change
checks are strong finite evidence, not a compiler-correctness or semantic-preservation
proof. Gates 3--5 add local mathematical lemmas with recorded axiom dependencies,
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
Gate 5 Action profile advances Units 1.1, 1.3, 1.4, 1.5, 1.7, and 1.8 with an
explicit RAM/effect contract, finite executable semantics and local proofs, audited
checked-memory lowering, source/manifest/IR mutations, and complete target post-state
comparison. It gives Unit 1.6 only regression coverage because its physical memory
observer and existing UART/finisher remain test glue rather than a new compiled
device primitive. The explicit profiles and trust manifests plus source-bound images account for the added
1.1 and 1.7 evidence. Unit 1.2 receives regression coverage only. Every listed
construction unit remains `partial`; broader G1/G2 obligations
remain open; bounded Task 002 remote CI/evidence handoff now passed.

No Stage II unit is marked passed. In particular, later Task 002 M-mode work will not
by itself satisfy Unit 2.1's supervisor-entry requirement. G1 and G2 remain
incomplete. Bounded Task 002 gates are complete; Gate 7 synchronous traps remain a historical passing checkpoint;
Local Gate 10 clean detached qualification passed; highest passing gate is now 11;
Gate 11 has published the branch/draft PR. Its initial CI failure is preserved;
the later repair passed full local qualification and both actual CI runs.
Gate 11 bounded acceptance passed without broadening any construction-unit claim.
Gate 6 directly advances partial Units 1.1,
1.3, 1.4, 1.5, 1.6, 1.7, and 1.8 through its versioned effectful device interface,
finite semantics, ordered lowering, machine audit, source-bound image, branch RAM
readbacks, and real runtime UART exchanges. Unit 1.2 retains regression coverage
only; all Stage I statuses remain partial and no Stage II unit is marked passed.

Gate 7 directly adds evidence for partial Units 1.1, 1.3, 1.4, 1.5, 1.6, 1.7,
and 1.8 through its versioned trap effects, exact membership checks, source policy
probes/local lemmas, structured entry/return lowering, machine audit, full-context
target observations, and distinguishing restore mutant. Unit 1.2 retains regression
coverage only. It also contributes narrowly scoped early Stage II evidence to
Unit 2.1 (M-mode entry and bounded stacks, not supervisor entry) and Unit 2.2
(synchronous cause/PC identification, diagnostics, saved integer state, and approved
return, not timer interrupts). Those two units are now `partial` in the
construction backlog; this evidence does not mark them or any Stage II unit passed.
Supervisor entry and the broader construction obligations remain open.

Gate 8 directly advances the same partial Stage I units as Gate 7 and adds
narrow early Stage II Unit 2.2 evidence for actual timer delivery, pending/masking,
context, bounded overflow/catch-up and shutdown. Unit 2.1 still lacks supervisor
entry; both Stage II backlog entries are partial and no Stage II unit passes.

Gate 9 directly advances partial Units 1.1, 1.3, 1.5, 1.6, 1.7 and 1.8 through
the integrated protocol/trust contract, genuine checked source, expanded artifact
audit and mixed target execution. Units 1.2 and 1.4 receive regression/integration
coverage, not a newly complete VM contract or semantics proof. It contributes
partial early Stage II 2.1/2.2 integration evidence only; supervisor entry and the
broader construction-unit obligations remain unmet. The backlog records only
partial progress for G2 and Units 2.1/2.2; no Stage II unit, G1 or G2 is passed.

Gate 10 directly advances partial Units 1.1, 1.5, 1.7 and 1.8 through retained
trust/closure checks, independent same-profile reconstruction, bounded cumulative
stress, legacy regression and failure/evidence qualification. Remaining Stage I
and early Stage II 2.1/2.2 receive regression/integration coverage, not complete
construction-unit qualification. All units, G1 and G2 remain incomplete.

-->
