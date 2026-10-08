# Task 002 session state

- Repository: `/home/sreekumaar/Downloads/lemma`, origin `https://github.com/srkftw/lemma.git`.
  Leave `/home/sreekumaar/Downloads/USGCE` untouched.
- Branch: `task/002-machine-foundation`; base Task 001
  `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`, stacked on unmerged draft PR #1.
- Highest passing gate: Gate 9. Gates 0--8 retain separate clean evidence.
- Latest clean tested implementation: `8fd45d8458f4901c7a2d4debcb60ebd71f18a39c`,
  tree `965b550c576f80284a1a24c427d9704b517d160d`.
- Current gate: Gate 10 in progress. Bounded deterministic monitor stress,
  fresh profile rebuilds, stale-PASS/artifact-failure experiments and real-check CI
  are under construction; their presence is not a pass.
- Development `--all --stress` passed (482 boots) in
  `build/foundation/gates1-9-stress-dev-01` at dirty `8fd45d8` on 2026-10-08.
  Monitor child: 26 boots, 2,742 requests, 4,389 observed IRQs, 60 synchronous
  recoveries and 576 retained records. This is pre-review-fix development evidence,
  not clean Gate 10 acceptance. Full foundation host suite was 420/420 before fixes.
- Review fixes are complete and independently closed: strict retained-session
  schema/ELF binding, process integers, malformed-CLI stale-PASS cleanup and CI
  host build ordering. Final precommit hosts: foundation 433/433 (32.250 seconds),
  Core0 32/32, scaffold 18/18 and metadata valid. Logs are retained under
  `build/foundation/gate10-host-dev-postfix/`. Root's actual malformed-CLI probe
  returned 2, removed the copied PASS and classified failure as harness-input-failure
  (`build/foundation/gate10-malformed-cli-dev.mBxPSQ/`).
- Next: commit this implementation, then run all target checks, legacy Core0
  and `qualify_foundation.py` in a separate clean detached worktree without copying
  outputs. Gate 10 is not passed until those actual checks succeed.
- Gate 11 publication is unrun: no Task 002 push, PR, publication attempt or new
  actual CI result. No G1/G2, Stage II, scheduler, managed runtime, isolation or
  physical-board completion claim.

## Exact clean Gate 9 acceptance

```sh
nix develop --no-write-lock-file --command ./scripts/check-foundation.sh --phase 9 \
  --work-dir build/foundation/gate9-clean-8fd45d8 --clean --timeout 300 --qemu-timeout 20
```

Exit 0: 18 fresh boots, 1,598 handled requests, 1,461 observed hardware IRQs,
20 synchronous recoveries, 192 checked retained records, 50 direct source probes
and four source rejections. Independent review replayed all raw transcripts and
recomputed both image bindings. Both provenance records are exact clean
`8fd45d8...`, with 101 identical current source inputs and one ELF/profile.

- Report: `build/foundation/gate9-clean-8fd45d8/gate9-results.json`.
- SHA-256: `69e37da2266a4c89ddd18243600da1da52300c7edbebe264eae9033bf3841ca6`.
- O0 ELF: `b72bf055b3d492989d24043a01b7dbeb25eda6c5161d4c3dc9f5a4c037f53d68`.
- O2 ELF: `8b1c19592419c09983a4d2f72731cda9701d48de63b535ad5524be69eee07382`.
- Precommit checks: foundation 398, Core0 32, scaffold 18, metadata and actual
  Lean build 53 jobs. Later added tests require fresh counts.

## Design and evidence cautions

Monitor uses unchanged `core0-v0.7`, category `test-monitor-image`,
ABI `lemma-monitor-v1`, two linked objects, 54 scalar/85 Action functions.
All ten commands, parsing, algorithms and encoding are compiled elaborated Lean.
Inputs arrive after READY; heavy host checksums run after QEMU is reaped.

Monitor period policy is 10,000--1,000,000 ticks; lower-level Core0 is unchanged.
A genuine period-one development request stalled and was killed/reaped
(`build/foundation/gate9-period1-diagnostic-eoo8qb_n`).
Clean tests cover actual 1/9,999 rejection and recovery. This empirical diagnostic
policy is not WCET or hard-real-time proof. Private volatile events word 160
retains STOP's eight-quanta checksum; O0/O2 audit checks retained loop/work.

Gate 8's historical raw CSR aggregate 11 was stale: its checked named map sums
28. Current audit/runner derive/require 28; historical reports are preserved and
disclosed, not rebound to new source.

## Earlier immutable records

Clean cumulative Gates 1--8 at `42674c1ba773454c36c277620e2acd289539e5a2`
(tree `f7bea0b4f126275773bbc84e8fb534849ac6bb35`) passed 456 boots; same-source
legacy passed 23. Aggregate hashes:

- `build/foundation/gates1-8-clean-42674c1/all-results.json`:
  `393a2a649e3f804ea7fc332b53d9c88cdd2d789dc34c7ac7357fbdb1d4aca8de`.
- `build/core0/task002-gate8-clean/check-results.json`:
  `7ba1294f53702fb4b86ef3a8ad65173b4100a9efc0256e11b90a4a72dda89f82`.

Gate 8 report-bearing commit: `427f2663cc20573ea13c0f50297ae44de938f0b8`.
Gate 9 dirty development `build/foundation/gate9-integration-01` passed 18 boots
and 1,465 IRQs; clean acceptance above supersedes it. Earlier non-acceptance smoke
remains at `build/foundation/gate9-manual-smoke-pjx963im`.
Full history remains in `docs/evidence/002-machine-foundation.md`,
`docs/plan/002-gates.json`, retained reports and Git. These do not establish
later current-source cumulative or detached-worktree success.
