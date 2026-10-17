<!--
# USB full-speed digital PHY v1

The additive `lemma-silicon-dev/0.11.0` binding uses descriptor ABI 12,
features 15, Kernel 6, Power 2, Paper 3 and the existing USB aperture
0x10010a00/0x400/PLIC 16. Profiles 0.6/0.8 retain their decoded-packet boundary.
The packet controller remains version 1; PHY abort handling is enabled only for
the new binding. This contract adds digital circuitry, not electrical USB
qualification or complete USB2 support.

The primary reference is the [USB-IF USB 2 specification](https://www.usb.org/document-library/usb-20-specification),
base PDF SHA256 `d39698a33486c399124af92bd02e4f978fd9a836b5cf4e52e6e4633eb1d89f61`.
The pinned public archive was `usb_20_20250603.zip`, SHA256
`5fe9c53c04033818af396e8852b3acbca5c3a76ba92fab549fd81cd0ea7b3692`.
Sections 7.1.8–7.1.11 define the encoding, stuffing, SYNC and full-speed rate;
7.1.7.5 covers reset and 8.3.5 the CRCs. Vendor files remain ignored research
inputs; this repository does not redistribute them.

`lemma_usb_fs_phy.sv` evaluates on the declared 100 MHz clock. Its registered
phase accumulator generates exactly 12 sampling enables per 25 clocks, with
four samples per 12 MHz symbol. Hard-decision lines are `{D-,D+}`:
J=01, K=10, SE0=00, SE1=11. No voltage, rise time, cable or analog receiver is
modeled. The receiver retimes on differential transitions; no host code
decodes NRZI or substitutes a packet-success flag.

This 100 MHz lattice emits 80/90 ns symbol periods. Its mean rate is 12 MHz,
but it does not satisfy the complete USB source-edge timing obligation.
Section 7.1.13.1.1 allows 2 ns variation for consecutive differential
transitions and 1 ns for paired transitions; 10 ns edge quantization cannot
establish those bounds. The independent waveform oracle uses its predeclared
one-system-clock quantization bound, separately from the normative jitter
envelope. A finer clock domain with declared CDC and checkpoint semantics is
required for that digital timing gate. This gap is separate from analog and
electrical qualification.

The transmitter streams at most 67 bytes including PID/CRC. It generates
eight-symbol SYNC, NRZI, a stuffed zero after six ones including the final
SYNC one, any required final stuffed zero, two SE0 symbols and one J symbol.
It never stretches a physical bit for source starvation: underflow emits an
invalid SE1/EOP and cannot count as a transmitted packet. A two-symbol guard
prevents immediate reuse of the transmitter.

The receiver rejects malformed SYNC, SE1, seven consecutive ones, excess
capacity, malformed EOP and byte alignment. It tolerates the admitted bounded
last-bit dribble. Rejected physical packets remain quarantined until EOP or
an observed SE0 followed by three idle J symbols; it cannot seek another SYNC
inside the rejected packet. A short malformed EOP therefore cannot poison the
next valid transaction indefinitely. A complete output held by backpressure
retains its byte/last/valid. Streaming overflow aborts partial staging rather
than publishing a shortened packet. The controller clears only its partial
packet/token state on a PHY abort; already published endpoint heads survive.

The SoC contains two independent registered PHY instances. Hosted Lean still
produces the existing raw packet commands; the host PHY encodes them onto a
resolved digital wire and the chip PHY decodes them into the actual controller.
Controller output follows the reverse route. Equal simultaneous drives retain
their digital value; conflicting drives produce SE1. A modeled root reset
drives SE0. PHY reset qualification begins after 250 continuous system clocks;
the preserved controller/root policy still uses its declared 10 ms/50 ms reset
budgets. Host process transport never writes addressed/configured state.

The raw `SENT` result means the host PHY has completed EOP/release and its
guard, rather than merely having accepted a byte buffer. It is no durable
receipt. The existing guest Store journal and independently persistent Lean
peer still determine Save acknowledgment through a backing barrier.

Standard transaction timing is **unfinished**. The development packet
controller retains 100 us token/ACK timeouts and the raw process adapter polls
at 1000-clock boundaries. A standards-timed host needs autonomous token/data
batching and ACK sequencing at physical packet boundaries. Host wall time is
not virtual USB timing. SOF scheduling, suspend/resume/remote wake, hubs,
isochronous endpoints, high-/low-speed operation, electrical behavior and full
USB conformance are separate missing work. No allocated VID/PID or
certification is claimed.

PHY phases, buffer contents, cursors, bit/stuff counters, retained outputs,
quarantine, guard and reset counters are generated-model authoritative state.
The profile 11 container is version 8. It additionally admits a logical SEND
whose bytes have all entered the host PHY while physical TX remains busy;
restoring an already completed retained SEND rejects before adoption. Existing
profile container formats remain unchanged. A restored attached USB fork is
suspended until an implementation-bound captured outcome tape covers its exact
accepted prefix and future horizon. It never contacts/resubmits to the live
peer. Snapshot/tape export does not poll, clock, drain or mutate the live
controller. Circuit suffix qualification and whole-machine pending suffix
qualification remain distinct; QEMU's cache-continuation gap is unaffected.

`python3 scripts/check_usb_fullspeed.py --work-dir UNUSED_BUILD_PATH --jobs 2`
performs source/tool-bound literal qualification: primary-polynomial CRC known
answers, independent NRZI/stuff/EOP waveform comparison, real SETUP/status ACK
enumeration, 64-byte opaque transfers/lost ACK/NAK/corruption, permitted digital
source rates at every sampling phase, backpressure, underflow, reset and six
exact complete generated-state suffixes. This command alone does not establish
RV64 notebook, durable peer or whole-machine continuation acceptance.

`python3 scripts/silicon_compute.py build --profile lemma-silicon-dev/0.11.0
--jobs 2 --output-dir UNUSED_BUILD_PATH` builds the native implementation.
Its compilation is separate from guest execution. The native implementation
is archived with every consumed source, tool and generated binding input so
later guest work cannot silently replace its circuit or Machine core.


The selected guest configuration pair is
`lemmasim-silicon-usb-wire-bulk-notebook` and
`lemmasim-silicon-usb-wire-bulk-initialize`. Its public workloads are
`usb-wire-bulk-notebook` and `usb-wire-bulk-initializer`. Genuine Lean roots
`siliconUSBWireBoot` / `siliconUSBWireInitializeMedium` and
`dispatchUSBWireBulk` use the same Kernel6 construction, legacy address-space
layout, separately linked StoreUser1/NotebookUser2/ArithmeticUser3 images and
Surface2 transfer contract. This USB family acquires no BootNV, Product
address-space or health-confirmation authority.

The compiled guest validates descriptor binding11/ABI12/features15, the actual
Paper3/version/staging register and existing USB MAC1/BLE identities. Its
strict DTB family requires the Wire compatible string, decoded-packet-boundary0,
PHY1, 48MHz sampling, 12MHz bit rate and developmentMAC1 fields. Those immutable
PHY facts are associated with the exact native binding and generated circuitry;
there is no guest-readable PHY-rate register and none is fabricated. The raw
USB controller remains the existing version1 aperture. Paper staging is the
checked 512-byte +e00 window, independent of the BLE +600 aperture.

`scripts/paper_wire.py` separately validates all47 reachable source/signature/
effect and complete pre/post LLVM body authorities, their actual caller edges,
fixed binding11 wrapper arguments and the four bounded UTF8 readonly pools.
The notebook and initializer share46 exact bodies; each remaining public root
is pinned from its own genuine export. Independent literal-byte/index checks,
RV64 object/table inspections and actual-artifact mutations retain their
separate meanings. The two exact configuration names grant no broader language,
PMP or managed-runtime authority. Firmware and user units without the Wire
literal owner use their unchanged readonly admission; a reachable owner in
another role still rejects. Historical profiles retain their original bodies.

Full image qualification uses ordinary `build_kernel.py` then `audit_kernel.py`
with unused outputs and a complete consumed-source archive. The first initializer
whole audit failed on observer role dispatch; subsequent retained-artifact
analysis exposed a missing exact notebook recovery-length registry entry.
Both original observations remain retained. Fresh compilation and ordinary
strict audit after the narrow observer corrections are required for public
schema5 preparation. Complete artifacts do not establish real PHY transactions,
owned Pending continuation, Ready, Save or independent cold recovery; those
require their own actual guest observations under declared resource bounds.

An archived pair may use separate explicit `--guest-source-root` and
`--initializer-guest-source-root` arguments to `native-bundle-build`. Each
archive must match its own original complete build, provenance, audited image
and tool identities, and both complete consumed source inventories must agree.
The separate initializer argument requires an explicit notebook archive. The
existing single-archive/current-source paths retain their checks; no failed
archive check falls back to the current repository. This applies to USB
schema4 and schema5 packages and grants no new guest execution authority.

The first genuine Wire Pending run is a retained failure, not a timeout. Its
310-input audited initializer reported descriptor stage2/status169 before USB
service startup. Actual raw SETUP traffic reached the controller, but the guest
never configured it. The consumed Wire FDT property code58 reused reset's
flag128. The existing duplicate-mark guard rejects that property, and required
flag256 remains absent from the complete valid node. The
original startup/reset/chip-transmit continuation observations remain separate
from the missing six required cuts. A fresh source-bound guest after an
independently checked flag repair is required; neither the required property
mask nor the 70-million-cycle/1800-second fixture bounds change.

The repaired Wire leaf assigns code58 its independent flag256. A genuine
host Action interpretation of the actual compiled FDT reproduces the original
status169/flags255, then observes all13 valid property calls reach8191 after
that one correction. It rejects a wrong boundary value, duplicate property and
wrong cell width, and preserves exact write prefixes for all five ordered read
faults. A separate pre-IR rule requires the genuine zero-value fixedCell call
with flag256; its flag128 mutation rejects independently of whole-body hashes.
Fresh a3 notebook and initializer builds and ordinary complete audits pass,
with identical312-input inventories sealed into separate role archives.
Seventeen actual-artifact mutations reject for each genuine kernel corpus,
and46 shared complete bodies agree. The reusable component command's original
BLE-only ISA-observer failure is retained; the corrected kernel CSR/fence ISA
observer and five ISA/class/endian/flags negatives are separate observations.
These artifact results do not qualify the still separate real Pending/PHY run.

## Ordinary Wire notebook and retained observation

The immutable Wire11 notebook actually reached Ready605M, reconciled the lost
final raw-publication barrier after an independent peer restart, and completed
Undo, Redo, Next, Previous and explicit Save11 by2.770B cycles. Complete controller
pixels and the independently decoded opaque journal agree. The original full
campaign then failed in its frozen HELLO observer before cold startup; that
terminal FAIL and its original records, medium and checkpoint remain unchanged.

The admitted formatted peer has six actual persisted effects and a CRC-valid
outbox writer83/next7/pending0. The actual hosted Lean loadOutbox and Pending4
HELLO return that7; the original decoder call instead used its default1. The
explicit retained-artifact observer requires this initial receipt/outbox state
before decoding. All75 actual transactions, USB toggles/CRCs/receipts and exact
72 persisted effects match, including exactly one lost-barrier effect. Eight
actual captured-byte/outbox/effect negatives reject wrong sequence, writer,
CRC and missing or extra effects. This is a corrected observation, not corrected
guest policy, and does not turn the original campaign into a whole-scenario PASS.

`observe_usb_workflow_wire.py --profile lemma-silicon-dev/0.11.0` is an explicit
immutable deployment; the historical USB8 default remains. Its separate
schema2 receipt authorizes the passive companion archive only for the exact
Saved11/high-water72 boundary. Before/after file and metadata identities match,
the outbox has no pending transaction and materialized bytes equal the actual
acknowledged guest bytes. No owner, peer or guest is polled, drained or paused.
A separately supervised new CPU uses that archive through policy4 under the
original1.6B/7200 cold bound,4GiB/12GB caps and a7400second absolute deadline
including startup/cleanup. The actual new CPU reached Ready at 740M cycles in
3946.213 seconds; whole supervision completed in 3954.955 seconds. All 3.63M
controller pixels and acknowledged opaque bytes matched the final Save11
artifact, all 42 opaque transactions were READs, and the peer receipt log stayed
unchanged. No new Save or snapshot restore occurred, and all owned children were
reaped. A separate read-only artifact check compares the complete live/cold P5
files and before/after medium hashes. The original live campaign's terminal
HELLO failure remains unchanged. Wire11 unsuccessful Save after disconnect is
still unqualified; normative USB/full MAC/physical conformance remain separate.

-->
