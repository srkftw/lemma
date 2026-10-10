# Guest record store v1

Status: compiled Lean production library and focused host Action/format checks;
kernel block/IPC integration and cold RV64 notebook acceptance are pending.
This contract freezes the disk format. It does not certify durability of a host
backend or physical medium. Implementation is `Lemma/Services/Store/`.

The service protocol requires namespace-scoped create/open (catalog records), object
replacement/append, lookup, enumerate, bounded read, deletion tombstones,
checkpoint and close. Create/open/close authority and IPC session handles belong
to the capability wrapper; they are not supplied by the disk format. An ordinary
client receives document records, never an index address, raw-block capability,
DMA pointer or service memory. The wrapper must authenticate the kernel-stamped
sender and granted namespace before invoking the library. That wrapper is not
yet implemented. No isolation result is inferred from scalar namespace keys.

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
the IPC/block worker blocks for device completion and clients retain pending
state while the UI continues. No daemon/task integration is claimed yet.

Focused checks use the actual elaborated Action declarations in a host-only
memory/sector effect harness and export durable disk bytes. A separately written
Python observer parses those bytes without calling the production recovery code.
These checks are distinct from LLVM/RV64 object closure and actual kernel-device
execution. Run identities and retained reports must keep that distinction.
