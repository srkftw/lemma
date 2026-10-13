<!--
# Hosted USB Pending policy4

`lemma-usb-host-dev/4` is an additive, opt-in hosted Lean policy. Policy3 and
its prepared artifacts remain unchanged. Both use the existing
`USBHOST/2 PACKET_BYTES_DEV` raw adapter and the modeled control/data endpoints.
This policy does not add a USB PHY or change the RV64 guest image. The small
`pending_main.c` entry only initializes the ordinary host Lean runtime and
invokes the Lean declaration; it has no protocol or receipt decisions.

The independent peer persists opaque bytes and transaction receipts. A lost
reply or raw socket error is uncertainty. Policy4 retains the same writer,
sequence, request bytes and durable outbox, then schedules `WAIT 100000` before
retrying. It does not allocate a replacement transaction or acknowledge the
guest without a validated peer receipt. Retrying an older sequence reads the
peer's retained result. A returned error/partial receipt preserves unresolved
outbox ownership and its actual byte count; persistence is not rolled back.

One opaque operation shares at most 100,000,000 explicitly requested wait
clocks across subsequent request fragments, uncertain peer receipts and all
response fragments. Fragment NAK uses 1,000 clocks; receipt uncertainty and
response NAK use 100,000. Packet/admission work adds actual virtual time and is
separately bounded by the machine campaign. Initial idle polling precedes an
operation, and enumeration/control retains its existing separate finite bounds.
Malformed peer receipts stop at three errors; malformed response handshakes
share three errors across fragments. STALL is terminal. Valid NAK preserves
the pending packet and toggle; only ACK advances the response toggle. Bounds
reject before emitting a wait that would exceed the operation budget.

Prepared validation requires the exact policy version, budgets, source hashes,
host tools, original policy3 dependency manifest and linked objects, freshly
elaborated dependency C, all new host objects, entry recipe and executable.
Unknown/missing/corrupt closure rejects. No target objects are added.

Build and independently qualify the policy:

```sh
./scripts/lemmasim usb-pending build \
  --legacy-prepared build/usb/host-pending-policy3-a1/prepared.json \
  --output-dir build/usb/host-pending-policy4-NEW
nix develop --no-write-lock-file --command python3 scripts/check_usb_pending.py \
  --prepared build/usb/host-pending-policy4-NEW/prepared.json \
  --verilator /nix/store/byap8v9aasg1dxjkz1hkpc5m8jxmaxwj-verilator-5.052/bin/verilator \
  --work-dir build/usb/usb-host-pending4-properties-NEW
```

For a source-bound USB6/USB8 native session, pass the new prepared manifest to
the existing `--usb-host-prepared` option. The independently running companion
peer, private outbox and explicit socket arguments remain required. The
checker exercises real delayed peer restart, retained-receipt deduplication,
absent peer, shared budget and malformed receipt failure while clocking the
literal USB controller for every wait. Its scope is hosted policy plus circuit
clocks. Whole guest policy4 Save/cold acceptance and USB PHY/conformance remain
unqualified. Native captured outcome replay, host wall time and virtual clock
budgets remain distinct.

-->
