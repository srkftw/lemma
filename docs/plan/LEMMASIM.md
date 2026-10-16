<!--
# LemmaSim first-class construction workstream

Status: partial — Task006 connects persistent native sessions, captured backing outcomes, canonical RTL durable ink, local RTL/Wasm execution and bounded managed mathematical services. The source-bound canonical bulk notebook now passes cold Ready, editing, acknowledged Save and independent cold recovery; earlier deadline failures remain failures. Finished-machine functionality, full fast timing/checkpoint scope, distribution and physical conformance remain separate incomplete obligations. The original G1-G7 gates and existing 56 software / six physical unit identifiers remain stable. This cross-cutting workstream runs **alongside** them; it is not a claim of completed implementation.

| ID | Deliverable | Depends on | Required exit evidence | Status |
| --- | --- | --- | --- | --- |
| S0 | Canonical machine contract and versioned assumptions | architecture baseline | interface inventory, UNKNOWN fields and reviewable compatibility policy | partial: frozen core/binding 0.1.0 and device/store ABIs; finished contract remains broader |
| S1 | Deterministic virtual motherboard | S0, G1 | real Lean-authored ELF boots, traceable RV64/MMIO/clock/reset events, negative tests | partial: actual one-hart RV64 binding/discovery/replay; no physical board result |
| S2 | Virtual memory/storage/power fault models | S1, G2/G3 | invalid accesses, flush/crash cutpoints and recovery independently checked | partial: owned memory and admitted block/flush/cut recovery |
| S3 | Virtual pen and e-paper controllers | S1, G4 interfaces | physical USB tablet bridge -> virtual controller -> guest driver -> pixels, with ordered traces | partial: pen FIFO/PLIC, guest ink/paper, recorded pressure; physical USB/manual NOT_RUN |
| S4 | Virtual interaction and distribution | S3, G4/G6 | installable Student mode; offline notebook; snapshot and restore | partial: persistent native lifecycle and exact fast/RTL subset checkpoints; installer, browser and finished-machine state remain incomplete |
| S5 | Developer and Laboratory modes | S2-S4 | reproducible replay, fault injection, inspectable device state, no bypass of guest enforcement | partial: bounded Developer inspection/replay and Laboratory fault workflows |
| S6 | Integrated virtual finished machine | S4/S5, G5-G7 | complete documented student workflows; proof and tutor trust boundaries checked | partial: bounded guest mathematics/course/hint/review/save/cold slice; proof kernel, packages, permissioned tutor and complete workflows unfinished |
| S7 | Physical/virtual conformance | S6 and custom open RV64 SoC embodiment | independently captured physical traces meet per-interface equivalence relations | blocked: physical hardware unavailable |

## Rules

- One machine contract governs both embodiments. The virtual device is a permanent product, never an interim development-only test harness.
- Preserve historical `LEMMA_VM.md` boot profiles and Task 001/002 evidence. Do not relabel an existing QEMU smoke test as completed virtual hardware.
- Same guest artifacts and functionality wherever possible; board-specific differences must be narrow, versioned, and conformance-tested.
- Student, Developer and Laboratory modes are one implementation with different host controls. Lab fault injection cannot quietly broaden guest privileges.
- Host-only implementation languages are allowed for simulation infrastructure, but target OS, kernel, runtime, mathematical code and maintained compiler logic retain Lean requirements.
- Every phase has executable pass/fail tests and records provenance. A specification-only check is not device implementation evidence.
- The active physical dependency is the custom monolithic open RV64 SoC. Earlier board/cartridge and OEM protocol discussions remain historical; no supplier package is assumed for the RTL development backend. Physical analog and panel inputs remain explicitly unverified. `SIMULATED_ONLY` and `PHYSICAL_CONFIRMED` are distinct evidence states.

## Relationship to established gates

