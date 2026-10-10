# Lemma One canonical machine contract

Status: **normative architecture target, not hardware-conformance evidence**. Version: **draft 0.1** (2026-10-09).

## One machine, two embodiments

**LemmaSim** is a permanent, distributable, first-class implementation of Lemma One. The physical Lemma One and LemmaSim implement the *same versioned observable machine contract*, with the same maintained freestanding Lean-authored RV64 operating system, services, checkers and applications. Student, Developer and Laboratory are modes of the same LemmaSim, not incompatible product forks.

The target is total **functional** equivalence: for every admitted guest-observable input, device operation and documented failure, the two embodiments produce equivalent traces under a declared observation abstraction. This is a testable goal, **not** a presently demonstrated fact. Thermal, tactile, optical-material and other intrinsically physical equivalence are excluded. Functional timing, deadlines, busy/completion events and error reporting remain included wherever exposed in the contract.

## Compatibility and precedence

1. The canonical contract defines the intended finished machine. A released version cannot silently change guest-visible ABI or peripheral semantics.
2. `docs/contracts/LEMMA_VM.md` documents *tested historical boot profiles* (including QEMU virt, Core0 and Task 002) and remains authoritative for those profiles. The finished canonical machine is **not** falsely claimed to be implemented by those tests.
3. Machine-contract changes require versioning, reference models, positive/negative conformance fixtures and a migration statement for storage/document formats.
4. When OEM hardware differs, implement a conformance-preserving physical adapter, change hardware, or explicitly revise the versioned contract for *both* embodiments. Never silently introduce divergent guest software behavior.
5. The guest must not use host-only shortcut services for ink, checking, storage or scheduling. Host drawing tablet, graphics and filesystem are strictly external I/O transports backing modeled devices.

## Required contract sections (unfrozen values must remain UNKNOWN)

| Area | Guest-visible specification to freeze | Evidence |
| --- | --- | --- |
| Processor | RV64 ISA/extensions, privilege levels, memory ordering, trap/CSR semantics, hart count | differential ISA and privilege tests |
| Board | memory map, bus widths, address alignment, discovery, firmware/reset handoff | boot trace and map consistency |
| Interrupts and clocks | sources, priority, masking, timers, virtual-time ordering, reset rules | boundary and race tests |
| RAM and DMA | size, regions, coherency, ownership, protection, faults | invalid access and isolation tests |
| Persistent media | block/erase/flush barriers, acknowledgements, write atomicity and crash model | power-loss cutpoint replay |
| Pen digitizer | coordinates, sampling, hover, pressure, tilt/buttons if supported, event framing, ordering, calibration | host-injected and recorded device-level traces |
| E-paper controller | display dimensions, pixel formats, command/register protocol, queue limits, refresh modes, completion/busy, error model | guest-driven pixel/transition traces |
| USB, buttons, network | enumeration/protocol, input state, cancellation, disconnect/error semantics | disconnect and malformed-packet tests |
| Power/reset | observable power states, reset causes, sequencing and brownout consequences | deterministic state-machine and fault campaigns |
| Updates and identity | firmware image identity, version negotiation, trust and recovery boundaries | rollback/failed-update tests |

Exact OEM panel waveforms, connector pinouts, measured electrical parameters and timing distributions are **unknown until sourced or measured**. Do not invent them. Host models may use explicitly named assumed parameter ranges; such models do not certify a future panel.

## Trace-level equivalence

Define `Obs_v(E,input,initial_state)` as the version-`v` canonicalized observable trace from embodiment `E`: software-visible MMIO/interrupt/clock/error events, device input/output, persisted records and application results. The goal is:

`Obs_v(Sim, i, s) ≈_v Obs_v(Physical, i, s)`

for all **admitted** inputs/states, where `≈_v` is specified *per interface* (exact bytes and semantic results where required; tolerance envelopes for analog-origin samples and declared timing bounds). A deterministic virtual clock and captured external-service responses are prerequisites for exact replay. Snapshot reproducibility does not imply arbitrary physical nondeterminism is reproducible.

For each test: record machine version, firmware/OS hash, simulator build, device-model version, assumptions, input trace, initial storage image hash, result, applicable equivalence relation and evidence provenance. Missing coverage is **unverified**, never pass.

## Acceptance

- **LemmaSim functional completion:** all canonical interfaces implemented; all supported student workflows, pen/document persistence, mathematics checking, offline textbooks and network-assisted tutoring function through real guest drivers; mandatory conformance suites pass; user-installable distributions and developer diagnostics exist.
- **Physical functional equivalence:** run the same applicable conformance corpus on measured physical hardware and resolve every discrepancy. Until then label results `SIMULATED_ONLY`.
- **Explicit exclusion:** claims of thermals, battery life, electromagnetic compatibility, panel feel, mechanical fit and material behavior require separate physical validation.

See [the simulator plan](docs/plan/LEMMASIM.md), [sim/](sim/README.md) and [conformance/](conformance/README.md).
