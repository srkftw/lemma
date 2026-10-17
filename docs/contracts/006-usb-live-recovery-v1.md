<!--
# Native live USB recovery v1

`lemma-usb-live-recovery/1` is an explicitly selected native execution scope for
the unchanged Clocked13 circuitry/Kernel6 aperture. Historical options,
container10, `LMUSBRW2` captures and `LMUSBRP1` replay keep their layouts and
semantics. A native manifest must explicitly admit this control contract; an
old prepared binary cannot inherit it. This scope is not full USB conformance,
guest journal recovery, authentication or a completed reconnect/Save claim.

`--usb-recovery` selects container11, `LMUSBRW3` capture and `LMUSBRP2` replay.
Container11 adds the recovery marker, monotonically increasing connection
epoch and a64-character namespace digest to the existing complete Clocked
USB state. The digest binds the validated Pending policy4 manifest/binary,
writer, capacity, original peer/socket/outbox paths and raw-I/O helper identity.
It intentionally excludes changing peer/outbox contents. It names ownership
and replay context; it is not an authentication credential or proof of trust.
Normal target protocol validation remains necessary.

Initial attachment is epoch1. Explicit reconnect requires a paused original
Developer/Laboratory owner, terminal transport, empty raw queues, no retained
command/handshake, a completed controller period and a reaped old child. The
request names the next epoch, unchanged next global raw-command ID and exact
namespace digest. Stale, duplicate, changed-namespace and restored-owner
requests reject before capture or process effects. No new argv/peer namespace
is accepted. The replacement process uses the original executable/arguments;
the raw transport assigns its first command the retained global ID. Frames and
peer transaction/writer sequences are unchanged.

An accepted attach is a raw row `CYCLE 3 EPOCH ATTACH NEXT_ID DIGEST`.
Capture flush and its actual filesystem barrier complete before a replacement
process starts. The logical attach does not advance a clock or set connected,
configured, authenticated, receipt or Saved state. Polling resumes at the next
strict1000-clock boundary. Real generated PHY reset, endpoint0 setup/status
transactions and the genuine hosted Lean policy establish the new connection.
Process-creation failure produces a captured disconnect; it does not roll back
the accepted epoch. A capture/barrier failure leaves an ambiguous artifact and
forbids further run, reconnect, restore, snapshot and tape publication on that
owner. Inspection/destruction remain available; no backing rollback is claimed.

Tape3 permits a new attach only after a recorded terminal disconnect, with the
exact next epoch/global request ID/binding. It retains request/reply bytes and
ordering, a completed-cycle horizon and checksum. Its horizon checksum uses
tag4, separate from the historical tag3 horizon. A just-admitted zero-clock
attach (or its immediate creation failure) may occur at the published horizon;
all ordinary device rows precede it. This records an observed boundary without
polling or draining the peer. Snapshot/export do not advance the guest or
complete pending work.

Restored forks retain logical epoch/namespace state, private backing and the
accepted cursor. They never spawn, poll or recontact an original process.
Only a completely validated tape can resume them, applying attach/disconnect
events at their recorded boundaries before ordinary circuitry clocks. Pending
work and every generated PHY/FIFO/controller state remain retained. Missing
tape, corrupt/incompatible schema, wrong prefix/epoch/binding or a requested
interval beyond its horizon reject without altering the live destination.
Generic session input replay rejects live reconnect requests; raw USB outcome
replay is the admitted continuation path. This is same-backend recorded
continuation, separate from cold recovery or QEMU cached-state migration.

The public control is `session-control --request
'{"action":"usb-reconnect","epoch":E,"next_request":N,"binding":"DIGEST"}'`.
The explicit native launch flag requires exact policy4 and persistent peer and
outbox arguments, or an isolated container11 restore with its recorded tape.
Guest quarantine/receipt reconciliation and shadow journal remount must finish
before any new write or Saved acknowledgement. A transport attach alone never
releases guest poison/read-only state or manufactures an acknowledged commit.

Implementation/qualification receipts remain separate. The focused Python
admission tests exercise operator/source/namespace/epoch guards without a CPU
or peer. Actual native circuit, guest reconnect, uncertain-write reconciliation,
offline ink and acknowledged Save/cold results require their own observations.
The browser has no live process adapter for this scope; its existing canonical
machine and previously qualified Clocked captured suffixes retain their claims.

The first qualified native implementation is64d7d234d5fe35401de2ebfb4e2b2e5cd3699ff7451cdbbd0c992c1b5c525962.
[Its separate receipt](../evidence/006-usb-live-recovery.json) records real process
EOF, three complete exact private suffixes, eight checksum-correct state/tape
rejections with unchanged authoritative archives, and actual prepared public
control through genuine policy4. The public owner accepts epoch2 atcycle4000
without advancing time, then receives the new process's real5M-clock reset with
global nextrequest5 atcycle7000. Peer/outbox bytes remain unchanged; configured,
receipt reconciliation and a successful guest retry are not inferred.
The pinned full host suite passes270 tests/57.938s. Earlier missing-tool,
preflight implementation and observer failures are retained in that receipt.

-->