G1: capture board/ISA boot profiles, then build S1 in parallel with Core0. G2/G3: connect traps, allocation, capabilities and durability to S2. G4: implement S3 with authentic guest digitizer/display drivers rather than host ink shortcuts. G5-G7: target the identical virtual and physical learning functionality. S4-S6 provide the additional finished LemmaSim distribution, reliability and usability gate; S7 establishes the physical counterpart.

## Initial repository layout

- `LEMMA_MACHINE_CONTRACT.md`: top-level normative machine target.
- `sim/`: host simulation backends, device models, launch profiles and user distribution (implemented Task004 hardware binding and command surface).
- `conformance/`: independent virtual input/device/store observations and checks; physical trace comparison remains unverified.
- `docs/plan/LEMMASIM.md`: durable sequencing and evidence policy.

[Task004 evidence](../evidence/004-lemmasim-durable-ink.md) binds its tested
implementation, retained failures, CI and offline export. The observed notebook
is a foundation for mathematical documents; S6 proof/tutor integration and S7
physical parity remain unfinished. Keep the named partial scopes and do not
replace the existing G1–G7 completion requirements with this subset.

## Task006 capability inventory

The columns distinguish behavior, circuitry, guest execution, timing/state,
distribution and physical qualification.
The Task006 checkpoint and evidence report record execution identities; a
model or an interface specification cannot close a later column.

