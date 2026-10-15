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
| Boot, update, identity | Development preload explicit; recoverable authenticated image selection required | Development preload plus immutable ROM/NV medium | BootNV9/Paper2 transactions and Lean-authored reset ROM | Actual installation/status/handoff and initial Product9 cold Ready; partial payload/brownout recovery handoff; trial confirmation/fallback qualification continues, old faults retained | Observational ROM/fork state qualified; comprehensive recovery unfinished | Real product build/session/install commands; CRC integrity only, production authentication/antirollback unfinished | Physical nonvolatile/trust implementation absent |
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
