<!--
# Native decoded USB host v2

This additive host transport revision uses `USBHOST/2 PACKET_BYTES_DEV` and the
prepared schema `lemma-usb-host-dev/2`. It retains the optional USB6 hardware
binding and the [decoded-packet device contract](006-usb-device-v1.md). Older
prepared host/runtime artifacts keep their original identities and results.
The host objects are accounted for separately and never enter an RV64 image.

The hosted Lean policy waits for a first opaque request fragment by issuing a
real IN token, receiving an actual NAK, and requesting 100,000 machine clocks
before the next poll. At 100 MHz this is 1 ms. This idle state has bounded
buffers and no pending irreversible transaction. It does not manufacture a
receipt or configured state. Control transfers and an already-started opaque
frame retain their existing 10,000-attempt bounded retry rules. Their scheduled
waits total at most 10 million clocks; packet transfer and adapter scheduling
add virtual clocks, so that total is not a full transfer deadline. Peer transaction/outbox,
barrier and durable receipt policy remains in the hosted Lean companion code;
the raw C++ transport does not interpret blocks or guest documents.

An actual process EOF, read/write failure, malformed external framing, bounded
transport timeout, or unsolicited command is a digital disconnect. The native
machine captures the observed reason at its polling boundary before changing
the circuit inputs or clearing raw queues. It then removes attach, reaps its
owned process, and continues virtual clocks and unrelated raw input. A power
domain reset captures `DOMAIN_RESET` and cancels that attachment. A durable
outbox remains owned by the hosted policy; reset does not resubmit or fabricate
its acknowledgment. Internal request-ID, ownership, capture-write and machine
ordering violations still fail closed and cannot masquerade as disconnection.

The machine polls process liveness every 1,000 virtual clocks, including while
a retained `RECV` waits for the circuit. A failed or pending reply cannot consume
a cleared controller packet queue. This liveness rule does not establish guest
notebook responsiveness by itself: the qualified native fixture observes actual
pen-controller input after disconnect without executing a notebook.
Configured process timeout uses external host elapsed time. It is captured as
an external outcome at the next virtual polling boundary, rather than added to
the machine's virtual counter or silently substituted for a controller deadline.

New failure-capable captures use `LMUSBRW2 <runtime-identity>` and stable
monotonic raw request IDs. Each row is `cycle tag id frame`: tag0 is an actual
external command admitted before scheduling its inputs; tag1 is the raw
machine reply recorded before attempting host delivery; tag2 is the observed
external failure or domain reset, recorded before changing attach or queues.
A tag1 followed by tag2 does not prove the process received the reply. Capture
write/resource errors reject rather than discarding an outcome. Historical
`LMUSBRW1` tapes admit only tags0/1 and the version1 host handshake.

Live attached USB policy and raw pending state are still excluded from machine
checkpoint admission. Snapshot rejects observationally; it does not poll, drain,
flush, reset, or contact the peer to make the state admissible. Whole-machine USB
replay, exact private USB forks, fast/browser USB execution and physical USB PHY
remain open. USB packet ACK is distinct from a durable peer barrier receipt.

Focused commands use fresh output paths:

```sh
nix develop --no-write-lock-file --command python3 scripts/lemmasim_usb.py build \
  --output-dir build/usb/NEW-HOST
nix-shell tooling/silicon/sim.nix --run 'python3 scripts/check_native_usb_disconnect.py \
  --rtl-build build/silicon/task006-usb-runtime-a4 \
  --work-dir build/usb/NEW-DISCONNECT'
```

The second command validates the exact consumed native sources and compiled
objects. The retained `a4` path is historical after a runtime change; prepare a
new source-bound build rather than bypassing that check. The genuine hosted
idle-policy fixture uses the host build's `.olean` modules and an unused
`LEMMA_USB_IDLE_WORK` directory; its transcript is a host boundary fixture, not
a guest or controller qualification. Exact source/tool identities and original
failures are in the accompanying evidence receipt.

-->
