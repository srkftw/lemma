# USB6 RV64 opaque backing development slice

`lemma-silicon-dev/0.6.0` is opt-in. Binding6 uses descriptor ABI7/features15,
USB MMIO `0x10010a00/0x400`, PLIC16, EP0 and bulk IN1/OUT2 with 64-byte packets.
Power-v2 and BLE5 remain inherited; historical profiles and launch defaults retain
separate bindings. Device decode subtracts the actual USB base.

The circuit accepts decoded packet bytes, checks token CRC5/DATA CRC16, and
implements endpoint toggles, retained receive heads, NAK backpressure, HALT,
SETUP generations, status-stage address/configuration publication and digital
reset qualification. The full USB PHY, NRZI/bit stuffing, electrical behavior,
USB class interoperability and complete USB conformance are unfinished. The
existing [device contract](006-usb-device-v1.md) defines the register behavior.

Maintained Lean `Control`, `Controller`, `BlockProtocol`, `Block` and `USBLink`
compile through the checked Kernel6 lowering to freestanding RV64. Only owned
purpose1 frames provide copied PIO payloads. The probe allocates a separate
purpose2 negative-test frame; stale generation, wrong purpose, invalid spans,
wrong endpoints and excessive capacity reject before consuming the retained
OUT head. Its metadata and independently accumulated bytes are checked afterward.

The native adapter transports raw packets and digital attach/reset signals.
The separate compiled hosted-Lean USB host generates/checks packets and performs
standard enumeration; it cannot set configured state directly. Its opaque block
policy reuses the genuine hosted-Lean companion client, durable outbox, writer
and transaction identities. The independent peer retains opaque bytes and
receipts. USB ACK or raw SENT is never a durable block acknowledgment. A lost
peer response retries the same retained transaction and receipt; packet delivery
is not claimed exactly once. The adapter captures accepted raw commands and
responses before they affect the machine. Live process policy and raw pending
state are not yet fully serialized: USB6 snapshot/restore rejects before
polling, draining or mutating the machine. Fast/browser USB execution is open.

The qualified guest path currently enumerates, discovers capacity, performs a
peer-backed barrier, tests owned-buffer rejection, and reads a real sector. The
notebook Store/journal path, write receipt correction, disconnected Save UI,
cold document recovery through USB and complete protocol recovery are separate
unfinished work. This slice does not close ordinary USB notebook Save.

The source-bound commands used for the retained run were:

```sh
nix develop --no-write-lock-file --command python3 scripts/lemmasim_usb.py build \
  --output-dir build/usb/host-qualified-a1
./scripts/lemmasim build --backend rtl --profile lemma-silicon-dev/0.6.0 \
  --workload usb --rtl-build build/silicon/task006-usb-runtime-a1 \
  --guest-build build/kernel/task006-usb-link-a3
python3 scripts/check_guest_usb_link.py \
  --host-prepared build/usb/host-qualified-a1/prepared.json \
  --work-dir build/usb/NEW-UNUSED-WORK-DIRECTORY --lost-ack
```

The checker initializes and owns its independent opaque peer, launches the
normal public machine session, drops its first durable barrier response, restarts
that peer, and independently observes packets/guest records/receipt/outbox.
Source mutation requires fresh source-bound preparation or an explicitly
validated unchanged-artifact archive; these retained paths are not a bypass.
The ordinary session command surface also accepts `--usb-host-prepared`,
`--usb-peer-directory`, `--usb-peer-socket`, `--usb-host-state` and the bounded
`--usb-peer-timeout-ms` in Developer/Laboratory mode with workload `usb`.

The original machine observation failed on an offline oracle that advanced an
OUT toggle at raw byte acceptance. The corrected observer advances only after
actual USB ACK, preserves NAK retries, and rechecks the same retained capture.
The read-request oracle was also corrected to distinguish a declared response
length from carried request bytes. Packet-CRC, ACK-to-NAK and raw-order mutations
now reject. No cold run was repeated for these observer corrections. Exact
identities and remaining scope are recorded in
[`006-usb6-rv64-peer.json`](../evidence/006-usb6-rv64-peer.json).
