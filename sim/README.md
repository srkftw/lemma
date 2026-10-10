# LemmaSim

Permanent, first-class virtual Lemma One. **Status: architectural scaffold; no complete simulated device implemented here yet.**

The canonical machine contract is [../LEMMA_MACHINE_CONTRACT.md](../LEMMA_MACHINE_CONTRACT.md). Historic tested QEMU `virt` boot profiles remain in [../docs/contracts/LEMMA_VM.md](../docs/contracts/LEMMA_VM.md).

Planned runtime: emulated RV64 and board, device models for storage/reset/power/pen/display/connectivity, a host drawing-tablet bridge feeding *guest-visible digitizer events*, and a rendered virtual e-paper surface driven by the *guest controller protocol*. Student, Developer and Laboratory modes share machine behavior; Developer/Laboratory expose inspection, replay and fault controls.

Implementation must separately document device register maps, state transitions, version identifiers, virtual-time event ordering, failure semantics and external input recording. Underlying QEMU, Renode, RTL or circuit simulators are implementation choices; none substitutes for interface conformance. Physical-only modeling (thermals, electrical characteristics, optical/tactile feel) is outside the functional equivalence guarantee.

No simulator executables or tests are asserted to exist by this README. See [../docs/plan/LEMMASIM.md](../docs/plan/LEMMASIM.md).
