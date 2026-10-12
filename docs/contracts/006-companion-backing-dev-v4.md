# Fast private timed I/O replay v4

The fast controller can consume the same LMIOLOG2 request/outcome format used
by the asynchronous backing boundary in v2. Its coordinates are QEMU virtual
nanoseconds, distinct from native RTL target cycles. The exact executable SHA256
in the log header must match the machine; nominal clock matching does not permit
cross-backend reuse.

The wrapper's adapter4 checkpoint layout is unchanged. Its new optional replay
transport does not alter authoritative wrapper state; exact runtime identity
admits the new consumer. Ordinary execution and restore through an older
immutable native bundle keep their existing identity and behavior. New replay
properties require the newly built backend and reject on unsupported older
executables rather than bypassing its validation.

The C bridge reads a complete regular file bounded to 64 MiB and validates every
entry length, checksum, request/completion identity and order before binding it.
An empty or unresolved log rejects. Only a quiescent asynchronous POSIX owner
explicitly identified as a private fork can bind replay. Public QEMU sessions
require `--restore`; they materialize checkpoint bytes in a new exclusively
owned file and do not pass a companion or the original user medium to the replay
process. A rejected restore is confined to that disposable candidate, preserving
the live session. The saved next-operation ID selects the suffix; mismatched
request IDs, fields, bytes or submission times reject without external execution.

Polling before the recorded acceptance time returns Pending. Polling at exactly
that time applies the recorded changed write prefix to the private medium and
records the original returned bytes, partial transfer or error before the
controller can publish it. Missing the acceptance time rejects; there is no
tolerance or rescaling. A private barrier must itself succeed to maintain that
fork, while the guest receives the captured success/error. In particular, a
captured failed barrier never becomes a guest durability acknowledgment and
does not undo earlier observed bytes. Replay beyond the complete recorded
operation sequence rejects rather than contacting a live file or peer.

The C bridge cursor derives from the authoritative next-operation ID at a
quiescent migration boundary. No host pointer, descriptor, socket or replay
cursor is serialized. Pending or poisoned external snapshot/export/restore
continues to reject observationally. This remains a whole-machine checkpoint
gap. LMIOLOG2 does not record the hosted client's `retry_ready` transition;
explicit companion retry controls are consequently excluded from the fast
replay admission in this version. Ordinary ink and Save suffixes using local
POSIX outcomes are admitted. A future capture version must preserve such
external control transitions before claiming their exact replay.

The qualification relation is declared before running: exact submitted and
accepted I/O bytes and virtual nanoseconds, raw device suffix, guest UART suffix,
acknowledged object bytes and complete controller pixels. This backing-I/O
relation neither changes nor closes the substantive QEMU cached-translation,
instruction-visibility and acceleration-state migration hole. It also does not
establish RTL timing parity, cold recovery, native/Wasm archive equality, USB,
radio or the product boot/update path.

The real OS error fixture uses RLIMIT_FSIZE to obtain an actual two-byte write
prefix followed by EFBIG and closes the live descriptor to obtain actual EBADF
from fsync. It removes the original medium before replay. Independent file
observations verify retained prefixes and no premature effects; corrupt log,
wrong identity, absent private-fork admission, changed request and missed
acceptance-time cases reject. A separate real RV64 notebook scenario reaches
Ready, takes an observational quiescent checkpoint, supplies raw strokes and
Save, removes the mutable live medium, and replays the suffix in a private fork.

```sh
nix develop --no-write-lock-file --command python3 -m unittest discover \
  -s tests/lemmasim -p test_backing_io.py -v
python3 scripts/lemmasim build --backend qemu \
  --profile lemma-silicon-dev/0.3.0 --workload notebook \
  --guest-bundle build/native/task006-canonical-a1
python3 scripts/check_fast_backing_replay.py \
  --disk build/silicon/task006-canonical-cold-a2/medium.raw \
  --work-dir build/companion/fast-backing-replay-a1 \
  --timeout 120 --boot-seconds 40 --action-seconds 20 --deadline 600
python3 scripts/lemmasim session --backend qemu \
  --profile lemma-silicon-dev/0.3.0 --workload notebook \
  --session-dir build/companion/manual-replay-unused --headless --paused \
  --restore build/companion/fast-backing-replay-a1/before-ink \
  --backing-replay build/companion/fast-backing-replay-a1/selected.io
```

Use unused output directories. The archived guest is a fully validated genuine
Lean-authored RV64 artifact; this build compiles the changed backend and does
not claim fresh target compilation. Normal preparation without an archive
continues to enforce current source identity. Retained failures and measured
results belong to their exact reported sources and commands.