| Subsystem | Specified behavior | Functional model | RTL | Lean guest integration | Fast timing / exact state | Distribution | Physical qualification |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Scalar CPU, M/S/U, Sv39, PMP | Development RV64IM binding, declared clock/counters; extension roadmap retained | QEMU scalar CPU | Existing open processor | Kernel and isolated services | Actual404 guest-issued S/U CSR cases and native arbitrary U-mode counter suffix; full ISA/exception/translation coverage and timing parity unfinished | Native and same-core Wasm | Not closed |
| RAM, fabric, DMA ownership | Checked pool, byte enables, bounded pending beats | External128MiB RAM; configurable latency | Fabric and controller boundary | Indexed deterministic allocation, owner accounting, actual zeroing/pinning/isolation | Hardware and wrapper pending beats serialized; full boundary campaign unfinished | Actual8192-frame canonical bulk RTL Ready609M/2872.596s, full edit/Save/newcold; older1.427B observation and original failures retained | Large physical RAM absent |
| Boot, update, identity | Development preload explicit; recoverable owner-authenticated image selection required | Development preload plus immutable ROM/NV medium | BootNV9/Paper2 transactions, Product10 executed-refresh/reset and genuine Lean ROM | Actual CRC installation/status/handoff, initial cold Ready, trial confirmation/fallback and payload/publication/power slices retained separately. New public-development-key HMACROM actually rejects badMAC240, publishes correct image and executes authenticated payload; full authenticated notebook/cold campaign RUNNING | Observational ROM/fork state qualified; comprehensive authenticated update/power and arbitrarycached continuation unfinished | `lemmasim product` plus additive `lemmasim-auth --public-development-key`; production ownerkey/entropy/trust/antirollback OPEN | Physical nonvolatile/trust implementation absent |
| Exact machine checkpoints | Backend-private observational state and private forks | CPU/RAM/controllers/private clocks and captured backing outcomes | Savable caches/TLBs and pipeline/fabric/controller signals | Selected queued-pen/in-flight-panel/USB Pending guest suffixes observed exact | Default QEMU continuation GAP_CONFIRMED; opt-in logical data-TLB stale/SFENCE suffix passed, executable/TB/jump/interrupt scope unfinished; native Pending forks require captured tape | Exact native/Wasm cold657M and predeclared raw suffix658000003 authoritative equality; separate same-Wasm suffixes | Not a physical claim |
| Pen |256 samples,64-bit sequence/time, loss/resync | FIFO, raw tablet/pointer transport, warm reset watchdog | Banked synchronous FIFO, cached head; changed one-hot refill literal check passed | Immutable guest ink, warm writing/Save/cold path | Selected raw-input/reset suffixes; full timing parity unfinished | Native and browser raw events | Tablet/manual conformance unverified; setup/routing not closed |
| Paper/panel digital control | Accepted updates, three synthetic phases and scan clocks | Functional sequencer | Versioned sequencer circuitry | Real driver and regional updates | Selected phase state preserved; full reset/latency parity unfinished | Controller pixels presented natively/WebGPU/2D | Synthetic program; physical panel unqualified |
| Local durable storage | Checked DMA and acknowledged barrier; partial failure is not rollback | Shared native/QEMU/Wasm read/write/barrier outcome interface | Existing block controller | Actual Store/recovery/notebook; aligned checksum64 words/sector, unchanged durable bytes and fast course/Save/cold/failure qualified | Recorded outcomes/private replay; native Pending exact suffix qualified, portable guest qualification unfinished | Local files and qualified browser-origin OPFS flush | Physical storage absent |
| Power, clocks, interrupts, reset | Cooperative suspend/wake; electrical domains/watchdog/brownout required | Power-v1 plus opt-in Power-v2 watchdog/power-good/brownout | Power-v2 domain cancellation and eight safe reset edges | Lean authorized syscall68 plus real WFI watchdog/cause/epoch guest qualification | Exact RTL safety/reset suffix qualified; Fast-v2 phase qualification and comprehensive timing unfinished | Native and browser controls | Power-domain/CDC/clock implementation unfinished |
| Companion storage/transport | Bounded framing, durable receipts, reconnect and lost-ACK reconciliation | Independent hosted-Lean opaque peer and durable client outbox | Existing block path reaches peer | Actual guest Store→peer barrier→ACK, lost ACK/both restart/cold recovery; target companion service unfinished | Native Pending observational capture and isolated tape suffix qualified; QEMU retry/cache scope limited | Normal companion build/init/serve/client commands | Not closed |
| USB | Enumeration/control/data endpoints, toggle/stall/cancel required | Raw socket transports modeled packets and captured actual EOF/errors; genuine hosted-Lean policy4 bounded delayed-restart receipt retry; opt-in native live-recovery/1 durable attach/global IDs, real public control and exact private captured suffixes qualified | EP0/control/data/toggle/ACK controller with disjoint Paper2 staging | USB8 actual cold Ready600M, raw ink/Saved5 through persisted lost ACK and peer restart; independent policy4 new-CPU cold680M/allpixels passed; actual Undo/Redo/Next/Previous/explicit Saved11 plus independent735M/fullpixels cold qualified; Clocked13 Sums recovery now qualifies real Failed/offline ink/EOF→reattach→old-receipt dedup→new barrier/remount→Saved17,109 unique effects and independent800M/fullpixels cold with64 READ/zeroWRITE/BARRIER (original live oracle FAIL retained); newClosureRecovery3/Doc8 full guest pair and schema8 nativepackage are compiled/audited, connectedCPU remainsNOT_RUN | Native captured queued/Saved5 suffix655→715M exact without peer contact; live-peer/no-tape/horizon rejection remains | USB8 native package and public usb-pending build; full workflow/cold qualification and USB PHY/conformance unfinished | Not closed |
| Wi-Fi6/802.11ax | Complete admitted digital MAC/baseband/PHY and calibration status; final HE normative scope remains open | CommonOFDM signed-complex sample model | Independent two-endpoint BCC/interleave/IFFT/DFT/Viterbi/CRC slice, loss/corruption and in-flight suffixes qualified | Genuine Lean codec executes real RV64 bytes; same-machine12 queue/IRQ integration pending | Component exact suffixes; full acquisition/MAC/HE/timing/state unfinished | Component tools; native12 build only, actual integrated guest pending | Analog/RF separate; digital unfinished |
| Bluetooth5.4 | Complete admitted digital controller/link/PHY and coexistence | Bounded manual LE1M packet/link slice; full5.4 feature scope unfinished | Actual independent CRC/whitening/sample exchange, timing, corruption/loss/coexistence/reset/checkpoint slice | Ordinary Lean packet/controller/link objects; whole-machine binding integration pending | Component exact suffix qualified; full link/radio timing/state unfinished | Development component tooling; product path unfinished | Analog/RF separate; digital unfinished |
| Runtime, G2 | Genuine managed-language lowering, lifetime, OOM and isolation | No host runtime performs guest work | Machine substrate | Ordinary records/sums, ByteArray, full-width Array UInt64 and bounded40-byte UTF8/String/Option execute in isolated Arithmetic with real COW/graph reclamation; actual course/save/newcold and31-slot OOM containment PASS; Closure7 actual rational/Q[x], Doc8 migration, OOM237/death96 and ink/Save/newcold qualified; general runtime/recursion/proof substrate unfinished | Historical profiles retain their language scope; actual Array/String OOM preserves ink and evidence boundaries | Prepared Array/String and packed-course native/static archives; packed renderer fast Save/newcold/failure qualified, original Array browser cold FAIL retained, private course reaches actual isolated Unsupported/OPFS Saved; new packed/browser cold and String browser execution unfinished | Not a physical claim |
| Mathematics/checking, G4/G5 | Raw ink separate from typed revisions and scoped trusted evidence | No host mathematical authority | Machine substrate | Isolated rational/polynomial service through Protocol7/Doc8 with real ordinary dynamic closure selection, exact domain/assumption binding;  actual Doc5→6→7 preserves mixed implementation histories/assistance, editing invalidates current applicability; proof kernel/theorem closure unfinished | QEMU real RV64 course/save/newcold/OOM/migration acceptance; actual local Closure browser cold/raw Save/opened Doc8 with complete course pixels; actual edited5/7 clears applicable Verified11, preserves history, then request84 guest-checks Invalid12→OPFS Saved24 with all2496 owned bytes and allpixels; actual hintSaved25 and manual-reviewSaved26 preserve fullDoc8/history/ink/allpixels; newbulk same-origin durable-only coldReady712.45M/163reads and reopened all2496Doc8/all3.63Mpixels with Invalid12/Verified11history/hints2/manualreview pass; finished workflow incomplete | Original course in guest image; immutable package installation unfinished | Not a physical claim |
| Courses/learner state, G6 | Packages, rights/source anchors, prerequisite graphs and uncertain estimates | Original authored sequence compiled into guest | Machine substrate | Durable ordered attempts/assistance, migrated records, explainable overridable/disabled review; actual cold acceptance | Fast guest observations; no learning-gain inference | Actualmounted Await guest loads both4040/4058byte package editions throughStore with complete ownedRAM/CRC checks (55M startup,99M each load); managedWorkspace compiles, installed-package Notebook integration unfinished | Not a physical claim |
| Tutor/learning policy, G7 | Permissioned untrusted proposals, independent assessment and rollback | Provider/communication adapter unfinished | USB/radio path unfinished | Authored hints distinct from a tutor; policy/evaluation extension unfinished | Not qualified | Not distributed | Not closed |
| Native/browser and developer distribution, S4–S6 | One machine, build/run/inspect/raw events/snapshots/replay and enforced user roles | Local static RTL/Wasm worker and immutable native development closure | Same generated RTL core | Same audited guest; selected String bundle initializer now actually executes; native helper compiles images | Actual Byte/Bulk browser Ready, writing and durable-only cold; exact native/Wasm657M+raw suffix and same-Wasm Pending checks; original writing/deadline FAILs retained; course workflow unfinished | Real OPFS private forks/export/import/replay and bounded cycle/host/completed-panel controls; prepared Array/String/packed-course bundles and optional original-source SIMD/LTO compilation with exact4-cut authoritative comparison/18.7% host reduction; fixed32-bit capture core actuallycold Ready878.55M/5332.565s/192MiB with allpixels/unchangedmedium/250validREADs, exact same-Wasm course suffix; fixed cold lineage now acknowledges Saved46 after actual check/hint/edit/resource/review; fullclose475M and40M suffix remain failures, independent same-origin Saved46 cold PASS with all313 READs/pixels and reopened fullDoc6; fresh Closure/UserCopy local cold Ready713.85M/3901.040s/192MiB, raw Saved22/allpixels and loadedDoc8/fullcourse pixels qualified,29M course and15.8M in-flight-save same-Wasm recorded continuations exact; entire native713.85M authoritative state matches independent browser cold atsamecycle (original native500MFAIL retained); fresh Invalid12/Saved24, hintSaved25 and manual-reviewSaved26/allpixels qualified; ordinaryUI exposes launch-local guest Pending/Saved/Failed reports; b17 predates pointer-loss fix, new07a pointer-fix bulk pack actualsame-origin coldReady712.45M/3146.484s/192MiB/163READs/allpixels and reopened fullDoc8/course pass; publication/handle-fix frontend018b actualcanvas pointer→Saved29/barrier181/allraw+3.63Mpixels passes57.6M/247.212s simulation/330MiB inprivatecontinuation; control2 active-private-medium names actualStudent copy/Close/Open qualified, newCPUcoldSaved29 PASS732M/4135.304launchseconds/3682.301simulationseconds/192MiB/all256MiB/all3.63Mpixels/exact174preplannedREADs/zeroWRITE+BARRIER; actualcorrupt32byte restore rejection preserves complete145626900byte checkpoint/budget/privateName, active-run scheduling/privateflushfailure separately host-qualified; newEntry2 original377 wholepair/fullaudits and canonicalnativepackage qualified, actualSaved26 coldReady669M/2452.566s/193324KiB/163READs/allpixels; rawSave29+56M/215.854s, independentSaved29 coldReady688M/2438.845s/193340KiB/174READs/allpixels, failednewrawSave+59M/203.832s/noSaved30/prior29medium+allpixels/3volatilesectors; originalUndo200MFAIL retained, currentnavigationOPEN; standalone installers/browser compiler/complete roles/redistribution unfinished | Full-machine conformance unverified |

