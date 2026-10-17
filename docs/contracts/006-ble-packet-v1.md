<!--
# BLE sampled-bit packet component v1

`lemma-ble-packet/1` is an executable **partial digital LE1M data-packet
component**, not Bluetooth5.4 support, a connected radio, RF qualification or
companion persistence. Existing machine profiles0.3/0.4 register no BLE device.
No address, PLIC source, DMA permission or application grant is added implicitly.
The generic Lean driver's base is a future explicit binding input.

Bluetooth Core5.4, version date2023-01-31, is the pinned primary specification:

- [Vol0B4.4, compliance requirements](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/consolidated-table-of-contents---compliance-requirements/bluetooth-compliance-requirements.html).
- [Vol6A1, PHY selection](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/low-energy-controller/physical-layer-specification.html).
- [Vol6B2.1/2.4/3.1.1/3.2/4.1.1, packet operations](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/low-energy-controller/link-layer-specification.html).
- [Vol6C4.1/4.2.1/4.3.1, independent numerical vectors](https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core-54/out/en/low-energy-controller/sample-data.html).

The future companion target selects GAP Central and Peripheral roles. That
requires the applicable GAP, L2CAP LE signaling, ATT/GATT and Security Manager
host requirements, plus mandatory controller/PHY requirements. LE1M is required;
2M/Coded, CTE, extended/periodic advertising, PAwR and isochronous features are
separate conditional feature choices. No such optional feature is claimed here.
Connection/security feature negotiation must eventually report actual support;
this component has no feature-report command that advertises incomplete support.
The detailed role-dependent mandatory closure remains unfinished.

The implemented slice has a one-octet alternating preamble,32-bit access
address,16-bit unencrypted LL Data header,0..27-byte payload and24-bit CRC.
PDU/CRC whitening is channel-dependent; preamble/address remain unwhitened.
The CRC polynomial is `x^24+x^10+x^9+x^6+x^4+x^3+x+1`. PDU bits enter in
least-significant-bit order; final CRC register bits emit most significant first.
Whitening uses a7-bit register seeded with `channel|64`; feedback is `0x44`
in the right-shifting representation. The official data vector initializes
`AA=0xAA08192B,CRCInit=0xC4C181,channel=16,header=0x16,payload=01 02 03 04 05`.
Its final CRC register is `0xA20B4B`; the independent harness retains the complete
120-bit official packet, rather than computing the expectation from RTL.

The RTL owns serialization, reception, CRC validation, whitening, staging and
queue publication. `Packet.lean` independently computes the same actual packet
operations and static uncoded address constraints through admitted scalar/fold
Lean. `Controller.lean` supplies privileged, finite PIO calls. Neither host
adapter nor fixture implements guest document, persistence or privileged policy.

The hard-decision interface is explicit: at100MHz, `tx_sample_valid` emits one
recovered bit every100clocks. A linked endpoint supplies those bits as
`rx_sample_valid/rx_sample_bit`. Each strobe denotes a completed1µs symbol.
This excludes the still-missing digital GFSK modulator/demodulator, Gaussian
filter, sample synchronization, AGC and calibration/status logic; those digital
obligations remain required even though analog RF propagation is excluded.
Two endpoints have separate buffers, CRC/LFSR state and counters. No shared
success flag, socket packet shortcut or host receiver constructs their results.

All accesses are aligned8-byte PIO, with zero-extended byte values in apertures.
Unknown/read-only writes, bad width/alignment, disabled access or invalid values
return the bus error. Invalid writes raise error event/fault2 without changing
configuration or buffers. The selected address constraints reject long runs,
advertising/single-bit-neighbor addresses, equal octets, excessive transitions
and insufficient transitions in the upper six bits. Random address generation,
entropy and connection uniqueness are separate missing policies.

