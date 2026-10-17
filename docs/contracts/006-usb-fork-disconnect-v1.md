<!--
# USB Wire11 injected disconnect fork v1

This Laboratory-only adapter input is distinct from historical recorded USB
continuation. It preserves the exact native implementation, parent checkpoint
and original tape. It does not migrate microstate, attach a live peer to a
restored fork, or resubmit any opaque action.

The initial scope is an acknowledged Saved11 Wire11 boundary with no endpoint
head, outgoing/queued packet, DMA, memory request or panel work. Its only raw
operation is a pending `WAIT 100000` at the next 1000-clock poll boundary. The
archived raw adapter's WAIT changes only its virtual deadline; the hosted Lean
idle path waits after a real NAK before receiving the first opaque fragment.
The matching peer/outbox has no pending operation, exact writer/high-water and
checksummed dedup state. Cancelling this WAIT creates no receipt or medium effect.

A new private opaque peer/outbox is copied from the independently acknowledged
archive. The genuine hosted Lean process loads that outbox and emits its actual
raw startup request. A host-only probe of the exact archived transport stops
only this newly owned process and captures an actual read EOF before issuing
OPEN or any packet/opaque action. All private medium, receipt and outbox bytes
must match before/after capture. This probe does not restore the old hosted
process's hidden logical context.
The private peer metadata names its exact new owned base path; every other
metadata field and all opaque base/log/outbox bytes match the source archive.

`usb-fault` requires a strict `lemma-usb-fork-disconnect-fault/1` sidecar. It binds
the parent full inventory, immutable native package, accepted prefix chain,
actual private EOF capture and complete private receipt/media hashes, stable
pending WAIT ID, next poll cycle and finite suffix horizon before admission.
The sidecar is rejected by historical `usb-outcomes`; it is never described as
an original observed outcome. Internally the unchanged raw bridge applies the
captured EOF reason at the declared branch-local poll boundary, cancelling the
WAIT and driving the existing modeled disconnect level into the controller.
No configuration, authentication, positive ACK, journal or Saved status is
supplied by the adapter. Absent/corrupt/mismatched authority rejects before
clock advancement. The original live owner and external paths are untouched.

The unsuccessful Save workload must admit real raw ink and toolbar input, observe
guest provisional/failure records and actual controller pixels, and reject a new
Saved record. Failed operations may persist bytes. The checker records private
opaque effects and observed medium bytes rather than assuming rollback. A new
cold recovery is a separate, independently bounded question when needed.
The initial ceilings are 200M ink cycles, 1.6B Save cycles, 7200s per action,
4GiB owned RSS and 12GB disk; these are resource limits, not timing WCETs.
The actual private EOF capture completed in 7.310s with zero replies/opaque
operations and unchanged private state. Actual native admission then rejected
no tape, historical sidecar, duplicate fault and a 1001-cycle request crossing
its 1000-cycle horizon, all at zero target clocks. Every before-edge checkpoint
byte equals the original. At the first real edge the captured EOF cancelled
WAIT129433 and reset the controller's connection/configuration; no host was
attached to the restored actor.

The guest admitted a new raw stroke and issued Pending12 for object65548, then
Failed227 after disconnect. At 40M additional clocks/202.242s, all3.63M FAILED
pixels and both original/new stroke points matched. There was no new Saved and
the independent private base/log/outbox and materialized durable bytes remained
unchanged. The later toolbar down/up was admitted and consumed, but the archived
compiled Notebook policy rejects contacts and toolbar when status>=2, so it
issued no new explicit Store retry. An independent retained observer qualifies
the unsuccessful autosave and blocked gesture separately. The original live
fixture FAIL/cancellation remains unchanged; its waiter wrongly compared the
Failed error field with a Pending sequence and expected a retry that the policy
does not permit. The first strict private-base-path guard FAIL also remains.
No new CPU cold prefix ran for this observation. Retry after FAILED remains a
separate versioned Lean successor, not an adapter change or completed claim.

The source-bound inputs, original failures and exact observations are recorded
in `docs/evidence/006-usb-fork-disconnect.json`. Reobserve the retained boundary:

```sh
python3 scripts/check_usb_fork_failure_observation.py \
  --workflow build/usb/wire-unsuccessful-save-fork-a2 \
  --work-dir build/usb/wire-unsuccessful-save-observation-NEW
```

The explicit Laboratory API is `session-control --request
'{"action":"usb-fault","path":"/absolute/path/fault.json"}'`. The strict
sidecar is built from actual private EOF and acknowledged parent artifacts;
ordinary `usb-outcomes` continues to reject it. Its raw bridge is an internal
adapter artifact with a declared injected-fault scope.

-->