Standalone pen mapping and improved global-route estimates do not close the
physical column. Detailed routing, complete SG13G2 rule coverage, process
DRC/LVS, extraction and post-route timing remain separate required results.

-->

October14 connected implementation update: the existing PackageClosure
four-process deployment now has complete genuine matched initializer/notebook
compilation and full ordinary audits (384 inputs,584.576s, both691736B ELFs).
It is prepared on the same native and browser machine cores. The browser's
Developer/Laboratory course file control sends opaque bytes through modeled
UART and displays only complete guest installation reports. Host transport
and permission checks pass; new installed-course guest and browser acceptance
are running/prepared and remain open. This advances G2/G4–G7 and S4–S6 without
closing general runtime, proof-kernel, tutor transport, whole distribution,
exact fast/checkpoint or physical obligations. The current checkpoint and
existing capability inventory retain those separate statuses.


Current connected observations: the package-enabled canonical native cold guest
reaches Ready978M, and the identical guest on the existing browserRTL/Wasm
worker reaches coldReady977.55M with192MiB heap. Complete acknowledged medium
and controller pixels match at their separately observed Ready cuts. Native
edition3 installation and immutable duplicate rejection execute in84M and11M
additional cycles; full course/check/learner/cold acceptance remains open.
ClosureRecovery3's independent copied-peer newCPU cold gate nowPASSes at885M
Ready plus120M for rawCOURSE/full2496-byte mathematics and controller recovery,
with no new write/barrier/math request and peer148/outbox149 unchanged.
Guest S-WFI/M-timer/native waiting-fork and fast immediate-reset semantics have
separate evidence; original native600k reboot completion failures remain. These
advances do not close any broader digital, fast-timing/checkpoint, distribution
or physical obligation. Exact receipts remain in the existing capability
inventory and006-session-state.md.

