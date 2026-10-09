# Pinned UART boundary for Core0 v0.5

The machine is the existing one-hart QEMU `virt`, RV64 integer-only, `-bios none`
profile. The source archive is QEMU 11.1.1 at
`c3d48b7d1e89604920e5b81b91140c2ad39a1943`, content SHA-256
`079ffbff8a7111bbc89022107cbabf3bbfd614d5fc9d7cc675991196aca12482`.
The following files were inspected directly from the pinned Nix source archive
`/nix/store/5fncyn7ha91mjhrxsl6id2wdi6zlgbnb-qemu-11.1.1.tar.xz`:

| File | Inspected responsibility | File SHA-256 |
| --- | --- | --- |
| `hw/riscv/virt.c` | UART map, DTB properties, device construction | `ab1ef03005e1a94c25f6a8c7e1ddb7c44393802a7db13410c5c97603a1ea4920` |
| `hw/char/serial.c` | register reads/writes, FIFO reset, transmitter/backend behavior | `b67d258a7dcb02174ad25eac3fc8ebc89b625aabf87e74f6f8ace7d94eb8b18f` |
| `hw/char/serial-mm.c` | shift-zero register wrapper and implemented span | covered by the source archive hash |

`virt.c:98,813-829,1485-1487` assigns base `0x10000000`, DTB span `0x100`,
compatible `ns16550a`, clock property 3,686,400, interrupt 10, and register shift
zero. The captured DTB hash is
`c9c27a1a5c9a652c5c9daa8109c5109d651dacf502b2b7c6081d63d99849d73f`.
`serial-mm.c` implements eight register bytes when shift is zero. Its wrapper accepts
some wider host accesses and masks writes to a byte; Lemma deliberately admits only
byte accesses. The DTB clock is a recorded property, not a timing oracle: the QEMU
device construction separately passes baudbase 399193 and the tests assert no baud
rate or physical latency.

`serial.c:87-94,330-363,409-431,479-500,523-529` establishes the used side effects:

- LSR at offset 5 observes DR `0x01`, errors `0x1e`, THRE `0x20`, TEMT `0x40`.
  Reading LSR clears BI/OE (`0x12`), preserving PE/FE (`0x0c`).
- RBR at offset 0 consumes a FIFO byte and clears DR/BI when it empties.
- THR at offset 0 writes a byte, clears THRE/TEMT, and starts backend transmission.
- FCR `0x07` at offset 2 enables FIFO operation and resets receive/transmit FIFOs.
  Reset cannot retract bytes already delivered to the external backend.

The closed source constructors do not accept addresses or widths. The emitter uses
one volatile `i8` access with `align 1`, bracketed by `core0_io_fence`. The optimized
audit accepts only alignment one or the exact power-of-two alignment implied by the
constant address: `2^28` at RBR/THR, 2 at FCR, 1 at LSR. No source emitter alignment
promise is strengthened. The machine audit verifies six `lbu`/`sb` sites and their
12 calls to the primitive whose body is exactly `fence iorw,iorw; ret`.

The finite Lean model makes access/fence events and bounded polling outcomes
observable. Scripted LSR samples abstract asynchronous backend timing; the model
does not reproduce FIFO capacity, all UART registers, backend retry scheduling,
interrupt delivery, or a physical serial link. Packet/encoder probes and local
lemmas have correspondingly local claims. QEMU execution separately tests receive,
transmit, bounded timeouts, and request/response behavior.

The branch test initializes the RAM marker to `0x3c`, then reads it through the
compiled checked-RAM API after the selected branch. Its response carries the actual
readback in bits 15..8 and the selector in bit zero. The host requires `0x5a00` with
no raw UART prefix for false, and `0x3c01` with raw prefix `a5` for true. Normalized
source and pre/post LLVM reachability separately check exclusive effect placement.
