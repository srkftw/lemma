# LemmaSim

Permanent virtual Lemma One. Task004 implements the native reference binding,
project-owned pen/paper devices and volatile/durable block transport, with a
compiled Lean notebook and isolated record service. Complete candidate
qualification is in progress; see the [checkpoint](../docs/plan/004-session-state.md).

The canonical machine contract is [../LEMMA_MACHINE_CONTRACT.md](../LEMMA_MACHINE_CONTRACT.md). Historic tested QEMU `virt` boot profiles remain in [../docs/contracts/LEMMA_VM.md](../docs/contracts/LEMMA_VM.md).

The separately pinned QEMU `lemmasim-virt` runs the real M/S/U RV64 path.
Host pointer or recorded samples enter the pen FIFO and PLIC; guest drivers,
ink, rasterization and toolbar produce controller pixels. The record service
uses guest VirtIO writes and flush publication. The host never draws strokes,
parses live documents or reconstructs a notebook for recovery. Student,
Developer and Laboratory modes share that machine. Developer controls and
Laboratory faults operate outside guest authority.

The [profile](profiles/lemmasim-virt-0.1.0.json),
[descriptor/register ABI](../docs/contracts/004-devices-v1.md),
[block medium](../docs/contracts/004-block-medium-v1.md) and
[host boundary](host/README.md) bind discovery, state transitions, virtual
timing, failure and capture. The maintained command is `scripts/lemmasim`;
ordinary launch uses prepared tools/images and an existing persistent disk.
See the [runnable workflow](../README.md#task004-lemmasim-implementation-checkpoint).

Headless and native display consume the same controller state. Mouse pressure
and refresh timing are synthetic. Native manual/tablet input has not been
exercised in the development evidence. Physical conformance remains unverified;
networking, managed Lean runtime, mathematics/tutor and whole-machine snapshots
remain outside this implementation. The future machine is governed by
[LEMMASIM.md](../docs/plan/LEMMASIM.md), not completed by this bounded notebook.
