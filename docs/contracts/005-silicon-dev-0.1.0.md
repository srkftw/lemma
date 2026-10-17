<!--
# Lemma silicon development binding 0.1.0

`lemma-silicon-dev/0.1.0` is a development backend of LemmaSim, subordinate to
the [canonical contract](../../LEMMA_MACHINE_CONTRACT.md) and the
[silicon specification](LEMMA_SILICON_v0.1.0.md). It is not a physical machine
conformance claim. The QEMU `lemmasim-virt/0.1.0` identity and its inherited
devices remain separate and supported.

The authoritative numerical input is
[the silicon profile](../../sim/profiles/lemma-silicon-dev-0.1.0.json).
[silicon_profile.py](../../scripts/silicon_profile.py) deterministically emits
the typed Lean constants, RTL constants, actual FDT and descriptor bytes.
The generated Lean binding is checked against that input. This is a specific
binding generator, not a general machine specification language.

The selected core is CVW `wallypipelinedcore` at
`20f2af74e7aa76513e94012231d16567fa42648a`, configured in
[config.vh](../../tooling/silicon/config.vh): RV64IM, Zicsr, Zifencei, Zicntr,
M/S/U, Sv39 with 4 KiB pages, 16 PMP entries of four-byte granularity, 32-entry
instruction/data TLBs. M includes Zmmul. A, compressed, floating point, H,
Sv48/Sv57, Sstc, performance-monitor and cache-management extensions are
disabled. Every integer instruction in the selected ISA is implemented by the
core, independently of the current guest's demonstration trace. Configuration
is source-inspected and artifact-tested; this does not constitute complete ISA
or privileged-spec certification.

The current LLVM instruction inventory requires RV64 integer arithmetic,
including division/remainder, load/store widths 1/2/4/8 bytes, branches, calls
and indirect returns. The structured hardware boundary additionally requires
CSR read/write/set/clear, `fence iorw,iorw`, `fence.i`, `sfence.vma`, `ecall`,
`mret`, `sret`, and `wfi`. CSR closure is mstatus/mie/mip/mtvec/mscratch/mepc/
mcause/mtval/medeleg/mideleg/mcounteren, pmpcfg0/pmpaddr0–7, and their admitted
S-mode status/interrupt/trap/scratch/counter/translation counterparts. The
guest reads time through MMIO and a private Lean M-firmware call; S/U counters
are disabled during startup. No default SBI firmware or hosted runtime is used.

Reset starts at ROM `0x1000`, in the core's actual architectural M reset
state. [BootROM.lean](../../Lemma/Platform/Silicon/BootROM.lean) emits only typed
instructions that set a0=hart0, a1=the actual FDT pointer and jump to the
Lean-produced ELF entry at `0x80000000`. LLVM assembles those instructions.
Simulation preloads ELF RAM and ROM bytes, then applies clocks and reset; it
does not initialize privilege/MMU state or intercept guest PCs. This does not
establish a physical nonvolatile boot solution.

The binding deliberately reuses the RAM, firmware/kernel reservations, timer,
PLIC, diagnostic UART, finisher and three device addresses of the working
guest. This is a project integration choice, not evidence that QEMU inherited
devices are silicon. RTC, unused VirtIO slots, PCIe, CFI flash, fw_cfg and the
QEMU platform bus are absent. The actual silicon FDT identifies this distinct
binding. The service workload receives compute-only discovery without pen/paper/block
entries and does not exercise those functions. Integrated device claims require
their own functional evidence.

The core exposes one 64-bit AHB transaction path with explicit response errors
and backpressure; the wrapper accepts one transaction at a time. MMIO writes
and DMA read responses contain only the right-justified bytes selected by the
declared transfer width. Replicated core store lanes and adjacent external RAM
bytes are excluded from that value. Unmapped or
unsupported-width/alignment accesses fault rather than aliasing RAM. RAM is
little endian. The architectural RAM window is 128 MiB of **external simulation
bytes**, including the independent FDT reservation. No MPW SRAM of that
capacity is inferred. Synthesized configurations and open memory collateral
are identified separately in the Task005 evidence report.

The silicon development allocator uses exactly 1,024 frames (4 MiB) at
`0x82000000..0x82400000`, a 128-frame per-user quota, and four-page kernel and
User stacks. This deliberately does not claim the canonical 32 MiB owned-memory
floor or the full canonical notebook workload. It uses the existing expanded
loader/text/registry/guard semantics and allocator scans, generation checks,
ownership, zeroing and teardown algorithms. The 512-frame historical profile and
8,192-frame native notebook profile retain their original selections. The
current 512x640 O2 notebook needs 126 owner pages: 21 fixed table/registry pages,
4 kernel stack, 13 text, 1 data, 4 User stack, 2 extra L0 tables, 41 ink/index buffers
and 40 framebuffer pages. Its quota leaves two spare pages; future image or
application growth must be checked against that bound. The silicon descriptor,
RTL block DMA span and top-level DMA guard all enforce the same 4 MiB window.
The remaining architectural RAM is external simulation memory, outside this
allocator supply. No physical SRAM capacity follows from this binding.

