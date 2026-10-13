# Product boot and recovery v1

This additive software/hardware contract uses `core0-boot-v0.1` and
`lemma-silicon-dev/0.7.0`. Existing development profiles keep ELF-preload boot.
Product execution loads the immutable ROM at `0x1000`, not the selected running
kernel. The ROM is genuinely elaborated Lean, checked against the isolated boot
profile, lowered to LLVM and linked as freestanding RV64IM/Zicsr/Zifencei.
The ROM has a 64 KiB RX envelope, scratch at `0x81fc0000..0x81fc4000` and
stack at `0x81fd0000..0x82000000`. `lemma-boot-direct-branches-v1` requires
the generated LLVM functions' `no-jump-tables=true` attribute; admitted direct
branches retain the same dispatch semantics. No arbitrary runtime helpers are
admitted. The structured reset boundary masks interrupts, clears `satp`, sets
the private stack, calls the checked ROM entry, then fences instruction visibility
and jumps only to its validated entry with hart 0 and DTB `0x87e00000`.

CRC32/ISO-HDLC detects corruption. It supplies **no authentication**, trusted
owner identity, anti-rollback guarantee or physical nonvolatile qualification.
Cryptographic authentication and durable trust state remain OPEN. Recovery is
an integrity-only, owner-local development transport and must be presented as
such. The versioned compatibility number `0x0007000300010001` is a registry
identifier, not a source hash or cryptographic identity.

## Separate boot controller

`lemma,boot-nv-v1` occupies `0x10012000..0x10012400`, IRQ 17. It is separate
from the user journal. Binding 7 inherits USB binding 6, with descriptor ABI 8,
features 31 and 17 PLIC sources. Its DTS node includes `lemma,abi-version=1`,
`lemma,sector-bytes=512`, `lemma,capacity-sectors=65544`, `lemma,rom-bytes=65536`
and `lemma,integrity-only=1`.

Registers are aligned 64-bit accesses. Identity is `0x564e424c`, version 1.

| Offset | Register |
| --- | --- |
| 0, 8, 16 | identity, version, capacity sectors |
| 24 | idle 0, pending 1, completed 2, cancelled completion 3 |
| 32, 40 | selected sector; command Read 1 / Write 2 / Barrier 3 |
| 48, 56 | assigned request identity; completed identity |
| 64, 72 | raw outcome; actual transferred bytes |
| 80, 88, 96 | matching completion ACK; cancellation; reset origin |
| `0x200..0x3ff` | 512-byte PIO buffer |

One request may be outstanding. Request fields and its PIO data remain stable
while pending. Completion interrupts remain asserted until matching ACK.
Successful Read/Write requires exactly 512 bytes; successful Barrier requires
zero. Invalid completion counts fail closed. Partial failures preserve actual
changed backing bytes and reported counts. Cancellation requests are retained
until the real external outcome arrives; cancelled work is not rolled back.
Reset changes the retained origin namespace. An old operation's actual outcome
must still be captured, but must not be published to a replacement controller.
No powered-down domain accepts new requests. Suspend admission includes boot
requests and externally pending orphan work.

The host adapter assigns independent captured operation IDs to logical
`(reset_origin, request_id)` identities. Its accepted boot bytes, capture tape,
pending operations and private fork backing are separate from user storage.
Snapshots must neither complete nor resubmit external work. A live USB adapter
still requires its own exact-state contract; a no-adapter snapshot is not USB
continuation qualification.

## Image and metadata wire format

The medium is 65,544 sectors (33,558,528 bytes). Metadata sectors are 0 and 1;
sectors 2..7 are reserved. Slot 0 begins at 8; slot 1 begins at 32,776. Each slot
contains 32,768 sectors (16 MiB). All fields below are little-endian UInt64.
Unused fields must be zero. CRC fields use reflected polynomial `0xedb88320`,
initial/final XOR `0xffffffff` and are stored zero-extended.

