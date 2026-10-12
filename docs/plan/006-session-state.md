# Task006 checkpoint

Task006 is a substantial **partial increment**, not whole-machine completion.
Resume `task/006-whole-machine-lemmasim`; do not merge. The assignment is
[006-whole-machine-lemmasim.md](../../codex/prompts/006-whole-machine-lemmasim.md).
The capability inventory remains in [LEMMASIM.md](LEMMASIM.md). USGCE and
repository settings are untouched.

## Baseline and implementation

Current main was fetched once: `abd9920d54df04ce52da9386170e99012c39bdfb`,
tree `7c30f469592f2c2a1bef6aab11f31d30a8a3ee28`. PR6's subsequent merge
retained Task005's source tree; its old dependency is closed. Actual main CI
run [38200671355](https://github.com/srkftw/lemma/actions/runs/38200671355)
completed successfully. This is not candidate CI evidence.

Coherent target/controller increments are `91911c5` (versioned capacity,
synchronous pen and panel), `4d18b93` (supported Core0 condition), `3101cc6`
(allocator search) and `9366387` (aligned tile transport). Target logic remains
genuinely elaborated Lean, through the checked Core0/LLVM/RV64 deployment path.
No managed runtime or accepted Core0 language extension was introduced.

The final reusable runtime and native session implementation use the contracts
[machine sessions](../contracts/006-machine-session.md),
[RTL checkpoint format](../contracts/006-rtl-runtime-v1.md), and
[synthetic panel program](../contracts/006-synthetic-panel-v1.md).

- One persistent command surface owns QEMU or RTL execution, bounded input,
  virtual-time run/pause/inspect, snapshot/restore, replay, warm/cold reset,
  private durable forks and teardown. Native Tk displays controller output.
- Verilator `--savable` captures processor/private circuitry; wrapper memory,
  media overlays/bases, held bus ownership, queues, clock/reset phase and
  observer state are serialized explicitly. QEMU migration includes CPU,
  128MiB RAM, timers, pen/paper/block state and its private instruction clock.
  Restore preflights integrity and implementation identity without flushing.
- `lemma-silicon-dev/0.2.0` supplies 1650×2200 geometry and 32MiB/8192-frame
  allocation inside 128MiB external simulation RAM. Historical 0.1 remains
  distinct. One selected definition supplies consumed bindings and discovery.
  The allocator and raster changes preserve lifetime/isolation/error behavior.
- Full 256-entry pen banks preserve complete sample fields. The synthetic
  panel circuitry scans immutable accepted updates with phase clocks and
  digital outputs; functional QEMU projection uses the same selected program.
  These are digital sequencing results, not qualified panel drive data.
- The matched QEMU binding has scalar RV64IM/MSU/Sv39/PMP, checked DMA,
  volatile sector overlays and actual `fdatasync` before durable acknowledgement.
  Fast adapter2 stores the global clock origin separately from guest-local time.
  Actual warm RESET and MTIME reset work; mcycle/minstret reset parity remains
  unqualified. No time/counter fields are discarded to claim equivalence.

## Observed results and limits

Final RTL v4e builds are `build/silicon/task006-runtime-final-v4e-{01,02}`;
their exact inventories are in `build/silicon/task006-runtime-final-summary.json`.
Both profiles pass real monitor exact continuation and bounded-input/preflight
checks. Profile0.1 additionally passes pending paper reset/cancellation and
block DMA continuation. Active profile0.2 sequencer continuation through a real
guest remains unqualified; literal circuitry checks cover its phase semantics.
Nonempty warm overlay and nonwhite warm panel retention are not covered by
those particular warm checks.

The current QEMU binary is pinned 11.1.1, SHA256
`87d7282df1de259a3560fee369ef1f303a644654793726fc9da12009d639d467`.
Actual guest pending-WRITE snapshots, no flush on save, wrong-base/truncation
rejection and DMA confinement passed. Final lifecycle and recorded reset/input
suffix passed at `build/lemmasim/fast-lifecycle-clock-a3/result.json`.
Two independently identified host elapsed-time statistics in QEMU's migration
container are compared separately from all CPU/RAM/private guest-clock bytes;
see [the pinned observer relation](../../conformance/lemmasim/QEMU_STATE_EQUIVALENCE.md).
Original unequal-container FAIL observations remain unchanged.

Fresh final Lean guests are `build/kernel/task006-full-initialize-a8` and
`build/kernel/task006-full-notebook-a7`, compiled/audited at `9366387` and
published into both prepared profile0.2 manifests. Final public workflow
observation at `build/l6-native3/result.json` is **PASS** (534.21s campaign):
117 admitted raw events, 100 retained samples/four strokes, undo/redo/erase,
three pages/two documents, Save publication25, a pending-paper fork and exact
suffix replay, durable-only new cold recovery, failed-FLUSH/no-Saved and another
new cold recovery. `build/l6-upgrade1/result.json` passes new-guest cold reopen
of the earlier acknowledged medium with identical old bytes and pixels.
Two subsequent failure-path repairs preserve ambiguous input attempts and
preflight RTL sidecar cycles. Real follow-up lifecycle replay and current Tk
input checks exercise the new admission marker; a stale-sidecar RTL check
proves unchanged complete live checkpoint bytes on rejection. Original workflow
files retain the source hashes they actually executed.

Canonical RTL cold notebook remains **FAIL_DEADLINE**:
`build/silicon/f8/result.json`, 1801.58s overall, 504M cycles and 290285792
retired instructions before READY. Real kernel registry validation/copy paths
dominated. Its separate initializer continuation did reach actual guest ACK
at cycle78700000 after three durable private-file barriers. The interrupted
prior cold prefix and later continuation are separate runs, not a measured
continuous boot time. No second long canonical campaign was launched merely
to refresh this report. Historical Task005 notebook runs retain their identities.

Measured fast cold initialization improved median 0.902→0.312s (2.89×,
~68MiB RSS); this is actual guest initialization, not notebook frame rate.
Canonical native ready improved observed 59.22→44.73s host/15.75→14.85s
virtual; mean six navigation actions improved 54.57→42.20s host and
14.31→13.41s virtual. These are shared-host observations with adaptive input
timestamps, not controlled attribution or a real-time claim. Raw sample
pressure/geometry/actions and final controller pixels agree.
Final RTL scalar throughput is 382713 versus 391694 cycles/s (2.29% slower,
~134MiB RSS); exact latency3 restore took 0.522s. Aligned tile loads use 120
64-bit reads/64 writes versus 512 byte reads/512 writes, with independent
neighbor/padding checks; host Action counts are not CPU throughput.

## Launch and recover

Use the executable [README procedure](../../README.md#task006-persistent-machine-sessions).
Prepare once, preserve the exclusively initialized medium outside `build/`,
and use new session/checkpoint directories. Existing media are never formatted
on launch/upgrade. Pinned native presentation is Linux x86-64. The future
browser and a portable installer are unfinished.

Focused acceptance interfaces, with unused output paths:

```sh
python3 scripts/check_live_notebook.py --work-dir build/live-006-new --checkpoint-relation pinned-host-time-v1
python3 conformance/lemmasim/check_fast_lifecycle.py --work-dir build/fast-lifecycle-006-new
python3 scripts/check_machine_runtime.py --help
python3 scripts/check_runtime_input_bounds.py --help
python3 scripts/check_silicon.py --lane devices --work-dir build/devices-006-new --timeout 600 --jobs 2
```

The two runtime checkers require explicit built simulator, monitor/device ELF
and discovery arguments shown by `--help`; historical guest reuse requires
consumed-source validation. It is fresh hardware execution, not recompilation.
Run the pinned host suites and both scaffold checks after implementation changes.
Keep every original failed receipt; use new output directories for corrections.

## Dependency-ready continuation

First repair measured kernel validation/copy costs sufficiently to qualify a
representative canonical RTL cold path and matched-profile suffix. Do not hide
timing/CSR mismatches or use the 4KiB synthesis RAM as notebook capacity.
Next complete production Lean boot/update recovery and guest power/reset/wake
control, then a guest-visible bounded companion controller/protocol with an
independent durable peer. No companion command or peer exists yet.

USB, Wi-Fi6/BT5.4 digital MAC/baseband/PHY, local browser worker/Wasm and durable
browser storage, G2 managed runtime and G5–G7 mathematics/learning remain required.
Exact cross-backend checkpoint migration is absent. Manual physical tablet
registration is NOT_RUN; synthetic mouse samples do not establish it.

Physical results are separate in
[006-controller-physical.md](../evidence/006-controller-physical.md): full pen
mapping PASS, minimal OpenROAD assertion reproduced and supported WNS_PATH
repair used, but 100MHz global setup WNS−3.542208ns and detailed-route timeout
remain FAIL. Paper's retained timeout and SG13G2 enclosure/CUTCLASS coverage
gap remain unresolved. Complete process DRC/LVS, routed extraction/post-route
timing, memories, compute/full-SoC and physical panel qualification are not closed.
