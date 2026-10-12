# Task006 observed implementation increment

Implementation: `9946e7ef75486f328d4e71e1ea34e9412a3bd0ab` on
`task/006-whole-machine-lemmasim`, based on main `abd9920d54df04ce52da9386170e99012c39bdfb`.
This is a substantially expanded running subset. **Task006's whole-machine
destination is not complete.** The [checkpoint](../plan/006-session-state.md)
and [capability inventory](../plan/LEMMASIM.md) preserve the remaining scope.
The [compact inventory](006-whole-machine-inventory.json) binds actual local
artifacts by length/SHA256, including retained FAIL results. Large outputs remain
under ignored `build/`; their original consumed-source identities are retained.

## Implemented behavior

One persistent `scripts/lemmasim` session now owns interactive/headless QEMU or
RTL execution, bounded virtual intervals, inspect/input/pause, exact checkpoints,
isolated durable forks, recorded suffix replay, warm/cold reset and teardown.
The native window displays controller-produced pixels and emits raw samples.
Linux evdev transport reports actual capabilities; physical tablet testing is
NOT_RUN. Pinned Linux native presentation and prepared audited images are usable;
portable installation and the browser embodiment are unfinished.

The selected `lemma-silicon-dev/0.2.0` definition supplies both bindings with
1650×2200 Gray4, 128MiB external RAM, a real Lean-managed 32MiB owned frame pool,
discovery, IRQs and timing parameters. QEMU uses scalar RV64IM/MSU/Sv39/PMP;
both bindings admit the same notebook ELF/DTB. QEMU's generated handoff and the
Lean-authored RTL ROM remain different **ELF-preload development boot** paths.
No RV64GC, production boot/update, secure boot or whole-machine equivalence claim.
Historical profiles and durable formats remain supported.

RTL serialization combines actual Verilator model state with explicit RAM/ROM,
fabric wait ownership, controller/adapter queues, display state, overlays/bases,
reset phase and virtual clock. Fast migration includes CPU/private instruction
clock, RAM and complete current controller state. No snapshot flushes or drains.
Restore validates state and owns a new durable backing; real guest barriers
persist that fork. Fast adapter2 serializes its monotone session-clock origin.
Warm reset now waits for actual QEMU RESET and observes real MTIME; cycle/instret
reset parity with RTL remains unqualified. Pending input attempts survive
ambiguous errors and block further mutation; stale RTL sidecar boundaries are
rejected before replacing the live machine.

Pen circuitry preserves the full 256-entry sample semantics using synchronous
banks/cached head. The versioned paper sequencer emits three synthetic phases,
scan/control clocks and immutable accepted-update data, with reset/cancellation
and separate visible state. Its QEMU functional projection consumes the same
program. Synthetic sequencing establishes no physical panel compatibility.
Lean allocator early search/quota admission and aligned odd-stride tile transport
reduce actual work without removing zeroing, ownership, bounds or lifetime checks.

## Actual acceptance

| Observation | Result and scope |
| --- | --- |
| Public canonical native workflow | **PASS**, `build/l6-native3/result.json`: 117 raw events, 100 immutable pressure samples, four strokes, undo/redo/erase, three pages/two documents, acknowledged Save25; 534.21s total including suffix/recovery checks |
| Snapshot/replay | **PASS** with pending paper and queued input, isolated durable fork, equal CPU/RAM/controller/private guest-clock state and exact outputs/base; two named host elapsed-time statistics differ in nine retained container bytes |
| Cold and failed persistence | **PASS**, genuinely new QEMU processes recover only acknowledged durable backing/pixels; failed first FLUSH shows Failed227 and no Saved, unchanged base, failed work absent on cold reopen |
| Format compatibility | **PASS**, `build/l6-upgrade1/result.json`: new guest cold-opens earlier acknowledged medium with identical durable bytes/pixels and no format/republish |
| Final capture/reset lifecycle | **PASS**, `build/lemmasim/fast-lifecycle-clock-a3/result.json`: actual reset/input suffix, clock origin, pending/applied capture and complete pinned state relation |
| RTL exact continuation | **PASS**, final v4e profiles0.1/0.2 real monitor; profile0.1 also pending paper cancellation/block DMA; profile0.2 active sequencer guest continuation is NOT_QUALIFIED |
| RTL stale sidecar | **PASS**, `build/rtl-atomic1/result.json`: actual current guest/model rejects cycle+1 sidecar with identical before/after complete checkpoint bytes and unchanged original medium; valid restore then succeeds into private backing |
| Controller/input checks | **PASS**, literal bank/phase/scan/backpressure/reset RTL observations; raw field limits/U64 timestamp and saved-queue preflight; functional DMA/overlay/barrier confinement checks |
| Native window | **PASS**, `build/task006-native-view3-result.json`: actual pinned Tk/Xvfb rendering/control widgets and two raw applied pointer samples; no manual interaction/physical tablet claim |
| Legacy target | **PASS**, clean committed `9946e7e` Core0 O0/O2 run: ten cases, thirteen expected rejections, independent reference, reproducibility/mutation/audit regression |
| Host and Lean checks | **PASS**, final relevant union1075 host tests (18 scaffold,36 Core0,455 foundation,317 kernel,99 LemmaSim,150 silicon); Lake build, genuine Lean SurfaceWords/FramesScans observations and scaffold metadata |
| Canonical RTL notebook | **FAIL_DEADLINE**, retained v3 `build/silicon/f8/result.json`: 1801.58s, 504M cycles/290285792 retired before READY. Actual initializer continuation/private barriers passed separately; no canonical notebook or cross-backend workflow PASS |

