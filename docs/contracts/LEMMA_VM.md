# LemmaVM — boot-slice contract proposal

Status: Task 001 executes and pins the bounded QEMU scalar-boot profile. Task 002
Gate 5 retains that boot contract and adds the fixed ordinary-memory test layout;
Gate 6 adds the polling-only compiled UART contract below. Traps, timers, privilege
transitions, and the remaining roadmap are still unimplemented at this checkpoint.

The reference backend is QEMU system emulation, RISC-V `virt`, one RV64 hart,
128 MiB RAM, no network or disk for the first smoke test, a UART for target output,
and an explicitly selected firmware policy: **`-bios none`**.

## Pinning and discovery

Record QEMU source/version/build identity, every command-line option, machine settings,
CPU feature set, memory layout, boot device tree and its hash. Avoid implicit devices
and interfaces not needed by this slice. QEMU-generated reset ROM/trampoline and DTB
are emulator artifacts: identify them rather than pretending `-bios none` means that
no emulator-provided instructions execute before the image.

The task must establish how the chosen ELF is loaded and reached in M-mode. Never
substitute OpenSBI, U-Boot, a Linux guest, user-mode QEMU, or host evaluation for this test.
A static UART address may be used in the initial profile only after it is checked against
the pinned machine's device tree and documented with the relevant source revision.
General device-tree parsing belongs in later boot work.

## Minimal observable behavior

Target code writes a distinct Core0 version banner and a framed result computed from
runtime input. The host harness compares results with the independent Lean reference.
Runtime input must arrive after code generation (for example through UART or a reserved
and declared test-memory fixture); merely printing a compiler-folded constant is insufficient.

Reserve test fixture memory away from program and stack and record its bytes/hash. It is
input data, not a second undeclared boot image. Target timeouts and malformed/truncated
responses fail tests. Terminate and reap emulator processes on every host failure path.

## Gate 5 fixed-memory test layout

The checked-memory image keeps the Task 001 RAM, image, stack, UART, and SiFive-test
addresses. It loads two declared fixture envelopes: machine bytes
`[0x807efff0,0x80806010)` and input bytes `[0x80fffff0,0x81001010)`. Within them,
the v0.4 region catalog places 4 KiB ordinary regions at `0x80801000`
(scratch), `0x80803000` (output), `0x80805000` (events), and `0x81000000`
(read-only input). Ten independent 16-byte canaries cover both sides of the image,
stack, ordinary regions, and input region.

Fixtures are deterministic functions of the suite, case, and runtime seed. Each
case boots a fresh VM and binds its descriptor, fixture hashes, ELF hash, and UART
transcript. The target reports its checked result, boundary canaries, and complete
post-execution ordinary-region state; the host compares that state with the finite
memory model. These are test observations inside trusted M-mode, not a physical
memory-protection or process-isolation claim.

## Gate 6 pinned UART session

The Gate 6 device image remains a one-hart, integer-only RV64 QEMU `virt` image with
`-bios none`. Its machine contract is QEMU 11.1.1 at revision
`c3d48b7d1e89604920e5b81b91140c2ad39a1943`; the pinned source archive content
SHA-256 is `079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482`.
The captured DTB node `/soc/serial@10000000` names `ns16550a`, base
`0x10000000`, span `0x100`, input clock 3,686,400 Hz, and interrupt 10. Gate 6
does not enable or claim that interrupt.

Lemma uses byte-wide, register-shift-zero accesses in the first eight bytes. RBR/THR
is offset 0, FCR/IIR offset 2, and LSR offset 5. LSR bits used are DR `0x01`, line
errors `0x1e`, THRE `0x20`, and TEMT `0x40`. Reading RBR consumes a receive byte;
reading LSR clears the modeled BI/OE latches; writing THR updates transmitter state;
writing FCR `0x07` enables FIFOs and clears RX/TX state. Every compiled access is a
volatile aligned byte bracketed by full IO fences.
The DTB clock property is not used as a timing oracle. Source inspection, the
emitter/optimizer alignment distinction, and the finite model's abstraction limits
are recorded in `docs/audits/uart-core0-v05.md`.

The host opens one QEMU process, waits for the compiled READY frame, and only then
sends two independent bounded requests over that process's serial input. It validates
raw response frames against an independent host oracle and records the one PID, ELF
hash, exact argv, transmitted/received bytes, exit status, timestamps, and timeout
cleanup. The machine harness itself performs only the zero-argument Action call and a
status-coded SiFive-test write; it contains no UART parser, polling loop, formatter, or
drain routine.

## Roadmap, not current guarantees

Later profiles add timers/interrupt controllers, M->S->U transitions, Sv39, VirtIO block,
input/display abstractions, networking and physical-board conformance. The first image
need not implement them and may not claim isolation, scheduling, durability or pen latency.

## Evidence

Save full launch arguments, UART transcript, exit/timeout outcome, output framing,
input corpus, model results, image hashes and relevant emulator metadata. Execute more
than one fresh boot and both unoptimized and optimized builds. No fabricated logs.

See official QEMU references in `docs/SOURCES.md`.
