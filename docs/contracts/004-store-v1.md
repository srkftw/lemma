# Guest record store v1

Status: compiled Lean production library, separately linked service source and
asynchronous IPC client, with focused host Action/format checks. The source has
passed genuine Core0 elaboration and LLVM lowering. Linked kernel/block/IPC
execution and cold RV64 notebook acceptance require their own observed results.
This contract freezes the disk format. It does not certify durability of a host
backend or physical medium. Implementation is `Lemma/Services/Store/`.

The reusable library supports namespace-scoped create/open (catalog records), object
replacement/append, lookup, enumerate, bounded read, deletion tombstones,
checkpoint and close. Create/open/close authority and IPC session handles belong
to the capability wrapper; they are not supplied by the disk format. An ordinary
client receives document records, never an index address, raw-block capability,
DMA pointer or service memory. `Server` authenticates the kernel-stamped sender
for staging ownership and admits namespaces 1 and 2 through a document endpoint
whose Call grants authorize those two namespaces. This is one authority domain;
the namespace field is not an authentication token. No isolation result is
inferred from scalar namespace keys or from compilation alone.

Every original stroke is a stable object. Later replacement records for a page
edit summary or catalog supersede the same namespace/object pair. Deletion is
kind2 with zero payload; its latest tombstone is retained by checkpoint. Thus
checkpoint reclaims obsolete object revisions while retaining independent raw
stroke objects. This is a record store, not a POSIX filesystem. A consumer that
uses a different object for every revision cannot expect reclamation to remove
those records. Limits are explicit: 1024 latest object keys in the current memory
index, 32768 bytes per transaction, one outstanding transaction. Exhaustion
rejects before affecting the active committed root. These memory-index limits
are implementation bounds; changing them does not change the disk encoding.

All sectors are 512 bytes. All fields below are aligned little-endian u64.
Every reserved byte is zero. FNV-1a64 uses offset `cbf29ce484222325` and prime
`100000001b3`, modulo 2^64, over the specified serialized bytes. It detects
ordinary corruption; it is neither authentication nor a proof against arbitrary
malicious media. Sequence/generation exhaustion at `7fffffffffffffff` rejects.

| Sector | Meaning |
| --- | --- |
| 0, 1 | Independently validated root publication slots |
| 2–7 | Reserved; no guest record data |
| 8 onward | Two segments, each `floor((capacitySectors-8)/2)` sectors |

Root fields are magic `0031544f4f524d4c` at0, version1 at8, generation16,
actual capacity24, segment number32, start sector40, segment length48,
checkpoint record count56, checkpoint tail in relative sectors64, and global
sequence72. Checksum80 covers bytes0..79; its bitwise inverse is88; remaining
416 bytes are zero. Start/length must agree with actual negotiated disk capacity.
The root's checkpoint sequence is the global sequence at the switch. Checkpoint
records may have older sequence numbers in index order. Exactly the declared
count must validate and terminate at the declared tail. Subsequent appends must
increase sequence by exactly one. Equal-generation roots must agree exactly;
contradiction is a failure. The greatest valid generation is selected.

Record header fields are magic `0000314345524d4c` at0, version1 at8,
segment generation16, namespace24, object32, transaction40, sequence48,
payload length56, kind64 (1 replacement, 2 tombstone), payload-sector count72,
payload checksum80, header checksum88, inverse96; remaining408 bytes are zero.
The header checksum covers bytes0..87. Length is bounded before any sector
address or loop count is derived. Payload follows in `ceil(length/512)` sectors;
the last sector is zero padded. Its checksum covers only the declared payload.
The publication sector follows the payload. Its fields0..64 match the header
except magic is `003154494d434d4c`; at72 is payload checksum,80 is header
checksum,88 is checksum over bytes0..87,96 inverse, and408 reserved zero bytes.

The append protocol is strict and serial:

1. Validate key, bounds, active state and index capacity; compute the payload
   checksum in guest code. Retain the immutable payload span until completion.