The pinned QEMU observer was fixed before the final native3 workload. It excludes
only `cpu_ticks_offset`/`cpu_clock_offset`, proven host statistics under the exact
icount configuration, while retaining all raw differences. Its independent
archive decoder and CPU/RAM/private-clock negative mutations are preserved in
[QEMU_STATE_EQUIVALENCE.md](../../conformance/lemmasim/QEMU_STATE_EQUIVALENCE.md).
Earlier raw-container FAIL is unchanged. Native3 preceded the two final error-path
repairs; the subsequent real lifecycle, stale-sidecar and Tk checks qualify those
changes without relabeling the original workflow files as reruns.

## Measured performance

| Workload | Before | After | Limit |
| --- | ---: | ---: | --- |
| Canonical native boot to READY | 59.22s host /15.75s virtual | 44.73s host /14.85s virtual | Shared host, same actions/capacity; no sole-change attribution |
| Mean six native navigation actions | 54.57s host /14.31s virtual | 42.20s host /13.41s virtual | Absolute input timestamps adapt to milestones; raw hashes differ |
| Cold guest initializer, median three runs | 0.902s | 0.312s | Same QEMU/profile, real three barriers; ~68MiB RSS, not UI frame rate |
| RTL scalar throughput, alternating three runs | 391694 cycles/s | 382713 cycles/s | **2.29% slower**, ~134MiB RSS; no real-time claim |
| Final RTL exact restore | — | 0.522s | Explicit latency3 checkpoint, separate 1M suffix2.503s |
| Full canonical tile transport | 512 byte reads +512 writes | 120 aligned reads +64 writes | Independent host Action counts/neighbor checks, not CPU cycles |

New native first-update-in-flight observation is 15ms versus17ms with a 2ms
inspection quantum; this is not visible completion. Explicit Save settles after
239ms virtual in both samples. Native peak memory was not measured for the full
editing campaign. No host pacing or virtual-device deadlines were accelerated.

Tools retain their exact pinned identities: Lean4.34.1/source
`5045d0056413266e57c625dcd7c365b10e377c52`, LLVM/Clang20.1.8,
QEMU11.1.1 SHA256 `87d7282df1de259a3560fee369ef1f303a644654793726fc9da12009d639d467`,
CVW `20f2af74e7aa76513e94012231d16567fa42648a`; RTL build inventories bind
Verilator/toolchain/flags/generated model and sources. Fresh final target
compilation is at `9366387`; reused historical monitor/device ELFs underwent
consumed-input validation and remain historical compilation identities.

## Separate physical results and remaining blockers

[Controller evidence](006-controller-physical.md) records full pen mapping PASS,
the minimal OpenROAD ECO assertion reproducer and real WNS_PATH repair.
Unchanged100MHz TT global setup WNS−3.542208ns remains **FAIL**; hold+0.034896ns,
but detailed routing times out. These are global estimates, not extraction.
Paper's retained timeout and LEF58 enclosure/CUTCLASS coverage remain unresolved;
no rule adapter/waiver was admitted and no timeout cause was invented.
Process DRC/LVS, routed parasitics and post-route timing are NOT_RUN. Large RAM,
compute/full-SoC, pads/power/analog/RF and physical panel qualification are separate.

Digital/software blockers are canonical RTL kernel validation/copy cost and
matched-profile timing/CSR acceptance; production Lean boot/update/recovery;
guest power/reset-cause/suspend/wake/watchdog; real companion/USB controller,
Lean framing/retry policy and independent durable peer; Wi-Fi6/BT5.4 digital
MAC/baseband/PHY; same-core browser/Wasm/storage barriers; G2 managed runtime
and G5–G7 mathematics/verifier/learning/tutor integration. No companion launch
command exists. The physical processes excluded by the assignment do not excuse
these unfinished digital paths.

Reproducible launch, interaction, snapshot, restore and replay commands are in
[README](../../README.md#task006-persistent-machine-sessions). Fresh main CI
passed run38200671355; candidate CI is a separate observation at publication,
and no merge is authorized.