Local storage now captures actual Linux file-limit partial writes with the
default signal disposition. The current exact-pinned QEMU/RV64 command passes
guest Compact -> raw failed Save -> independent cold recovery of all bytes and
pixels -> resumed raw Saved8. Native Pending partial-write/fsync failures have
their own exact private suffix qualification. The original-source canonical
Wasm port now preserves those two authoritative suffixes and actually flushes
private replay barriers even for recorded original errors; a failed private
barrier poisons and stops the fork. Current native and static browser packages
retain the same audited Layout2 guest. These advance the existing local-storage,
checkpoint and S4-S6 columns; full new package-course/browser cold acceptance,
archived-fast refresh, general fast timing/caches, distribution rights and
physical qualification remain separate open obligations.

The later Layout2 browser cold now reaches actual Ready977.55M within its
original bound, with all35 external outcome boundaries, all256MiB observed
bytes and all controller pixels matching the retained native cold prefix.
The native installed-course open remains FAIL at its original400M cap: its
retained RAM had copied2944/4040 bytes. A private diagnostic identifies repeated
kernel registry validation as a major cost. The new count-borrow component
retains live frame authority and passes host/genuine-LLVM guards; complete
fresh target qualification and a course speedup are still pending. Repaired
fast and RTL runtimes can now be packed with an unchanged audited guest pair
through the normal native-bundle-build command. These observations retain the
existing separate digital, timing/checkpoint, distribution and physical gaps.


