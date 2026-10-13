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

Commands for the qualified artifact shapes (use unused output directories):

```sh
python3 scripts/archive_companion_boundary.py \
  --peer build/usb/notebook-next-workflow-a2/peer \
  --outbox build/usb/notebook-next-workflow-a2/outbox \
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

The companion remains the development opaque peer; USB decoded-packet and
sample timing scopes, PHY conformance and arbitrary QEMU cached-state
continuation remain separate obligations.

-->
