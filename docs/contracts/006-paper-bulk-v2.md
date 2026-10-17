<!--
# Surface-v2 bounded paper uploads

This is an additive software ABI on the existing paper controller. A separately
selected Surface-v2 kernel dispatcher admits syscall64 operation5. The legacy
Surface dispatcher continues to reject operation5. Hardware timing, Gray4 pixel
packing, controller commands and the actual1650×2200 display are unchanged.

The exact canonical selections are `lemmasim-silicon-bulk-notebook` and
`lemmasim-silicon-bulk-initialize`, software
`lemma-managed-sums-bulk-deployment-v1` on unchanged hardware0.3. Product7's
separate selection is `lemmasim-silicon-product-bulk-notebook`, software
`lemma-managed-sums-bulk-product-deployment-v1`. Both select the real
`Notebook.mainSumsBulk` User2 image and the existing isolated Sums Arithmetic3
image; they add neither a language feature nor a new processor/controller.
Only their declared dispatchers reach `DeviceService.surfaceV2`. The User owns
an additional page at0x10a000 and sends the exact seven-entry/tail packets.
Every historical root keeps the legacy dispatcher and upload mode.

The request is `(surface_capability, 5, page, count, 0)`. The capability must name
the caller's live generation-checked Call grant for the boot-selected Surface
endpoint. `page` is4096-byte aligned and `count` is1..7. No request changes the
endpoint, frame owner, DMA authority or controller geometry.

The User page contains little-endian64-bit words:

| Offset | Contents |
| --- | --- |
| 0..31 | Version2, count, reserved0, reserved0 |
| 32..255 | Seven32-byte entries: x, y, width, height |
| 256..3839 | Seven512-byte packed pixel slots |
| 3840..4095 | Outside the admitted request prefix |

Only the first `count` entries and pixel slots are used. Each dimension is1..32.
Subtraction bounds require `x ≤ display_width − width` and
`y ≤ display_height − height`, without wrapped coordinate arithmetic. A slot's
used pixel length is `ceil(width/2) * height`; trailing slot bytes are not sent
to the controller. Existing nibble/odd-edge behavior remains the producer and
controller contract.

Before any paper PIO write, the kernel preflights the complete User prefix
`256 + count*512`, resolves a live owner1/purpose1 scratch frame, and copies that
prefix into the scratch frame. The scratch handle must differ from the
address-space descriptor. The version, count and reserved words are validated,
then **all** admitted tile geometry is validated. No copied metadata or pixel
alias is retained across syscall entry or a scheduling boundary. Invalid User
permissions/ranges, source-copy faults, stale handles, wrong purpose, header or
later tile geometry cannot publish an earlier tile. A failed source copy may
have changed a private scratch prefix; it has not changed paper pixels.

Each upload uses the fresh `Paper.uploadOffset` owner/generation/purpose check
and existing controller metadata/pixel/command/error sequence. The offset is
8-byte aligned and must accommodate the rounded word transfer inside4096 bytes.
No controller command or ownership check is bypassed. Metadata and pixels stay
immutable during this nonpreemptible supervisor Action.

Success returns `(0, count)`. A controller failure returns its error status and
the number of preceding successful tiles. That failure can leave an uploaded
prefix, including the failing controller command's own specified effects;
this ABI does not promise atomic batch publication. Refresh remains a separate
operation, with the existing busy, sequence and completion rules.

The focused host fixture evaluates the actual maintained Actions using real
Frames, AddressSpace, Objects and Capability constructors, finite physical RAM
and an independently constructed literal PIO oracle:

```sh
nix develop --no-write-lock-file --command lake build \
  Lemma.Platform.LemmaSim.DeviceService
nix develop --no-write-lock-file --command lake env lean --run \
  tests/ink/PaperBulk.lean
```

It compares one seven-tile request with seven legacy uploads, checks exact
controller write/pixel ordering, every guard class and a later controller-error
prefix. Primitive-operation counts measure the Action work only; they are not
RV64 cycles, processor timing parity, notebook Ready or physical panel evidence.
Whole-image checked lowering, selected dispatcher/deployment admission and
actual guest notebook performance are separate required qualifications.

-->