The registry-count source now has an independently audited matched guest pair
and prepared native/browser bundles. A new fast CPU improves the comparable
original-medium Ready from269M to250M instruction-clock units; its100M course
view stillFAILs. New original-bound canonical native/browser scenarios are
running, not passed. A subsequent descriptor direct-load component preserves
all ordered effects and live checks while reducing static O2 base call sites
34->5; full new target execution remains required. Candidate552 CI isFAIL9/10
because an independently demonstrated packet/payload observer assumed global
adjacency across two preemptible Console syscalls. Its corrected correlation
retains all exact values and per-transaction order, with fresh full qualification
pending. These advance processor/memory tooling and packaging evidence only;
G2/G4-G7 installed-course workflow and the separate parity/distribution/physical
obligations remain open.

The direct-load pair now passes fresh full audits and has prepared native/static
bundles. Actual fast guest execution connects course text, exact checking,
revision-bound history, hints/assistance, review controls and acknowledged raw
ink. Its original3B aggregate still fails during Close. Independent cold boot
recovers every acknowledged byte/object and every pixel of the actual original
guest framebuffer; the original Pending-versus-Saved footer comparison remains
a separate failure. Registry-only RTL coldReady improves978M to847M target
clocks on the same medium. Complete connected RTL/browser course acceptance,
general managed/proof runtime, tutor transport and the separate parity,
distribution and physical obligations remain open. Exact b137 CI passes10/10
without skips; later source needs its own candidate. See the existing checkpoint
and006-descriptor-direct-integrated evidence for identities and limitations.

Software3 text-delta now has a fresh full audited pair and prepared native/static
bundles. Its same39 fast course/math/learner/ink phases use2.805B versus2.929B
instruction-clock units; original3B Close failure remains. Original-bound RTL
software3 execution is running. Registry-only browser coldReady846.10M matches
all35 native I/O boundaries, all backing bytes and every controller pixel. The
original native400M course failure remains substantive: its package is fully
read/validated but rendering is unfinished. Software4 pure white-word computation
now qualifies across text/controls/mathematics with exact pixels and ordered
memory effects; fresh whole artifacts and performance remain required. This
advances the existing guest/product lane while all wider G2/G4–G7, exact timing/
checkpoint, distribution and physical obligations keep their separate status.

Aligned2/sourcefe87446 now has a fresh395-input canonical matched pair and both
full ordinary audits. The existing G2/G4–G7/S4–S6 slice passes all42 fast phases
under original3B/900s, including actual course/checker/learner/ink, complete cold
pixels/objects and full cold reopen. Actual2-byte partialpwrite/EFBIG Failed,
newcold and ordinary retry/rawink also pass. Total instruction clocks2.639B
versus2.649B with the same actual input/runtime; this does not establish RTL
timing parity. Native7 cold Ready802M passes, then its original400M COURSE
bound fails with a required controller WAIT_TIME refresh still active. Browser7
cold Ready801.4M passes; its original400M COURSE endpoint also fails: body RAM
and staging are exact, but9 dirty tiles and11,835 body pixels remain incomplete.
Their prior source6/native and source4/browser400M failures remain failures.
The separate four-process companion recovery4 acceptance is also running.
See [aligned2 evidence](../evidence/006-course-aligned-delta-v2.json); all broader
G2/G4–G7, fast/checkpoint, distribution and physical obligations remain open.


