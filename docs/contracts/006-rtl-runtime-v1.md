# LemmaSim reusable RTL runtime and checkpoint v1

The host-only `sim/rtl/host/machine_runtime.*` owns one `Vlemma_soc`, its
external byte memories and adapters. `main.cpp` is a command/observation
frontend. All instructions and device-controller transitions still execute in
the configured CVW and Lemma circuits. This interface implements the current
versioned digital subset; it does not complete the canonical Lemma One.

The runtime is single-threaded. `run N` advances 1..1,000,000,000 complete clock
cycles, stopping on the configured guest finisher/observer condition. Returning
to the command loop is a paused boundary; pause never drains an input FIFO,
finishes a display operation or flushes storage. Each call has a bounded host
wall deadline. Host wall time affects pacing and resource failure only.

`cycle` is the next cycle to execute. At each cycle, equal-time external events
enter in insertion order before the falling-edge evaluation. Controller memory,
framebuffer and medium responses are resolved before the rising edge. CPU/DMA
ownership and controller logic choose completions, interrupts and timers at that
edge. Outputs are observed from the settled pre-edge state. A checkpoint is
taken immediately after the completed rising edge, with clock high; restoring
resumes at the next falling edge. The Verilator context time is twice `cycle`.
This defines one backend's ordering; different CPU implementations need their
own declared observation relation.

The default external-memory adapter retains the historical zero-wait beat.
`--memory-latency N`, 0..1024 additional clock cycles, admits one immutable
address/write/data/byte-enable request until its response. A changed owner or
payload under backpressure is an error. RAM/ROM accesses are bounded 8-byte
aligned bus beats; the motherboard translates supported CPU/DMA sizes and byte
enables. ROM writes return a device error. RAM writes change enabled bytes only
on a real ready handshake. DMA authorization remains in the RTL motherboard;
the adapter does not grant access. Reset cancels an outstanding external beat.
Framebuffer and medium ports retain their current immediate response model;
their controller queues and transfer state are real circuitry. Large external
RAM is a functional model, not a physical SRAM macro.

External event queues are bounded at 1,000,000; the pen adapter queue at 65,536;
UART ingress at 16 MiB. Scheduled UART payloads have a 32 MiB aggregate
hexadecimal byte budget, checked before admission and during checkpoint
preflight. Raw event files must be regular files at most 256 MiB; each line is
bounded at 32 MiB plus 8192 bytes. Consumed events release their payload budget
at the next admission, and restore reconstructs the budget from all retained
events. Session command accumulation is bounded at 32 KiB; an overlong line
is consumed and rejected without changing the machine. The UART transcript window is bounded at 64 KiB while
its file retains emitted bytes. Volatile medium capacity is 32,768 sectors.
Pen samples retain unsigned 64-bit timestamps; admitted x/y are 0..65535,
pressure 0..4095, flags 0..15, tool 0..2 and buttons 0..7. Parser, live admission
and checkpoint preflight reject fields outside those ranges before hardware
port conversion. Scheduled UART and pen samples and legacy reset events are copied literally;
input capture records the actual cycle and admitted fields. No gesture, ink,
store codec or recovery operation runs in this adapter. There is no admitted
entropy source or randomized channel in this runtime version.

`warm-reset [N]` asserts processor/controller reset for N clocks (default eight),
retaining external RAM, durable and unflushed medium bytes, and visible panel
state. It cancels pending input, optical update and memory beat and clears
external target/latch surfaces to white. `cold-cycle` additionally discards the
volatile medium overlay, clears external RAM and reinstalls the exact original
ELF/DTB preload bytes; the retained panel remains visible until guest-driven
redraw. This remains explicitly **ELF-preload development boot** through the
existing Lean-authored ROM handoff. Neither operation establishes a nonvolatile
bootloader, authenticated update, reset-cause CSR, watchdog or guest power
service. A new external-medium-only cold machine remains a separate acceptance
operation; restoring a checkpoint is never evidence of cold recovery.