Each slot header is one sector: words 0..5 are image magic
`0x31474d49414d454c`, version 1, nonzero image ID, compatibility, segment count
1..8 and entry. Words 6..7 are DTB byte length 40..3072 and its CRC32. Slot
bytes 512..3583 contain the per-image DTB; the ROM checks its FDT magic,
big-endian declared length and actual CRC, then loads it at `0x87e00000`.
This bounded discovery region is additional boot-profile authority. Volatile
DTB RAM is never restored by the host after power loss. Words 8..47 contain eight rows of
`(slot-byte-offset, file-bytes, memory-bytes, destination, file-CRC32)`;
inactive rows are zero. Words 48..62 are zero; word 63 is CRC of bytes 0..503.
Offsets are sector-aligned and at least 4096, destinations word-aligned, memory
length nonzero and at least file length, and all spans are checked without
wrapping. A pure BSS segment has zero file length and the empty CRC32 value 0.
Loaded segments are disjoint and lie in `0x80000000..0x81f00000`.
The aligned entry lies in the first 64 KiB and in a file-backed segment.
The ROM validates the actual media bytes, copies aligned words and byte tails,
and zeroes BSS before publishing the loaded image context.

Metadata words 0..8 are metadata magic `0x31444d42414d454c`, version 1,
generation, confirmed slot, confirmed ID, trial slot, trial ID, attempts and
limit 3. Words 9..62 are zero; word 63 is CRC of bytes 0..503. Generation 0
and `UInt64.max` are rejected. Confirmed slot is 0/1 with nonzero ID.
Trial-none is 2 and requires ID/attempts zero; a trial is the other slot with
nonzero ID and attempts at most 3. The highest valid generation wins; equal
generation requires exact equal metadata bytes. Conflicting equal-generation
records enter recovery. Failed reads do not authorize first-image installation.

An update writes only the inactive slot. Payload barrier and full integrity
validation precede alternate-sector metadata WRITE and Barrier. Before every
trial handoff the guest publishes generation+1 and attempts+1 with a barrier.
Three unconfirmed attempts select the known confirmed slot. A failed trial
load also falls back to confirmed. Repeating an already-published image after
a lost receipt validates its bytes and reconciles the same record without
resetting generation or attempts. First-image recovery requires no valid or
conflicting metadata, verifies the payload, then publishes both peers with
individual barriers. Interruption may leave one usable peer.

Boot context scratch words 0..5 are `0x31585443414d454c`, version 1, loaded
slot, image ID, selected generation and trial flag. Confirmation requires
this exact receipt and fresh metadata. It publishes a new confirmed record
through alternate WRITE/Barrier. The ROM never automatically confirms an image.
The product guest's independent health policy must qualify its confirmation
point; component tests do not establish notebook readiness.

## Owner-local recovery UART v1

A byte `0x52` queued at reset requests recovery before normal boot. On entry
the ROM initializes the controller/UART, clears the FIFO and sends a beacon
receipt with transaction 0 and capacity. A host sends only that byte until the
beacon arrives, then sends framed requests. Failure to load normal boot also
enters this announced recovery path. Queued recovery bytes are raw UART input;
the host never marks an image accepted or changes guest memory on its behalf.

A request has ten words: magic `0x31564f4345524d4c`, version 1, nonzero
transaction, opcode, slot, relative sector, image ID, reserved zero, payload
CRC32, and CRC32 of the first 72 bytes. Opcode 1 appends exactly 512 opaque
bytes. Opcodes are capacity 0, stage sector 1, validate/publish 2, boot 3,
and fresh image-status reconciliation 4 (confirmed 1 / trial 2). Responses have
magic `0x3154504345524d4c`, transaction, actual status, value and CRC32 of the
first 32 bytes. UART polls have 100,000-iteration bounds; synchronization and
the command loop each have 65,536-step bounds. Corrupt/partial frames produce
no installation effects and synchronize on a fresh magic. A receipt follows
the relevant actual barrier, never an in-memory write alone. Status opcode4
performs a fresh barrier, selects fresh metadata and verifies the entire matching
image and discovery bytes before returning confirmed/trial. An earlier failed
barrier or corrupt image cannot be reconciled by a metadata read alone. Status
does not reset generation or trial attempts.

