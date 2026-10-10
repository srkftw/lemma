# Notebook and ink records: envelope v1, page v2

This is the bounded document consumer implemented by
`Lemma/Applications/Notebook.lean`, `Lemma/Documents/Ink.lean` and
`Lemma/Ink/{Geometry,Rasterizer,Surface}.lean`. All interpretation, pixels,
serialization and editing execute in the capability-isolated User guest. The
host supplies controller input and displays the paper controller's visible RAM.
The contract does not establish physical input, timing or target acceptance.

## Authority and working memory

Boot grants are surface, input, namespace-scoped document endpoint and diagnostic
console, in slots 0–3. There is no raw block, MMIO or task-management grant.
The notebook selects namespaces 1 and 2 through the same document service.
The home tool closes the old namespace with document operation 10, then opens
the new namespace with operation 1 after pending work has drained. A missing
root creates that namespace's first page through ordinary guest transactions;
opening an unformatted or damaged medium displays read-only state instead.
Neither namespace's object IDs are interpreted in the other namespace.

The current page index is resident; other page indices and immutable ink chunks
are read in bounded 128-byte IPC transfers when a page is opened. Incoming samples
do not scan previous pages or notebook history. Rasterization touches only tiles
intersecting the current segment's bounded bounding rectangle. Editing and page
opening may scan the current page's bounded index.

Cold boot opens notebook1/page1. Other recovered pages are opened through the
same guest toolbar. Diagnostic record `0x425` names an accepted full-page
refresh: sequence, page, namespace, zero. It is emitted after streamed guest
redraw and controller command acceptance; it is not a completion or Save ACK.
Developer observations check that sequence against real controller completion.
This also permits bounded cold-navigation checks without host page selection.

| Owned virtual range | Purpose |
|---|---|
| `0x20000..0x20fff` | Existing User data page: surface metadata/tile, raw head, 64-byte raster context, notebook state and IPC packets |
| `0x110000..0x110000+ceil(width/2)*height` | Gray4 framebuffer, separately allocated whole pages |
| `0x300000..0x307fff`, `0x308000..0x30ffff` | Two 32 KiB raw ink buffers |
| `0x310000..0x317fff` | Current page index |
| `0x318000..0x31ffff` | One streamed ink chunk or immutable packed page-save snapshot |
| `0x320000..0x320fff` | Notebook root |
| `0x320200..0x3209ff` |16384-bit dirty-tile deduplication bitmap, outside the64-byte root record |
| `0x321000..0x328fff` |16384-entry bounded FIFO of16-bit dirty tile IDs, four entries per aligned64-bit word |

The notebook allocates41 working pages plus the framebuffer. For1650×2200,
the framebuffer needs 444 pages; for 1404×1872 it needs 321 pages. These fit the
Lemmasim descriptor's 1024-leaf User registry and expanded owned arena. The
existing finisher address `0x100000` is excluded. Code uses the separately
versioned LemmaSim User image layout. Exhaustion is an explicit failure, not an
instruction to discard an existing document.

Live segments paint identical brush-v1 covered pixels directly into the owned
Gray4 framebuffer. Each invocation clips to one32×32 tile; no tile staging
copy is required per sample. A dirty bitmap deduplicates its bounded tile queue.
The main loop uploads at most four queued tiles per iteration when the controller
is idle, then submits their coalesced refresh rectangle only after every pending
tile has uploaded. Input and store progress proceed between upload batches.
Completed or in-flight controller pixels remain governed by the unchanged
latched paper ABI; target uploads never substitute for refresh completion.
Page reload and edit redraw clear the dirty queue and upload the whole newly
guest-produced surface before its full refresh.

Each service turn advances one bounded save operation, then display work, then
drains at most eight queued pen records through nonblocking input operation1.
Empty is checked once. A full384-sample raw buffer is checked before another
fetch; filling that buffer, release, loss, or a toolbar action ends the drain
before a new contact begins. The pending store buffer remains immutable.
When neither save nor display/recovery work remains, the ordinary blocking
input operation2 sleeps through the existing interrupt/WFI path. The batch
bound changes guest scheduling of work, not pen ordering or device semantics.

Surface syscall64 retains operations0 geometry,1 upload,2 refresh and3 accepted
sequence. Additive operation4 returns the read-only controller status register;
its metadata and pixels arguments must both be zero. Invalid arguments return16
without reading the controller; ordinary capability authorization runs first.
Bit0 is Busy. It grants no MMIO pointer or reset authority and has no read side
effect in the controller. The kernel may reenable a previously masked source12
after this authorized query observes Interrupted8 cleared, allowing the real
completion interrupt and ACK to proceed. Its reset/completion transitions are
the paper ABI's existing ones.

