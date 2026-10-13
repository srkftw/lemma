# USB6 recorded raw continuation v1

This opt-in native `lemma-silicon-dev/0.6.0` extension adds container version 6.
Historical 0.3/Power4/BLE5/Product7 serialized layouts stay unchanged. Product7
with an attached USB host remains rejected; this extension does not supply an
open-ended privately live companion or a QEMU cached-state solution.

The completed-cycle checkpoint retains attachment/connection/terminal levels,
the actual retained raw command and stable ID, incoming cursor/bytes, partial
outgoing packet and four queued controller-produced packets, root reset and
wait deadlines, next 1000-clock poll boundary, request namespace and accepted
raw-row cursor/chain. Verilator state retains the endpoint heads, buffers,
CRC/toggle/control-transfer state, IRQ and the processor/fabric state. Host
pointers, process descriptors, sockets and wall-clock references are excluded.

`Machine::snapshot(path)` performs no USB poll, reply, drain or completion.
Restoring a USB6 attachment into a new machine produces a suspended private
fork. `run` rejects before advancing its clock until
`Machine::bind_usb_replay(path)` admits a complete, matching outcome tape.
Restoration into an existing live attachment remains rejected: it must not
silently discard or duplicate unresolved external ownership. Corrupt or
incompatible state fails validation before replacing the destination.

`Machine::export_usb_replay(path)` copies the original already-flushed raw
capture observationally. It publishes a new exclusive `LMUSBRP1` artifact with
implementation identity, completed-cycle `HORIZON`, canonical raw rows and a
64-bit checksum over rows and horizon. The original `LMUSBRW2` capture stays
unchanged. Row order and IDs, bounds, canonical framing, checksum, accepted
prefix chain and retained request namespace are validated before binding.
The checksum detects accidental corruption; it is not authentication.

A restored fork never launches, polls, writes or resubmits to the original USB
host or durable peer. It applies raw commands and observed disconnects at the
recorded virtual boundaries and compares every generated raw reply byte,
order and boundary. Its queues/controller execute normally. A requested run
interval crossing the recorded horizon is rejected before any advancement.
A longer complete tape may be rebound after validating the now-accepted prefix.
This relation covers the recorded same-backend suffix with historical external
outcomes. It makes no claim that replay created a new externally durable commit
or retained an unrecorded external future. Physical USB PHY and general USB
conformance remain separate.

Actual qualification, using the unchanged genuine strict-audited USB bulk
initializer and independent hosted Lean peer:

```sh
nix-shell tooling/silicon/sim.nix --run 'python3 scripts/check_native_usb_pending.py \
  --rtl-build build/silicon/task006-usb-runtime-a7 \
  --guest-build build/kernel/task006-usb-bulk-initialize-a3 \
  --guest-source-root build/kernel/task006-usb-bulk-initialize-a3/consumed-source-root \
  --host-prepared build/usb/host-pending-policy3-a1/prepared.json \
  --formatted-peer build/usb/store-initialize-a3/peer \
  --formatted-outbox build/usb/store-initialize-a3/outbox \
  --work-dir build/usb/native-pending-NEW'
```

The host property uses the real Machine and actual guest-issued MMIO; it never
sets controller internals. It checks startup, actual bus reset, owned receive
head/submit queue and domain reset. Original snapshot/tape export leave live
inspection and capture unchanged; private suffix snapshots match exactly.
No-tape, horizon crossing, checksum and incompatible-state rejection are
checked. The retained a1 tool-PATH failure and a2 unflushed-header defect remain
FAIL. Publishing/checking the header in the constructor repaired a2 without
polling or draining a snapshot. Actual results and resource costs are in
`docs/evidence/006-usb-raw-continuation.json`.
