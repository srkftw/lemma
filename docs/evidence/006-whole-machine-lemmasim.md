<!--
# Task006 observed implementation increment

Branch `task/006-whole-machine-lemmasim`, [PR8](https://github.com/srkftw/lemma/pull/8),
based on main `abd9920d54df04ce52da9386170e99012c39bdfb`.
**The whole-machine destination remains unfinished.** The
[checkpoint](../plan/006-session-state.md), [capability inventory](../plan/LEMMASIM.md#task006-capability-inventory)
and [source-bound artifact inventory](006-whole-machine-inventory.json) retain
completed functionality, actual failures and exact remaining scope. Generated
outputs stay under ignored `build/`; historical artifacts keep their execution identities.

## Implemented product

The persistent `scripts/lemmasim` command surface owns QEMU or RTL execution,
bounded virtual intervals, pause/inspect/raw input, exact checkpoints, isolated
durable forks, recorded suffix replay, warm/cold reset and teardown. Native Tk
presents controller pixels. Evdev transports actual reported capabilities;
physical tablet/manual acceptance is NOT_RUN. Linux native pins/prepared images
are usable; portable installation and same-core browser/Wasm are unfinished.

`lemma-silicon-dev/0.3.0` supplies both bindings with canonical1650×2200 Gray4,
128MiB external RAM, an actual Lean32MiB/8192-frame pool, consumed discovery,
IRQs,100MHz clock and10MHz MTIME. Historical0.1/0.2 remain supported.
Scalar RV64IM/MSU/Sv39/PMP is the declared CPU subset, not RV64GC. QEMU's
handoff and the Lean-authored RTL ROM remain different explicit ELF-preload
mechanisms, consuming identical compatible guest ELF/DTB/descriptor. Production
nonvolatile boot/update/recovery and secure boot are absent. Synthesized4KiB
register RAM is a separate configuration and cannot run this notebook.

The full256-entry pen uses synchronous banks/cached head without truncating
samples. Paper circuitry scans immutable accepted updates through three synthetic
phases, row/control clocks, digital timing and reset/error behavior; QEMU projects
the selected program. Target/latched/visible states remain distinct. These are
digital sequencing results, not qualified physical waveforms or panel response.
Block DMA/queues/volatile overlays and actual host `fdatasync` precede durable
acknowledgement; real Lean drivers, store/recovery, ink and notebook remain authoritative.

New Power-v1/IRQ14 and separately authorized syscall68 implement actual Lean
cooperative suspend/wake and reset causes. Busy paper/block work rejects suspend.
Accepted suspend retains RAM/tasks/time/panel/media, enters pen loss/resync and
masks input until wake. Raw button levels reach the controller; host presentation
does not decide the guest policy. The object-table v2 explicitly grants the fifth
power endpoint; historical v1 keeps four. OOM, stale capabilities and preallocation
rejections remain checked. Clocks continue; electrical domains/watchdog/brownout
remain required. [The contract](../contracts/006-power-control-v1.md) defines the scope.

Checkpoint state combines actual Verilator `--savable` processor/private circuitry
with explicit RAM/ROM/fabric ownership, media/overlays, input/adapter queues,
controller staging/progress/visible outputs, interrupts/timers and reset/clock phase.
Fast migration retains CPU/RAM/private clock and controller state. Wrapper
adapter2 binds the monotone origin separately. Snapshot never drains or flushes;
restore validates bounded lengths/checksums/identities and owns a private medium.
Live handles disconnect. No QEMU/RTL microstate migration or portable architectural
checkpoint is implemented.
QEMU's common CPU post-load explicitly flushes the software TLB; cached Sv39
translations and TCG blocks are not in the stream. Listed actual fast suffixes
are equal, but arbitrary cache-state continuation remains unfinished. RTL's
complete savable model includes its caches/TLBs. Reservations are explicitly
serialized by QEMU RISC-V VMState; the selected RV64IM binding excludes A.

The final QEMU11.1.1 successor is SHA256
`927bef771d31134b73b76a2c219d1717144feec6986b07df5c58ef85d08ad6e5`;
current RTL runtime is `c36d0628df1fff3b538257a72f41c30559e8dad60348e48923cb3fddbd03c6bb`.
Fast counters use the declared clock and serialize all private phase/write/inhibit
arrays. UART reset preserves exact restored state. Hardware pen reset clears
FIFO/time state; software RESET1 remains loss/resync. VMState3 retains the aligned
pen reset origin, mapping watchdog/sample time to reset-local MTIME. Unsupported
old-version/missing/misaligned/future state rejects. The independent observer
compares all CPU/RAM/private-counter/pen-origin/Power/wrapper bytes, except two
source-proven host elapsed-time statistics; complete raw differences remain retained.
[Observer relation](../../conformance/lemmasim/QEMU_STATE_EQUIVALENCE.md).

Target/controller commits are `91911c5`, `4d18b93`, `3101cc6`, `9366387`;
persistent runtime `9946e7ef`; checked-memory work `536fea2`/`97e4dcb`;
power/authority `0626acc`; fixed counters `b01d336`; genuine Lean Loader `2bf6658`;
bounded profiling/warm workflow `fff15dc`; warm pen state `de21f0c5`;
lightweight live input `d8d7b0cc306a91a113b5a95e964a2a19313f457d`.
All target/compiler policy remains genuinely elaborated Lean → checked Core0 → LLVM
→ freestanding RV64. No new accepted Core0 language or foreign target helper.

## Actual acceptance and retained limits

| Observation | Result and exact scope |
| --- | --- |
| Final canonical power | **PASS**, `build/l6-power-final-a1/result.json`,133.37s: busy rejection, held contact/suspend retention, malformed Power rejection with unchanged live checkpoint, queued wake exact fork, real post-wake ink/Save, new cold every-pixel/durable recovery; failed FLUSH227/no Saved and another new cold recovery |
| Final warm notebook | **PASS**, `build/l6-warm-final-a1/result.json`,27.24s: pending contact, new cause2/Ready/redraw, actual-MTIME pressure ink, Save31, new cold identical pixels/durable bytes; acknowledged source unchanged |
| Original warm failure | **FAIL**, `build/l6-warm-prepatch-a3/result.json`,198.61s: same frozen checker/guest/medium/first nine raw events; old6dc reached warm Ready but new ink timed out with loss8/resync. Final927 changes no timestamps or observer predicates |
| Fixed counters and pen boundary | **PASS**, current-only `build/lemmasim/counter-pen-current-only-a1/result.json` and `task006-warm-pen-current-a1/result.json`: cold/warm, fractional phase, writes/inhibit/wrap, watchdog and full private forks, missing/malformed/stale state negatives. Debugger CSR/MMIO qualification; guest-issued CSR instructions not qualified |
| Paired Power probe | **PASS**, `build/lemmasim/task006-power-final-pair-a2/result.json`: final927/current genuine c49a5 probe against retained actual RTLc36; exact admitted fields/results except predeclared100000-tick wake-time bound. Full states retained; partial relation only |
| Real RTL power | **PASS**, `build/lemmasim/task006-power-final-rtl-a1/rtl/result.json`,249.76s: actual Lean cold/wake/queued exact suffix; no canonical notebook or Save claim. Literal Power checks separately pass six busy sources/malformed/W1C/reset |
| Genuine Loader deployment | **PASS**, `build/task006-loader-plan/maintained-result.json`: full initializer/notebook/probe builds and strict audits, notebook8192-frame capacity checks. Finite-RAM alignment/error/RX/BSS/abort cleanup tests pass; no runtime stub |
| Canonical RTL cold prefix | **OBSERVED_PREFIX_NOT_READY**, `build/silicon/task006-loader-cold-a1/result.json`,100Mcycles354.74s; first sampled user mode38M, no Ready/paper/Save. Retained pre-Loader242M and earlier504M deadline FAILs remain unchanged |
| Bounded profiling checkpoint | **PASS**, `build/silicon/task006-boot-checkpoint-a2/result.json`: real1M probe prefix snapshot, unchanged boundary, existing-destination rejection, exact145270622-byte continuation containers and isolated fork inspect, teardown. No notebook readiness claim |
| Historical public notebook | **PASS**, `build/l6-native3/result.json`,534.21s on source9946/older87d:117 raw events,100 samples/four strokes, undo/redo/erase, three pages/two documents, Save25, pending-paper exact fork, new cold and failed-FLUSH recovery. Not relabeled as current927 execution |
| Durable format compatibility | **PASS**, `build/l6-upgrade1/result.json`: actual new936 guest cold-opens earlier3101 medium without formatting or republishing, identical old bytes/pixels |
| Historical exact runtime/native | **PASS** on original identities: v4e RTL profiles0.1/0.2 monitor,0.1 pending paper/block DMA; stale-sidecar live-state rejection; pinned Tk/Xvfb widgets/raw input. Profile0.2 active sequencer guest continuation/manual tablet remain unqualified |
| Final relevant host set | **PASS**, `build/task006-current-host-a1/result.json`:616 tests (103 LemmaSim,327 kernel,168 silicon,18 scaffold), metadata check;613 frozen code inputs unchanged. Separate pinned Lake build completed55 jobs. Host checks are not target/physical acceptance |
| Live input clock | **PASS**, `build/lemmasim/task006-input-clock-a3/result.json`: exact three raw admissions/cursors/phases, full post-inject responses, queued/cold-readonly/fractional-warm-readonly states; each23298752-byte container pair is literally equal. Earlier CLI-path and literal-coordinate oracle FAILs remain unchanged |

Final current927 workflows consume genuine new Loader notebook ELF
`9b7972a35f189c929bf7b16dd37dbcfc0a9ba5a710729eb91a06fdd277a1553b`,
initializer `722923948db13663aa0ea78b827c99db68d046d3ab620b29a940a5298a060fed`,
and probe `c49a5b83eef94fa9848e90883d5c85a79fc3d2e3387fb96664551a8507738b7e`.
Actual compilation and audits consume the exact2bf Loader sources; an initializer
command began at0626 with those dirty inputs, not clean-at-start2bf. Probe bytes
match earlier power probe but its new compilation/audit identity is preserved.
Lean4.34.1/source5045d005…,LLVM20.1.8,CVW20f2af74… and all RTL build flags/tools
are pinned in source-bound inventories. Historical failures and source reuse are
validated without claiming recompilation.

## Measured performance

| Workload | Before | After | Limit |
| --- | ---: | ---: | --- |
| Checked4096-byte user copy |2674 callbacks/2918 reads/512 writes|818/2777/512|Real finite-RAM Lean Action counts; per-action authorization preserved, not CPU throughput |
| Aligned4096-byte Loader copy |8192 physical accesses/4096 callbacks|1024/512|8× fewer accesses, bounds/RX/BSS/abort checks unchanged; not machine speed |
| Public paused session control |143.28ms median via two CLI processes|60.42ms direct existing Unix RPC|10 requests,2.37×, shared host; same owner/API/virtual cycles |
| Live input timestamp query |19.25ms median full inspect,8670B|1.45ms clock,207B|20 paused RPCs each,13.29×; actual current927 probe. Full post-inject inspect remains; not total stroke latency |
| Canonical RTL100M cold prefix |195809cycles/s,510.70s|281900cycles/s,354.74s|Shared host, same medium/runtime/UserELFs, new Loader kernel; no sole-change attribution or Ready claim;147732KiB HWM |
| Canonical RTL user-mode observation |No U sample through100M|U sampled at38M|Fixed1M sampling; overlapping task-symbol candidates retained, no guessed task identity |
| Current canonical QEMU Ready |—|12.20s virtual/12.17s host|Final927/Loader power workflow, shared host; historical editing measurements below remain separate |
| Historical canonical native Ready |59.22s host/15.75s virtual|44.73s/14.85s|Same old binding/actions, adaptive input timestamps/shared host |
| Historical six-action mean navigation |54.57s host/14.31s virtual|42.20s/13.41s|No sole-change attribution |
| Historical guest initializer median3 |0.902s|0.312s|Real barriers,~68MiB RSS; not UI frame rate |
| Historical RTL scalar throughput |391694cycles/s|382713cycles/s|2.29% slower,~134MiB RSS; host-paced, no real-time claim |

Snapshot-final preserves expensive observed RTL prefixes for bounded later
continuation. Ordinary presentation avoids detailed trace flushing; no optimization
skips hardware cycles, guest operations or device deadlines. Full canonical native
campaign peak RSS was not measured. Before/after measurements retain their actual
workload/source identities and do not erase failed cold paths.

## Separate physical lane and unfinished destination

[Controller evidence](006-controller-physical.md): full256-entry banked pen
mapping PASS; minimal OpenROAD ECO assertion reproduced; justified WNS_PATH
repair used.100MHz TT global setup WNS−3.542208ns remains **FAIL**, hold+0.034896ns;
detailed routing times out. Global-route estimates are not routed extraction.
Paper timeout and SG13G2 LEF58 enclosure/CUTCLASS associations remain unresolved;
no rule omission/waiver is hidden and no timeout cause is invented. Process
DRC/LVS, routed parasitics and post-route timing are NOT_RUN. Power physical flow,
large memories, compute/full SoC, pads/analog/RF and panel qualification are open.

Digital/software obstacles remain canonical RTL Ready and full matched timing,
ISA/CSR/paper warm-state mapping; fast cached-translation checkpoint coverage;
production Lean boot/update/recovery;
electrical power/watchdog/brownout; real companion/USB controller, Lean bounded
framing/retry and independently durable peer/lost-ACK recovery; Wi-Fi6/BT5.4
digital MAC/baseband/PHY; unexpected live backing-I/O fault recording/replay;
same-core local browser/Wasm/durable quota/barriers; G2 managed runtime and G5–G7
mathematics/verifier/courses/learner/tutor. No companion launch command exists.

Use [README launch, interaction, snapshot, restore and replay](../../README.md#task006-persistent-machine-sessions).
Focused current power/warm acceptance requires an actual acknowledged medium:

```sh
python3 scripts/check_power_session.py --work-dir build/power-new --disk PATH_TO_ACKNOWLEDGED_RAW
python3 scripts/check_warm_notebook.py --work-dir build/warm-new --disk PATH_TO_ACKNOWLEDGED_RAW
python3 conformance/lemmasim/check_counter_state.py --output-dir build/counters-new
python3 conformance/lemmasim/check_warm_pen_state.py --output-dir build/warm-pen-new
```

The owner subsequently authorized merging PR8 after applicable checks pass.
Candidate9812a22 [CI38245370738](https://github.com/srkftw/lemma/actions/runs/38245370738)
passed nine target/RTL jobs and failed the metadata job's three stale foundation
workflow assertions. The repair accounts for every logged pipeline in the new
multi-command Lean block and preserves explicit pipefail/timeout requirements;
the exact literal-device expectation becomes eight commands/four binaries and
includes the new power lane. The actual workflow, guest/RTL implementation and
historical observations are unchanged. Repaired-candidate CI is separate from
historical/main passes; a timeout, absent result or unfinished physical step
remains exactly that.
Final local repair checks passed 13 focused and 456 foundation host tests,
21.323s for the latter, on test source SHA256
`0950dff309a3f26190c4177eb1cb65a3896c019aa59fc882479e6ff19dd67b24`;
the command/log/result record is `build/task006-merge-ci-repair-a2/`.
Metadata and18 scaffold tests also passed. No additional local historical guest/physical rerun
was needed for this host-test/documentation repair.
The subsequent [CI38287697012](https://github.com/srkftw/lemma/actions/runs/38287697012)
at703ddc9 passed the repaired foundation suite and exposed the first Lean
fixture's missing `Lemma.Kernel.Memory.UserCopy.olean` in a fresh checkout.
Default `lake build` does not build all fixture imports; CI must explicitly
build those modules before the five Lean/compiler fixture commands. This
retained dependency failure is separate from the earlier stale assertions.
The explicit build `lake build Lemma Lemma.Platform.LemmaSim.NotebookKernel`
passed94 jobs in51.936s in a clean detached703ddc9 checkout with an initially
absent `.lake` cache. All five exact bounded CI fixture commands then passed:
checked copy6.428s, Loader25.516s, power authority131.483s, object budget5.877s,
and24 O0/O2 compiler guard cases1.718s. The checkout stayed clean and all
processes were reaped. Actual result/log/input hashes are retained in
`build/task006-metadata-clean-a1/result.json`, SHA256
`8e612cf0df5bc601cb059b4be8b99466331f7787b963365c15b8277f78438ce4`.
The focused workflow regression passed13 tests; target/controller inputs were
unchanged. The repaired candidate still requires its own successful CI.

## October12 implementation continuation

The subsequent actual candidate CI38288756841 at `d219650` passed all10 jobs.
PR8 was already merged when this continuation inspected it. The current owner
instruction forbids another merge; new work stays on the preserved Task006
branch for draft publication. The original failed CI and canonical/physical
observations above retain their identities and meanings.

`aa49491` adds shared backing read/write/barrier outcomes and isolated replay,
including real partial-write and sync/read errors. `e0e325c` adds a deterministic
free-frame cursor and maintained owner accounting without changing allocation
choice, quota priority, generations, zeroing, pinning or cleanup. See the
[frame evidence](006-frame-index.md). `3704441` adds an independently persistent
hosted-Lean opaque peer and normal companion launch command; actual lost-ACK
and both-restart receipt reconciliation passed, while USB and an asynchronous
guest companion service remain unfinished. See [peer evidence](006-companion-backing.md).

`84c5dcd` connects actual rational/polynomial checks, revision-bound evidence,
an authored course and hints to the guest notebook and store. Real raw input,
edited/unsupported/resource cases, acknowledged Save, independent cold complete
pixels/record recovery and failed barrier passed. Three earlier source/observer
failures are retained separately. See [the exact-course receipt](006-exact-course.json).
This bounded arithmetic checker does not close the managed-runtime or Lean
proof-kernel gate.

The local RTL/Wasm port builds the existing generated circuitry and reusable
Machine. Actual browser-worker OPFS initialization/cold-prefix execution,
corrupt rejection without any archive change, private origin restore and an
8.15M-cycle queued-input suffix passed. The browser/native-host Wasm suffix
archive is exact, with68.316s host time,325MiB Wasm heap and1.683GiB peak host
RSS. Browser Ready, writing, acknowledged Save and full cold recovery remain
unqualified. The canonical RTL campaign and changed-source hot-path work are
still active. See [browser source/tool/observation identities](006-browser-machine.json).
These results do not fix the QEMU cached-state hole, complete digital radios,
establish production boot/update or close physical implementation.

`8137ee7` adds durable ordered learner events, explicit uncertain estimates and
an overridable/disableable review baseline. Actual v1 record migration,
assisted mathematics, policy changes, independent cold full record/pixels and
unsuccessful Save passed in `build/task006-review-course-a3/result.json`.
`cb10b29` connects the same backing interface to QEMU and the actual guest
Store/notebook. The independent peer persisted barrier transaction78 but lost
its ACK; no guest Saved acknowledgment followed. Both restarts reconciled that
same transaction without another peer append, then a new cold CPU recovered
all objects and complete display. See [the guest receipt](006-companion-guest.json).
These are separately observed connected guest workflows; they do not implement
USB or transfer guest document recovery into the peer.

`e312758` adds an immutable native development bundle containing audited
genuine guest artifacts, complete consumed source closure and identified native/
QEMU implementations. Actual guest initialization and archived RTL clock0 launch
passed after newer target edits invalidated ordinary current-source preparation.
Reusing that guest is explicit archived-source execution, not fresh compilation.
Pinned external Linux dependencies and unresolved project redistribution terms
remain visible. See [the package evidence](006-native-bundle.md).

`54763c8` adds the separately linked Arithmetic service and async notebook client.
Normal A5 checks, edited and unsupported cases, actual OOM/fault isolation, and
finite-stall cancellation have independent receipts; the original stalled Save
failure remains retained. This is connected guest mathematics, not proof-kernel
completion. See [isolated arithmetic](006-isolated-arithmetic.json).

Portable a11 builds the shared private-Pending boundary and an explicit outcome
tape control. Actual guest qualification failed at its30M-cycle bound before
first WRITE. The loopback browser launch now validates immutable bundle/guest/
Wasm identities; six real HTTP responses and four focused host tests passed.
The retained older browser canonical boundary remains not Ready. See
[portable backing and local launch](006-browser-private-pending.json).

-->
