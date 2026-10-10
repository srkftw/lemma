# Lemma machine profile 0.1.0

Decision date: 2026-10-10. Architecture freeze adopted by Task 004, not an
implementation or physical-conformance certificate. `lemma-one-core/0.1.0`
is the common software/device-service floor; `lemmasim-virt/0.1.0` is its
precise first virtual binding. Student, Developer and Laboratory use one
machine. Physical conformance is **UNVERIFIED**; motherboard/cartridge is
**NOT_FROZEN**. The complete machine remains governed by
[the canonical contract](../../LEMMA_MACHINE_CONTRACT.md). Historical
[LemmaVM](LEMMA_VM.md) profiles and their evidence are unchanged.

The machine executes maintained Lean-authored freestanding RV64 kernel,
firmware, drivers, services and applications through the existing genuine Lean
elaboration/Core0/LLVM path. Target code is little-endian RV64IM, LP64,
integer-only; one hart uses M/S/U and Sv39 4KiB pages. No target hosted runtime,
Linux, C/C++/Rust/Zig/handwritten assembly, libc or managed Lean runtime is
introduced. Host hardware models may be C, transport raw input, block bytes and
controller-visible pixels, and use normal host runtimes. They do not implement
notebooks, brushes, document serialization, recovery, mathematical authority or
capability policy.

The binding derives from immutable QEMU `c3d48b7d1e89604920e5b81b91140c2ad39a1943`,
keeps the pinned Lean/LLVM/LLD/Nix environment, and is separately named
`lemmasim-virt`. TCG, `rv64,smrnmi=false,smdbltrp=false`, one hart, 128MiB,
`-bios none` preserve real reset ROM/DTB and Lean M-firmware → S-kernel → U-task
handoff. Integer-only emitted code does not imply the CPU lacks inherited
extensions. The generated DTB/CPU inventory belongs to each run identity.

| Function | Base | Span | IRQ |
| --- | ---: | ---: | ---: |
| RAM | `0x80000000` | `0x08000000` | — |
| CLINT | `0x02000000` | `0x10000` | local timer7 |
| PLIC | `0x0c000000` | pinned virt span | — |
| UART | `0x10000000` | `0x100` | 10 |
| Modern VirtIO block, explicit transport0 | `0x10001000` | `0x1000` | 1 |
| Paper v1 | `0x10010000` | `0x1000` | 12 |
| Pen v1 | `0x10011000` | `0x1000` | 13 |

The eight inherited VirtIO transports occupy `0x10001000..0x10009000`;
paper/pen do not overlap them. Source11 remains goldfish RTC. Fixed inherited
mask ROM, SiFive finisher, CLINT, PLIC, UART, RTC (`0x00101000`), fw_cfg,
platform bus, PCIe host/interrupts and two CFI flash banks remain present and
must be accounted for in binding observations. Additional guest-visible
peripherals and CPU features cannot be erased from identity by `-nodefaults`.
No network/PCI endpoints, random input device or flash image is attached by the
Task 004 launch. RTC origin is fixed by its launch policy. UART is diagnostic,
not pen/disk transport.

A bounded descriptor is read by the guest from the paper device; its exact
layout and the pen/paper protocols are [subordinate v1 ABIs](004-devices-v1.md).
Unknown mandatory versions or inconsistent/overlapping map/reservations fail.
The 10MHz guest monotonic timer is separate from wall time. Geometry/capabilities
are queried: default1650×2200 and fixture1404×1872 use the same guest binary.
Neither is a confirmed physical purchase. Synthetic pen pressure range is
0..4095; mouse pressure is marked synthetic. Missing tilt is absent.

Pixels are packed row-major Gray4, black0/white15, even-x high nibble,
stride`ceil(width/2)`, unused last nibble white. Only controller refresh completion
changes visible pixels. Both native/headless frontend consume that same state.
Fast threshold-monochrome and quality-gray refresh use named synthetic timings;
no vendor waveform or measured latency is asserted. Document coordinates remain
normalized integers0..2^24, mapped with wide integer
`floor(q*(dimension-1)/2^24)`; raw input provenance is distinct.

Block transport is modern OASIS VirtIO1.2 MMIO, split ring, one queue,
512-byte sectors, VERSION_1 and FLUSH negotiation. The initial raw medium is
256MiB/524288 sectors; clients query capacity. Owned pinned DMA/bounce pages
retain ownership until completion/reset quiescence. Notebook receives document,
input and surface capabilities; raw block is reserved to the store authority.
Ordinary write completion is distinct from durable commit acknowledgement.
Store-defined payload/commit barriers, explicit errors, power cuts and recovery
are guest responsibilities. Host panel retention is physical display state,
never document truth. Reset is not clean shutdown.

Deterministic virtual replay identifies core/binding/device/backend versions,
all guest hashes, geometry/capabilities, clock policy, initial media hash and
external events/faults. Use pinned QEMU's record/replay machinery and bound
external raw streams; instruction counting alone is insufficient. Exact replay
is distinct from future physical tolerance. Whole-machine snapshot is optional;
this controller adapter does not claim snapshot support.

Avalue ENT-13T3 Gen3 is a supplier system lead, not an orderable/documented
RISC-V cartridge. E Ink/Linfiny/Wacom public category information does not grant
controller/waveform rights. JH7110/VisionFive2 remains a physical-port candidate,
not a qualified boot/DRAM/peripheral closure. FPGA/PMIC/connector sketches,
DDR/BootROM, cartridge SKU, physical pressure/timings, battery/network/USB,
finished capacities, multicore, browser runtime, managed Lean ABI, textbooks
and tutor remain deliberately unfrozen. No hardware purchase, private supplier
material or proprietary waveform is implied or included.

Incompatible semantics require a new explicit profile/ABI/format version and
stored-data migration or refusal. Optional capabilities are negotiated without
changing existing meanings. All new hardware observations are **SIMULATED_ONLY**;
physical whole-machine equivalence requires a named actual binding and measurements.

Normative machine-readable source: [profile JSON](../../sim/profiles/lemmasim-virt-0.1.0.json).
Public basis: [VirtIO1.2](https://docs.oasis-open.org/virtio/virtio/v1.2/virtio-v1.2.html),
[QEMU virt](https://www.qemu.org/docs/master/system/riscv/virt.html),
[QEMU replay](https://www.qemu.org/docs/master/system/replay.html), and immutable
[pinned map](https://github.com/qemu/qemu/blob/c3d48b7d1e89604920e5b81b91140c2ad39a1943/hw/riscv/virt.c).
Frozen project allocations are decisions, not vendor-register claims.