| Offset | Access | Meaning |
| --- | --- | --- |
|0|R|magic `0x31544b50454c4d4c`|
|8|R|component version1|
|16|R|bits0TX active,1RX active,2RX head pending,3TX guard,4coexistence grant|
|24|RW|static-valid32-bit access address|
|32|RW|24-bit CRC initialization|
|40|RW|general-purpose channel0..36|
|48|RW|TX LL Data header0..31,LLID1/2,CP/RFU zero|
|56|RW|TX length0..27; zero requires LLID1|
|64|W|1submit,2release RX head,3cancel TX/RX|
|72|RW|latched IRQ events:bit0TX complete,1RX ready,3error; W1C|
|80|R|last fault|
|88|R|immutable RX header bits0..7/length bits8..15|
|96|R|clock counter modulo2^64|
|104|R|remaining local TX guard clocks|
|256+8i|RW|TX staging byte,`0≤i<27`|
|512+8i|R|immutable acknowledged RX head byte,`0≤i<27`|

TX submit captures a separate immutable buffer, header and length. Further
configuration/staging writes during an active TX/RX fail with busy3. Submission
while TX/RX/guard is active or coexistence disallows it also returns busy3.
No pending command is silently queued. Each complete TX/RX sets a15000-clock
local transmit guard. Peer inter-frame MAC scheduling, acknowledgments and
retransmission remain missing. This is not a connection-event implementation.

RX validates the complete CRC before publishing the one-slot immutable head.
While that head is full, another valid packet fails with overflow4 and retains
the old head. Bad CRC is fault1; missing/late/early decisions after acquisition
are fault5; unsupported header/length is fault7. All produce no RX publication.
Cancellation/coexistence withdrawal aborts transmission before another sample
and records fault6. New completion/error events win a coincident W1C for their
own bits; acknowledged older event bits clear. IRQ is level-active while any
event is latched. Completion counters count actual publication/completion only.

Reset or disabled power cancels in-flight work and clears all controller queues,
configuration, phase/dividers, CRC/whitening, synchronization, events and counters.
No DMA exists: storage or document bytes cannot be written by this component.
The future SoC binding must integrate actual reset/power/clock domains and keep
powered-down admission, cancellation and IRQ behavior identical.

Observational component snapshots use Verilator's complete generated scalar/
array state plus explicit pending wire decisions and clock counters. They copy
neither raw host pointers nor an external peer. Original endpoints are never
flushed, drained or fenced. Each restored endpoint owns a distinct model/context;
the stored pending input and subsequent generated decisions drive its suffix
independently. This qualifies these components' same-backend continuation only;
whole-machine session integration, corrupt-state public admission, native/Wasm
migration and irreversible physical/external-radio action policy are unfinished.

Run `python3 scripts/check_ble_packet.py --lane all --work-dir UNUSED_BUILD_DIR`
for bounded pinned RTL qualification, genuine Lean checked lowering and RV64
object generation. The Lean host Action fixture is explicitly a semantic model,
not execution of target instructions. A complete audited RV64 guest reading this
actual controller, PLIC admission, a fast model, SoC descriptors, companion
transport/service integration, L2CAP/reliable connection/security and radio/RF
qualification are still required. Bluetooth5.4 remains NOT COMPLETE.

The selected Kernel-v0.5 BLE probe also has one audited LLVM20 optimization:
`Link.headerResult` exchanges the two sequence bits into header bits2/3. LLVM
uses `llvm.bitreverse.i4` on a nibble masked to3, then zero extends the result.
Its [pinned intrinsic semantics](https://releases.llvm.org/20.1.0/docs/LangRef.html#llvm-bitreverse-intrinsics)
reverse four bits. Exact pre/post checked body hashes, the pure three-word
signature, one call site and the i4 declaration bind this admission to the
selected kernel. It grants no general bit-reversal, foreign helper, ISA
extension or legacy-profile authority. The actual RV64IM object uses shifts,
AND and OR; full object/instruction/helper closure is still required.

The expanded shared DTB `leafProperty` can generate two readonly branch tables:
property codes36..50 (six live cases) and leaf roles1..9 (five live cases).
The auditor binds both to the exact optimized source body and exact signature,
checks each unsigned subtraction/bound/scale/load/transfer, and follows each
transfer's own local targets when checking dominance. Sparse holes in both
maps return through their shared checked default. Byte, relocation, owner and
companion-code equality checks remain required. Earlier single-table historical
artifacts retain their own admission; this is not permission for arbitrary
indirect control flow.

-->
