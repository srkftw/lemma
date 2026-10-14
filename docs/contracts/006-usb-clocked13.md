<!--
# Clocked USB development binding13

This additive `lemma-silicon-dev/0.13.0` binding preserves the historical
0.6/0.8 decoded-packet paths and 0.11 rational100MHz PHY path. It selects
descriptorABI14/features15, the existing Kernel6 authority, Paper3, the same
128MiB external RAM/8192-frame pool, USB aperture0x10010a00/0x400 and PLIC16.
It has no product boot medium. USB MAC development limitations remain explicit.

The controller still clocks at100MHz and MTIME at10MHz. Each of the two
distinct generated PHY endpoints receives its own nominal48MHz source clock;
four rising source edges produce a12Mbit/s symbol. The native digital scheduler
uses integer2.4GHz quanta,24 per controller period, and separately retains each
source's signed rate offset, initial phase, fractional residue and level.
Admitted fixed offsets are -2500..2500ppm and phases0..49 quanta. Fractional
carry supplies every edge; it never replaces main-clock execution with a
rounded instruction-count or skips a required controller edge. Static source
offsets and the selected edge lattice are digital environmental inputs, not
physical oscillator qualification.

Each bridge has two128-entry Gray-pointer FIFOs with two-flop pointer
synchronizers. Reset asserts independently and releases after observed local
and remote clocks. A complete received packet can retain at most67 bytes;
completed-packet admission remains locked until its last byte or ordered abort
marker is consumed. Backpressure cannot overwrite that head. Reset invalidates
the buffered transaction. Analog metastability/MTBF and physical CDC closure
are not claimed by the digital synchronizer model.

Clocked-only, read-only USB words176/184/192/200/208/216 return PHYversion2,
nominal48MHz, nominal100MHz, CDCversion1, FIFOcapacity128 and packetbound67.
Writes reject. Historical controllers continue rejecting these addresses.
These are versioned circuitry facts; they are not measured frequencies or an
authentication/configuration shortcut. DTB compatible is
`lemma,usb-device-clocked-v2`, with existing `phy-sample-hz`, `phy-bit-hz` and
development-MAC fields plus `controller-clock-hz`, `cdc-version`,
`cdc-fifo-capacity` and `packet-bytes`. Guest discovery must check the actual
read-only words as well as the selected descriptor/FDT facts.

## State and external outcomes

Container10 is admitted only by the exact Clocked implementation identity.
Every published Machine API boundary is a completed100MHz period; the two
source phases and every generated FIFO/PHY state remain in flight and are
serialized. Logical source phases are validated against the reset origin and
current64-bit cycle without overflowing intermediate arithmetic. Restore also
checks generated clock-pin levels/main-low phase against the wrapper before
adoption. A checksum-valid inconsistent phase is rejected without changing the
live machine. Interrupted partial tick execution is explicitly unpublishable and further
run requests reject before clock advancement or external polling. This does
not advertise snapshots within an unfinished host API call.

Attached external-peer snapshots retain the existing observational Pending
policy: no polling, draining, completion or peer mutation. Restored private
forks remain suspended until an implementation-bound accepted raw-outcome tape
covers the exact prefix and requested horizon. They never resubmit an external
action. Main-rise handshakes are consumed once; independent PHY edges later in
the period can finish a packet without consuming that byte again. The replay
missing-outcome check occurs after all source edges in that controller period.
Full privately-live peer continuation and QEMU cached-state continuation are
separate unfinished obligations.

## Qualified component scope

`python3 scripts/check_usb_clocked.py --work-dir UNUSED --timeout 180 --jobs 2`
executes two distinct RTL endpoints, independent NRZI/bit-stuff/SE0/CRC vectors,
450 selected source-rate/receiver-phase cases and six complete generated-state
suffixes including packet/reset/backpressure phases. The independent scheduler
reference covers250 rate/phase cases through10,000 controller periods and
rejects skipped edges and corrupt phases. Selected source-edge error is bounded
by one2.4GHz quantum; this is not electrical USB certification or a full MAC
transaction-timing result.

`nix-shell tooling/silicon/sim.nix --run 'python3 scripts/check_native_usb_clock.py
--rtl-build NATIVE --rtl-source-root COMPLETE_ARCHIVE --work-dir UNUSED'`
links the original source-bound Machine/generated objects. The qualified
native phase fixture has three exact10,003-cycle suffixes with nominal and
opposite2500ppm clocks,145,141,488-byte checkpoints and checksum-valid negative
phase/container cases. It installs no guest ELF or external peer. Actual
Clocked guest transactions, notebook Ready/Save and connected Pending replay
need their own results; these component properties do not pass those gates.

## Genuine guest discovery and artifact authority

The exact `lemmasim-silicon-usb-clocked-bulk-notebook` and
`lemmasim-silicon-usb-clocked-bulk-initialize` selections use additive compiled
Lean roots and deployment `lemma-managed-sums-bulk-usb-clocked-deployment-v1`.
Existing Descriptor, DTB and NotebookKernel definitions remain byte-for-byte
unchanged. The new family validates binding13/ABI14/features15, full handed DTB,
Paper3 identity and staging, USB MAC1 identity and all six actual Clocked words.
No boot-NV/Product authority or additional Kernel6 aperture is granted.

