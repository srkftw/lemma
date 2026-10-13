<!--
# Task 004 — LemmaSim: the first durable writing machine

Authorized 2026-10-10 by the owner in the task conversation. Reviewed baseline:
`504f6e462e502d93192ba689d16d8552ca1e68b5`; fetched main was identical.
Branch: `task/004-lemmasim-durable-ink`. Publish a draft PR; no merge authority.

Implement a usable native, offline, pen-first persistent notebook through:
raw host input -> modeled pen FIFO/PLIC -> compiled Lean driver -> isolated
input/ink/notebook -> guest rasterizer -> paper controller visible pixels;
guest document store -> modern VirtIO-MMIO block -> persistent medium;
real cold boot -> guest recovery. Host code supplies hardware effects only.
A UART demo, volatile canvas, model-only tests or store without a notebook
consumer do not complete this task. Preserve an honest runnable checkpoint
if execution is interrupted; never lower the completion boundary.

The owner's Appendix A is normative: adopt lemma-one-core/0.1.0 and
lemmasim-virt/0.1.0, frozen subordinate binary descriptor/pen/paper ABIs,
1650x2200 and1404x1872 geometry using one binary. Preserve historical LemmaVM.
Use pinned Lean/LLVM/QEMU; a separate host-only QEMU patch is authorized.
No target C/assembly strings, managed runtime rewrite, host notebook/recovery,
custom CPU emulator, semihosting or physical claims.

Implement in dependency order: boot binding/stack/memory; block/durable store
with user consumer; guest page/toolbar; pen/live ink/rasterizer; persistent
page/edit/reopen/recovery; replay/Developer controls/full acceptance/publication.
Use >=16KiB affected kernel stacks with real selected compiled bounds and25%
headroom target, >=32MiB descriptor-derived owned pool, checked bulk spans,
full destination preflight, isolated pages/syscalls/capabilities/IPC.

Block: modern MMIO split queue, VERSION_1/FLUSH negotiation, pinned kernel
bounce DMA, lifetime until genuine completion/reset, explicit errors. Store:
namespace create/open/append/read/enumerate/checkpoint/close/tombstones;
versioned bounded records, integrity checks, payload flush then publication
flush then acknowledgement, recover incomplete/torn/invalid/stale/unknown media
fail-closed, two root generations and real capacity reuse. Never autoformat a
nonempty unknown disk. Lab power cuts discard volatile writes; include torn
sector and failed flush. A process kill alone is not physical power loss.

Paper: Gray4 32x32 uploads, target vs visible, latched rectangle refresh, busy,
fast/quality synthetic timings, interrupts, completion/reset/interruption.
Pen: stable read-head/ack FIFO, epoch/sequence/timestamp/provenance/pressure,
out-of-band loss, disconnect/lost-up cancellation; host pointer never calls ink.
Ink: stable stroke IDs, retained raw samples, normalized24-bit coordinates,
integer segment interpolation/pressure width/clipping/dirty tiles, erasure,
versioned undo/redo. Notebook: create/open, add/navigate pages, width, erase,
undo/redo, explicit save, autosave, close/reopen/restart. Honest Pending/Saved/
failed/read-only, asynchronous bounded pending data, second namespace,
16pages/100000 retained samples without per-sample history scans.

Replay: immutable run identity with complete backend/device/guest/media hashes,
geometry/capabilities/clock/event/fault inputs; use actual QEMU replay mechanisms,
stable same-time ordering, fresh disk copies, diagnose bad streams. Compare
real traces, document bytes, guest pixels. Developer controls outside tablet:
pause, FIFO/loss, target/visible/busy, commit state, cuts, capture/replay.

One committed-candidate matrix retains all inherited checks and covers live
cold-reopen, storage cutpoints/checkpoint/torn/flush failure, edits/namespaces,
loss, display transitions, isolation/DMA, both geometries, replay and workload.
Use independent transition/recovery oracles and two behavioral source negatives.
Do not invent build/test/CI/manual outcomes. Bound/reap processes.

Maintain build/init/run/replay/check and offline evidence archive commands.
Init refuses overwrites; run never reformats mount errors; replay preserves
originals. Retain one concise report/checkpoint/result/artifact manifest, large
outputs under ignored build/. README documents actual workflow/limits.
Final handoff: exact commit/branch/PR, genuinely usable behavior, launch,
observed evidence, limitations and every unrun/failed obligation. Task 004 does
not complete all G/S gates, managed Lean, mathematics/tutor or physical equivalence.

-->
