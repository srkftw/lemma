# Native Pending checkpoint continuation v5

This extends the asynchronous opaque backing boundary in [v3](006-companion-backing-dev-v3.md)
and the timed outcome format in [v4](006-companion-backing-dev-v4.md). It admits
native RTL checkpoints while external work remains Pending. QEMU Pending
migration still rejects, and its cached-state equivalence gap remains open.
This is an outcome-bound private fork policy, not a claim that an unknown live
operation can continue independently without its outcome.

The native `LMSSRTL1` container version is now 2, with the same 112-byte header
and implementation identity check. The wrapper retains the immutable request,
original submission cycle, next poll cycle, reset-orphan ownership and logical
retry-ready state, alongside controller/media/flush cursors and all earlier
state. The generated RTL serialization retains the processor pipeline, cached
translations/instruction visibility, bus ownership and controller circuitry.
No socket, descriptor, host pointer, raw pipe buffer or peer process is serialized.
Historical v1 binaries/archives retain their own format and exact identities;
the v2 runtime does not silently reinterpret v1 state.

## Accepted backing view and observation

The medium is exclusively owned for this declared profile. Before the first
guest request, attach samples its complete 256 MiB through 256 bounded 1 MiB
passive reads. A sparse accepted-byte view retains nonzero sectors. Every actual
returned read prefix or changed write prefix updates that view after capture and
before machine admission, even when the operation returns an error. The view
is separate from `durable_barrier`: a failed write or barrier does not roll back
bytes or confer durable success. Zero sectors need no map entry. The maximum
retained payload is 256 MiB plus map/allocator metadata, distinct from guest RAM.
Unmodeled concurrent external writers are outside this ownership profile.

A snapshot serializes this accepted view, volatile overlay and logical Pending
work without calling the platform's read, poll, retry, barrier or cancellation.
Its log/artifact persistence operations do not flush the guest backing. The
live operation and virtual cycle remain unchanged. The accepted view does not
pretend to reveal an unacknowledged remote outcome: a peer may already have
changed bytes or retained a receipt while its reply is unavailable.

A restore materializes only the accepted bytes in a new exclusive private
medium. If the saved operation is Pending and no complete outcome tape is
already bound, the fork is explicitly suspended. `run` rejects before advancing
its virtual clock. The original operation continues in its original owner;
restoring a fork never resubmits it. Inspect and further observational snapshots
remain available. Pending export/rebind still rejects, including the browser
OPFS rebind helper: this increment does not claim usable browser Pending forks.

`Machine.bind_backing_replay` / native `backing-outcomes PATH` validates a bounded,
complete LMIOLOG2 tape, exact implementation identity, checksums, ordering,
inherited request bytes/ID/submission time and the saved poll cadence before
changing the fork binding. An incomplete, incompatible or corrupt tape leaves
the suspended fork unchanged. Native polls retain the 1,000-target-cycle cadence.
At the recorded acceptance cycle, the original returned prefix/error is
captured before controller publication; changed prefixes are applied only to
private backing. A private barrier must succeed locally, while the guest still
receives the recorded success/error. Replay exhaustion rejects rather than
consulting the original peer or inventing an outcome.

The host suspension/replay binding and tape path are execution ownership,
excluded from authoritative state. Logical Pending/retry/orphan state is
serialized. The admitted real-peer suffix uses a saved `retry_ready=true`,
explicit same-cycle retry control and its recorded completion. LMIOLOG2 does
not record arbitrary later retry-ready transitions or raw adapter buffers;
this v5 relation excludes such additional transitions. A bare Pending archive
alone is not unconditional arbitrary-boundary live continuation.

## Commands and focused evidence

Native session restore can bind a completed tape at launch using the existing
`--backing-replay LOG --restore SNAPSHOT` path, or later through Developer/
Laboratory lifecycle input:

```json
{"action":"backing-outcomes","path":"/absolute/actual.io"}
```

The request binds isolated replay ownership and is separate from raw input
capture. Student mode and the fast backend reject this new lifecycle operation.
Raw pen/button/UART and reset suffixes retain the existing event replay contract.
The equivalent low-level native command sequence is:

```text
inspect
run 1
backing-outcomes /absolute/actual.io
companion-retry
run 19000
snapshot /absolute/replayed.snap
```

For the retained real-peer corpus, `run 1` explicitly rejects without a tape;
after binding/retry the exact 19,000-cycle suffix completes. These are literal
controller/runtime qualification commands, not notebook Ready or guest USB/
companion-driver acceptance. Real guest instructions and raw pen ingress run
through the modeled machine, with no host ink/document interpretation.

```sh
python3 scripts/silicon_compute.py build --profile lemma-silicon-dev/0.3.0 \
  --jobs 2 --output-dir build/silicon/task006-backing-runtime-a6
nix-shell tooling/silicon/sim.nix --run \
  'python3 scripts/check_native_backing.py \
    --rtl-build build/silicon/task006-backing-runtime-a6 \
    --guest-bundle build/native/task006-canonical-a1 \
    --fixture fault-pending --work-dir build/silicon/native-fault-pending-a2'
nix-shell tooling/silicon/sim.nix --run \
  'python3 scripts/check_native_pending_fork.py \
    --rtl-build build/silicon/task006-backing-runtime-a6 \
    --guest-bundle build/native/task006-canonical-a1 \
    --companion-prepared build/companion/task006-peer-a7/prepared.json \
    --observe-existing build/silicon/native-peer-pending-a3 \
    --work-dir build/silicon/native-peer-pending-a4-observer'
python3 scripts/check_native_pending_restore.py \
  --rtl-build build/silicon/task006-backing-runtime-a6 \
  --qualified-observation build/silicon/native-peer-pending-a4-observer/result.json \
  --work-dir build/silicon/native-peer-pending-restore-a1
```

These paths retain observations; repetitions require unused output directories.
Omit `--observe-existing` to execute a new real-peer case. That mode qualifies an
independently corrected receipt observer on unchanged executed artifacts; it
checks that the actual fixture binary reproduces exactly from the validated
objects. It neither reruns peer initialization nor converts the original FAIL.
The exact measurements and original failures are in
[the compact receipt](../evidence/006-native-pending-checkpoint.json).