Source12 is masked after one notification and wakes a waiting input consumer.
The deferred driver ACK clears completion/error bits2/4, while Interrupted8
remains masked until guest recovery completes. The notebook queries status even
when no dirty rectangle remains, restores the owned framebuffer in batches of
at most four tiles between input/store iterations, then submits one full quality
refresh. It keeps a nonblocking input/progress phase until completion clears8;
it never changes notebook records or clears8 by host intervention. A reset of
the accepted recovery refresh restarts restoration. UI state words456/464/472
hold dirty count/tail/head and480/488 hold recovery phase/cursor; word448 remains
the independently maintained issued IPC chunk length.

The maintained Developer reset control resets the whole machine, causing normal
boot and full guest redraw. A standalone idle controller reset in ABI1 has no
epoch notification and is not exposed by this control. Its caller must restore
the whole target image before subsequent incremental refreshes; retained visible
pixels are physical controller state and do not restore target RAM.

## Fixed records

All fields are aligned little-endian unsigned 64-bit words. Magic is
`0x314b4e49414d454c`. Roots and raw chunks use version 1; current page records
use version 2. Unsupported versions and malformed bounds are
rejected. The underlying record service provides lengths, checksums and durable
publication; those checksums detect corruption and do not authenticate media.

Notebook root object 1 is 64 bytes: magic, version, kind 1, page count, selected
brush width in Q8 pixels, then three reserved zero words. Page count is 1–64;
the UI selects brush widths 256, 512, 1024 and 2048 (1, 2, 4 and 8 pixels).

Page object `0x100+pageID` has an exact version-2 byte length of
`128 + chunkCount*24 + editCount*16`. Its 128-byte header contains magic,
version 2, kind 2, page ID, chunk count, edit count and edit cursor, followed
by nine reserved zero words. At offset 128 are `chunkCount` entries of three
words: immutable chunk object ID, stable stroke ID, and visible flag 0/1. At
offset `128 + chunkCount*24` are `editCount` two-word edits: operation kind and
stable stroke ID. Both counts are at most 512; the cursor is at most edit count.
Kind 1 adds
the stroke; kind 2 hides it. Undo reverses the operation before the cursor; redo
reapplies the operation at the cursor. A new edit clears the redo suffix. Hidden
raw chunks are retained. Erase hides the latest visible stroke, including every
chunk carrying that stroke ID; it is an explicit whole-stroke editing operation.

The guest reads historical version-1 pages only at their exact 20,608-byte length,
with 512 fixed entry slots at offset 128 and 512 fixed edit slots at offset 12,416.
Version selects these offsets explicitly; an unknown version is refused. The
resident page retains this fixed layout and version 1. Version-2 decoding checks
the complete active prefixes and exact length before clearing and replacing the
resident page; unused slots are zeroed and the edit cursor is preserved. Saving
copies the active prefixes into the separately owned streamed buffer, sets
version 2 there, and holds that serialized buffer immutable until the asynchronous
transaction ends. A page containing one stroke and its add operation is 168
bytes rather than 20,608 bytes. Root/chunk formats and stable object IDs do not
change, and old pages are rewritten as v2 only upon a normal acknowledged edit.

Ink object IDs exceed `0x10000` and derive from the monotonic document sequence.
An ink chunk has a 128-byte header followed by 1–384 original 72-byte pen samples
(at most 27,776 bytes total):

| Byte offset | Field |
|---:|---|
| 0, 8, 16 | Magic, format version, kind 3 |
| 24, 32 | Page ID, stable stroke ID |
| 40 | Reserved zero |
| 48, 56, 64 | Sample count, nominal brush width Q8, brush version 1 |
| 72, 80, 88 | Original coordinate maximum X/Y, pressure maximum |
| 96, 104 | Original screen width/height |
| 112 | Lifecycle: start bit 1, end bit 2, continuation bit 4 |
| 120 | Reserved zero |

Each original sample retains sequence, guest timestamp, raw X/Y, pressure,
contact/proximity/disconnect/synthetic flags, tool, buttons and device epoch.
Continuation chunks repeat the previous chunk's final sample as their first
sample, preserving interpolation across the explicit boundary. A chunk has
exactly one of Start or Continuation, with optional End: the supported values
are 1, 3, 4 and 6. An acknowledged prefix without End remains valid document
provenance; recovery never resumes an active physical contact.

Before reading a streamed body and again before rendering it, the guest checks
the 128-byte header against the current page and indexed stroke ID. Ink version 1
requires brush version 1, zero reserved words, declared sample/range/geometry
bounds, and a supported lifecycle. Unknown versions, contradictory identities
and malformed headers return error 234; they are never interpreted as brush 1.
This bounded load check does not scan notebook history on incoming pen samples.

