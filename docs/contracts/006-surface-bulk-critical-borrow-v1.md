<!--
# Same-critical-section Surface bulk transport v1

`lemma-surface-bulk-critical-borrow-v1` is an implementation successor inside
the existing Kernel4/Surface2/Paper1 transport. It changes no User profile,
capability, mathematical authority, durable format, device contract or ISA.
All target algorithms remain ordinary elaborated Lean Actions, erased through
checked CFG/LLVM lowering. The historical independently admitting capability,
copy and Paper entrypoints remain available with their original bodies.

The selected `NotebookKernel.dispatchBulk` syscall path uses the descriptor
base returned by the immediately preceding `Task.capture`. Capture first
validates the hardware frame, current process, owned stack, descriptor, table
and registry identities; it copies36 words only into descriptor offsets
2048..2335 and checks live task state and saved translation. PC alignment and
the full permission/PTE/owner/generation/purpose/pin/mapping-duplicate lookup
still run. Capability type, active header, entry state/serial, object identity,
kind and rights are checked afresh. Only repeated structural descriptor reads
are borrowed; no descriptor authority survives the nonpreemptible Action.

Surface op5 retains reserved-before-capability precedence, count1..7,
page-aligned pointer, scratch-handle lookup and current-descriptor alias
rejection. UserCopy retains scratch owner1/purpose1/generation and span checks,
range/request precedence, complete user-leaf preflight before the first write,
and the original ordered physical copy. A fresh scratch resolve after copying
still precedes packet version2/count/reserved/geometry checks. All tiles are
validated before the first upload. Each tile keeps its shape/span guards,
five controller fields, every ordered read64 then fenced PIO write64, command
and controller error read. A controller failure reports the completed tile
prefix; it cannot execute a later tile.

The borrowed descriptor header/registry, capability entries, frame records and
configuration are disjoint from capture's saved context, UserCopy's scratch
frame and paper staging registers. Checked user leaves have their address-space
owner and cannot alias the owner1 scratch frame. A current-generation scratch
handle cannot name the same frame as the descriptor while differing from its
handle: stale-generation resolution fails before copying. The kernel performs
no allocation/release, mapping, grant/revoke, scheduling or metadata write
inside the borrow. DMA buffers are separately owned live frames; this Surface
path never submits block DMA. Pending DMA and paper output cannot write the
borrowed descriptor/capability/frame metadata. These are private call-chain
obligations, checked against actual source and emitted bodies, rather than a
cache across syscalls. Syscall reply and scheduling occur after the borrow.

The Paper successor groups eight consecutive word pairs in one bounded step,
followed by zero to seven tail words. At most eight blocks and seven tail
callbacks execute. Local pool/alignment/staging guards expose bounded addresses
to LLVM. No physical read, device write, I/O fence, command or error check is
removed or reordered by grouping; partial widths and rounded final words retain
the original bytes and controller length. The full32x32 tile changes64 paper
callbacks to8. The private helper rejects addresses outside its bounded pool
and staging spans and is never a User export.

The checked physical boundary first checks alignment and its fixed authority
interval before a volatile load/store. Its ordinary recoverable errors include
out-of-bounds7, misaligned8 and write-denied5; these guards remain in lowering.
A real architectural access fault is a trap, not a fabricated checked success
or a newly synthesized Action status. The path promises no successful return
or cleanup after such a global fault. Controlled finite tests also propagate
injected checked statuses7/8/9/95/255 and non-returning faults at retained
accesses, preserving their prefix. Those tests do not establish a temporal RAM
fault contract: removing duplicate reads deliberately does not preserve a
transient fault that first arises only at a removed read. Stable address faults
are observed at the retained initial checks, and disjoint intervening writes
cannot introduce descriptor or frame corruption during the borrow.

`SurfaceBulkBorrow.lean` compares the actual old private device callback and
prior ordinary upload body against the maintained successor in finite byte RAM
with an independent literal PIO oracle. It requires equal results, full RAM,
controller command prefixes and every retained request/value/status in order;
only independently recorded successful AS/frame read blocks may be projected.
Its natural-offset proofs establish the saved-context/header/loader/capability
layout separation, not compiler or whole-kernel correctness. The direct Paper
comparison projects no accesses and checks1156 shapes, legal/invalid offsets,
pool edges, and every word/error/global-fault prefix in representative block and
tail shapes. The full dispatcher tests ownership, generation, stack canaries,
PTE/permission/capability/alias/range/status and partial copy/PIO failures in
both original and expanded pools. `SurfaceBulkBorrowLower.lean` checks genuine
Kernel4 source closures and emits complete LLVM for O2/RV64 object inspection;
the old Kernel1/2 and User1/7 profiles reject this physical/device code.

The metadata-only checkpoint measured2421→2324 primitive requests in the
legacy pool and2729→2464 in the expanded fixture: exactly three full-AS read
blocks plus seven repeated frame-resolve blocks disappear. Grouping preserves
that primitive count and additionally removes392 paper callbacks per seven-tile
batch. These are component observations. Fresh whole-image audit, actual guest
cycles, canonical full-frame completion and connected Save/cold workflow require
separate evidence. The earlier native500M incomplete-boot FAIL and browser
713.85M Ready PASS retain their original target/runtime identities and bounds.

-->
