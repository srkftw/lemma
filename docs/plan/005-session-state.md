# Task 005 checkpoint

Snapshot `1e05f0809395a1c5a9efa6ae403ea38ee74efcd4`, branch `task/005-open-silicon-bringup`, existing [draft PR #7](https://github.com/srkftw/lemma/pull/7) against main. Reviewed main `23b19296f5938821cdc5c092c3921e55e0067a28`; PR#5 merged. Exact PR#6 specification `dee6415dcb42dd242fa744b8dd271e5618873d50` was incorporated with attribution as `ef635f55916277c91ee51ab7adf10476bf444669`; PR#6 remains separate. No merge authorization. This publication retains each tested implementation identity; it is not a new execution campaign.

**Task remains in progress.** Current RTL A/B/C prerequisites, notebook startup/first controller completion and bounded SoC mapping have observed results. The fresh RTL pressure-stroke/edit/Save session (D2) is **RUNNING**, with no completed durability/cold-reopen result. Failed FLUSH/storage cut (E), full replay and cross-backend comparison are **NOT_RUN**; ongoing work is not PASS.

## Running implementation

`lemma-silicon-dev/0.1.0` is a distinct development binding of first-class LemmaSim, subordinate to the canonical contract. One CVW RV64IM hart (M includes Zmmul), Zicsr/Zifencei/Zicntr, M/S/U, Sv39, 16 PMP entries, 32-entry instruction/data TLBs, 4 KiB instruction cache, **no data cache in actual RTL**. One numerical profile generates Lean/RTL/FDT/descriptor values. Actual architectural reset at ROM0x1000 runs Lean-authored typed ROM instructions -> genuine Lean M-firmware -> existing S-kernel -> isolated U images. Enforced 4 MiB DMA bounds, pinned buffer lifetime and reset quiescence define coherence. The development guest uses 1024 frames/quota128/four-page stacks; it does not claim the canonical 32 MiB floor.

Reusable RTL implements AHB fabric/error/backpressure, timer/PLIC/UART, pen identity/FIFO/loss/resync, paper command/tile/latching/Busy/reset sequencer and VirtIO split-ring block DMA/completion/FLUSH. Fabric retains owner/payload while stalled and through terminal AHB error; block retains stalled requests through reset/error, prevents unsafe queue mutation and gives new events priority over simultaneous ACK. Compiler policy, allocator/scheduler, capabilities/IPC, drivers, codecs/journal/recovery, notebook and rasterization remain shared genuinely elaborated Lean -> checked Core0 -> LLVM/LLD with strict provenance audits.

Fresh Notebook09 `text.bin` is49,216 bytes, hence13 text pages and126 owner pages total (21 table/registry +4 kernel stack +13 text +1 data +4 User stack +2 extra L0 +41 ink/index +40 framebuffer), leaving **two** of128 quota pages. Fresh ownership/call-chain report `build/silicon/prepared-1791708937239632104/guest-capacity.json` SHA `c4f422a7ea9aad04b1c8f704088aa699ff66421290084cf18fb5d6197a0f2717` retains the actual guest identity; no historical125-page claim. The binding records this current bound. These documentation updates are outside the consumed target and RTL inputs.

Host adapters supply clocks/reset, raw input and external bytes; no guest instruction execution, document construction or recovery. Larger 128 MiB RAM, immutable ROM byte preload, 655360-byte target/latched paper frame store and medium are external models. The panel model follows actual controller ports/completion events. Those bytes are not integrated SRAM or physical nonvolatile boot. QEMU remains the default native notebook; historical profiles and exact QEMU replay retain their identities.

## Actual outcomes

Execution hardware binary SHA `cbfab194513755cb52d57801a01299b46a579788e34cdf5f5cf49ba615e18c82`, build at09 `09460f310c6051245db6204b25e92315f1ef659a8d56f800ddd1562f426c83aa`; ROM SHA `4847f734666cc197a8e94c2ab2146cc45f0536a41f83376af8ddbadca737a1a2`. Later1e edits affect preparation/CI only; the fresh1e literal bus/host rebuild reproduced the identical binary. Each result retains its original target/hardware/observer identities.

| Claim | Observed result and scope |
|---|---|
| A09 PASS, O0/O2 | Each monitor: 11 independent arithmetic/control-flow replies, one synchronous recovery, three machine-timer traps, finisher0x5555. O0: 4,134,528 cycles/1,857,975 retired; O2: 2,439,548/1,574,963. Genuine historical strictly audited427f monitor images retain disclosed dirty-source status; current hardware execution, not fresh09 target compilation. |
| B09 PASS | 944.624075s checker/945.248265s supervisor: existing five-actor Buffer service/clients, M/S/U/Sv39, syscalls/capabilities/IPC, five ordinary commands, 109 arithmetic preemptions, actual readonly-text store fault cause15 at0x10000, containment/reap and exact useful CLI/Peer reads afterward. Complete independent replay of1648 wire events/145008 UART bytes. All179 target/223 hardware/7 runner/12 service-runner hashes matched; every owned process reaped. Strict clean78 ELF `fc6e94e2…` reused after exact source validation, not relabeled09 compilation. Short corpus, not full historical J. |
| C09 PASS | Fresh strict09 quarantined Lean probe ELF `9daa995b…`, actual isolated U task: pen loss/resync plus post-loss positive samples; paper invalid/Busy/reset-abort; block READ/FLUSH, real DMA/interrupts. 65M cycles/37,147,193 retired/270.723121s; 303 raw/258 accepted samples, two media requests/one FLUSH, one panel abort/no completion. Exact consumed closure with independent1e observer. No notebook ink/durability claim. |
| Notebook09 startup/controller observed | Fresh strict09 O2 ELF `d34bddba…` prepared/audited in96.472111s. First full327680-pixel controller completion, sequence1, at **cycle413,693,109**; harness stopped at413,693,110 cycles/235,997,735 retired/682 timer traps. Guest Ready0x420 record `(2748779069952,1,1,1)` observed; supervisor1493.161870s, protocol stop/reap. Frame reads655360/writes983040; zero raw pen/FLUSH, three media requests; retained seed unchanged. Independent literal checks passed for all nine toolbar glyphs and245760 lower-canvas pixels, exercising the aligned guest word path. **Startup/display prerequisite, not D**. |
| RTL initializer, retained7f PASS | 109,308,117 cycles/59,850,608 retired; eight media requests/three FLUSH. Existing Lean formatted blank raw media to generation1/sequence0. Reused seed SHA `c79dca00a597781d134ffdc3573eb1edc01915244b9c78efb7cac1eb6c188f46`; no host-created journal. |
| Native09 O0/O2 PASS | Genuine fresh notebook builds/audits; write/cold reopen304.366256s, 50 unique raw samples/two strokes/sequence8, exact document/record/pixel equality. Native1650x2200/825-byte stride uses admitted byte fallback; aligned word rendering **NOT_RUN_ON_NATIVE**. Scoped regression, not RTL D or all Task004 lanes. |
| Native09 matched11-input PASS | Fresh09 O2 `82baa5d7…`, write93.318851s/new-process retained-medium-only cold9.236792s. Pressure stroke, brush512->1024 edit, explicit Save/sequence6; actual Page/ink payload and visible pixels;16 write/13 cold selected guards matched. Native reference; RTL/cross comparison pending. |

Literal tests cover pen head/FIFO/loss, paper acceptance isolation/Busy/reset/full completion and block12 backpressure/reset/error/ACK cases, with original-negative sensitivity. Fresh1e literal bus/compiled-host test PASS covers replicated MMIO widths, held CPU/DMA requests, terminal error/reset and deadline handling; its hart is held in reset. Literal tests are separate from guest A/B/D.

Focused local silicon host suite:62 tests PASS; scaffold metadata and18 tests PASS after the documentation update. These checks are separate from RTL execution.

Actual CI09 run38124847458: nine existing jobs PASS; added RTL-device job114427033651 **FAIL** at final observer after real Devices/BusLanes/full host compilation passed. It compared absolute recorded argv with a relative binary path. Local compiled handling showed identical exit/stdout/stderr;1e canonicalizes the path and the focused local rerun passed.1e also puts a fresh capacity audit in preparation output rather than overwriting an immutable reused guest report. Local repair is **not a passing new CI run**. Duplicate task-branch push campaigns were removed; main/PR/workflow_dispatch and existing jobs remain.

Retain7f notebook500M **FAIL** (exit3/3256.767790s, zero pen/panel/FLUSH), earlier short service/initializer failures, cancelled78 B/preflight failure and obsolete EDA attempts in their existing indices. No old result is relabeled. The two-line metadata-read optimization remains staged/unapplied; benefit unmeasured. Current D2 execution is ongoing under `build/silicon/notebook-width-09f1345-rtl2*`, with first input700M cycles; the earlier500M input1 plan is retained unused. No accepted D result follows from either input manifest.

## Measured open-flow feasibility

Clean5da full bounded `lemma_soc REGISTER_RAM=1`: generic **464917 cells/109.766s**; actual SG13G2 bounded-ABC map **673802 cells/141961 flip-flops/13,889,148.802223µm² (13.889149mm²)/55.456s**. Both have zero unresolved cells/latches/residual memories; all arrays included as register cells, no RAM black boxes. Read-only comparison at1e confirms all216 RTL/header hashes equal original5da inputs; result identity remains5da. Retained cleanb6 actual O0/O2 scalar20-case execution uses the4 KiB working RAM; kernel/notebook cannot fit. External ROM/128 MiB simulation RAM/frames/media excluded. **Full SoC placement/timing/DRC/LVS NOT_RUN**.

Separately mapped actual pen: full256x181-bit FIFO (5.65625KiB),175117 cells/46821 flip-flops/4,118,404.159798µm². Paper includes512-byte tile registers:76687 cells/5480 flip-flops/1,036,021.455µm²; external frames excluded. Separate4 KiB register RAM map:2,902,880.332799µm². These explicit register-memory costs are feasibility baselines, not integrated SRAM macros. The separate pen map retains its clean e1d58bc identity; paper and standalone RAM maps retain their ef635f dirty source snapshots and exact consumed hashes. They are not new1e runs.

Paper reached real placement/CTS/global routing:90320 instances/1,193,987.6928µm² cells/4,131,171.072µm² core/28.9019184% utilization. TT1.20V/25C,100MHz/10ns,2ns IO,6fF load,0.25ns uncertainty/0.15ns transition: **setup−12.73ns FAIL; hold+0.03ns MET**, with separate2 slew/32 fanout/20 capacitance violations. **Global-route RC estimates**, not extracted post-route timing. Synthetic constraints cover exposed ports; an empty check_setup report is not full physical interface signoff. Detailed route **FAIL_TIMEOUT1800.567s**, incomplete20%; zero observed violations is not DRC PASS. No final controller geometry -> process DRC/transistor LVS **NOT_RUN**. Strict read-only parsing retained the original reports without reroute/overwrite.

Original public-inverter process preflight has actual DRC0/LVS match with width/bulk negative sensitivity, **that cell only**. Physical memory/nonvolatile boot, power grid/pads, complete routing, antenna/density, extracted timing and foundry acceptance remain unresolved. SG13G2 is provisional; no analog/radio/panel-waveform/package/tapeout claim.

## Exact dependencies and commands

CVW `20f2af74e7aa76513e94012231d16567fa42648a`, Apache-2.0 WITH SHL-2.1 plus six retained MIT notices; CVA6 `81245a47fad8fe1a5d562d953ef2662e099def76` assessed only. Existing nixpkgs `7dd199b0e2993e37b4775ed66b1c291699608c9f`; Verilator5.052; Yosys0.69 native read_slang. OpenROAD26Q2 `553ed63bc9f65277418adc82dffe1762c20aec9f`, OpenSTA `43177bba8f5f88dfb7dc35795242080a4fe2e986`, ABC `17cadca080b33edc5a13c8e6e8e8092f8c350b25`, Magic8.3.681/Netgen1.5.323. PDK `5e6d592e4002946a4616f798c357f0f3c06cf3b6`; TT Liberty SHA `7677a8918689f452e80405ad16a83e744709342574f2aedcc507c2758986b396`. OpenROAD headless realization passed after retained original timeout; upstream tool selftests NOT_RUN. Target pins unchanged: Lean4.34.1 `5045d0056413266e57c625dcd7c365b10e377c52`; LLVM/LLD20.1.8 `87f0227cb60147a26a1eeb4fb06e3b505e9c7261`; patched native QEMU11.1.1 `c3d48b7d1e89604920e5b81b91140c2ad39a1943`. Component notices remain; no whole-repository relicensing.

Prepare once, reuse identified artifacts, use unused result paths. RTL supports Developer mode; unsupported modes fail without QEMU fallback.

```sh
nix develop --no-write-lock-file --command ./scripts/lemmasim build --backend rtl --profile lemma-silicon-dev/0.1.0 --workload service
nix develop --no-write-lock-file --command ./scripts/lemmasim run --backend rtl --mode developer --workload service --cycles 400000000 --observer-cycle 300000000 --timeout 1800 --record build/silicon/service-new --trace-limit 10000
nix develop --no-write-lock-file --command python3 scripts/check_kernel_buffer.py --backend rtl --image build/kernel/silicon-service-78cd693-final1/image.elf --output-dir build/silicon/service-acceptance-new --timeout 3600
python3 scripts/check_silicon.py --lane devices --work-dir build/silicon/devices-new --timeout 600 --jobs 2
nix develop --no-write-lock-file --command ./scripts/lemmasim build --backend rtl --workload notebook --opt-level O2 --rtl-build build/silicon/bus-and-host-closure-final1/host
```

Notebook/initializer/devices need256 MiB raw `--disk`; only Lean formats it. An identified retained seed may be copied as initial bytes. Actual startup used `run --backend rtl --mode developer --workload notebook --disk <seed-copy> --record <unused-path> --cycles 1000000000 --timeout 7200 --trace-limit 1000 --stop-after-panel 1 --block-trace`. `--events` supplies raw cycle-tagged samples; `--fail-flush` models external barrier failure. Replay regenerates execution from initial bytes/input; its acceptance remains pending.

Reproduce the bounded synthesis using unused outputs (the actual5da command is retained in its result index):

```sh
python3 scripts/silicon_compute.py manifest --register-ram > build/silicon/soc-sources-new.json
nix-shell tooling/silicon/eda.nix --run 'nice -n 19 python3 scripts/silicon_synth.py --manifest build/silicon/soc-sources-new.json --top lemma_soc --parameter REGISTER_RAM=1 --output-dir build/silicon/physical/soc-small-new --map --map-effort bounded --deadline 2400'
```

**Single next bottleneck:** actual RTL notebook pressure-stroke/edit/Save and retained-medium cold reopen at a useful bounded runtime, followed by failed FLUSH. Startup now reaches controller completion; no new notebook/store authority or host recovery shortcut is needed.

## Compact artifact index

Indices contain exact source/commands and subordinate bulk hashes. Old identities remain; report publication is not a rerun.

| Retained path | SHA256 |
|---|---|
| `build/silicon/compute-A-09f1345-evidence-index.json` | `306a5a2c72bf2eff6677b4afdb86b3c39947d702dd272355e1ae3de3e4afd726` |
| `build/silicon/compute-B-09f1345-evidence-index.json` | `4017a4a8962df5dd48ab2041d48d75beda8c67162825978f40127d809b6c578f` |
| `build/silicon/C09-device-inventory.json` | `c7436217f47fa6ab13c09758694f5e7b33581c07d19cdc8ee531862de01ec925` |
| `build/silicon/notebook-startup-calibration-09f1345.json` | `8333ee1df6418a94f9f890c36bc5b9937e729bba8ae6e11edac2ce8c713fcb2f` |
| `build/silicon/notebook-startup-pixels-1e05f08.json` | `db1a797f311ca1c63f007c6c3c9ad2d0c21f112509ce71eade39e71efeb4235e` |
| `build/silicon/native-surface-09f1345-inventory.json` | `f9b9b1fb0439a68fa171b1476ea8bd4c8ac7629c5034a2e45452dc146fa62ca6` |
| `build/silicon/native-width-09f1345-current-evidence-index.json` | `af91a7270a32e434a260dd086980e80ad5a015e84b450eedfb4f43eefaf41571` |
| `build/silicon/physical/F-final-5da0058.json` | `28f57f09d438bced065e2e30871517ac993b509ae49c25807d23298e72549f15` |
| `build/silicon/physical/inventory-F-2dac502-offline.json` | `e2ab9f17b1c7ebfa73c6c2db484b908a8c8e28aaf951974335029ec3d27c4473` |

The source map and active construction plan record these implemented modules. Historical Task001–004 evidence and OEM discussions retain their original scope.
