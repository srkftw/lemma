<!--
# Companion acknowledged-boundary archive

`archive_companion_boundary.py` passively reads the opaque peer base, append
log and atomic client outbox. It never asks either running process to pause,
flush, drain, reconcile or report status. The base remains immutable; the exact
checksummed append-log prefix contains both the bytes and retained transaction
receipts. A qualified outbox contains no pending frame, and its next sequence
must equal the peer prefix high-water plus one for the same writer.

The tool permits three observations within 30 seconds. Each attempt records
regular-file identities before copying, then compares device/inode/length/
mtime/ctime and the metadata/log/outbox contents afterward. A partial journal,
pending outbox, different writer/sequence or additional unacknowledged effect
rejects. The expected mutation prefix is independently bound to an actual
qualified native USB8 raw-outcome suffix and its guest Saved receipt. Native
packet/control/CRC/toggle decoding retains its checks; the initial hello
sequence is an explicit positive UInt64 parameter, defaulting to the original
sequence one for historical callers.

An explicit `--reference-workflow` alternative binds the final Saved11
workflow. It requires the independently corrected frozen wire observation,
exact four-object journal, initial six-effect receipt prefix, next sequence
seven, and final high-water 72 with no pending outbox. Materialized bytes must
equal the actual acknowledged artifact. This alternative does not relax the
existing Saved5 suffix path or convert the retained original observer FAIL.

Only privately copied artifacts receive file and directory barriers. An
offline observer may materialize opaque sectors for comparison; it never
repairs records or supplies recovered state to the guest. A current passive
archive is its own boundary. Matching an earlier accepted prefix does not make
it a machine snapshot at that earlier cycle.

The cold checker starts a new CPU and independently running peer from the
frozen archive with hosted USB policy4. It supplies no machine restore state.
Its original resource ceilings are 1.6 billion target cycles and 7200 seconds
for cold Ready, plus a separately declared 200 seconds for process startup and
cleanup. The detached supervisor records an absolute deadline, performs no
automatic restart, preserves cancellation and reaps owned children. Complete
controller pixels, all acknowledged opaque bytes and retained peer receipt
state must match; recovery must neither format nor issue a replacement Save.
The first cold qualification is recorded separately from the archive and is
not established by successful host archive tests.

The first actual policy4 cold run passed at 680 million target cycles and
4353.814 seconds, with all controller pixels, opaque bytes and peer receipts
unchanged. It executed the observer at commit `b400f8f`; the receipt records
that exact observer hash. Subsequent public input validation additionally
requires all six authoritative files, canonical non-symbolic paths, bounded
sizes and exact hashes before copying or starting an actor. The strengthened
guard passes against the same frozen archive and rejects missing/extra inputs,
symbolic parents, invalid sizes and capacity mismatch. These guard checks are
host checks, not a second cold guest run.

The final actual USB8 workflow completed ink, lost-ACK reconciliation, Undo,
Redo, next/previous page and explicit Saved11. Its original whole report
remains FAIL because the terminal wire observer assumed initial sequence one.
The initial peer/outbox independently establish sequence seven. A separate
frozen wire observation passes without executing another CPU. Its first
attempt also remains FAIL: the independent object oracle was corrected from
the consumed Notebook source, which writes page1 at sequence8 and page2 at
sequence10 before root11; previous-page loading and explicit flushing create
no additional page records.

A new CPU then cold-recovered this current final boundary at 735 million
target cycles and 3536.545 seconds. Every controller pixel and acknowledged
byte matched, 42 opaque reads produced no new write or barrier, and the peer
receipt log stayed unchanged. The original 1.6B/7200-second ceiling applied.
The obsolete prepared-host selection failed before execution in the retained
first attempt; the successful run uses the unchanged qualified policy4-a3
host closure. This is a Saved11 cold recovery, separate from the earlier
Saved5 cold result and all machine snapshot continuation checks.

Commands for the qualified artifact shapes (use unused output directories):

```sh
python3 scripts/archive_companion_boundary.py \
  --peer build/usb/usb8-acknowledged-boundary-a1/peer \
  --outbox build/usb/usb8-acknowledged-boundary-a1/outbox \
  --initial-peer build/usb/store-initialize-a3/peer \
  --reference-suffix build/usb/usb8-success-private-suffix-a1/result.json \
  --saved-sequence 5 --high-water 36 \
  --output build/usb/acknowledged-boundary-NEW
python3 scripts/check_usb_cold_boundary.py launch \
  --boundary build/usb/acknowledged-boundary-NEW \
  --host-prepared build/usb/host-pending-policy4-a3/prepared.json \
  --native-bundle build/native/task006-usb-next-a1 \
  --work-dir build/usb/acknowledged-cold-NEW
```

The final acknowledged artifact uses its own declared sequence/high-water:

```sh
python3 scripts/observe_usb_workflow_wire.py \
  --workflow build/usb/notebook-next-workflow-a2 \
  --initial-peer build/usb/store-initialize-a3/peer \
  --initial-outbox build/usb/store-initialize-a3/outbox \
  --native-bundle build/native/task006-usb-next-a1 \
  --work-dir build/usb/final-wire-NEW
python3 scripts/archive_companion_boundary.py \
  --peer build/usb/notebook-next-workflow-a2/peer \
  --outbox build/usb/notebook-next-workflow-a2/outbox \
  --initial-peer build/usb/store-initialize-a3/peer \
  --reference-workflow build/usb/final-wire-NEW/result.json \
  --saved-sequence 11 --high-water 72 \
  --output build/usb/final-acknowledged-NEW
python3 scripts/check_usb_cold_boundary.py launch \
  --boundary build/usb/final-acknowledged-NEW \
  --host-prepared build/usb/host-pending-policy4-a3/prepared.json \
  --native-bundle build/native/task006-usb-next-a1 \
  --saved-sequence 11 --high-water 72 \
  --work-dir build/usb/final-cold-NEW
```

The companion remains the development opaque peer; USB decoded-packet and
sample timing scopes, PHY conformance and arbitrary QEMU cached-state
continuation remain separate obligations.

-->
