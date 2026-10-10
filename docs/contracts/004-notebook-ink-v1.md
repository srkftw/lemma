# Notebook and ink records v1

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
Neither namespace's object IDs are interpreted in the other namespace.

The current page index is resident; other page indices and immutable ink chunks
are read in bounded 128-byte IPC transfers when a page is opened. Incoming samples
do not scan previous pages or notebook history. Rasterization touches only tiles
intersecting the current segment's bounded bounding rectangle. Editing and page
opening may scan the current page's bounded index.

| Owned virtual range | Purpose |
|---|---|
| `0x20000..0x20fff` | Existing User data page: surface metadata/tile, raw head, 64-byte raster context, notebook state and IPC packets |
| `0x110000..0x110000+ceil(width/2)*height` | Gray4 framebuffer, separately allocated whole pages |
| `0x300000..0x307fff`, `0x308000..0x30ffff` | Two 32 KiB raw ink buffers |
| `0x310000..0x317fff` | Current page index |
| `0x318000..0x31ffff` | One streamed ink chunk |
| `0x320000..0x320fff` | Notebook root |

The notebook allocates 33 working pages plus the framebuffer. For 1650×2200,
the framebuffer needs 444 pages; for 1404×1872 it needs 321 pages. These fit the
Lemmasim descriptor's 1024-leaf User registry and expanded owned arena. The
existing finisher address `0x100000` is excluded. Code uses the separately
versioned LemmaSim User image layout. Exhaustion is an explicit failure, not an
instruction to discard an existing document.

## Fixed records

All fields are aligned little-endian unsigned 64-bit words. Magic is
`0x314b4e49414d454c`, version is 1. Unsupported versions and malformed bounds are
rejected. The underlying record service provides lengths, checksums and durable
publication; those checksums detect corruption and do not authenticate media.

Notebook root object 1 is 64 bytes: magic, version, kind 1, page count, selected
brush width in Q8 pixels, then three reserved zero words. Page count is 1–64;
the UI selects brush widths 256, 512, 1024 and 2048 (1, 2, 4 and 8 pixels).

Page object `0x100+pageID` is exactly 20,608 bytes. Its 128-byte header contains
magic, version, kind 2, page ID, chunk count, edit count and edit cursor, followed
by reserved zero words. At offset 128 are 512 entries of three words:
immutable chunk object ID, stable stroke ID, and visible flag 0/1. At offset
12,416 are 512 two-word edits: operation kind and stable stroke ID. Kind 1 adds
the stroke; kind 2 hides it. Undo reverses the operation before the cursor; redo
reapplies the operation at the cursor. A new edit clears the redo suffix. Hidden
raw chunks are retained. Erase hides the latest visible stroke, including every
chunk carrying that stroke ID; it is an explicit whole-stroke editing operation.

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
sample, preserving interpolation across the explicit boundary. The lifecycle is
document provenance; recovery never resumes an active physical contact.

Page coordinates use the canonical `[0,2^24]` range. X maps directly through the
recorded raw range. Y is calibrated against the recorded screen geometry, removes
the 160-pixel tool/status band and normalizes the writing area. On reopening,
the same canonical coordinates map into the current writing area. Rasterizer v1
uses integer segment distance, pressure interpolation and clipping; no floating
point ABI is involved. Gray4 is row-major, even X in the high nibble, with unused
edge nibbles white. The initial brush produces black ink; paper/background rules
and toolbar glyphs are authored guest pixels.

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

The displayed S/P/F/R state means Saved/Pending/Save failed/Read-only. A second
full buffer applies bounded backpressure instead of overwriting raw samples.
Page switches and edits wait until the outstanding save and current stroke have
settled. This implementation has 512 chunk entries and 512 edits per page, 64
pages per notebook, and the underlying service's independent object/disk limits;
limits produce explicit errors. The 16-page/100,000-sample workload fits these
representation bounds but requires its own observed end-to-end acceptance.

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
