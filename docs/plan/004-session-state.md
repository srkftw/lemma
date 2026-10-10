# Task 004 checkpoint

Branch: `task/004-lemmasim-durable-ink`, based on main
`504f6e462e502d93192ba689d16d8552ca1e68b5` after one fetch on2026-10-10.
Status: IMPLEMENTING; the primary durable-notebook completion boundary is unmet.
No Task004 merge is authorized. Publish a draft for review when ready.

Implemented: explicit machine/descriptor/register bindings; real Lean checked
MMIO; owned32MiB pool; owned16KiB kernel and User stacks; bounded copy/loader
extensions; modern VirtIO block/flush and PLIC drivers; actual paper/pen devices;
isolated User record store and notebook; integer pressure-aware tile ink;
versioned pages/edit history; native QEMU hardware frontend; integrated volatile
block filter; captured raw input and pinned QEMU record/replay transport.
The new packed page-v2 codec retains an explicit fixed page-v1 reader.

Observed exact guest `6bcbe63720e1a0095fb59a94d2112c472a3a90c3`:
actual descriptor/DTB validation, separate store/notebook startup and modern
VirtIO flush publication, guest-drawn page, two strokes/50 original samples,
genuine final Saved sequence8. Independent workflow and new-process cold
committed-byte/controller-pixel comparison pass. The earlier malformed input
manifest FAIL is retained; a fresh manifest describes identical raw input bytes.
An actual notebook recording and exact native QEMU replay compare all media,
raw/device/guest events, descriptor/DTB, controller pixels and ordered block
operations. This is development evidence, not the final Task004 matrix.

New cached-context/clipped rasterizer and readable guest toolbar/status words
have genuine elaboration/codegen and independent literal checks. The linked development
run at `cd3971c` passes editing/erase/undo/redo, three pages, two notebooks and
100 retained samples, plus exact cold committed-byte/controller-pixel comparison.
Its original full audit rejected a newly emitted glyph jump table; the next
candidate narrowly accounts for that table and must rerun the full audit.
The 15-case development append/checkpoint cut campaign passes independent and
new-process cold checks, including torn payload and failed flush. A genuine
compiled early-ACK mutation is independently rejected after a running SIGKILL
cut (ACK11, stable10); the positive preserves ACK11. A QEMU pause initially
masked that bug by flushing and remains retained as a failed experiment.
Final candidate/workload/isolation acceptance remains open.

Host QEMU v14-fixed SHA256:
`bb1f83174881786ab59bbf2d15b68b489e738097c37b50750066dadf848f5f82`.
Actual PLIC/device/pixel, VirtIO durability/fault, and transport replay checks pass
under `build/lemmasim/{device,medium,replay}-qemu-v14-fixed*` (device directory is
`device-qtest-v14-fixed-attempt1`, medium is `medium-qtest-v14-fixed-attempt1`).
Replay requires recorded SIGTERM closing, replay `-no-shutdown`, sleep=on,
and an exactly observed instruction boundary. Transport evidence is not notebook
replay qualification. The v13 screenshot exporter wrote illegal padded PPM rows;
v14 fixes this and passes an asymmetric literal pixel check. Native manual/tablet
input has not been exercised. Mouse pressure is synthetic.

Retained failures include early QEMU builds, source-snapshot races, absent SEIP
before the M interrupt-enable repair, compiled bounded-fold status mishandling,
sleep-off replay ingress, malformed PPM rows and a QMP-quit replay shutdown race.
Earlier host fold harness PASS results are explicitly invalid for compiled-fold
coverage; corrected literal/native probes and real guest observations supersede
that limited claim without relabeling the retained artifacts.

Next: exact committed kernel/notebook/host candidate, brush-width and damaged
mount observations, second geometry, loss/active-DMA client isolation and the
16-page100000-sample workload; rerun complete notebook cuts/replay/negative on
that candidate. Run the exact-candidate inherited acceptance/CI
matrix and update the published [draft PR5](https://github.com/srkftw/lemma/pull/5). New O0 selected call-chain bounds at6bcbe637 are
kernel9296/16352, notebook9008/16384 and store3936/16384; all exceed25% margin.
These are selected bounds, not whole-program proofs. A legacy service O0 path
now measures8928/8192 and fails. The owned four-page legacy kernel stack repair now has a fresh development O0
selected bound8928/16352, 45.4percent headroom, and passes owned teardown/pin/
canary/accounting checks. Full committed linked regressions remain pending;
assertions are retained. No final-candidate or CI PASS,
physical conformance, managed runtime or later mathematics gate is claimed.

Generated outputs are ignored under `build/`. Ordinary launch must use a prepared
build; it never rebuilds dependencies or formats a failed mount. The maintained
CLI has offline copy/archive operations. Actions retention is configured14days;
an offline archive must be explicitly exported and kept outside ignored build
outputs. Final milestone evidence retention and publication are still pending.