Clocked USB FDT facts have nine distinct fixed-cell flags: boundary0/256,
PHY2/512, sample48M/1024, bit12M/2048, developmentMAC1/4096,
controller100M/8192, CDC1/16384, FIFO128/32768 and packet67/65536.
Completion requires the exact full node mask0x1ffff. Duplicate, missing, wrong
width/value or failed reads reject through the genuine checked Action path.
The independent raw fixture consumes actual compiled DTB bytes and tests30
ordered fault prefixes plus six actual readonly register reads and their faults
and mismatches. It does not fabricate a parsed source AST.

`nix develop --no-write-lock-file --command python3 scripts/check_paper_clocked.py
--dtb ACTUAL_PROFILE13_DTB --work-dir UNUSED --timeout 420` genuinely elaborates
both maintained roots, emits checked LLVM, optimizes through pinned LLVM20 and
generates RV64 objects. Separate exact50-body/caller authorities, eight typed
UTF8 pools, six-word hardware identity table, full generic IR and object
provenance, and four actual unsigned switch domains32/32/64/9 are load-bearing.
Quarantined source/pool/role/caller and machine guard mutations must reject.
All other ordinary kernel guards remain active. A component result is separate
from a whole linked image, actual physical packet execution and notebook Ready.

Original component broad-source FAILs remain retained. A separately labeled
reobserver proves exact recursive64-module NotebookKernel and50-module exporter
closures plus pinned tools/artifacts while identifying unrelated not-imported
course-package edits. It does not relabel an original result, authorize an
unbounded source change, or substitute for fresh whole-source guest capture.

The primary reference remains the pinned public USB2.0 specification base PDF
SHA256d39698a33486c399124af92bd02e4f978fd9a836b5cf4e52e6e4633eb1d89f61,
sections7.1.8–7.1.11,7.1.7.5,7.1.13.1.1 and8.3.5. Standard MAC response timing,
all token/error/retry/topology cases, electrical/RF effects, analog CDC behavior
and full USB conformance remain unqualified.

## Observed guest transactions and continuation

The fresh matched whole notebook/initializer pair uses complete326-input source
archives and ordinary strict audits. Schema6 package
`build/native/task006-usb-clocked-a2` retains both original role archives and
all254 native inputs. Public preparation uses `lemmasim build --backend rtl`
with exact `--rtl-source-root` and `--guest-source-root` per role; packing then
uses `native-bundle-build` with separate `--initializer-guest-source-root`.
No mutable ROOT source fallback or canonical replacement flags are admitted.

The actual Clocked initializer qualification at
`build/usb/clocked-pending-a1/result.json` passed in119.178seconds. Nine observed
cuts cover cold peer startup, held reset, each physical send/receive and EOP
guard phase, real owned-buffer submit/receive and a reset during a symbol.
Clocks were fixed+2500/-2500ppm with initial origins7/38. Full checkpoint and
applicable suffix bytes matched through9,724,069controller cycles. Snapshot
export never polled or drained the live peer. No-tape, insufficient horizon,
corrupt snapshot/tape and wrong implementation identities rejected unchanged.
A checksum-valid wrong future SENT reply failed against the actual generated
completion; that interrupted cycle then rejected further run/poll and snapshot
publication unchanged. This checks historical-outcome-only private continuation.

Observed checkpoints were145,568,304bytes, peak owned process-tree RSS was
1,046,476KiB and retained output was6,822,775,177apparent bytes. The1800second,
70Mcycle,4GiB/12GB bounds and owned-child cleanup held. Valid guest traffic
had no PHY stuffing/line errors or underflows. These are source-bound native
transaction and continuation results; Clocked notebook Ready/Save and full USB
MAC/physical conformance still require separate evidence.

## Complete selected-profile archive authority

The initial254-input native capture retained the manifest maps but omitted the
selected13 JSON separately bound by its original `profile_sha256`. The original
actual119.178second transaction receipt and254-input capture remain unchanged.
Schema2 successor `build/usb/native13-consumed-source-archive-a3/source` includes
all255 bound inputs, with an exact selected-profile path/hash checked against
that original manifest. It does not rewrite the compilation manifest or binary.
Current schema6 package `build/native/task006-usb-clocked-a4` also reconciles
the prepared-profile hash with the original native profile hash and retains the
selected bytes in its exact native source closure.

`python3 scripts/check_clocked_archive.py --rtl-build NATIVE --rtl-source-root
COMPLETE_SCHEMA2_ARCHIVE --original-native-source-root ORIGINAL_SCHEMA1_ARCHIVE
--native-bundle PACKAGE --execution-result ACTUAL_PENDING_RECEIPT --work-dir
UNUSED` separately qualified nine actual metadata/file mutations in2.687seconds.
Missing/corrupt/symlink profiles, changed selected identity and incomplete native
package closure reject. A deliberately unavailable ROOT profile cannot replace
an archived input. Direct explicit-archive and package replay both revalidate
complete authority before using the bound host load/clock facts. The API vectors
stop before subprocess/capture, and are not new CPU replay results. Only already
validated guest-source metadata is skipped by the raw artifact loop. Historical
profile/schema branches keep their previous semantics.
-->
