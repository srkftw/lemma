# Companion opaque backing transport development profile v1

`lemma-companion-backing-dev/1` is an independent persistent opaque block peer
and native/fast `BackingPlatform` transports. It exercises real remote receipts
below the existing Lean RV64 block driver and notebook journal. It does **not**
close the modeled companion controller, owned DMA, guest companion service,
USB enumeration/endpoints, BLE link, authentication or asynchronous offline
responsiveness obligations. The Unix socket supplies host byte transport only.

`sim/companion/Protocol.lean`, `Client.lean`, and `Peer.lean` are ordinary
elaborated hosted Lean. Protocol validation, transaction ordering, the durable
outbox, bounded retry, receipt deduplication and opaque log reconstruction are
Lean policy. Their normal hosted Lean runtime is linked only into the separate
host peer/client executables. It never enters an RV64 image. Python supplies
raw sockets, file copies, `pread`, `fsync`, truncate and atomic rename. C++ only
marshals the shared backing requests and returned outcomes. Neither host side
interprets guest records, document recovery, ink or mathematical objects.

## Wire and resource semantics

The raw transport carries a little-endian u32 byte count and those bytes. A
protocol frame is eight little-endian u64 fields: `LMCMP001`, version1, kind,
writer epoch, transaction sequence, offset, length and errno; followed by payload
and CRC64-ECMA (polynomial `0x42f0e1eba9ea3693`, initial/final0). Read kind0 has
sequence0, an aligned nonempty multiple of512 bytes, at most1MiB. Write kind1
contains exactly512 bytes and a nonzero sequence. Barrier kind2 has no payload.
Reply kind3 returns the exact observed byte prefix and errno0..4095. Every
frame and response binds the writer, sequence and offset. Frames are bounded
at1MiB+72 bytes. Checksums detect damage; they do not authenticate a peer.

One nonzero writer epoch owns a peer. Client and peer have separate OS locks;
the server accepts same-user Unix connections, a backlog of8 and one active
request. The declared trust level is an owner-controlled local development
connection. Random initialization chooses an OS-generated epoch; an explicit
epoch is available for deterministic laboratory tests. Neither is a device
identity key or production entropy guarantee. Multiple independent writers,
encrypted/authenticated network transport and credit negotiation remain open.

The medium is256MiB. A readonly opaque base plus complete valid peer log records
defines its bytes. A64MiB journal and100000 retained receipts bound resource
use. Reaching a bound rejects new work; this profile has no automatic compaction.
Each write or barrier is an ordered length-prefixed checksummed log record
containing its bytes and receipt identity together. Success is returned only
after the actual backing `fsync`. A failed sync leaves complete observed bytes
and receipt in the live peer and reports error. It does not roll back bytes.
A same-ID same-byte retry re-syncs that record before returning success.
Different bytes under an old sequence and skipped sequences are errors.

On peer restart, Lean checks complete records, writer identity and consecutive
sequences and rebuilds an opaque sector overlay and receipt map. An incomplete
trailing append is truncated and synced before service; a complete corrupt
record fails closed. This is transport-medium reconstruction, not guest journal
or document recovery. The guest still performs its existing cold recovery.

## Uncertainty, continuation and observational reads

Before sending a mutating request, the client atomically replaces and syncs a
checksummed durable outbox containing the exact writer/sequence/frame. Two
bounded2-second raw sends retry the same transaction. A validated durable
receipt clears and advances that outbox through another atomic synced replace.
If all replies are lost, `PENDING` is returned instead of fabricated bytes or
durability. The native adapter throws; the shared machine owner remains poisoned
with its captured pending operation. It cannot advance, snapshot or replay that
ambiguous boundary as if complete. The outbox remains for an explicit restart
and same-ID reconciliation. This is a resumable development failure path, not
the finished product's asynchronous disconnected writing policy.

Read requests, including passive snapshot/export reads, never reconcile an
outbox or execute a barrier. An explicit restarted client reconciles its pending
transaction before reaching Ready. A later explicit mutating request also
reconciles before submitting another transaction. Until a valid receipt,
neither client nor machine reports successful durability. Packet delivery is
not exactly once; retained transaction receipts deduplicate mutating effects.

