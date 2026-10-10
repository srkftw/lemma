# CI and development feedback

This policy removes the second full campaign on task pushes. It preserves all
acceptance lanes, fresh project builds and observations. The cleanup is based on
PR #5 at `2d8813dd94b94f16d41beabfc1360abbebcb81a7`, separately from Task 004's
active working changes. Main was `504f6e462e502d93192ba689d16d8552ca1e68b5`;
open drafts were notebook PR #5 and silicon specification PR #6. This change
does not qualify Task 004 or repair target code.

## Trigger and cancellation policy

| Event | Before | After | Source and cancellation |
| --- | --- | --- | --- |
| `task/**` push | Full campaign | Short host preflight | Exact push SHA; newer pushes on that branch supersede preflight only |
| PR opened, synchronized or reopened, including drafts | Full campaign | One full campaign | Exact event synthetic merge SHA; newer updates cancel acceptance for that PR number only |
| Main push after merge | Full campaign | Full campaign | Exact main SHA; each run has a unique group, so every main revision keeps running and pending verification |
| Manual `workflow_dispatch` | Full campaign | Full campaign | Selected ref's event SHA; unique run group, isolated from PR/main/preflight and other manual campaigns |
| Other branch push | No campaign | No campaign | Open a draft PR for full acceptance; local preflight remains available |

There are no path filters, draft exclusions, conditional mandatory jobs, shared
build-output downloads or aggregate acceptance checks. Contract, evidence,
tooling and documentation changes still receive full PR acceptance. The jobs
start independently; preflight does not gate them. No merge queue was observed:
the public main branch endpoint reported `protected: false`, empty required
contexts/checks, and the rulesets endpoint returned `[]` on 2026-10-10. The
dedicated protection endpoint returned HTTP401 without credentials, so its
configuration could not be inspected directly. No settings changed and no
`merge_group` trigger was added. Reinspect requirements before future rollout.

GitHub's [PR event](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#pull_request)
uses a merge candidate. Branch HEAD is a separate target; removing its ordinary
full campaign does not establish that HEAD and the merge are equivalent. When
exact HEAD full qualification is needed, select that branch for a manual run or
use the pinned local acceptance interfaces. Refresh a PR with current main and
rerun acceptance when its merge candidate changes; a historical green head is
not evidence for a new merge tree.

Groups for main and manual use the event and run ID, rather than a fixed ref
with only `cancel-in-progress: false`: GitHub can otherwise replace an older
pending run. See [concurrency behavior](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency).
Ordinary PR groups use PR number; preflight has its own purpose prefix. Explicit
manual qualification cannot be canceled by an ordinary update. A user can still
cancel a run in GitHub; a canceled mandatory job is not acceptance.

## Coverage and job inventory

Main historically has eight jobs; Task 004 adds the ninth below. Every existing
job ID, displayed check name, runner, bound, acceptance command, validator,
artifact path and 14-day retention remains. This inventory describes PR #5.
All jobs use `ubuntu-24.04`, read-only contents permission, pinned actions and
checkout with credentials removed.

| Stable check name | Commands/coverage retained before and after | Bound |
| --- | --- | --- |
| Metadata and host-only suites | Scaffold checker/suite, Core0/foundation/kernel host suites, `lake build`; adds CI orchestration regressions | 45 min |
| Legacy Core0 RV64 acceptance | `check-core0.sh --clean`: independent Lean oracle, O0/O2 boots, source rejections, separate repeat builds, source mutation, foreign-link audit rejection | 45 min |
| Foundation Gates 1-9 and clean qualification | `check-foundation.sh --all --stress --clean`, then `qualify_foundation.py` consuming that run's Gate 9 directory; independent replay, repeat builds and failure experiments | 60 min |
| Task 003 implemented Gates A-E RV64 acceptance | `check_kernel.py --clean`, exact matrix/images/observations and source/tool/audit/hash revalidation | 45 min |
| Task 003 Gates F-I RV64 acceptance | `check_kernel_cumulative.py --lane F-I --clean`, eight cases plus full lane revalidation | 45 min |
| Task 003 Buffer service RV64 acceptance | `check_kernel_cumulative.py --lane J --clean`, four real service cases plus full lane revalidation | 45 min |
| Task 003 source-negative RV64 qualification | `check_kernel_mutations.py --expected-commit HEAD`, four paired control/mutant cases plus campaign revalidation | 45 min |
| Task 003 architectural containment RV64 acceptance | `check_kernel_architecture.py --clean`, twelve actual hardware fault/continuation cases plus revalidation | 45 min |
| Task 004 real notebook O0/O2 writing and cold recovery | Separately pinned host QEMU build; `check-lemmasim.sh --clean --lane writing --with-o0`; two actual 50-sample writing and new-process committed-byte/pixel recovery cases | 120 min |

