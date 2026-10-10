# Task 004 checkpoint

Branch: `task/004-lemmasim-durable-ink`, based on main
`504f6e462e502d93192ba689d16d8552ca1e68b5` after one fetch on2026-10-10.
Status: IMPLEMENTING. The primary completion boundary remains unmet. Draft
[PR5](https://github.com/srkftw/lemma/pull/5) is published; no merge is authorized.

Production code provides the explicit descriptor/DTB binding, real PLIC pen and
paper devices, modern VirtIO block/flush driver, owned32MiB pool and16KiB stacks,
isolated compiled Lean store/notebook, integer pressure-aware ink, pages,
erase/undo/redo, guest toolbar/status, volatile/durable block filter and native
QEMU capture/replay. Legacy profiles/checks retain their historical evidence
meaning. Ordinary launch consumes prepared images and never formats a failed
mount; README documents build/init/run/copy/archive commands.

Exact committed `2d8813dd94b94f16d41beabfc1360abbebcb81a7` development campaign
`build/lemmasim/task004-2d8813d-full1` passes O2/O0 basic50-sample writing and
new-process committed-byte/controller-pixel recovery, then was interrupted and
reaped during editing. Its result remains FAIL; later cases are NOT_RUN.
Actual PR CI run[38074538129](https://github.com/srkftw/lemma/actions/runs/38074538129)
checks synthetic merge `ceeaf359052185b8774909c1cd3f43fd61d545e9` with that tree:
six guest jobs PASS; metadata, Task004 writing and J FAIL. Retained logs/artifacts
are under `build/lemmasim/ci-2d8813d-run38074538129`. The causes were a stale host
job inventory, missing freshly built Lean modules, and a quota fixture releasing
its own buffer before it could witness denial. The next candidate repairs these
without removing a lane, relaxing quota or treating old CI as a new pass.

The 6250-sample100Hz probe initially overflowed after651 arrivals. Dirty dev4
still FAILS: first ordinary rejection at31.990030262 virtual seconds/event1200;
only767 unique raw samples in two committed chunks. Its original observations,
readonly PC profile and2,596,864-byte owned-memory accounting remain under
`build/lemmasim/focused6250-87d4513-direct-dev4` and
`build/lemmasim/profile6250-87d4513-direct-dev4`. The input rate/corpus is unchanged.

Current development changes reduce repeated registry/stack validation within
one call, use fully preflighted aligned word copies, cache independently checked
store sectors, render into the owned framebuffer and coalesce dirty tiles.
Validation results are not cached across calls. Dirty dev5 fresh O2 notebook and
initializer builds/full audits, selected capacity and real guest initialization
PASS at `build/lemmasim/focused6250-64e3bbb-shared-base-dev5-prepare`.
Guest SHA256 `e38ac938c52e7ac62981e020f6455111186fed8e6333dbc004f8adbe83a35f2f`;
prepared SHA256 `adb827a227e239a06a23dde64dbb49d0fb57b7d64815b3377b3452faea462f63`.
Selected O2 trap chain including288-byte entry is1984/16352bytes; this is not a
whole-program stack proof. The unchanged dev5 probe FAILS: first ordinary loss at39.190118350 virtual
seconds/event1920,1533 unique committed raw samples and ACK14. It was reaped;
cold is NOT_RUN after the failed live observation. Final allocator accounting
remains634frames/free7558. The readonly profile locates repeated IPC/registry
validation; the loop consumes one sample per small RPC. A bounded queued-input
drain is implemented, without changing the corpus, rate or ownership checks.
These are dirty development observations, not committed-candidate acceptance.

Fresh dirty dev6 builds/audits and explicit guest initialization PASS at
`build/lemmasim/focused6250-64e3bbb-input8-dev6-prepare`; notebook SHA256
`0d32f5dfcb4c3f709187378d7eab6e1bb76404c46735daa98419011bfca0ae6d`,
prepared SHA256 `3bad10ad32e9fadd5351b79878fa0def0d954fd357df42878aefb8e5d54a90ca`.
The unchanged100Hz live guest retains6250 unique raw samples with no ordinary
loss, Saved53 and exact independent pixels. New-process cold recovery retains
all committed bytes and identical controller pixels in39.406seconds. Both
processes are reaped. The runner's original FAIL remains retained because its
host observer transposed PTE/permissions fields; the corrected cold observer
then missed Ready's polling window. Independent workflow/cold observations and
full final cold metadata (634frames,7558free) are separately recorded under
`build/lemmasim/focused6250-64e3bbb-input8-dev6`. The synchronous Ready observer
repair is implemented and passes literal tests; its full observed run and the
complete clean-candidate matrix remain pending. The separate development
observation manifest SHA256 is
`2a59db43904ca3965184d449c14014bbcfdba8f53d4b20618035965f80d9825d`.

Automated native GTK/QMP pointer ingress on dirty dev4 captures22 samples,
retains21 original stroke samples, commits Saved5 and passes independent ink,
exact pinned-QEMU replay and cold byte/pixel comparison. Its top-level native
campaign remains FAIL: QMP reset during observed PaperBusy rebooted into stale
RAM metadata and stopped before the notebook. Original files are in
`build/lemmasim/native-gtk-87d4513-dirty-dev4-attempt2`. The new Lean-authored linker
clears the entire reserved1MiB metadata interval with the existing structured M
startup; strict ELF/instruction checks pass. Dirty dev5's actual native campaign
`build/lemmasim/native-gtk-64e3bbb-dirty-dev5-attempt1` PASSes record, independent
ingress, pinned-QEMU replay, cold byte/pixel comparison and a second boot/full
guest restoration after reset during observed PaperBusy. The captured22 ingress
samples retain21 original stroke samples and Saved5. All processes are reaped.
QMP reset may drain/flush and is not a power-cut observation.
Manual interaction and a physical pressure-aware tablet are NOT_RUN.

Current focused host checks:304 kernel,62 pinned device/launcher,36 Core0 and18
scaffold tests PASS. Literal production Action checks cover memory/context/stack
negatives, paper recovery, rasterization, store cache and360 packet-copy cases
plus24 injected transfer failures. They do not certify RV64 execution. The
unpinned device suite FAILed because `cc` was missing; its pinned rerun passes.
An unpinned foundation host attempt ran453 tests with23 failures because `lake`
was absent; that result is retained. The correct pinned rerun PASSes453 tests.
Store quota repair is committed at `64e3bbb1e31276c1d0a163128d47a12a6fa52511`;
its clean linked J acceptance is pending. Audit indexing at `87d4513` preserves
exact old parsing and lets the real O0 control finish within its original limit.

Earlier source-specific observations remain separate: `6bcbe637` basic/replay,
15 append/checkpoint device faults and compiled early-ACK rejection; `cd3971c`
editing/cold; clean `a1dae683ba48cac9836f49507c57df04f8e90c6b` Core0, foundation,
F-I, J and architecture PASS, A-E deadline FAIL and source-negative control audit
timeout FAIL. `build/lemmasim/inherited-a1-handoff.json` retains exact identities.
They do not pass changed executable code. Historical failures are not relabeled.

Pinned host QEMU v17 SHA256
`0e95380d2eb582ebf95f989fc6a07eac26a50c222bbbee95dd5fa5421d2864ce`
adds an explicitly disabled-by-default laboratory DMA delay. Real device,
medium and transport replay checks pass; the host recipe/source remains pinned.

Next: commit the functional slice and run one exact-candidate full notebook matrix
including editing, both geometries, loss, active-DMA isolation, storage faults,
source-negative and16-page100000-sample workload, plus required inherited CI.
Export offline evidence outside ignored `build/` and update the draft review.
Actions retention is14days, not a permanent milestone archive. Final retention,
qualification and review readiness remain pending. No physical conformance,
managed runtime, later mathematics gate or Task004 completion is claimed.
