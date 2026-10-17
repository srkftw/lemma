<!--
# Lemma machine conformance

**Status: suite scaffold; no conformance pass claimed.**

Required future suite categories:
1. ISA/privilege/boot/interrupt/reset and MMIO ordering.
2. Memory protection, DMA, clock/timer and interrupt races.
3. Storage barriers, failures and acknowledged-commit recovery.
4. Pen coordinates/pressure/hover ordering, cancellation, calibration and disconnection.
5. E-paper controller command/busy/completion and visible-frame behavior.
6. Networking, buttons, USB and device failure outcomes.
7. Same guest-image workflows, documents, math evidence, learning state and tutor permissions.
8. Cross-embodiment traces and measured tolerances.

Each test must specify contract version, input/state, reference oracle, accepted trace relation, firmware image hash, simulator and device versions, result and source of evidence. Physical checks stay UNVERIFIED until executed on hardware. A host-only structural test must never be called a guest-device acceptance run.

See [../LEMMA_MACHINE_CONTRACT.md](../LEMMA_MACHINE_CONTRACT.md).

-->