2. Write header and all body sectors; write a zero sentinel at the next tail.
3. Complete a real negotiated block flush.
4. Write the matching publication sector.
5. Complete a second real negotiated block flush.
6. Publish the in-memory latest index and acknowledged sequence; only then reply
   success to the client. `Saved` must identify that acknowledged sequence.

Checkpoint writes current latest objects to the inactive segment with the new
generation, using real sector reads/writes. It recomputes/verifies payload hashes
and builds new headers/publications in compiled Lean. A zero tail sentinel is
written and the entire replacement segment is flushed. Then the inactive root
slot is written and flushed. Only after that flush does the active index/root
switch. The prior segment/root remain intact throughout the switch. Reusing an
older segment on the following checkpoint is safe because the current root slot
is not the slot being rewritten. A failed checkpoint never authorizes release of
DMA pages; quiescence remains the block adapter's responsibility.

The admitted crash model discards volatile writes and can tear an in-flight
sector write or fail a flush. Previously flushed sectors are retained except
the sector currently being rewritten. No claim covers arbitrary later corruption
of previously stable sectors. A cut before publication/final flush may omit the
pending transaction; if all its bytes reached stable media it may recover wholly.
An incomplete append header/body/publication ends the uncommitted suffix. A
damaged declared checkpoint is a mount failure, never an empty-store fallback.
Unknown mandatory versions reject. Duplicate/stale object revisions and
contradictory roots reject. A transport error latches read-only/failed state.
Recovery runs once at mount and rebuilds the latest-object index; ordinary
samples perform no journal scan. Append work is O(payload) plus bounded hash
index lookup. Checkpoint scans the bounded latest index, not every old revision.

Mount does not format. `formatStart` is an explicit destructive initialization
entry for a verified new/empty image or separately authorized erase. Both absent
or damaged roots are never permission to initialize. A launcher must distinguish
its empty-image recipe from a failed mount and preserve a nonempty failed image.

The reusable guest adapter interface is `Engine.mountStart(context, buffer,
index, capacity)`, `appendStart(context, namespace, object, transaction,
payload, bytes, kind)`, `checkpointStart(context, alternateIndex)`,
`readStart(context, namespace, object, offset, count, output)`, `lookup`,
`enumerate`, and `complete(context, status)`. Context is4096 bytes; transport
buffer512; each index49152 bytes. Complete spans must be preflighted and mapped
to service-owned memory before entry. No span overlap is permitted. Read output
is preflighted completely before the first copy. The block adapter must retain
its kernel-owned bounce pins until DMA completion or actual reset/quiescence.

| Context offset | Field |
| --- | --- |
| 0 | Requested operation:0 idle,1 read,2 write,3 flush |
| 8,16,24 | Phase, sector, private buffer virtual address |
| 32,40 | Last terminal status, acknowledged global sequence |
| 48..104 | Capacity, generation, segment, start, length, tail, sequence, index |
| 112..208 | Private pending record/payload/checksum state |
| 216..248 | Recovery count/tail and active publication slot |
| 256..328 | Private checkpoint destination/cursor/copy state |
| 336 | Failure/read-only latch |
| 344..368 | Bounded read cursor and expected indexed sequence |
| 512,576 | Two private validated root candidates |
| 1024..1535 | Private expected-publication sector |

Phase16 header write,17 body write,18 sentinel write,19 payload flush,20
publication write,21 final flush. Checkpoint phases32..40 cover source header,
target header, body read/write, publication, sentinel, segment flush, root write,
root flush. Format64..69 covers sentinel flush and both root writes/flushes.
Mount1..5 covers roots/header/body/publication. Read80..81 covers header/body.
The adapter executes exactly one matching request, then invokes `complete` once.
Status0 on flush means actual flush completion, never merely queued work.
Calling completion without an outstanding request fails. Fields are service
private; a client cannot forge them. The engine does not sleep/spin itself:
the IPC/block worker waits for device completion and clients retain pending
state while the UI continues. The initial worker uses a bounded guest timer
sleep of 10000 ticks between asynchronous completion probes. This is a temporary
completion wait adapter, not a host sleep or a declaration of event blocking.

