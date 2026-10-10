# Task 004 checkpoint

Branch: `task/004-lemmasim-durable-ink`, based on main
`504f6e462e502d93192ba689d16d8552ca1e68b5` after one fetch on 2026-10-10.
Status: IMPLEMENTING; the primary completion boundary is unmet.
[Draft PR #5](https://github.com/srkftw/lemma/pull/5) remains draft. No merge is authorized.

Prior published implementation: `dfd5c90cc457e2e1094792453f2a040abc19a54b`, tree
`5ddf2b0b0ef16e93da326fdd49d1f52c0937c1cb`. The genuine compiled RV64 guest has
32 MiB owned memory, 16 KiB stacks, checked discovery, PLIC pen/paper, modern
VirtIO/flush, isolated record storage, integer ink/rasterization and page/edit
workflows. Source existence and scoped passes do not complete Task004.

The exact dfd headless full matrix `build/lemmasim/task004-dfd5c90-full2-headless`
is retained FAIL, SHA256 `eb32a2b7045b6c03ee18ad767f46e2a47e8e527a7b266fb825b83053345c3852`.
Its seven workflow/cold pairs, isolation and live-DMA client death, unknown/damaged
media refusal, all15 real storage faults/cold checks, two behavioral source
negatives, captured native ingress and thirteen replay observations passed.
The final100,000-sample workload reached acknowledged sequence848 across16 pages,
then Save used a long-lived checkpoint reply and reported IPC timeout93 after
thirty seconds. The service continued the actual root replacement. The owner
interrupted the failed workflow; QEMU was reaped. The outer checker separately
reported missing consistent final owned-memory observations. No workload cold
comparison or aggregate PASS was obtained. Both failures remain original FAIL.

This repair adds checkpoint-only endpoint v2 Begin/Status operations12/13,
bound to the full kernel-stamped sender, namespace and positive ticket. Pending
is an observation, never a durable acknowledgement; completion is latched only
after the engine's final root flush. The v1 disk format and operations1–11,
including legacy deferred checkpoint7, retain their meanings. The notebook
polls short replies every100ms of monotonic guest time and waits for initial
Mounting through the same service. It keeps the thirty-second per-RPC ceiling.
The launcher now diagnoses an observed Save failure once all scheduled input
has arrived, instead of waiting indefinitely for a quiescent Saved boundary.

Actual dirty development observation `build/lemmasim/large-checkpoint-async-dev-attempt1/result.json`
is PASS, not exact-candidate acceptance. It copied the retained full2 disk without
changing the original. The guest mounted in83.7336s; Save stayed Pending for
157.15795 guest seconds and became Saved848 after two durable flushes with zero
pending sectors. Root generation2/segment1 became generation3/segment0. All289
committed objects and100,000 unique raw samples were preserved byte-for-byte.
A separate cold process mounted in84.7791s and matched document bytes and exact
visible pixels; both processes were reaped. Audited dirty Notebook O2 image:
`aab2e53d53f39cd216808d910c6ff9f9fb9cf09a4cdf14b6ab7016e51c414efd`.
The ordinary build refused to publish its prepared manifest when a test fixture
changed mid-build; that failure is retained. Explicit development metadata never
claims ordinary CLI or clean-source qualification. Store endpoint and notebook
literal fixtures also passed through genuine Lean elaboration/Core0 lowering.
Selected O2 kernel trap bound1984 /16352 usable bytes includes288-byte entry;
this is a selected-path bound, not a whole-program proof. Fresh repaired O0 and
full exact-candidate acceptance are pending.

Actual prior PR CI [38086018901](https://github.com/srkftw/lemma/actions/runs/38086018901)
passed allnine jobs at synthetic merge `6f2ff0cb93bfc5d8306a500fe2735892de4a7247`
with the exact dfd tree. Nine artifact ZIPs were downloaded and verified against
service digest/size;14-day expiry is2026-10-24. Those checks do not pass this
changed executable source. Exact repaired-candidate CI and final offline archive
are pending; no permanent remote archive is configured.

Prior dfd controlled native GTK/Xvfb capture, replay, cold recovery and busy-reset
restoration passed, as did ordinary CLI init/write/cold/copy and Developer
pause/inspect/resume. These were automated observations: manual interaction and
physical pressure-aware tablet input are NOT_RUN. The separate ambient GTK
attempt remains FAIL; its close actor is UNKNOWN. Historical c96 complete-object
identity failure and earlier campaign/CI failures remain under their original
ignored output paths. The scoped Lean exporter repair retained the strict entire
production-object comparison; no old FAIL has been relabeled.

Pinned host QEMU v17 SHA256:
`0e95380d2eb582ebf95f989fc6a07eac26a50c222bbbee95dd5fa5421d2864ce`.
Next: commit this functional repair, run one fresh clean exact-candidate full
matrix and required actual CI, export verified offline evidence outside ignored
build/, write one concise report/result/manifest, and update the draft for review.
Preserve the original failures, legacy profiles, physical UNVERIFIED status, and
later managed-runtime/mathematics boundaries. Do not claim completion here.
