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

Observed exact guest `dcac50ca3aeb07adea6168237fb6add562f4331e`:
actual descriptor/DTB validation and separate store/notebook startup, explicit
VirtIO initialization with durable acknowledgement, guest-drawn page, and25
original samples committed through real block I/O. A cold restart recovered
those bytes and redrew the ink. The70s first writing run stopped before its
final notebook-root acknowledgement; it is NOT a live-workflow PASS. The compact
page and quiet-scheduling changes require a fresh linked guest run.

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

Next: compile the clean compact-page candidate and run basic writing/cold reopen,
editing/two namespaces, second geometry, actual notebook device cuts/checkpoint,
input loss/isolation, meaningful notebook replay and16-page100000-sample workload.
Then perform one exact-candidate inherited acceptance/CI matrix and draft PR.
Selected O2 stack observations at the earlier guest are kernel2000/16352,
notebook1264/16384 and store736/16384; these are selected compiled call-chain
bounds, not whole-program proofs. Updated O0 paths and full final coverage remain
unrun. No physical conformance, managed runtime or later mathematics gate passed.

Generated outputs are ignored under `build/`. Ordinary launch must use a prepared
build; it never rebuilds dependencies or formats a failed mount. The maintained
CLI has offline copy/archive operations. Actions retention is configured14days;
an offline archive must be explicitly exported and kept outside ignored build
outputs. Final milestone evidence retention and publication are still pending.