`LMSSRTL1` checkpoints are implementation-specific exact continuation files.
The header contains version, SHA256 implementation closure identity, bounded
wrapper/model lengths and CRC64-ECMA integrity checksums. CRC is not
authentication. The implementation identity covers profile, core revision,
source/configuration hashes, host runtime, pinned Nix/toolchain inputs, flags
and external-versus-register RAM configuration. Identity schema
`lemmasim-rtl-implementation/2` names consumed files relative to the repository
or pinned core, while the audit manifest retains their actual absolute paths.
Build output directories and checkout locations do not enter the identity.
Changing the runtime or model still rejects earlier implementation identities. Unsupported identities,
truncation, length/count/key errors and checksum failures are rejected before
state allocation or application. The model component must have the same
serialized shape as the current generated model. Checkpoint creation uses an
exclusive new destination; it cannot replace an existing snapshot.

The container header is 112 bytes: eight magic bytes, little-endian u64 version,
64 ASCII hex identity bytes, then four u64 wrapper/model lengths and their
CRC64 values. The wrapper begins with u64 event cursor followed by u64 next
cycle (file offset120). The session owner checks its sidecar cycle against that
saved value before calling restore, preventing a stale sidecar from changing
the current machine before reporting an error. Runtime CRC/model/state checks
remain required; reading this boundary header does not replace them.

State inventory:

- Verilator `--savable`: the entire generated model, including architectural
  registers, pipeline, implemented cache/TLB state, CSR/interrupt/timer state,
  fabric owner/error response, pen banks/head/contact/loss state, paper accepted
  update and sequencer phase/counters, and block queue/DMA payload/cursor.
- Wrapper: full RAM and ROM, exact sparse development preload, framebuffer
  target/latch bytes, visible panel bytes, pending accepted optical pixels,
  pending memory beat and wait phase, reset deadline and preload clock origin.
- Medium: all durable sector bytes and the separate volatile overlay. Sector
  zeroes have a canonical sparse representation; no journal content is parsed.
- External adapters: scheduled events, event cursor, pending pen/UART queues;
  virtual clock; flush-fault ordinal; UART stop marker, panel-completion cutoff
  and virtual-cycle observer cutoff; cumulative passive observations and bounded
  UART transcript. Presentation files and host file/socket handles are external.

Restore always disconnects the original medium and runs against the snapshot's
owned durable bytes. A medium restore requires `--fork-directory PATH`. Restore
exclusively creates a private sparse backing file there, writes only the
snapshot's durable base and performs file and directory barriers before applying
the restored state. The unflushed overlay remains separate. Subsequent guest
FLUSH operations use the same actual write and file barrier as the original
medium, and publish only to this isolated fork. The file remains after closing
the session; `private_medium_path` in inspection names the retained backing.
It can be used by a genuinely new cold machine after its owner exits. The
runtime holds an exclusive advisory lock on that private medium until closing
or restoring another fork. Handles and private paths are host ownership fields,
excluded from the serialized state and from exact guest/device observations.
`export-medium PATH` creates a new durable-base file, excluding unflushed bytes;
it never replaces another file. A future live transport must declare reconnect
or recorded-response semantics and extend this inventory. Cross-backend
QEMU/RTL architectural migration is absent. Fast-backend exact continuation has
its own implementation and qualification; it is not provided by this file.

The optional `--panel-drive-trace PATH` observes digital sequencer outputs only.
`LMDIG1\0\0` is followed by up to 1,000,000 28-byte little-endian records: cycle
u64, accepted sequence u64, x/y u32, phase u8, logical drive code u8, power u8,
gate/source-clock flags u8. Further beats remain counted and hashed; the bounded
file is explicitly partial. Phase counts and the ordered logical-port hash
count source-clock beats; `drive_clocks` counts every asserted drive clock.
These synthetic logical symbols do not establish electrophoretic response,
voltage safety, panel compatibility or physical display timing.