MMIO UART registers use byte accesses; timer msip uses 32 bits and
mtime/mtimecmp use 64 bits; PLIC and VirtIO transport registers use 32 bits;
pen and paper control registers use aligned 64 bits. The integrated CPU binding
requires natural alignment for every multi-byte access, including the paper
staging aperture; unaligned CPU beats fault before device selection. The
standalone paper module accepts contained unaligned aperture beats, but that
does not extend this CPU binding. Byte staging accesses remain supported. The UART is a diagnostic
byte transport at the existing driver offsets, with IER receive/transmit bits,
IIR causes 4/2/1, and LSR transmit-ready plus receive-present. Its FDT
`lemma,diagnostic-uart-v1` compatible identifies this exact register subset;
clock-frequency is the actual 100 MHz controller clock. There is no physical
baud generator, modem, FIFO trigger or electrical UART claim. The QEMU FDT
retains its actual `ns16550a` identity and 3,686,400 Hz peripheral clock. Unsupported offsets/widths and unmapped accesses
produce an actual two-cycle AHB error response and architectural access fault.
The fabric retains a terminal device error and its read data across both AHB
error cycles; it does not issue the completed device transaction again.
Reset clears controller requests and IRQ state before new traffic; external
medium/panel retention is an independently declared model.

The timer supplies real MTIP. Lean M firmware rearms mtimecmp and forwards a
writable SSIP to S; notebook device IRQs reach a real PLIC S context. The
selected core has no H extension: MIDELEG readback is 2 for the compute service
and 514 for the notebook, unlike the QEMU WARL readbacks 0x1446/0x1646. The
guest boot seam checks those exact different values; it shares firmware,
allocator, scheduler, capabilities, IPC, store and application policy.
The service boot timer self-test uses the binding's 10,000 timer ticks (1 ms)
instead of QEMU's unchanged 1,000,000 ticks (100 ms). Both execute the same
actual rearm, WFI, interrupt-count and acknowledgement checks. This startup
interval does not change the existing 10,000-tick user scheduling quantum
(1 ms at the declared 10 MHz timer rate).

The instruction cache is 4 KiB and follows the guest's real `fence.i` operations;
the data cache is disabled in the inspected core configuration. Guest data
accesses, page-table walks and RTL controller DMA observe
the same serialized external RAM byte port. DMA is restricted to the declared
owned frame-pool physical window and the existing pinned-buffer lifetime
rules. This is an implemented uncached configuration, not a prose assertion
that an otherwise cached address happens to be coherent.

Descriptor ABI2 retains the 32 little-endian u64 layout and checksum of ABI1;
word1 distinguishes ABI2 and word25 is zero because there is no RTC. Geometry
comes from the development profile and is queried by the shared notebook.
The guest's silicon FDT pass requires the exact six-device inventory and 13
PLIC sources; QEMU's RTC and seven empty transports remain required by its
separate historical inventory. Each backend retains its own timing and input
identity. Cross-backend comparison applies to device results and durable guest
payloads, not instruction schedules, boot inventory or cycle counts.

Pen and paper use the [existing v1 protocol](004-devices-v1.md); block uses the
existing modern VirtIO MMIO split-ring subset. RTL handles controller state,
queue execution and bounded DMA. External host models provide only raw input,
memory/medium bytes and visible panel state driven by controller output. Guest
Lean remains authoritative for ink, records, recovery and save acknowledgement.

Task006's compatible pen implementation retains all 256 FIFO entries and all
64 sequence/timestamp bits. Sixteen independent synchronous storage banks and
a registered ingress payload isolate raw validation from storage enables. The
immutable public head is cached. An acknowledged nonfinal pop advances it once,
then applies MMIO/input backpressure for a two-clock refill; dropping the already
completed request does not cancel that refill. Reset cancels private pending
ingress/refill state and leaves the FIFO empty. A watchdog reached during refill
is handled at its next boundary, at most two controller clocks later, retaining
the new head. No sample, ACK, loss, resynchronization or register field is
truncated. This is permitted bus latency, with no v1 register ABI change.

The paper controller captures each MMIO request before decoding it. The master
holds the request until `ready`; dropping `valid` or applying reset cancels a
pending request. Reads select the aperture bank or control word, sample it at
the registered `READ_BANKS` edge, then register the selected bytes and error
before returning `ready`. That sampled response remains stable through the
completion. A changing status read therefore describes its sampling edge,
not a later response cycle. Control writes retain all 64 bits for bounds
validation; upper bits cannot alias a valid tile or refresh command.

Eight banks hold the 512-byte tile aperture. Accepted uploads isolate their
staging bytes while a bounded row/pixel cursor drives the framebuffer port.
The first packed byte is captured at acceptance; subsequent bytes pass through
registered row, bank and byte selection. Cursor advancement requires a real
framebuffer handshake, and a stalled pixel remains stable. Refresh acceptance
and snapshot isolation retain the v1 contract. These internal pipeline stages
change permitted transaction latency, not guest ink or storage policy.

Synthetic display timings are not qualified physical waveforms. Analog pen,
panel electrical compatibility, memory controller/macros, pads, packaging,
RF/radios, fabrication acceptance and full-chip signoff remain unverified.

-->
