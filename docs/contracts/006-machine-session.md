# Task006 machine sessions and matched development binding

This increment implements resumable versions of the existing digital subset.
It does not redefine the complete machine in `LEMMA_MACHINE_CONTRACT.md`.
`lemma-silicon-dev/0.2.0` admits the canonical 1650×2200 Gray4 geometry and
32 MiB checked owned frame pool inside the same externally modeled 128 MiB RAM.
The descriptor ABI is 3; the pool has 8192 frames and an 8192-frame owner ceiling.
Actual Lean allocation, zeroing, generation checks, pinning and reaping remain
authoritative. The 1024-leaf per-task mapping bound remains. Neither capacity
is an on-chip SRAM implementation. Historical 0.1 JSON and its 4 MiB/128-owner
quota remain distinct supported bindings; no historical execution is relabeled.

The selected JSON generates the consumed Lean binding, RTL package, host
header, DTB and binary descriptor. The closed Lean deployment catalog selects
`siliconFullBoot` or `siliconFullInitializeMedium`; the guest checks actual
discovery before configuring its allocator. No accepted Core0 language feature
or durable record format changes. The optional digital panel program is
specified in `006-synthetic-panel-v1.md`.

`scripts/lemmasim session` owns one long-lived machine. A single owner advances
bounded virtual intervals and admits raw external samples between them. The
Unix socket exposes inspect, pause/resume, run, inject, snapshot/restore,
recorded-suffix replay, warm reset, cold cycle, panel export, durable-base export
and destroy. Queues, request lengths, files, clients and interval resource
deadlines are bounded. A failed automatic interval pauses and retains an
inspectable error. Host time controls pacing/resource failure only.
Pause/resume are simulator controls, not a guest suspend service.

The native Tk presentation reads only device-produced pixels. Its mouse is an
explicit synthetic pressure source. `--tablet` replaces it with Linux evdev
reported coordinates/contact/pressure/tool/buttons; absent pressure is reported
unavailable, and tilt is reported but not admitted by the current pen ABI.
Raw OS frames and their actual virtual-boundary admissions have separate
captures. Physical registration and manual tablet conformance remain unverified.
Live OS handles and samples not yet admitted belong to the external world.
Restore disconnects that adapter; recorded replay supplies the remaining
admitted samples. A live handle is never silently restored to an old timeline.

The versioned session sidecar binds exact implementation, guest and discovery
identities; file names, counts, lengths and SHA256 are checked before applying
state. Native RTL checkpoints additionally validate their bounded binary
container before allocation. These are integrity checks, not authentication.
Snapshots preserve in-flight work without flush, drain, reset or convenient
completion. Restore owns an isolated durable fork and cannot overwrite the
source notebook. The QEMU fork copies the saved durable base into a new session
file before restoring CPU/RAM/controller state; the RTL fork exclusively creates
and locks a private backing file containing the saved durable sector bytes.
Subsequent guest barriers persist that file, not an ephemeral RAM-only base.
Fast restore validates a paused candidate process before replacing the current
machine. Export is exclusive creation of durable bytes, excluding volatile work.
Different backend implementations cannot exchange exact checkpoints.

Captured input includes the actual admission nanosecond phase on QEMU, as well
as the independent delivery cycle and all seven raw pen fields. Replay validates
the complete bounded timeline before applying state. Use `--until-ns` for an
exact QEMU endpoint: rounding its 8 ns instruction clock to 10 ns controller
cycles loses information. External records are reserved as `admission: pending`
before device mutation and marked `applied` only after the backend returns.
An ambiguous backend error or failed capture acknowledgement preserves the
attempt, pauses the owner and forbids further advancement/checkpointing; inspect
and durable export remain available. Replay rejects pending records before
restoring anything. Legacy captures without the added marker remain admitted
records under their original identities. A full or failed capture file rejects
input and pauses the owner. Detailed traces
are selectable, buffered and bounded; omitted observations are counted without
changing device transitions.

Fast adapter `lemmasim-fast-adapter/2` saves `clock.json` with schema
`lemmasim-fast-clock/1` and a bounded nonnegative nanosecond origin. Its session
clock stays monotone through a cold power cycle; the new QEMU process starts its
local clock at zero. `virtual_ns` includes that origin, while `local_virtual_ns`
does not. Storage and paper deadlines retain their actual local nanosecond
values alongside the explicit origin; they are not normalized for comparison.
Timestamped delivery is translated once into the local clock. Restore
validates and restores the origin before applying a recorded suffix. Earlier
development adapter checkpoints are unsupported by this version. Warm reset
waits for the actual QEMU RESET event and observes MTIME through MMIO; both
backends reset MTIME. QEMU's instruction-count mcycle/minstret reset behavior
differs from RTL and remains an explicit architectural comparison gap. These
counters are retained in the observations and are never filtered to claim parity.

The QEMU fast binding uses the same selected Lean ELF and supplied DTB, a
RV64IM/MSU/Sv39/PMP scalar configuration, CLINT 10 MHz, and the selected machine
geometry/registers/IRQs. It rejects a wider advertised CPU configuration.
QEMU's constructed reset handoff differs from the Lean-authored RTL ROM;
both are explicitly ELF-preload development boot. Nonvolatile boot/update and
authentication are absent. Instruction-count pacing is8ns/instruction;
this does not reproduce the RTL processor schedule. The block functional
controller advances bounded DMA phases on virtual timers, performs checked
frame-pool transfers and acknowledges a flush only after `fdatasync` succeeds.
Its timer, queue, transfer buffer and volatile sector overlay are snapshot state.
The ordinary historical QEMU asynchronous block graph remains separate.

## Observation relation fixed before comparison

For a paired selected-profile workload, require identical admitted raw sample
fields, ordering within each external stream, guest object identities and
contents, durable sector bytes, publication sequences/status, and controller
visible Gray4 bytes. Paper phase/row/column/logical-code streams and beat counts
must match the synthetic program. Preserve all emitted time/counter fields and
raw traces. Do not normalize timestamps, pen fields or ink payloads afterward.

CPU instruction schedules, retired counts and boot/service latencies are
implementation-specific observations and are reported separately. A workload
may admit an explicit common virtual arrival schedule and bounded milestones;
it must specify those bounds before execution. A missed bound is a mismatch.
Controller synthetic sequencing uses the declared 100 MHz clock; fast projection
may round a transition to the next 10 ns boundary, at most one controller clock.
Fast block DMA phases are 100 ns each plus admitted medium delay/backpressure;
RTL fabric contention has its own observed elapsed cycles. This difference is
reported; it is not an equivalence claim for bus microstate or all timing CSRs.
Exact same-backend continuation requires equal virtual time, architectural/
private CPU state, RAM, controller state, raw suffix output and durable bytes.
The pinned QEMU migration container also saves two host elapsed-time statistics,
`cpu_ticks_offset` and `cpu_clock_offset`. These are identified separately from
guest time under the fixed `icount` configuration; every other container byte
must agree. The independently inspected serializer and mutation checks define
this narrow distinction. Retain raw files, differences and the original failed
full-container comparison; never call unequal containers byte-identical.

Pending guest suspend/power/watchdog/control interfaces, nonvolatile recovery
boot, companion/USB/radio transport, browser/Wasm, managed runtime and G5–G7
applications remain completion requirements. Their absence is not physics.
