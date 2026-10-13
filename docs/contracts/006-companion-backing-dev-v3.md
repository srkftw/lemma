<!--
# Native asynchronous medium boundary v3

This extends the development backing binding in v2 to the reusable RTL
`Machine`. It keeps the existing block circuitry and its held-request handshake.
The maintained protocol/outbox/receipt policy remains the same hosted Lean code;
the native adapter carries raw requests and actual replies through
`BackingPlatform::submit/poll`. POSIX and OPFS synchronous implementations still
return their actual result in the submission cycle. Peer polling uses a declared
1000-target-cycle cadence while all RTL clocks continue; this is an external
medium adapter policy, not a processor-timing claim for QEMU.

A held request retains its kind, sector and copied write bytes. Flush walks the
existing ordered overlay, retaining a sector cursor; it clears the overlay only
after the actual barrier succeeds. Real failed prefixes/barriers retain observed
backing changes and volatile sectors. The native host records immutable
submissions and actual outcomes in LMIOLOG2, with target cycles as boundaries.
This is distinct from fast-controller nanosecond coordinates. Source-bound
implementation identity rejects earlier state/log layouts; historical binaries
and their version1 logs remain intact.

The native LMIOLOG2 consumer validates all checksums, bounds, exact request IDs,
bytes and boundary ordering before execution. It applies captured outcomes only
in a private restored backing, at the exact recorded acceptance cycle, without
contacting the original file or peer. Rebuilding acceleration state is not part
of this mechanism. A preceding exact RTL checkpoint retains the actual processor,
fabric and controller state through generated Verilator serialization. The
wrapper additionally retains the medium owner and flush cursor.

Global reset cancels the old controller transaction. Already-submitted external
work becomes an orphan: its eventual actual result is recorded, but it cannot
complete the canceled DMA. New medium work waits for that result. The modeled
`external_media_busy` input keeps Power-v1's existing busy guard aware of such
work even after controller reset. Cooperative MMIO reset continues to hold the
circuit's original media request until its ready handshake. This does not close
watchdog/brownout, all reset domains, USB/radio cancellation or product recovery.

Pending/poisoned external snapshot, restore, export and private-backing rebind
are rejected without retry, hidden drain or guest mutation. Inactive host poll
cursors/handles have no future guest effect and are not serialized. Arbitrary
pending external checkpoint/fork continuation remains an explicit gap; this
increment does not claim that rejecting it satisfies the whole-machine goal.
Developer/Laboratory `companion-retry` now also reaches native sessions, sending
only the same raw RETRY to the Lean client. Recorded replay does not rerun the
peer's irreversible action; its captured acceptance controls the medium reply.

## Focused qualification

```sh
python3 scripts/silicon_compute.py build --profile lemma-silicon-dev/0.3.0 \
  --jobs 2 --output-dir build/silicon/task006-backing-runtime-a5
nix-shell tooling/silicon/sim.nix --run \
  'python3 scripts/check_native_backing.py \
    --rtl-build build/silicon/task006-backing-runtime-a5 \
    --guest-bundle build/native/task006-canonical-a1 \
    --work-dir build/companion/native-pending-a5'
```

These exact paths retain the observed run; use unused output directories to
repeat. The check directly initializes a literal held controller request. It
loads the fully validated archived genuine reset ROM/guest artifacts and
establishes continuing instruction retirement and raw pen ingress, pending-state
observational rejection,
byte-exact completed RTL checkpoint suffix through timed private replay, and
global-reset orphan completion without DMA. It does not establish guest-driver
execution, native canonical notebook Ready or native companion cold recovery.
The separate v2 real RV64 guest campaign establishes notebook ink/save/recovery
through this same shared transport on the fast backend. Cross-backend timing and
QEMU cached-translation/instruction-visibility continuation remain open.

-->
