# Task 004 checkpoint

Branch: `task/004-lemmasim-durable-ink`, based on main
`504f6e462e502d93192ba689d16d8552ca1e68b5` after one fetch on2026-10-10.
Status: IMPLEMENTING; the primary durable-notebook completion boundary is unmet.

Initial coherent foundation: frozen profile/register ABIs and generated constants,
real Lean v0.3 checked MMIO lowering, descriptor reader, owned32MiB pool and
16KiB task kernel stacks, modern VirtIO sector/flush driver, paper/pen/PLIC drivers,
QEMU host-only device integration, guest store codecs/recovery/checkpoint engine,
and integer tile rasterizer. Historical configuration selection is retained.

Observed: focused Lean builds and compiler fixture pass; independently checked
host-model traces and actual Lean host-Action store traces pass. These are not a
freestanding notebook run. First linked O2 image attempt failed the build's source
snapshot check during concurrent edits. Its selected compiled trap path1904bytes
fits16352 usable bytes but does not qualify a candidate. Legacy O0 selected path
8240bytes failed8192 capacity; a structural repair is written and unverified.
QEMU patch compilation has retained failures; no integrated guest boot is yet
claimed at this checkpoint. Generated attempts remain under ignored `build/`.

Next: boot the actual patched QEMU/guest, repair observed device-path faults;
expand user mapping metadata for real surface/store consumers; link isolated store
and notebook clients; draw the guest page, connect pen/ink, and complete persistence,
editing, cold recovery, device-level crash backend and replay. Student use,
16-page100000-sample workload, complete regression acceptance, CI and draft PR
are not yet observed. Do not infer any gate or workflow pass from existing code.