The transaction ID correlates replies; it does not guarantee exactly-once
packet delivery. Durable metadata/status reconciliation handles lost replies.
A disconnected operation can have changed backing bytes without an acknowledged
durable result. Reset/retry must preserve this distinction.


## Product supervisor mappings

`AddressSpace.configureProduct(7)` performs a fresh actual binding7/DTB
validation before publishing the kernel-only selection word `0x80400fc0=7`.
Other admitted selection is zero; an unknown value fails closed. The explicit
`Process.initProduct`, `Task.prepareManagedProduct` and `Loader.loadProduct`
construct the kernel and every selected User root through `createProduct`.
Existing constructors retain their original read/fault prefixes and mappings.

Layout3 requires the actual8192-frame configuration. It owns and pins fourteen
initial purpose2 page tables rather than the expanded legacy thirteen. The
four pages `0x81fc0000..0x81fc4000` hold ROM context, header and metadata;
`0x10012000` is the NV device page. All five aliases are supervisor RW/NX,
with U and X clear. Neighboring scratch and device pages remain unmapped.
The existing header field+88 stores layout witness `0x3353415000000020`;
its low32 bits retain table capacity32. Versions1/2 require the old exact32.
Thus changing only the version between2 and3 fails at an already-required
header read. Allocation, generations, purpose ownership, pinning, publication,
rollback and registry duplicate checks remain in force.

`tests/kernel/ProductAddressSpace.lean` executes the actual maintained Actions
against finite raw RAM. Its independent Sv39 walker checks literal mappings
and permissions, owned/pinned tables, version/header mutations, legacy absence
and selector read/fault behavior, and rollback at each new mapping boundary.
This host result is separate from linked RV64 and actual S-mode confirmation.

`lemma-product-pmp-v1` adds a separate ninth PMP entry for this same NV
aperture. Structured startup selects it only for the explicit normal Product
supervisor deployment: `pmpaddr8=0x0400487f`, `pmpcfg2=0x1b` grant NAPOT
`0x10012000..0x10012400`, RW/NX, unlocked. It clears cfg2 before programming,
checks real M-mode readbacks, and enters the existing machine-fatal path if
either differs. Historical startup keeps its exact eight entries, cfg0 and
instruction sequence; it gains neither cfg2 nor a larger device interval.
The canonical core has sixteen implemented entries. U access still requires
its page-table U bit, which is clear on the Product device alias.

The original Product3 kernel read NV identity with SATP zero and took actual
load-access fault5 at `0x10012000`, followed by supervisor-double-fault51.
Its recorded state demonstrated that the existing PMP entry7 ended exactly
at that address. The separate entry repairs that missing startup authority;
host geometry tests alone do not qualify the subsequent RV64 boot.

## Qualification boundaries

The local command surface is `scripts/lemmasim product --help`. Preparation
checks the exact native source/tool/binary closure and genuine audited ROM;
an explicitly supplied consumed-source archive must match the complete original
manifest. Prepared paths remain local dependencies. This is not a self-contained
redistribution bundle or a new licensing grant.

```sh
nix develop --no-write-lock-file --command python3 scripts/build_product_boot.py \
  --work-dir build/boot/my-rom --timeout 300
nix develop --no-write-lock-file --command python3 scripts/lemmasim product prepare \
  --native-build build/silicon/my-product-native \
  --rom-build build/boot/my-rom --output-dir build/boot/my-prepared
python3 scripts/lemmasim product create-medium --boot-medium build/boot/my-boot.raw
python3 scripts/lemmasim product launch --prepared build/boot/my-prepared \
  --boot-medium build/boot/my-boot.raw --disk existing-user-journal.raw \
  --session-dir build/boot/my-session --recovery --paused --mode developer
python3 scripts/lemmasim product capacity --session-dir build/boot/my-session
```