The service receives raw-block authority in boot slot 0 and document endpoint
Receive authority in boot slot 1. It allocates 34 private pages for its context,
sector buffer, two 1024-row indexes and one 32 KiB staging payload. Those pages
must be included in the deployment's real quota and user mapping capacity.
The kernel block bridge accepts only private sector spans and owns pinned DMA
bounces. Syscall 66 supplies capacity, sector read/write, flush and completion;
accepted work returns 168 until actual completion. Application death does not
make a queued write durable or release a writable DMA frame.

The document message payload is bounded by the existing 256-byte IPC packet:
a 64-byte kernel IPC envelope, the following 64-byte application header, and at
most 128 bytes of chunk data. Each header field is little-endian aligned u64.
Magic is `31525453414d454c`, version is 1. The eight fields at offsets 0 through
56 are magic, version, operation, namespace, object, transaction, offset, count.
The sender and reply handle come from the kernel envelope, never that header.

| Operation | Request semantics |
| --- | --- |
| 1 | Open namespace; returns mount mode and acknowledged sequence |
| 2 | Begin replacement with nonzero object/transaction and desired length ≤ 32768 |
| 3 | Stage at most 128 bytes at exactly the next offset, for the same sender/key/transaction |
| 4 | Commit the complete staged replacement; reply follows final flush |
| 5 | Read at most 128 bytes of an object at an offset; short read/EOF is explicit |
| 6 | Commit a zero-payload tombstone with nonzero object/transaction |
| 7 | Checkpoint current latest objects; reply follows root publication flush |
| 8 | Inspect acknowledged sequence and mount mode |
| 9 | Cancel an uncommitted staging buffer owned by the same sender/key/transaction |
| 10 | Close only when the shared staging slot is free |
| 11 | Explicit format; requires launch boot argument 1 and unformatted mode |

Operations 1, 7, 8 and 10 have object/transaction/offset/count zero. Operation
11 also has namespace zero; all other requests admit only namespaces 1 or 2.
Catalog creation is an ordinary versioned replacement record, rather than a
kernel notebook operation. Enumeration is a reusable library entry and is not
yet a document-endpoint message. A notebook may use its own indexed catalog
objects without rescanning history. Unknown operations and malformed framing
reject before document or staging changes.

Replies repeat operation/namespace/object, put the actual acknowledged global
sequence in the transaction field, and put actual read length in count. Read
length may be less than the offered count; offset equal to object length returns
zero, and offset beyond it rejects without making other clients read-only.
Malformed media headers and actual transport errors still latch failure. Other
successful replies have count zero.
Detail is mount mode (0 mounting, 1 ready, 2 no validated root, 3 failed) or the
next staging offset. Error replies have no data. Application statuses 220–230
are format/engine failures; 231 is staging busy, 232 wrong staging owner, and
233 incomplete replacement. Packet length must exactly agree with count.

Only one immutable payload and one transaction are outstanding. An abandoned
uncommitted stage expires after ten guest seconds; this releases no DMA pins,
committed record or acknowledged sequence. During I/O the service retains the
reply capability and does not receive another document command. Other tasks,
including the notebook's input loop, remain scheduled. `Client.beginCall` plus
`pollCall` supports that loop: additive syscall 67 returns IPC `wouldBlock` 12
with zero bytes without consuming a transaction, or returns a completely
validated reply. `waitCall` uses the existing blocking ABI.

Normal launch argument 0 forbids format. Argument 1 is permitted only for the
launcher's verified-empty image recipe or an explicit destructive operation;
no-root status alone does not prove an empty disk. A failed nonempty mount never
becomes a successful format. The launcher and capability deployment remain
separate checks from the codec's host oracle.

Focused checks use the actual elaborated Action declarations in a host-only
memory/sector effect harness and export durable disk bytes. A separately written
Python observer parses those bytes without calling the production recovery code.
These checks are distinct from LLVM/RV64 object closure and actual kernel-device
execution. Run identities and retained reports must keep that distinction.