The writing lane remains scoped. Task 004's full notebook, recovery/cuts, replay,
geometry, isolation and workload qualification still uses its maintained checker
and checkpoint; this CI cleanup does not shrink those obligations or infer a
pass from the writing lane. The intentionally independent references, repeated
builds, legacy profiles, stress, mutations and architecture tests are useful
redundancy. They are not outputs to share between jobs.

Each full job now runs `scripts/ci_source.py` after explicitly checking out
`github.sha`. The uploaded `build/ci/source.json` records the actual Git commit,
tree, raw commit parents, event/ref/run/job, PR head/base, runner Python version
and pin-file hashes. It rejects a dirty checkout, wrong event SHA, malformed
identity, missing pins or PR parents inconsistent with that event. Raw commit
parents work with checkout's shallow history. This supplements each lane's
existing toolchain/artifact/guest provenance; it is not a PASS report.

## Fast development loop

Run from the project checkout with an unused output directory:

```sh
python3 scripts/ci_preflight.py --output-dir build/ci/local-preflight-1
```

Preflight runs metadata plus scaffold, Core0 harness and CI policy suites using
the host Python standard library. It fails on empty suites, failures, import
errors or skipped tests and retains scoped logs/results. The hosted job has a
three-minute command limit and five-minute job limit. It does not realize Nix,
build Lean, generate RV64 artifacts or boot QEMU. A preflight pass is host
feedback only. Full metadata repeats the suites in the pinned environment.

Open a draft PR early to receive the independent parallel acceptance jobs.
For focused compiler/guest feedback, use the README's build/audit/run and lane
interfaces in `nix develop --no-write-lock-file`; choose new evidence paths and
retain failures. Final qualification requires a clean committed candidate and
the separate inherited and Task 004 interfaces. Do not move successful reports
across source revisions. A new project directory with a warm Nix store is a
clean project build, not a cold toolchain observation.

## Measurements and expected savings

[The baseline JSON](evidence/ci-efficiency-baseline.json) binds real API responses,
run IDs, outcomes, timing categories, archive sizes and an authenticated PR #5
notebook log. Detailed raw responses remain under ignored
`build/ci-efficiency/baseline/` with hashes. The API's PR `head_sha` is branch
HEAD; the fetched notebook log confirms actual synthetic merge
`ceeaf359052185b8774909c1cd3f43fd61d545e9` for that job.

