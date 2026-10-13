<!--
# LemmaSim external backing-I/O v1

The host-only [shared boundary](../../sim/host/backing_io.h) carries opaque bytes;
it does not parse records, run recovery or decide document acknowledgements.
The RTL Machine runtime consumes it for medium reads, ascending-sector FLUSH
writes and the final barrier. Its POSIX implementation uses actual buffered
`pread`, `pwrite` and `fsync` on the regular medium exclusively owned by the native session. The QEMU
adapter has not yet adopted this boundary. A browser adapter can provide the
same narrow callbacks; this contract alone does not establish browser durability.

Each external operation has a monotone u64 identity, the exact virtual cycle,
kind, byte offset, bounded length and immutable write bytes. A single owner
advances `Idle/Completed/Cancelled -> Pending -> Completed`. Cancellation is
legal only before external execution. An exception after execution may have
changed external bytes; the owner is poisoned and cannot retry, advance or
checkpoint that ambiguous operation. Current native calls are synchronous and
do not yield: an external callback completes before the next RTL rising edge.
There is consequently no external syscall in flight at the supported completed
rising-edge snapshot boundary. The RTL queue/DMA/controller can still be in
flight and remains captured. An asynchronous adapter must implement and version
its additional pending state and fork/cancellation rule before advertising it.

Reads and writes return the exact transferred prefix and terminal errno. A
zero-byte transfer before the requested length is a short transfer/EIO; EINTR
is captured rather than retried indefinitely. Ordinary failures reach the real
controller's IOERR completion. Successful buffered writes may precede a failed
later write or fsync. They remain changed in the backing file; failure neither
rolls them back nor clears the volatile overlay. The POSIX profile excludes
direct I/O and models changed buffered bytes as the positively returned write
prefix. It makes no guarantee about their survival across physical host failure.
`observed_write` and `durable_barrier` are separate operation identities. Only
a successful barrier moves the latter; guest store publication and Saved remain
separate, Lean-authoritative decisions.

Snapshots and exports read the actual backing bytes through `passive_read`.
They issue no guest operation, barrier, drain or completion. The historical
wrapper field named `durable` stores these observed backing bytes, including
unacknowledged bytes left by a failed publication. The volatile overlay is
captured separately. Restoring retains operation identities and materializes
the saved backing into an exclusive private fork. Thus a cold reopen may see
unacknowledged persistence and the guest journal must decide applicability.
A restore is not cold recovery.

`BackingPlatform` supplies capacity, observational reads, execution and isolated
record application. `Machine.attach_backing` validates canonical medium capacity.
`rebind_private_backing` is permitted only after restore, compares every observed
backing byte before replacing ownership, and preserves all serialized operation
state. It supports moving a restored private fork to another platform without
turning MEMFS or an in-memory buffer into a claimed persistence barrier. No raw
descriptor, host pointer or original backing path enters a checkpoint.

## Capture and isolated replay

Native RTL sessions automatically create `backing.io`. A successful restore starts
a new exclusive `backing.io.fork-N-XXXXXX` stream and retains the original log.
Operation identities can rewind with restored machine state without creating
duplicate identities in an external stream. The public
`Machine.backing_capture_path()` getter names the current stream; this path and
its branch ordinal are host ownership fields excluded from authoritative state. Low-level `lemma-rtl`
also exposes `--backing-capture NEW_FILE` and `--backing-replay LOG_FILE`.
Replay requires a restored private fork. The ordinary session command accepts
`--backing-replay LOG_FILE --restore SNAPSHOT_DIRECTORY`. The existing raw-input
suffix replay remains necessary for admitted pen/button/UART events.

`LMIOLOG1` is followed by the 64-byte implementation identity, then length-prefixed
records. Each contains seven little-endian u64 fields: identity, virtual boundary,
kind, offset, requested length, transferred length and errno; immutable requested
write bytes; exact returned/changed prefix bytes; and CRC64-ECMA. CRC and source
identity provide integrity and compatibility, not authentication. A zero-length
placeholder is written before external execution, and completed outcome bytes
are recorded before the device can receive the result. Interrupted placeholders,
truncation, corrupt records, malformed fields and inconsistent ordering reject.
The entire regular log is preflighted before replay. A capture write failure
poisons the owner instead of permitting an unrecorded success.

Logs are bounded at 64 MiB and 1,000,000 records; transfers at 1 MiB. Capacity is
reserved before external execution. Exhaustion pauses with an explicit error.
The capture file receives its own fsync at snapshot; that observational-log
barrier never flushes the guest medium. The log is external replay input rather
than part of exact machine state. Saved machine state includes the next operation
identity, last accepted completion, last successful barrier, observed write and
phase. The implementation closure includes every shared boundary source.

Replay checks the complete request, including cycle and immutable write bytes,
before consuming an outcome. Reads use recorded returned bytes; they never
consult the original medium. Writes apply only their recorded changed prefix to
the private backing. A local fork barrier must succeed to retain replay effects,
while the original captured success/error remains the guest-visible result.
An error in materializing the fork is a replay failure, not a replacement guest
outcome. Original files, networks and peers are never recontacted. Missing or
divergent requests fail closed. Replaying a failed barrier preserves its changed
bytes without inventing a Saved acknowledgement.

The focused host check runs real RLIMIT_FSIZE partial pwrite/EFBIG and real
pread/fsync EBADF failures, independently inspects resulting bytes, closes the
original descriptor, and reproduces the recorded prefix into a new file. It also
checks separate acknowledgement, cancellation/poison and CRC/truncation behavior:

```sh
nix develop --no-write-lock-file --command python3 -m unittest discover \
  -s tests/lemmasim -p test_backing_io.py -v
```

This is host-boundary evidence; it does not establish guest cold recovery,
QEMU parity, USB/companion completion, browser distribution or physical storage.

The native Pending checkpoint successor is specified in [v5](006-companion-backing-dev-v5.md); the synchronous v1 observations above retain their original scope.

-->
