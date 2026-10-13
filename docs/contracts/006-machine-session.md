<!--
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
Unix socket exposes clock, inspect, pause/resume, run, inject, snapshot/restore,
recorded-suffix replay, warm reset, cold cycle, panel export, durable-base export
and destroy. Queues, request lengths, files, clients and interval resource
deadlines are bounded. A failed automatic interval pauses and retains an
inspectable error. Host time controls pacing/resource failure only.
Pause/resume are simulator controls, not a guest suspend service.

Short session paths retain their in-session `machine.sock` address and existing
wire protocol. A session whose path exceeds the Unix-socket address bound owns
a unique short control directory with mode0700 and a mode0600 socket. Its
optional `lemmasim-live/1` manifest `control` binding has version1, the complete
session path, private directory/address, owner PID/start ticks and random nonce.
The owner file, live start time and endpoint permissions are checked before
contact; both request and response carry the nonce. Cross-session redirection,
stale/PID-reused owners, changed endpoint permissions/types and responses with
another nonce fail closed. Machine construction failure and normal close remove
only this owner's recorded directory/file/socket
inodes. No shared static control address or change to medium/fork ownership is
introduced.

The read-only public `clock` action returns `machine` timing and the owner's
`running` pacing flag. RTL timing contains mandatory `backend`, `cycle`, `ticks`
and `finished` fields from its existing completed-edge observer. QEMU adds its
actual `virtual_ns`, `local_virtual_ns`, `local_ticks`, `time_origin_ns` and
`runstate`; it reads actual local MTIME rather than deriving it from elapsed
session time. Fractional nanosecond phase and warm-reset timer behavior are
preserved. The request performs no run, pause, reset, admission or storage
barrier, and does not request panel hashes or formatted CPU registers. Full
Developer inspection retains its existing device, storage and CSR observations.
Raw pointer and tablet adapters use this clock for the sample timestamp. Fast
input admission reads the same lightweight clock for its exact current phase;
the owner records every raw field and still returns full post-injection state.

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
The RTL savable model includes its cache/TLB circuitry. QEMU11.1.1's common
CPU post-load explicitly flushes the software TLB; cached Sv39 translations
and TCG translation blocks are not serialized. The listed fast guest suffixes
have observed identical continuation, but arbitrary cached-translation state
is not yet covered by an exact fast checkpoint. RISC-V reservation fields are
serialized, although selected RV64IM excludes A. A complete fast cache-state
mapping or separately specified architectural boundary remains required;
checkpoint-byte equality alone cannot establish that missing coverage.

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
backends reset MTIME. The selected profile0.3 fast successor binds mcycle to the
declared100MHz clock and resets fixed counters at completed paused RESET.
Historical executables retain their original behavior. Actual QEMU retirement
and its immediate reset boundary differ from RTL retirement and eight reset
edges; full architectural parity remains unqualified. All counters and private
baselines remain exact checkpoint state and are never filtered to claim parity.

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

## Power-v1 successor

Profile `lemma-silicon-dev/0.3.0` retains canonical geometry and capacity, adding
the [digital power contract](006-power-control-v1.md), descriptor ABI4 and
[kernel v0.4's narrowly extended PLIC range](006-core0-kernel-v0.4.md).
Both backends consume its selected register definitions. Timestamped button
levels are raw external events; Lean kernel policy accepts or rejects suspend.
Pause controls simulation pacing separately from guest cooperative suspend.

Exact state includes every power register, physical button level, queued levels
and clock phase. Queued wake events survive snapshots. Restore disconnects live
adapters and owns isolated backing; starting a restored power probe determines
its optional medium from the validated file inventory, never a supplied user
disk. Unsupported power state rejects in a disposable candidate before replacing
the current machine. Synthetic power inputs establish digital behavior only.

Watchdog, electrical power sequencing, brownout and remaining controls,
nonvolatile recovery boot, companion/USB/radio transport, browser/Wasm, managed
runtime and G5–G7 applications remain completion requirements. Their absence
is not physics.

-->