Page coordinates use the canonical `[0,2^24]` range. X maps directly through the
recorded raw range. Y is calibrated against the recorded screen geometry, removes
the 160-pixel tool/status band and normalizes the writing area. On reopening,
the same canonical coordinates map into the current writing area. Rasterizer v1
uses integer segment distance, pressure interpolation and clipping; no floating
point ABI is involved. Gray4 is row-major, even X in the high nibble, with unused
edge nibbles white. The initial brush produces black ink; paper/background rules
and toolbar glyphs are authored guest pixels.

The rasterizer validates the eight-word segment context and then caches mapped
pixel endpoints and brush parameters in fixed-width loop arguments. It scans
the conservative segment bounds intersected with one 32×32 tile and the screen,
at most 1024 pixels. There are 16 context word reads per tile rather than context
reads for every pixel. This changes work only; brush version 1 and its covered
pixels retain their original meaning. A host-only signed-integer oracle scans
each full tile independently to compare exact Gray4 bytes and dirty counts.

## Publication and input loss

A chunk's immutable buffer is held while the service performs begin, bounded
transfers and commit. Input may proceed in the second buffer. The guest then
publishes the changed page index and notebook root as separate durable service
transactions. `Saved` and diagnostic marker `0x421` follow the final root's
acknowledgement. Previously acknowledged roots and referenced records are never
deleted by this consumer. An interruption between these publications may leave
an orphan chunk or a wholly valid unacknowledged page change; it cannot make an
earlier acknowledged publication disappear. Store checkpoint/reclamation is
requested by the Save tool and follows the store's two-segment protocol.

The guest writes the full state words SAVED, PENDING, FAILED or READ ONLY in an
authored 3×5 alphabet, together with N (namespace), P (two-digit page) and W
(brush width in pixels). The 20 cells occupy 240×16 pixels beginning at (24,132),
and status uploads cover nine tiles in the 288×32 band. This fits both queried
geometries and the application's minimum 512-pixel width. Previous/next use
literal arrow glyphs; erase/save are E/S. No host font or UI supplies these words.
A second
full buffer applies bounded backpressure instead of overwriting raw samples.
Page switches and edits wait until the outstanding save and current stroke have
settled. This implementation has 512 chunk entries and 512 edits per page, 64
pages per notebook, and the underlying service's independent object/disk limits;
limits produce explicit errors. The 16-page/100,000-sample workload fits these
representation bounds but requires its own observed end-to-end acceptance.
Changing brush width publishes its new root through the same transaction path.
Chunk admission checks the resident entry capacity before any document begin or
commit. A new stroke also checks edit capacity; a continuation reuses the first
chunk's edit. Erase checks its edit cursor before changing visibility. A redo
suffix may be replaced when the cursor still has room. Bounds are checked again
before the completed chunk mutates the resident index. Limit235 cancels the
unsaved tail, resynchronizes contact, preserves prior indexed/root bytes and the
acknowledged sequence, and keeps the guest loop alive in FAILED state with a
recovery repaint. It does not acknowledge an unindexable chunk or silently erase
an older committed stroke. Restart remains the way to reopen after this failure;
this bounded consumer has no history-compaction UI.
Guest diagnostic record `0x423` reports Pending with the expected store sequence,
page, namespace and object; `0x424` reports Save failed with its error, page,
namespace and object. Opening unformatted/damaged media also reports its error
through `0x424`, keeps the notebook read-only, and draws its diagnostic page
without invoking format. The final `0x421` carries the acknowledged sequence, page,
namespace and stroke. Checkpoint reports object/stroke zero and preserves the
logical document sequence. These bounded console observations allow Developer
mode to display guest-reported state without parsing live application memory.

An explicit device loss, epoch/sequence gap or backward timestamp cancels the
active unsaved tail. Prior published chunks remain. The guest defers a full
repaint until any asynchronous store reply has been consumed, then repaints the
current committed/indexed page. It ignores new contact while that repaint is
pending and requires a fresh contact transition afterward. It never interpolates
across the cancelled boundary. Lost pen-up and disconnection are also represented
by the controller's explicit loss boundary and watchdog policy.

Paper refresh is coalesced. Busy status 171 retains the dirty rectangle for a
later retry; it does not terminate live ink. Visible pixels change only on the
paper device's completion. Marker `0x420` reports guest page readiness and the
accepted refresh sequence; the marker alone is not evidence that the panel has
completed that refresh. Initializer argument 1 alone requests explicit service
formatting and emits `0x41f` after its durable acknowledgement. Normal argument 0
never formats an unknown or unformatted image.
