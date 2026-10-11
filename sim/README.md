# LemmaSim

Permanent virtual Lemma One. Task004 implements the native reference binding,
project-owned pen/paper devices and volatile/durable block transport, with a
compiled Lean notebook and isolated record service. Its bounded qualification
is recorded in the [evidence report](../docs/evidence/004-lemmasim-durable-ink.md)
and [checkpoint](../docs/plan/004-session-state.md); this does not finish the
canonical machine.

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
See the [runnable workflow](../README.md#task004-native-durable-notebook).

Headless and native display consume the same controller state. Mouse pressure
and refresh timing are synthetic. Automated GTK mouse capture, exact replay,
cold recovery and Busy reset were exercised with dedicated Xvfb 21.1.24 from
the pinned Nix input. Its optional recipe and executable SHA are retained in
the evidence archive; it is a test environment, not a runtime installer.
Manual visible interaction and physical tablet input are NOT_RUN. Physical conformance remains unverified;
networking, managed Lean runtime, mathematics/tutor and whole-machine snapshots
remain outside this implementation. The future machine is governed by
[LEMMASIM.md](../docs/plan/LEMMASIM.md), not completed by this bounded notebook.
