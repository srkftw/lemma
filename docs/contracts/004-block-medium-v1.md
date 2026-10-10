# LemmaSim stable/volatile block medium v1

Backend identity is `lemma-durable/1`. It is host-only hardware code in
[lemma_durable.c](../../sim/host/lemma_durable.c), integrated into the separately
built pinned QEMU. It sees sector bytes and transport requests; it does not parse
guest records, transactions, namespaces, strokes or notebook state. Guest store
authorization and recovery remain in compiled Lean.

The normal graph is `VirtIO block → blkreplay when recording/replaying →
lemma-durable → raw → local file`. The local file is the stable-media image.
Every node must permit real flushes; the filter rejects `cache.no-flush` and
nonlocal/nonraw backing graphs. Successful QEMU host flush must mean the host
filesystem and storage device honor the requested durability barrier. This is a
host-storage assumption, not a physical power-loss measurement of that machine.

A completed ordinary write replaces only the filter's volatile RAM sectors.
Reads return those pending sectors over stable bytes. Killing the process loses
that overlay even if the host page cache survives; unflushed guest writes have
never reached the host image. Default pending capacity is32768 sectors/16MiB;
the configurable bound is1..262144 sectors. Requests must be aligned whole512-byte
sectors,1..65536bytes. Capacity for the entire write is preflighted before changes;
exhaustion returns an error and preserves existing pending and stable bytes.

One coroutine mutex serializes reads, writes and flush publication. Flush freezes
the overlay, writes its sectors in ascending sector order through QEMU's child
block path, and waits for a successful child flush/fsync. Only then does it clear
pending RAM, advance `durable_flush`, and return success. FUA is not claimed by
this filter; the block layer supplies the corresponding flush. A guest document
acknowledgement still requires the store's payload flush and publication flush.
The backend's durable-flush counter is not a document sequence.
The bound VirtIO block device explicitly uses `werror=report,rerror=report`:
its inherited ENOSPC policy must not stop the machine and hide a failed request
from the guest.

Laboratory options use exact1-based request ordinals; zero disables a fault:

| Option | Device-level behavior |
| --- | --- |
|`fail-write=N`|writeN fails before volatile mutation|
|`fail-flush=N`|flushN fails before any child write|
|`cut-before-flush=N`|discard process/RAM immediately before flushN writes|
|`cut-after-flush=N`|cut after durable child flushN, before VirtIO completion|
|`tear-flush=N`|write first dirty sector as first256new/last256old bytes, flush that mixed sector, then cut|
|`delay-after-ns=T`, `delay-write-ns=D`|one-shot first valid write beginning at/after virtual timeT waitsD before reading its data iovec or completing; no sector/content selection|

The optional write-delay policy is `virtual-one-shot-write-delay/1`; both fields
default0 (disabled). Duration is1..10000000000ns, threshold0..3600000000000ns.
A nonzero threshold requires a duration. The frontend admits these options only
in Laboratory mode and binds them in run/replay `fault_inputs`. This uses QEMU's
virtual-clock coroutine timer; actual completion occurs at/after its recorded
deadline and may reflect event-dispatch granularity. The request and its DMA
iovec remain live across the wait. Normal reference runs receive no delay.
Trace `write-delay-begin`/`write-delay-end` retain actual virtual timestamps,
offset and byte count. Read-only `delayed_write` state exposes active/used,
request ordinal, offset, bytes and deadline. QEMU drain (pause/reset/close) wakes
the delay early and records `write-delay-drained`; that interval cannot establish
the full-delay client-death observation. A whole-process power cut drops it.

A tear requested with no dirty sector reports an explicit error. Power cuts exit86
without QEMU cleanup, so they cannot silently flush pending data. Other child
I/O/flush errors propagate; the store must keep its last acknowledged sequence
and expose failure. The journal protocol decides which prior publication remains
valid; this filter never deletes or selects notebook records. A normal QMP quit
can invoke QEMU's close-time flush, so it is a clean host shutdown, not a laboratory
power cut. QMP `stop`/Developer pause also drains the QEMU block graph and may
flush pending writes before reporting paused. It is an inspection boundary,
not a physical power-loss operation. Unacknowledged transactions may consequently
recover wholly. A Laboratory whole-process cut must run without a preceding
pause, quit, reset or cleanup flush when testing loss of volatile sectors.

An optional new `trace-file` records virtual-time hardware write/flush/fault
observations. QOM `storage-state` on `/machine/lemma-hardware` exposes
pending-sector capacity/count, request counters and last successful durable flush.
It does not invent the guest's committed/pending document sequence. The reference
launch has one medium, one VirtIO queue and no I/O thread. Above the filter,
pinned QEMU `blkreplay` records completion-BH ordering. Native input uses QEMU's
record/replay input path; external raw files and fault options are separately
bound inputs. A cut can truncate the QEMU replay log and must be diagnosed as an
incomplete replay session, rather than presented as successful exact replay.
The pinned replay launch uses `shift=3,align=off,sleep=on`; disabling sleep in
this revision bypasses its asynchronous-event processing and is not admitted.
Internal filter timestamps precede `blkreplay` completion publication: compare
their ordered operation/sector observations separately from the guest-visible
completion and commit boundary when an in-flight host flush spans that boundary.

[check_qemu_medium.py](../../sim/host/check_qemu_medium.py) independently builds
literal VirtIO1.2 split-ring requests in a hardware-only qtest machine and observes
stable bytes, volatile readback, flush, failed flush, before/after cuts, torn
sectors and exhaustion. It shares no production transition or journal oracle.
These hardware observations are distinct from the compiled guest notebook's
cold-recovery and acknowledgement acceptance.