| Representative campaign | Event to final job | Summed runner minutes | Uploaded archive MiB | Result |
| --- | ---: | ---: | ---: | --- |
| [Task 003 push](https://github.com/srkftw/lemma/actions/runs/38036945640) | 29m51s | 107.90 | 147.76 | Success |
| [Task 003 PR](https://github.com/srkftw/lemma/actions/runs/38036948421) | 29m51s | 124.60 | 147.96 | Success |
| [Task 004 push](https://github.com/srkftw/lemma/actions/runs/38074535663) | 32m53s | 138.75 | 157.47 | Failure |
| [Task 004 PR](https://github.com/srkftw/lemma/actions/runs/38074538129) | 34m25s | 141.42 | 154.46 | Failure |
| [Main](https://github.com/srkftw/lemma/actions/runs/38038810136) | 22m46s | 107.62 | 147.83 | Success |

Removing the sampled push campaign would eliminate its 108–139 runner minutes
and 148–157 MiB of future archives per update, minus the new preflight cost.
That is about 46–50% of paired runner time. These are estimates based on measured
old runs, not measured after-change GitHub savings or rounded billing minutes.
PR wall time does not halve merely because the duplicate disappears; reduced
runner contention is possible but unmeasured. Main and explicit manual work
remain full, and main retains every run even during rapid merges.

Per-job API queue time was 2–4 seconds; event to first runner was 3–32 seconds
(including dispatch). Nix installation took 3–9 seconds per job. Metadata's
first Nix/check step took 53–101 seconds; its Lean build step took 52–89 seconds.
The expensive target steps combine realization, compilation, audits and guest
tests, so their individual durations cannot be inferred from API timestamps.
The LemmaSim host QEMU step took 468–519 seconds. Both sampled writing steps
failed after 67–69 seconds; these do not predict a successful notebook runtime.
Upload/compression steps totaled 37–47 seconds per campaign, at most ten
seconds per lane. Archive metadata does not justify deleting evidence contents.

## Dependencies, artifacts and trust

No project outputs, PASS reports, guest observations or qualification outputs
are cached. Existing Nix binary substitution and source realization remain
mandatory on cache misses. No custom Actions dependency cache was added:
the selected existing Lean/LLVM/LLD/stock-QEMU closure alone measured
7,204,814,352 NAR bytes (6.71 GiB), excluding the additional devshell tools,
pinned Lean source and derived LemmaSim QEMU. Closure transfer/compression and
hit/miss behavior require benchmarks before proposing a cache.

A future dependency-only cache would need exact platform/runner/Nix-action keys,
`flake.nix`, `flake.lock`, `lean-toolchain`, `tooling/toolchain-lock.json`, the
LemmaSim QEMU derivation, `apply_qemu.py` and all patch inputs, and all filtered
`sim/host` C/header inputs including the durable filter. It must verify existing
NAR/tool/source identities, realize normally on a miss, allow only a trusted
main producer and restore-only PR consumers, and preserve required uncached
qualification. No hit/miss benchmark or new warmed/cold claim is made here.
See [cache trust restrictions](https://docs.github.com/en/actions/reference/workflows-and-actions/dependency-caching).

All existing artifact inclusions and always-upload steps remain, including
failure logs, binaries, raw guest observations, audits, hashes, provenance,
mutation evidence and replay inputs. New context is included in every lane;
preflight adds a small scoped artifact. No historical artifacts were deleted,
retention reduced, secrets added, token permissions widened or runner changed.
Main-only full pushes remove future duplicate uploads without altering retained
historical evidence.

## Validation and rollout

Workflow validation includes pinned actionlint, Bash syntax checks for every
inline command, Python parsing, static nine-lane contracts, evaluated concurrency
truth tables and real temporary-Git/unittest failure cases. These checks cannot
establish GitHub scheduling or successful remote cache/upload behavior. Actual
new GitHub runs require publishing; this session does not authorize a push.
Local exact-candidate commands/results and any failures are recorded separately
in the accompanying validation evidence. Cache hit/miss tests are inapplicable
because no cache path was introduced.

Keep Task 004's work isolated when applying this cleanup. This branch's diff is
relative to its PR head; do not replace a newer Task 004 workflow/checker with
the older file. If landing separately on pre-Task-004 main, port the common
trigger/provenance/preflight changes to its eight existing jobs, then retain
the ninth job when Task 004 integrates. Do not add a writing job to a tree
without its implementation. Resolve the workflow test inventory accordingly.

After authorized publication, verify a task push starts only preflight, a draft
PR starts all existing stable checks at its synthetic merge, a newer PR update
cancels only its ordinary predecessor, and two manual runs plus a main push keep
their own groups. Verify all source manifests, upload inclusions after failure,
and complete mandatory acceptance on the reviewed merge candidate. Do not treat
local expression tests as these GitHub observations.

Rollback uses a normal revert of this cleanup commit on the integration branch.
It restores duplicate task-push campaigns and the old cancellation policy;
do not delete artifacts or target/task branches. If porting to main, revert the
port commit and preserve any independently added Task 004 qualification lane.
