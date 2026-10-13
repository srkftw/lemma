<!--
# Both-sided lost-write receipt restart

The focused host-only test elaborates ordinary Lean that sends one opaque
512-byte write through `USBPendingPolicy.exchangeOpaque`. The separately
running Lean peer persists that write and its receipt, loses the reply and
exits. The client reaches an actual WAIT request with a durable pending outbox,
then is terminated before it can admit a receipt. Neither side is rewritten
or given a fabricated acknowledgment.

A fresh client reads the same outbox before the fresh peer starts after a
500-millisecond host delay. Every retry wait clocks the actual literal USB
controller. The test requires the same writer, sequence and payload, exactly
one persisted effect, a validated successful receipt and a cleared outbox.
The 100-million virtual wait budget and 180-second host ceiling remain finite.
All owned processes are reaped. This is retained-transaction reconciliation,
not exactly-once packet delivery or a fresh RV64 guest execution result.

```sh
nix develop --no-write-lock-file --command \
  python3 scripts/check_usb_client_restart.py \
  --prepared build/usb/host-pending-policy4-a3/prepared.json \
  --clock-proof build/usb/usb-host-pending4-properties-a9/result.json \
  --work-dir build/usb/usb-host-both-restart-NEW
```

The normal host Lean runtime and entry shim remain outside the RV64 image.
The prepared policy and unchanged literal clock adapter are validated before
execution. The checked-in receipt binds the genuine fixture, executable,
source/tool identities and original failures separately.

-->
