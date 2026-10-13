# BLE manual-context sequence policy v1

`lemma-ble-manual-link/1` supplies bounded, Lean-authored ACL SN/NESN policy
above the actual `lemma-ble-packet/1` CRC-valid immutable receive head. It
implements the sequence rules in pinned Bluetooth Core 5.4
[Vol 6B §4.5.9](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/low-energy-controller/link-layer-specification.html).
The context is supplied explicitly for development. Connection establishment,
channel hopping/event scheduling, L2CAP, encryption/authentication and complete
Bluetooth support remain missing. An access address and CRC do not authenticate
a peer.

State bits 0/1 contain transmit SN and expected receive SN. Bit 2 is one
outstanding immutable payload; bit 3 is an uncertain frozen context. Bits 8–9
count its transmissions, from one through three. Idle or frozen contexts have
zero attempts. Malformed combinations or high bits fail before changing state.
Only length 0–27, LLID 1/2 and the packet component's unencrypted/no-CTE header
are accepted. Zero length requires LLID 1. Receive space is exactly zero or one.

A valid packet whose NESN differs from the local outstanding SN acknowledges
that payload and advances local TX SN. A received SN matching the expected SN
admits its payload and advances expected RX SN only when receive space exists.
A duplicate never delivers its bytes again. Full space leaves expected RX SN
unchanged; the resulting NESN withholds receipt and permits the same retry.
CRC failure must never call the policy at all. This policy accepts the actual
hardware head rather than a host-created success indication.

Retries retain the payload and SN; the next NESN may describe new receive
progress. Three transmissions is the resource ceiling. Exhaustion (status 198)
or cancellation (200) freezes the context because an unacknowledged payload
may already have reached the peer. Frozen work cannot be replaced by another
transaction. Restart/rebind requires explicit external reconciliation; no
exactly-once packet delivery or durable receipt is claimed. Busy, malformed and
frozen inputs return distinct statuses 196, 197 and 199.

The pure transition result contains status in its upper 32 bits and bounded
state/observation flags in its lower 24 bits. Observation flags 16–19 mean
outstanding payload acknowledged, new receive, duplicate and receive shortage.
Callers retain only the defined state mask. Ordinary Action wrappers expose
these same scalar functions through checked lowering; the hosted development
peer reuses the functions directly. No second target interpreter is involved.

`sim/radio/ble_peer.lean` is a separately hosted, volatile development peer.
Its normal Lean runtime never enters the RV64 image. It retains one opaque
27-byte application head, exposes explicit credit, and emits empty LLID 1 ACK
requests. It does not inspect notebook records or implement a journal. Its
adapter must encode each `TX` request through a distinct real packet controller
and supply `RX` only after that controller's CRC-valid publication. The command
capture is bounded to 256 bytes; malformed frames do not change sequence state.
`CANCEL` freezes state. `STATUS` is observational. A peer restart discards this
volatile context; it is not companion storage or cold durable recovery.

The versioned hosted text boundary begins with
`BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT`. Commands are `RX <decimal header>
<decimal length> <lowercase opaque hex or ->`, `CREDIT`, `STATUS`, `CANCEL` and
`QUIT`. ACK requests are `TX <decimal header> 0 -`. The native adapter supplies
raw timing and packet-controller transport only; it must not set configured or
authenticated state on either endpoint. Snapshot integration must preserve the
packet models, pending sample decisions and queued raw frames, and must isolate
or replay the external peer rather than reissue irreversible actions to it.

Every response, including handshake and errors, ends in a complete accepted
logical-state trailer:

```text
<action> | STATE <state> ACCEPTED <count> DUPLICATES <count> PENDING <length> <opaque lowercase hex or ->
```

Both counters are bounded to `2^63-1`. Overflow is status201 before mutation.
The opaque head is at most27 bytes. A host adapter caches this actual accepted
response before scheduling any peer controller transaction. Taking a snapshot
does not request `STATUS`, flush the peer, advance a clock or drain a response.

A newly created, privately bound process may receive `--private-restore`; its
first command must be `RESTORE <state> <accepted> <duplicates> <opaque hex or ->`.
The Lean peer validates all fields before adopting them. Unknown state bits,
inconsistent outstanding/frozen/attempt fields, oversized heads, out-of-range
counters and a nonempty head with zero accepted count reject with status197
and exit2. A normal live process never accepts `RESTORE`. After restore,
replay/fork inputs must go to that private peer and packet endpoint. This is
complete logical policy continuation at an accepted-response boundary, not an
arbitrary-boundary whole-machine checkpoint. Pending host operations require
recorded outcomes or explicit snapshot rejection; they cannot be rerun against
the original peer.

`sim/radio/ble_peer_transport.{h,cpp}` is a host-only, nonblocking raw process
adapter. It retains stable request IDs, one outstanding operation,256-byte
response framing and an actual deadline. It returns the real complete response
before controller PIO, and tears down/reaps only its owned process group.
Readiness means the host process completed its handshake/private restore. It
does not establish/configure/authenticate a Bluetooth connection or report
companion durability. An EOF, timeout or malformed reply is an error; no ACK is
fabricated. Snapshot callers must reject `is_pending()` and retain controller,
wire and cached policy state separately.

`parse_recorded_reply(frame)` admits an already captured complete response with
the same canonical framing checks, without creating a process or changing peer
state. It preserves the raw action/trailer and returns request ID zero for the
runtime to bind to its recorded request. It rejects newlines, extra responses,
inconsistent heads and frames over256 bytes. This parser grants no authority to
an unbound frame: the runtime must check request identity, event cursor and the
applicable captured outcome boundary before scheduling device effects.

Run the hosted peer with:

```sh
nix develop --no-write-lock-file --command lake env lean --run sim/radio/ble_peer.lean
```

Run ordinary lowering, real RV64 object generation and the hosted lost-ACK
state/credit/cancellation check with an unused output directory:

```sh
python3 scripts/check_ble_link.py --work-dir build/radio/manual-link-new
```

Exercise the actual hosted Lean peer through two distinct sampled-bit packet
circuits, including lost ACK, duplicate rejection, CRC corruption and credit:

```sh
python3 scripts/check_ble_wire_peer.py --work-dir build/radio/wire-peer-new
```

These checks are software/component qualifications. The additive future
`lemmasim-silicon-ble-link-probe` will use base `0x10010600`, span `0x400`, PLIC
source 15 and explicit `core0-kernel-v0.5`; old 0.3/0.4 apertures stay unchanged.
Versioned0.5 descriptor/SoC integration is a separate workstream; this component
receipt does not qualify its registration. Actual guest/controller/IRQ execution,
bounded live native retries, whole-machine replay and companion durability
remain separate unfinished qualifications.
