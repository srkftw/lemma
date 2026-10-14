<!--
# Task006 controller changes and physical observations

The full-depth pen now uses sixteen independent synchronous 16-row banks,
registered ingress data/address/enable, and an immutable registered head. A
nonfinal acknowledged pop applies two clocks of refill backpressure. All 256
entries, 64-bit sequence/time and remaining sample fields are preserved.
The optional profile0.2 synthetic panel sequencer is specified separately in
[its contract](../contracts/006-synthetic-panel-v1.md). Historical profile0.1
selects no sequencer and keeps its prior display timing. Physical results below
apply to the pen only; neither the new panel sequencer nor a complete machine
is physically qualified.

The source-bound consolidated literal workload passed at
`build/silicon/devices-task006-panel-sequencer/result.json`
(SHA256 `3ade71ad45e101c5b2a784393cc5cefd690a9bf16863bcf75861acfac790ed6b`).
It retains the legacy device/block observations, independently traverses every
pen bank/row twice and checks high timestamp bits, refill/reset/watchdog
cutpoints, plus every synthetic phase/row/source clock, immutable accepted
pixels, memory backpressure, reset retention and failed-scan cancellation.
These are real literal RTL tests, separate from Lean guest execution.
Independent wrong-bank selection and 32-bit timestamp-truncation mutations
both fail that observer. The quarantined sensitivity result is
`build/silicon/pen-task006-sensitivity-fixed-path/result.json`, SHA256
`1635a10908f5081635a67640b7a6d71c0ad2c726911c66c209253a42a71a637e`.

Fresh full-depth SG13G2 pen mapping passed: 230244 cells, 50026 flip-flops,
4,293,546.755399 µm² standard-cell area, zero unresolved cells/latches/residual
memories. Pipeline storage increases area 4.25% against the retained historical
4,118,404.159798 µm² map. This register memory is included circuitry; it is not
an SRAM macro or external simulation RAM. Result:
`build/silicon/physical/pen-task006-separate-banks-map/result.json`, SHA256
`55bee387766e60f4826e9a30f361e779d609f8868fb00d7f230b17c3fb0d2aee`.
The initial multidimensional-bank experiment was canceled during expensive
Yosys shared-memory priority analysis and retains FAIL; splitting the banks
materially changed the consumed design before the fresh run.