Control spans1 is the next additive implementation in the same Notebook, with
artifact cohort8. Full scalar bytes/footprint/fault repair and genuine component
checks pass; all four ordinary catalog/IR/object roles and actual LLVM semantic
mutations are qualified. Canonical controls+identity stores fall20,520→3,615,
with no framebuffer reads; this is not yet a CPU speedup claim. Fresh whole
images and actual native/browser controller/workflow qualification remain
required. See [control spans1 evidence](../evidence/006-course-control-aligned-v1.json).


Control spans1/source092bfc0 now has a fresh406-input initializer/notebook pair
and both full audits,1012.052s supervised/1.917GB peak. The same42 fast phases
and real partial-pwrite failure/newcold/retry pass; total2.615B versus2.639B
instruction clocks, no controlled host speedup or RTL timing parity claim.
Native8 and browser8 are running original cold/400M bounds. Static browser
packaging now includes a standalone extracted stdlib launcher and original
validator/server; actual isolated launch from/tmp and exact HTTP assets pass.
This closes that launch dependency only: native runtime relocation, browser-local
compiler, full browser workflow and redistribution permission remain open.
See [distribution evidence](../evidence/006-local-browser-distribution-v1.json).

The same canonical G2/course notebook now has an actual fast course-preserving
explicit Save/cold-reopen slice at cohort11: raw annotation, Pending/Saved detail0,
complete course/controller pixels and every medium byte survive a new cold CPU.
The checked-in `scripts/check_course_save.py` is reusable; fast instruction units
remain distinct from canonical RTL clocks. Both fresh canonical/companion11 whole
pairs have full audits/source seals. Latest RTL, local Wasm and companion Saved16
cold cases are running independently; no whole-machine gate is relabeled complete.
The older9 RTL check reached revision-bound5/6 Verified/workspace20, then failed an
early controller-label assertion with37 dirty tiles pending. Its private remaining-
budget suffix displays VERIFIED with unchanged bytes; the full original campaign
remainsFAIL/incomplete. See the existing
[dirty-batch/course Save evidence](../evidence/006-notebook-dirty-batch-v1.json).

The same guest product lane now includes ingress-idle policy2: only the empty
installer-header boundary backs off, preserving original partial-input handling.
Fresh canonical whole builds/audits and fast course/annotation/idle-Save/newcold
pass with an independent complete annotation plane. Comparable cold Ready falls
from249M to185M fast units; the6phase case from762M to576M. Extracted native
UART/install/pending-fork/newcold/Load also passes. The actual failed-first-FLUSH
case preserves visible provisional ink, reports Failed without Saved and cold
recovers prior acknowledged full display/bytes. This known injected failure does
not establish rollback after actual OS failures.

Source11 exact RTL has completed cold Ready, course/raw annotation and explicit
Save at1.197B clocks; its independent second cold remains running. New policy2
RTL and Wasm cold runs retain their original bounds. Companion compilation
succeeded but its full audit rejected the new171-function installer against the
historical169 catalog. The versioned authority repair retains the original pins,
independently compares every common preIR function and rejects a valid LLVM cap
mutation. Both corrected companion whole linked audits/source seals now pass;
actual new peer cold remains required. Browser11 also cold-opens the saved-ink
medium to Ready827.8M/6677.447s,192MiB heap, with independently exact complete
notebook/ink pixels; course/Save/reload and useful latency remain open. G2/G4-G7,
S4-S6, fast/checkpoint, distribution/rights and physical status stay separate.
