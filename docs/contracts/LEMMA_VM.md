# LemmaVM — boot-slice contract proposal

Status: Task 001 executes and pins the bounded QEMU scalar-boot profile; the later
roadmap in this contract remains unimplemented.

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

## Roadmap, not current guarantees

Later profiles add timers/interrupt controllers, M->S->U transitions, Sv39, VirtIO block,
input/display abstractions, networking and physical-board conformance. The first image
need not implement them and may not claim isolation, scheduling, durability or pen latency.

## Evidence

Save full launch arguments, UART transcript, exit/timeout outcome, output framing,
input corpus, model results, image hashes and relevant emulator metadata. Execute more
than one fresh boot and both unoptimized and optimized builds. No fabricated logs.

See official QEMU references in `docs/SOURCES.md`.
