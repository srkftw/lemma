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

Reproduce with unused output paths:

```sh
python3 scripts/check_silicon.py --lane devices --work-dir build/silicon/devices-006-new --timeout 600 --jobs 2
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/check_openroad_journal.py --output-dir build/silicon/journal-006-new'
nix-shell tooling/silicon/eda.nix --run 'python3 scripts/silicon_synth.py --top lemma_pen --source sim/rtl/lemma_pen.sv --map --layout --output-dir build/silicon/physical/pen-006-new --deadline 900'
```

-->
