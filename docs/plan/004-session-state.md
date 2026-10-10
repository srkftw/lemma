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

Next: freeze/commit the narrow harness repairs; run one exact-candidate full
notebook matrix (editing, both geometries, loss, active-DMA isolation, device
faults, two real behavioral source negatives, 16 pages / 100,000 raw samples),
focused J and all required actual CI. Export final offline evidence outside
ignored `build/`, write the concise report/result/manifest, and update the draft.
Actions artifacts retain for 14 days; permanent offline retention is pending.
Do not claim Task004 completion, physical conformance, managed runtime or later
mathematics gates from this checkpoint.