For retained exact native/ROM builds, `prepare` also accepts
`--native-source-archive` and `--rom-source-archive`. They select validated
original input bytes; they do not bypass the normal current-source check.
Prepared schema2 regenerates the fixed digital discovery descriptor from that
exact native profile with pinned dtc1.8.1, and binds its bytes and DTB extent.
Only the 256-byte hardware descriptor is supplied to the machine. The generated
profile DTB remains a preparation artifact: ROM still reads the installed DTB
through real NV transactions. Installation rejects a package whose discovery
extent differs from this fixed profile. Native execution defaults to one host
evaluation thread; this changes neither virtual clock nor target event policy.
The omitted descriptor in original prepared schema1 caused an observed
Descriptor.invalid169 startup failure; that failure is retained separately.
The native build must be profile7 with real128MiB simulation RAM. Creating a
boot medium only creates blank raw bytes and never formats the user journal.

`package_product_image.py --guest-build <strictly-audited-product-build>
--image-id <nonzero-registry-ID> --output-dir <unused-package>` packages opaque
ELF/DTB bytes. `product install --session-dir <recovery-session> --package
<package> --slot 0|1 --cycles <declared-bound> --timeout <declared-bound>` sends
sector frames and waits for actual target receipts. `product status` reconciles
a slot/image ID, and `product boot` requests the real validated handoff. These
commands do not interpret or manufacture A/B metadata. Full image installation,
handoff and confirmation still require the separate acceptance evidence below.
Packaging validates the complete original compiled source inventory. An explicit
`--source-archive <consumed-source-root>` must match the original provenance and
every recorded source byte; it enables reuse after maintained sources advance.
The bulk Product software successor is admitted only as the exact independently
audited `lemmasim-silicon-product-bulk-notebook` selection on the same profile7.

The existing `snapshot`, `restore`, `session-control` and `session-replay`
commands operate on this same persistent machine. Starting a restored Product
session omits both media; native restore validates and privately backs their
accepted bytes. It never opens the original boot medium. A recovery client at
an already announced restored boundary uses `--continue-recovery`: past UART
output is not emitted again, and every new result still requires an actual
matching CRC-checked receipt. This is same-backend continuation, not cold boot.
Every submitted command advances its receipt cursor to the current UART output
boundary before injection. An earlier success receipt cannot acknowledge a new
request, including an explicitly reused transaction ID. A partial or non-recovery
output boundary rejects the request before injection. This is a transport rule;
it does not claim exactly-once delivery or durable deduplication of packet IDs.
Laboratory supply inputs remain separate from ordinary writing controls.

`scripts/build_product_boot.py` builds and audits the ROM with pinned tools and
exact consumed source identities. `tests/boot/ProductPolicy.lean` exercises
independent CRC vectors, corrupt/torn metadata and bounded decisions.
`tests/boot/ProductNVPolicy.lean` executes the actual maintained Action policy
against a raw I/O model, including partial writes, failed barriers, cancellation,
lost-receipt attempt retention and confirmation. `tests/boot/boot_nv_tb.sv`
qualifies the literal circuit protocol. These are component results. Actual
ROM boot, interrupted update, watchdog/brownout fallback, user-document survival,
snapshot/replay and distribution require their own machine observations.

The retained interrupted-payload observation privately restores the published
image checkpoint, writes one changed inactive DTB sector through the ROM
transport, and cold resets before any publication request. The write receipt
records observed persistence; it does not acknowledge an installed image.
ROM then records the next boot attempt durably, rejects the changed trial
image, and loads the exact confirmed ELF, zeroed BSS and DTB. Its context
identifies slot0, image1, generation3 and trial0. The confirmed image in that
historical observation has its own retained startup fault, so the result
establishes fallback loading without claiming a healthy notebook.

A separate metadata interruption stops after the actual attempt-record WRITE
outcome and before its barrier. The record bytes may therefore survive reset
without an acknowledged handoff. ROM cold recovery rereads and validates that
generation3 record, retains attempt1, and commits generation4/attempt2 through
a new WRITE and barrier before loading the exact trial image. The captured
request/outcome log contains the interrupted write once; reset does not submit
it again. This qualifies the declared observed-persistence failure model,
without claiming unconditional physical power-loss durability.