The pinned OpenROAD LEGACY repair phase double-closes an ECO journal when an
improved final pass also reaches `max_iterations`. The 34-cell
[journal reproducer](../../tooling/silicon/journal-repro.tcl) independently
produces SIGABRT with `journal begin/end/end`. On the identical circuit,
supported `WNS_PATH` performs a real buffer removal, improves WNS
−1.64→−1.58 ns and exits normally, retaining its timing violation. The controller
recipe therefore selects that supported phase, retaining sizing, buffering,
pin swaps, cloning, splitting and all timing constraints. This is a compatible
flow adjustment, not a source patch or a disabled repair stage. The pinned
[repair source](https://github.com/The-OpenROAD-Project/OpenROAD/blob/553ed63bc9f65277418adc82dffe1762c20aec9f/src/rsz/src/RepairSetup.cc)
contains the reproduced journal lifetime path. Source-bound sensitivity PASS:
`build/silicon/physical/task006-journal-source-bound/result.json`, SHA256
`eb38ca258010e55966d7e8b0b00f410ae1dfa2e1de874827c009f7df54d56a47`.

One bounded controller physical retry reached placement, CTS, setup/hold repair
and global routing without the assertion. At unchanged TT 1.20 V/25 C,
100 MHz/10 ns, 2 ns IO delays, 6 fF load, 0.25 ns clock uncertainty and 0.15 ns
transition: live global-route setup WNS **−3.542208 ns FAIL**, hold WNS
**+0.034896 ns MET**, zero reported slew/capacitance/fanout violations.
Placement repair initially reports −3.985 ns/1028 violating endpoints versus
historical −10.980 ns/46886; two observed moves improve it to −3.543 ns.
The global result is 289737 instances, 5,072,191.488 µm² cell area and
29.5724117% utilization. Unconstrained-endpoint checks report no warnings;
global TNS was not separately captured (repair progress retains its TNS).
These are global-route estimated parasitics, not routed extraction/signoff.

Detailed routing timed out during pin access after 80000 groups under the
900-second overall command bound; OpenROAD received SIGTERM and was reaped.
There is no final routed layout, router DRC count, process DRC, LVS, extracted
parasitics or post-route timing. The original pen abort and paper timeout remain
unchanged. New physical result is **FAIL_TIMEOUT**, not PASS:
`build/silicon/physical/pen-task006-banked-wns-path-layout/result.json`, SHA256
`6a05ef84130ec42372529fb854fd6492840fe99c590164b686db137ff89468a1`.
A compact actual artifact inventory including global geometry and estimated
SPEF is `build/silicon/physical/task006-controller-inventory/inventory.json`,
SHA256 `101c2cdf13ac9b1d242f1e414043853eb08519232a15907f0183491499bef081`.

The SG13G2 enclosure coverage blocker remains precise: legacy unqualified
ENCLOSURE clauses are imported without CUTCLASS associations and the pinned
router skips those general enclosure checks. No rule adapter was admitted;
fixed/generated/pin cuts, orientations and arrays still need independent
positive/negative geometric validation. This gap has not been established as
the cause of either timeout. No repeated paper route was run. Controller
closure still requires setup improvement, detailed routing, complete rule
coverage, process DRC/LVS and actual extracted timing; power/pads, memories,
compute/full-SoC closure and physical panel conformance remain separate.

The October12 continuation replaces the second refill edge's wide binary bank
multiplexer with a registered one-hot bank selection and parallel mask/OR.
Its decode is latched on the existing first refill edge; no public edge,
capacity, field width, queue order or reset behavior changes. The actual
full-depth literal device workload passed at
`build/silicon/devices-task006-onehot-a1/result.json` on pen source SHA256
`f73a3c556e1444cfdcb380a902496af041f64d99d880507020b54ff0a5fbf2e4`.
That test includes both traversals of all256 entries, high timestamp bits and
refill/reset/watchdog cutpoints; it is separate from guest notebook acceptance.

One changed-source, unchanged-constraint physical attempt mapped227520 cells,
50038 flip-flops,4275630.953999µm² area (0.417273% below the earlier banked map),
without unresolved cells, residual memory or latches. Actual100MHz global-route
setup WNS improved by0.135892ns to **−3.406316ns**, still **FAIL**. Hold WNS is
**+0.031082ns**. The currently critical reported path starts at `sample_y[43]`
and reaches `_351090_`,15.220151ns arrival against11.813835ns required;
the earlier binary-select-to-head path is no longer the worst reported path.
Global geometry is286697 instances,5019481.3536µm² cells and29.379903% utilization.
Unlike the previous run, the electrical report contains128 clock-buffer fanout
violations; none is waived. These remain estimated global-route parasitics.

The900s overall flow bound expired during detailed-routing pin access after
30000 groups. OpenROAD was terminated/reaped and the actual result is **FAIL**
with a timed-out command. Process checks were requested but never reached;
DRC, LVS, routed extraction and post-route timing are **NOT_RUN**. No complete
layout or signoff follows. The original failures remain unchanged, and the
SG13G2 enclosure/CUTCLASS gap is still not established as the timeout's cause.
[The compact source/tool/result receipt](006-pen-onehot.json) retains this
attempt separately. It used `--process-checks` in addition to the command below.

The October13 private-ingress continuation addresses that measured input-to-
ingress hold path. Payload/address registers now capture every nonreset edge;
the unchanged registered accepted-only strobe commits the preceding payload.
Head bypass, all 256 entries, full sequence/time widths, one-hot bank selection,
queue order, loss/ACK/reset behavior and the two refill clocks are preserved.
Source SHA256 is `2bab7e3356a1ebfa13366c19b57de7d63a757236ee6fff749409839707f76ce3`.
Unaccepted samples can change private register bits; dynamic power is unmeasured.
Existing immutable guest runtimes/checkpoints keep their original identities.

A bounded old/new external-interface miter matched all six public output
signals at 28,457 clock edges, including consecutive accepted samples, full
queues, invalid inputs and ACK/write/reset collisions. Literal MMIO checks
traverse the full depth and every field, including high timestamps and an
explicit test-only high sequence seed crossing the 32-bit carry. The unchanged
independent two-wrap/refill/watchdog corpus and existing Pen-v1 overflow,
exact-ACK/resynchronization/reset corpus passed. A quarantined bank-write
mutation that bypasses the registered payload compiled, then failed the miter
at edge 1,131. These are finite literal RTL observations, not formal proofs or
new guest execution.

One frozen-source attempt retained the original 900-second overall bound,
100MHz constraints, SG13G2 corner and supported `WNS_PATH` repairs. Mapping
produced 184159 cells and 50102 flip-flops, with no unresolved cells, latches or
residual memories. Fewer cells did not reduce mapped area: 4354753.951798 µm²
is 1.850557% larger than the earlier one-hot map. Final global-route setup WNS
improved by 1.673568ns to **−1.732748ns**, still **FAIL**; hold WNS is
**+0.034803ns**. The worst reported path is now a mapped refill-state flip-flop
to `next_sequence[63]`, arriving at 13.643834ns against 11.911086ns required.
Global geometry is 237630 instances, 5110058.016 µm² cell area and 29.369574%
utilization. All 128 clock-buffer fanout violations remain unwaived. These
are global-route estimated parasitics, not routed extraction or signoff.

Detailed routing again timed out in pin access, after 20000 reported completed
groups. OpenROAD received SIGTERM and was reaped; the actual result remains
**FAIL**. No router DRC count, process DRC/LVS, extracted parasitics or post-route
timing was reached. Original failures and the unresolved enclosure/CUTCLASS
coverage remain intact; that gap is not established as the timeout cause.
The [new source/tool/result receipt](006-pen-private-ingress.json) preserves
the exact candidate, bounded tests, failed flow and global ODB/DEF/estimated
SPEF as a resumable checkpoint. No unchanged follow-up route was launched.

The later free-running bank-read experiment is **not adopted**. Its private
read registers captured each clock while the existing two refill edges still
controlled public head publication. The 28,457-edge comparison against the
retained private-ingress source and independent full-depth/two-wrap corpus
passed; a quarantined wrong-row read failed at edge 1,131. All 256 entries,
fields, ordering, ACK/loss/reset and refill observations were preserved in
these finite tests. Private capture ran on more clock edges; dynamic power was
not measured.

One changed-source attempt used the same 900-second bound, 100 MHz constraints,
corner and repair recipe. Mapping produced 167,864 cells, the same 50,102
flip-flops and 4,273,921.637998 µm² area, with no unresolved cells, latches or
residual memories. Area fell 1.856186%, but global-route setup WNS worsened by
0.288327 ns to **−2.021075 ns FAIL**. Hold WNS was **+0.030106 ns**; all 128
clock-buffer fanout violations remained unwaived. Global geometry contained
217,626 instances and 4,978,085.8176 µm² cell area. These are estimated
global-route parasitics, not routed extraction.

Detailed routing timed out in pin access after 80,000 reported groups;
OpenROAD was terminated and reaped. No router DRC, process DRC/LVS, routed
extraction or post-route timing was reached. Group counts and geometry differ
between designs, so they do not establish normalized routing speed. The
enclosure/CUTCLASS gap remains unqualified and is not established as the
timeout cause.

The tested private-ingress pen source `2bab7e3356a1ebfa13366c19b57de7d63a757236ee6fff749409839707f76ce3`
was restored. The exact candidate, patch, focused test sources, mutation and
failed physical outputs remain archived under
`build/silicon/pen-task006-read-capture-owner-a1` and
`build/silicon/physical/pen-task006-read-capture-a1`.
[The unadopted experiment receipt](006-pen-read-capture.json) retains both the
area improvement and timing regression, with all original failures unchanged.
No second route was launched. The new worst path runs from `sample_y[21]`
through validation/acceptance control to `next_sequence[59]`.

A separate ignored prototype isolates the sequence counter's synchronous
reset and exact accepted-sample enable. The same external-interface corpus
and 32,768 finite guard combinations passed. One map-only observation retained
50,102 flip-flops and produced 184,075 cells. The mapped `next_sequence[63]`
data cone has 17 rather than 18 maximum cell stages; its `sample_y[21]` path
has 12 rather than 13, and the direct `refill[2]` path is absent under the same
observed one-hot FSM encoding. These are static graph counts, not timing or
speed measurements. This prototype remains unadopted; placement, routing and
physical STA are NOT_RUN. Its exact sources, tests and mapped artifacts are
included in the same receipt for the next physical inspection.

The subsequent separate-counter experiment is also **not adopted**. Its exact
accepted-sample enable preserved the same 28,457-edge external-interface
corpus and all 32,768 finite guard combinations. Removing `sample_ready` from
the enable compiled, then failed at edge 24,137. These are bounded RTL tests,
not formal proofs or new guest execution.

One fresh mapping and physical attempt kept the same 900-second overall bound,
100 MHz constraints, corner and repair recipe. Mapping produced 184,075 cells,
50,102 flip-flops and 4,354,297.781398 µm² area, with no unresolved cells,
latches or residual memory. The shorter static counter cone did not improve
placed timing: global-route setup WNS was **−3.229613 ns FAIL**, 1.496865 ns
worse than the retained private-ingress design. Hold WNS was **+0.031813 ns**,
with all 128 clock-buffer fanout violations still unwaived. The worst path
moved to `sample_y[35]` through validation/acceptance control to
`head_entry[156]`, arriving at 15.056982 ns against 11.827369 ns required.
These are global-route estimated parasitics, not routed extraction.

Detailed routing timed out in pin access after 80,000 reported groups;
OpenROAD was terminated and reaped. Router DRC, process DRC/LVS, routed
extraction and post-route timing were NOT_RUN. Geometry and group counts do
not establish normalized routing speed, and the unresolved enclosure/CUTCLASS
gap is not established as the timeout cause.

The tested `2bab7e3356a1ebfa13366c19b57de7d63a757236ee6fff749409839707f76ce3`
pen source was restored again. The exact counter candidate, patch, focused
checker and test inputs remain archived under
`build/silicon/pen-task006-sequence-enable-owner-a1`; the failed physical
checkpoint is under `build/silicon/physical/pen-task006-sequence-enable-a1`.
[The successor experiment receipt](006-pen-sequence-enable.json) retains the
actual timing regression and all earlier failures. No unchanged follow-up
route was launched. The observed validation-to-head-publication path and
remaining pin-access demand require a separately qualified physical change
before another attempt; no next candidate or physical closure is claimed.

Reproduce with unused output paths:

```sh
python3 scripts/check_silicon.py --lane devices --work-dir build/silicon/devices-006-new --timeout 600 --jobs 2
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/check_openroad_journal.py --output-dir build/silicon/journal-006-new'
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/silicon_synth.py --top lemma_pen --source sim/rtl/lemma_pen.sv --map --layout --output-dir build/silicon/physical/pen-006-new --deadline 900'
```

-->