Machine snapshots export authoritative observed medium bytes through passive
reads and preserve the existing backing-I/O state. Restore disconnects the
external peer and constructs the existing private POSIX backing fork. RTL
captured outcome replay operates only against that fork. The fast adapter
captures the same outcome format but its recorded-I/O replay consumer remains
unfinished in this increment. The peer adapter rejects direct
`apply_recorded`; it never contacts the original peer from replay. A native
fork must not be rebound to the original companion outbox. Remote outbox and
peer histories are external host state; raw host pointers are never serialized.

## Launch

Build in the pinned development environment, using an unused output directory:

```sh
nix develop --no-write-lock-file --command scripts/lemmasim companion \
  build --output-dir build/companion/peer
scripts/lemmasim companion init --directory build/companion/device \
  --base /absolute/path/to/an-existing-256MiB-medium.img
scripts/lemmasim companion serve --prepared build/companion/peer/prepared.json \
  --directory build/companion/device --socket /absolute/path/to/peer.sock
```

Omitting `--base` creates blank opaque bytes; it does not format a guest store.
Initialization refuses an existing directory. Imports are copies and never
modify the source medium. A separately launched client diagnostic speaks only
raw block operations (`kind operation-id cycle offset length hex-or-dash`):

```sh
scripts/lemmasim companion client --prepared build/companion/peer/prepared.json \
  --directory build/companion/device --socket /absolute/path/to/peer.sock \
  --state build/companion/client
```

After a current source-bound guest/backend has been prepared through the
ordinary build interface, a cold machine can attach. For the fast path:

```sh
scripts/lemmasim build --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --workload notebook --guest-build /absolute/path/to/current-audited-guest --opt-level O2
scripts/lemmasim session --backend qemu --profile lemma-silicon-dev/0.3.0 \
  --workload notebook --mode developer --session-dir build/companion/notebook \
  --companion build/companion/device --companion-prepared build/companion/peer/prepared.json \
  --companion-socket /absolute/path/to/peer.sock --companion-state build/companion/client
```

For a separately prepared exact RTL backend:

```sh
scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.3.0 \
  --workload notebook --mode developer --session-dir build/companion/notebook \
  --companion build/companion/device --companion-prepared build/companion/peer/prepared.json \
  --companion-socket /absolute/path/to/peer.sock --companion-state build/companion/client
```

Do not supply `--disk` or `--restore` while attaching an external peer. Cold
machines reuse the client outbox directory after the previous machine exits.
Restored snapshots use their private backing fork without a companion binding.

Raw server `--drop-reply N --exit-after-reply N` selects a completed response
ordinal; response1 is ordinarily the client startup Read. These controls do not
parse transactions, and only withhold an actual Lean response after its barrier.

## Fast shared backing state

`lemma-fast-block/2` uses the C ABI in `sim/companion/backing_c.h` to call the
same platform and outcome codec as RTL. Actual `pread`, `pwrite` and `fsync`
results replace the former boolean-only calls. Volatile controller writes stay
in its sector overlay; Flush writes those sectors in sorted order and issues a
real backing barrier before status DMA. A failed write/barrier preserves the
overlay and any observed changed backing bytes. A partial failed Read returns
IOERR and does not publish partial data into the guest buffer.

Each generation creates an exclusive `backing-N.io`: `LMIOLOG1`, exact64-byte
backend SHA256 text, then length-prefixed checksummed shared outcomes. Request
boundaries are local QEMU virtual nanoseconds; RTL logs bind target cycles.
These are distinct execution coordinates, not CPU timing parity. Zero reserved
length means an unresolved external operation, never a complete replay record.
IDs, completed cursor, last observed Write and last successful Barrier are
serialized with the controller. Host descriptors, child processes, sockets,
capture file paths and external outbox pointers are never serialized.

Snapshot/export uses passive byte reads and never reconciles an outbox or
flushes the guest medium. A restored fast candidate receives a new exclusively
owned local file containing those observed bytes, without external peer/client
binding. Validation failures affect only that disposable candidate. Pending or
ambiguous external work rejects saving instead of draining it. This is an
explicit current admission limit; arbitrary pending-operation continuation is
unfinished. Serializing backing state does not close QEMU's omitted soft-TLB
and translation-block/jump-cache state described in
`conformance/lemmasim/QEMU_STATE_EQUIVALENCE.md`.
