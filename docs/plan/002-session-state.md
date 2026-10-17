<!--
# Task 002 session state

- Repository: `/home/sreekumaar/Downloads/lemma`, origin
  `https://github.com/srkftw/lemma.git`. Leave USGCE untouched.
- Branch: `task/002-machine-foundation`; base Task 001
  `b8e9c59365ae8e9925e0bf6fbca6a963d990ec85`, stacked on unmerged draft PR #1.
- Highest passing gate: **11**, Task 002's bounded milestone only, not G1/G2.
- Exact clean tested implementation: `09c47ba24577da87390f4c693237fe71ab67c965`,
  tree `7051d19087e09a6eede78210fdbe7652105e355d`.
- Clean detached verification:
  `/home/sreekumaar/Downloads/lemma/build/qualification-worktree.exc0kN`.
  Initially no `.lake` or `build`; no prior project outputs copied. It remains clean.
- Actual checks all exited 0: metadata; scaffold 18; Core0 host 32; cold Lean build
  53 jobs; foundation host 438 (24.635 seconds); cumulative stress 482 fresh boots;
  legacy 23 boots (ten cases/profile, 13 source rejections); final qualification.
- Monitor subset: 26 boots, 2,742 requests, 4,229 observed hardware IRQs,
  60 synchronous recoveries, 576 retained records. Qualification replayed these
  same 26 sessions (not extra boots), reproduced 16 artifacts/profile, passed five
  failure experiments and closed 66 unique evidence artifacts.
- Child logs: `build/qualification-host/`. Child report SHA-256:
  - `build/foundation/gates1-9-clean/all-results.json`:
    `205719680253a4287b226f4481e21540014ce71ff6265f218a280ab1f31cdcc0`.
  - `build/core0/qualification-legacy/check-results.json`:
    `822c33466924cb5b4ff785d64791ded017800eb233c498804f9a7974e7a7b7b9`.
  - `build/foundation/qualification/qualification-results.json`:
    `9f8aacd874d9f7c317c9f8573a92ba7b1dfd55892312055066f406ea033e78c1`.
- Initial report-bearing revision: `ac2a95ec460d271ef00f92335ae3ea821d1b329d`,
  tree `6e129a2ed43608d2bd728df26d09037d93e72fb9`.
- Normal push succeeded (exit 0), upstream is `origin/task/002-machine-foundation`.
  Draft PR #2: https://github.com/srkftw/lemma/pull/2, open and unmerged,
  targeting `task/001-core0-freestanding-slice`; PR #1 remains unmerged.
- The repair is committed and normally pushed (exit 0). Three focused regressions,
  actual pinned-source probe, independent code review and all eight fresh clean
  acceptance commands passed. The prior successful local `e0e1f2` run remains
  historical at `build/qualification-worktree.hJDCyB`; no artifacts were rebound.
- Resume with `git status --short --branch`: Task 002 implementation/qualification
  is complete. If documentation-only report changes remain, finish their review
  and normal commit/push; inspect any automatically triggered head CI and hand off.
  If the checkout is already clean, synchronized and head CI is green, proceed
  to human review of draft PR #2 and the still-open construction backlog. Do not
  restart passing gates or rewrite reports to chase their own commit hash.
  Both implementation push run `37825241614` and PR run `37825247231` are terminal
  success, all six jobs passed; full logs, downloaded/stream-checked archive
  metadata and qualified source bindings are retained in
  `build/foundation/gate11-ci-repair/terminal-observation.json`, SHA-256
  `af6af5e23c1d4ad4613d72ff37868961fb00b35e72ebc3313aae829e5f1783f2`.
  https://github.com/srkftw/lemma/actions/runs/37825247231 .
  Logs confirm actual synthetic merge `e292d4359fabbf46d2c18423103333217a58c062`,
  tree `7051d19087e09a6eede78210fdbe7652105e355d`; push checks exact head `09c47ba`.
  Historical PR CI run `37823411915` on report head `ac2a95e...` **failed**:
  https://github.com/srkftw/lemma/actions/runs/37823411915 . Metadata/host and
  legacy jobs passed; foundation Gates 1/2 passed (24/136 boots), then Gate 3
  failed `pinned-source-semantics-failure` because `nix eval` returned an
  unrealized Lean source path. Later gates and qualification did not run.
  Completed job logs confirm actual synthetic PR merge checkout
  `0755c817d35c5d466875a2df0e7339a681d3cda4`, tree
  `6e129a2ed43608d2bd728df26d09037d93e72fb9`. Terminal metadata, failure record
  and all three logs are retained in `build/foundation/gate11-ci/`; uploaded
  failure artifact `11569704127` is retained on GitHub. Historical push run
  `37823368652` failed for the same cause; neither was relabeled green.
  Do not merge, force-push, or relabel this as an external blocker. The repair
  explicitly realizes `pkgs.lean4.src`, retaining all pinned file/hash checks.
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

-->
