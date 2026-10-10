# Task 004 checkpoint

Branch: `task/004-lemmasim-durable-ink`, based on main
`504f6e462e502d93192ba689d16d8552ca1e68b5` after one fetch on 2026-10-10.
Status: IMPLEMENTING; the primary completion boundary is unmet.
[Draft PR #5](https://github.com/srkftw/lemma/pull/5) remains draft. No merge is authorized.

Published implementation: `80b89dcc6e26d2ebcb70bd77fc299bbfb53c4272`.
The compiled guest has the descriptor/DTB binding, 32 MiB owned pool, 16 KiB
stacks, PLIC pen/paper drivers, modern VirtIO block/flush driver, isolated record
store, integer ink/rasterizer, guest toolbar/pages/editing, and host-only hardware
models with volatile/durable media and native QEMU capture/replay. README contains
ordinary build/init/run/copy/archive commands. Executable source existence does
not pass an acceptance gate.

The clean `build/lemmasim/task004-80b89dc-full1` campaign observed O2 basic writing
and new-process committed-byte/controller-pixel recovery PASS, then was stopped
and reaped after the related inherited J audit failed before boot. Its top-level
FAIL and interruption reason remain retained; later cases are NOT_RUN. Local J
failure is in `build/worktrees/task004-inherited-kernel/build/kernel/verify-J-80b89dc`.
Actual PR CI [38081633889](https://github.com/srkftw/lemma/actions/runs/38081633889)
checks synthetic merge `e78e9fe03fed19fc7f6dcdcd3536d791aeaad335` with the same tree.
The retained snapshot/logs/artifacts are under
`build/lemmasim/ci-80b89dc-run38081633889`. Legacy Core0, foundation qualification
and host jobs passed; J, F-I, architecture and source-negative reached a stale
IPC audit requiring `Process.validateStack`. Writing failed on a missing fresh
`Store.Engine.olean` prerequisite. A-E was still running at the retained snapshot.
The next candidate repairs the audits and fresh module preparation without
weakening guards or inheriting old green results. The repaired exact current
IPC/stack validators pass retained O0 inputs and 309 pinned kernel host tests.
Fresh standalone store-cache preparation passes with nonexistent inherited
module paths (43.5 seconds); four fail-closed dependency regressions pass. These
are scoped harness observations, not new RV64 acceptance.

Separate dirty development observations remain scoped to their exact inputs.
The unchanged 100 Hz dev6 workload retained 6,250 raw samples, Saved53 and exact
independent pixels; a cold process recovered identical committed bytes/pixels.
Notebook SHA256: `0d32f5dfcb4c3f709187378d7eab6e1bb76404c46735daa98419011bfca0ae6d`.
Its runner FAILs from host observer errors remain unchanged; corrected observations
are in `build/lemmasim/focused6250-64e3bbb-input8-dev6`, manifest SHA256
`2a59db43904ca3965184d449c14014bbcfdba8f53d4b20618035965f80d9825d`.
Dirty dev5 native GTK/QMP ingress, actual replay, cold recovery and guest redraw
after reset during PaperBusy PASS in
`build/lemmasim/native-gtk-64e3bbb-dirty-dev5-attempt1`. Reset may drain/flush and is
not a power cut. Manual interaction and physical tablet input are NOT_RUN.
Selected O2 trap stack bound is 1,984 / 16,352 usable bytes including 288-byte
entry; this is not a whole-program stack proof. Observed ownership is 634 frames,
7,558 free; the final 100,000-sample memory observation remains pending.

Earlier source-specific fault/editing/replay and inherited runs are not passes
for changed executable code. Retain `build/lemmasim/inherited-a1-handoff.json`,
`build/lemmasim/ci-2d8813d-run38074538129` and the dev4/dev5 overflow failures.
Pinned host QEMU v17 SHA256:
`0e95380d2eb582ebf95f989fc6a07eac26a50c222bbbee95dd5fa5421d2864ce`.
Legacy profiles and historical evidence meanings are preserved.

The harness/archive repairs are published at `dea6281d64a44e5c409fe33e1df7bf4a5f86feb9`.
Its fresh focused J lane passes all four O0/O2 audits and real workflows, including
held-buffer denial, fault/restart and exact final accounting. Result SHA256:
`0a928036080269b3556a1b24f27116e09faece1d23b86acb61bf5e8b40116875` under
`build/worktrees/task004-inherited-kernel/build/kernel/verify-J-dea6281`.
The full notebook campaign `build/lemmasim/task004-dea6281-full1` was stopped and
reaped before its first workflow after source inspection found that reload did
not reject an unknown stored brush version or contradictory page/stroke ID.
Its original FAIL/interruption remain retained. A bounded guest header validator
and literal rejection fixtures are integrated; normal produced v1 records
remain unchanged. The focused literal/read/input-drain checks and genuine Core0
closure plus RV64 O0/O2 object generation pass. Probe result SHA256:
`9f86794ee14b9e0401633fa71d9f1db45fd35ba4802be17adaa23e5515e13b10` in
`build/lemmasim/ink-header-codegen-attempt1`. The first fixture elaboration FAIL
is retained. These J and focused observations do not pass the next linked notebook.

The header validation is published at `115a33575e0d600151b6c83b58a7b4665906f860`.
Its full run was stopped and reaped before a workflow when actual `dea6281` CI
reported another fresh prerequisite omission: `NotebookReads` imports the
separately linked Notebook module, which the kernel-only preparation never builds.
Retain `build/lemmasim/ci-dea6281-run38083119478` and
`build/lemmasim/task004-115a335-full1`; neither is a pass. Preparation now names
NotebookKernel, Notebook and CFGLower explicitly. A new private workspace with
no inherited project modules passes the three-target build and all ten fixtures
(90.93 seconds, all child processes reaped); source hashes and the outer cache
inventory are unchanged. Result SHA256:
`270b83acdccc8d28206969b3cb892dc586d14ae3d09f60d0bc33f47822adc9b0` in
`build/lemmasim/fresh-fixture-cache-115a335-checkerfix-attempt1`.
This is fresh preparation evidence, not RV64 acceptance. Actual `dea6281` CI had five
passed jobs, three cancelled jobs and one failed notebook job. The published
`115a335` PR run `38083988506` was queued at its retained initial snapshot.

Next: freeze/commit the explicit fixture preparation repair; run one exact-candidate full
notebook matrix (editing, both geometries, loss, active-DMA isolation, device
faults, two real behavioral source negatives, 16 pages / 100,000 raw samples),
all required actual CI; the unchanged J implementation retains its separate
exact `dea6281` local observation rather than inheriting it into the new notebook. Export final offline evidence outside
ignored `build/`, write the concise report/result/manifest, and update the draft.
Actions artifacts retain for 14 days; permanent offline retention is pending.
Do not claim Task004 completion, physical conformance, managed runtime or later
mathematics gates from this checkpoint.
