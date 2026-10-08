# Task 002 session state

- Repository: `/home/sreekumaar/Downloads/lemma`, origin
  `https://github.com/srkftw/lemma.git`. Leave USGCE untouched.
- Branch: `task/002-machine-foundation`; base Task 001
  `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`, stacked on unmerged draft PR #1.
- Highest passing gate: **10**. Gate 11 publication/actual CI is in progress.
- Exact clean tested implementation: `e0e1f2188fba1d26fbdd8723f37091001802064d`,
  tree `9660ade13a0b202bb0a76325eb36cf0c2b75a7d4`.
- Clean detached verification:
  `/home/sreekumaar/Downloads/lemma/build/qualification-worktree.hJDCyB`.
  Initially no `.lake` or `build`; no prior project outputs copied. It remains clean.
- Actual checks all exited 0: metadata; scaffold 18; Core0 host 32; cold Lean build
  53 jobs; foundation host 435 (35.382 seconds); cumulative stress 482 fresh boots;
  legacy 23 boots (ten cases/profile, 13 source rejections); final qualification.
- Monitor subset: 26 boots, 2,742 requests, 4,243 observed hardware IRQs,
  60 synchronous recoveries, 576 retained records. Qualification replayed these
  same 26 sessions (not extra boots), reproduced 16 artifacts/profile, passed five
  failure experiments and closed 66 unique evidence artifacts.
- Child logs: `build/qualification-host/`. Child report SHA-256:
  - `build/foundation/gates1-9-clean/all-results.json`:
    `8d8189b489e07643dcacf5f03bf4c5317fab191a5a69584f57c2c51d1c575f5f`.
  - `build/core0/qualification-legacy/check-results.json`:
    `1878d6d734d118836ddc4840f686098029339f29a164d11d185c34db3a42cafd`.
  - `build/foundation/qualification/qualification-results.json`:
    `3b7923e051835c2bd2de87b69ac365ced24b95f73d364fcf488fd5373c7284d9`.
- Current action: finalize evidence/guidance, commit the report-bearing revision,
  push normally with upstream, create a stacked draft PR, inspect actual CI.
  No Task 002 push/PR/CI has yet occurred. Do not merge or force-push.
- Keep tested implementation, later report-bearing revision, and any synthetic
  PR merge checkout distinct. Do not rerun merely to chase an evidence-commit hash.

## Exact clean acceptance commands

Run in the clean detached worktree through
`nix develop --no-write-lock-file --command`:

```sh
python3 scripts/check_scaffold.py
python3 -m unittest discover -s tests/scaffold -v
python3 -m unittest discover -s tests/core0 -v
lake build
python3 -m unittest discover -s tests/foundation -v
./scripts/check-foundation.sh --all --stress --work-dir build/foundation/gates1-9-clean --clean --timeout 300 --qemu-timeout 20
./scripts/check-core0.sh --work-dir build/core0/qualification-legacy --clean
python3 scripts/qualify_foundation.py --gate9-dir build/foundation/gates1-9-clean/gate9 --work-dir build/foundation/qualification --clean --timeout 300 --qemu-timeout 20
```

## Historical evidence and limits

The earlier clean `8fe29c4` worktree `build/qualification-worktree.BeCycl` passed
cumulative/legacy but failed qualification on four duplicate command-stream role
labels. Canonical PASS is absent and all intermediate evidence is retained.
Failure report SHA-256:
`50f784c97c1fd53c47763f951c4d7a3d7b2b85ba234446b36df84dcec16c21fd`.
Distinct semantic roles plus actual-callsite/full-catalog regressions fixed it;
strict 66-artifact/eight-mandatory-role validation was not weakened.

Earlier accepted Gates 1--8 `42674c1`, focused Gate 9 `8fd45d8`, and dirty
development runs retain their own source identities/hashes in the ledger/report.
Historical provenance totals include five copied negative-audit records, not
five additional builds. Gate 8's old raw CSR aggregate 11 was stale; its named
map sums 28, which current audit/runner derive and check. Historical reports remain
unchanged and disclosed.

Monitor: unchanged `core0-v0.7`, `test-monitor-image`, `lemma-monitor-v1`,
two linked objects, 54 scalar/85 Action functions. Inputs arrive after READY;
heavy host checks run after QEMU is reaped. Empirical monitor timer policy is
10,000--1,000,000 ticks, not a WCET guarantee. A genuine period-one development
stall was killed/reaped and is retained; actual rejection/recovery is tested.

No G1/G2 or Stage II unit completion, supervisor entry/isolation, managed
runtime/heap, scheduler, physical-board compatibility or compiler-correctness
proof. Full history: `docs/evidence/002-machine-foundation.md` and
`docs/plan/002-gates.json`.
