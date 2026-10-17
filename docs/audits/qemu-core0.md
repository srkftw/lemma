<!--
# LemmaVM QEMU `virt` audit for Task 001

The tested emulator is QEMU 11.1.1, upstream commit
`c3d48b7d1e89604920e5b81b91140c2ad39a1943`, from the pinned Nix output recorded
in `tooling/toolchain-lock.json`.  The executable is
`/nix/store/9ihv5zpj6l7fl12mdcxrbmiih3wgrmhw-qemu-11.1.1/bin/qemu-system-riscv64`.

## Frozen launch profile

Each differential case starts a fresh emulator with:

```text
qemu-system-riscv64
  -machine virt,acpi=off
  -accel tcg -cpu rv64 -smp 1 -m 128M
  -bios none -kernel <image.elf>
  -device loader,file=<input.bin>,addr=0x81000000,force-raw=on
  -nodefaults -nic none
  -display none -serial stdio -monitor none
  -no-reboot -seed 1
```

No block device or network backend is attached.  The generic-loader fixture has no
`cpu-num` property, because setting it would also change the CPU program counter.
The host runner enforces a per-run timeout, kills the process group on expiration,
reaps it, requires exit status zero and empty stderr, and accepts only one complete
versioned UART frame.

`-nodefaults` does not remove the `virt` board's buses or MMIO transport windows; it
prevents default guest devices from being attached.  These unused platform nodes are
visible in the captured DTB and are not guest code dependencies.

## Reset and handoff

`-bios none` means no OpenSBI or other external firmware image is loaded.  It does not
mean that execution starts directly in the project ELF.  QEMU synthesizes the machine
ROM at `0x1000` (`VIRT_MROM`, size `0xf000`) in `hw/riscv/virt.c` and
`hw/riscv/boot.c:riscv_setup_rom_reset_vec`.

The six-instruction RV64 reset vector obtains `mhartid`, loads the generated DTB
address and next address from its data words, and jumps there in M mode.  Under this
profile the observed handoff is:

- PC/reset ROM: `0x00001000`;
- `a0`: hart ID `0`;
- `a1`: runtime DTB at `0x87e00000`;
- `a2`: firmware-dynamic information at `0x1028`; and
- next address: `0x80000000`.

The Task 001 startup contract consumes and preserves only `a0` (hart ID) and `a1`
(DTB pointer), storing them in the two declared BSS boot slots.  The observed `a2`
firmware-dynamic pointer is intentionally ignored by this no-firmware scalar slice;
supporting an SBI-style firmware handoff would require a new versioned contract.

For `-kernel`, QEMU 11.1.1 assigns the reset next address from
`boot_info.image_low_addr` in `hw/riscv/virt.c`, not from ELF `e_entry`.  A probe whose
entry field differed from its lowest load segment confirmed the latter was reached.
Therefore the closure audit requires all three facts: ELF `e_entry == 0x80000000`,
`_start == 0x80000000`, and the lowest executable `PT_LOAD` begins at `0x80000000`.

An actual post-reset monitor capture produced these emulator-artifact hashes:

| Region/artifact | SHA-256 |
| --- | --- |
| full MROM, `0x1000..0x10000` | `d0fd275d8b65aecfaeeabbfdca02152793356dfc852fa1304fc790c33a1fd75b` |
| pre-reset `dumpdtb` | `c9c27a1a5c9a652c5c9daa8109c5109d651dacf502b2b7c6081d63d99849d73f` |
| runtime DTB at `a1` | `6190e60bba396a340b526ac10219a43184e3927fa76c8a096bc5700ade41c5df` |

The two DTBs differ only in `/chosen/rng-seed`: QEMU randomizes that 32-byte property
during reset.  Both captures are deterministic with `-seed 1`.  Each real build also
regenerates `platform.dtb` and its DTS, validates the declared nodes, and records the
artifact hash; it does not claim the pre-reset blob is byte-identical to the handoff
blob.

## Validated layout and devices

The captured device tree establishes:

| Item | DTB value | Project use |
| --- | --- | --- |
| DRAM | `reg = <0 0x80000000 0 0x08000000>` | 128 MiB RAM |
| CPU | one `cpu@0`, `rv64i` base and at least `m`, `zicsr`, `zifencei` | generated integer code |
| UART | `ns16550a`, `reg = <0 0x10000000 0 0x100>` | bounded framed output |
| finisher | `sifive,test0/test1`, `reg = <0 0x00100000 0 0x1000>` | VM termination |

The project image envelope is `[0x80000000,0x807f0000)`, the fixed stack is
`[0x807f0000,0x80800000)`, and runtime input is
`[0x81000000,0x81001000)`.  The Lean layout validator enforces containment, alignment,
and non-overlap.  The runtime DTB at `0x87e00000` is outside those regions.

The SiFive finisher encodes host status in the upper 16 bits.  Probes established that
`0x5555` exits successfully, while a failure write must use `0x00013333` (not merely
`0x3333`) to make QEMU return nonzero.  Both writes are 32-bit volatile MMIO surrounded
by the generated I/O fence primitive.

-->
