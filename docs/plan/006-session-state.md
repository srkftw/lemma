# Task006 checkpoint

Task006 remains a substantial partial increment, not a completed Lemma One.
Resume `task/006-whole-machine-lemmasim`; the owner subsequently authorized
merging PR8 after applicable checks pass. Preserve the task branch.
The [assignment](../../codex/prompts/006-whole-machine-lemmasim.md),
[capability inventory](LEMMASIM.md#task006-capability-inventory) and
[evidence](../evidence/006-whole-machine-lemmasim.md) retain the entire destination.
USGCE, repository settings, unrelated branches and durable formats are preserved.

## Baseline and implemented continuation

Main was fetched once at `abd9920d54df04ce52da9386170e99012c39bdfb`, tree
`7c30f469592f2c2a1bef6aab11f31d30a8a3ee28`. PR6's source-identical merge
closed the historical specification dependency. Main CI38200671355 passed;
it is not candidate CI. The prior candidate CI38218707989 failed the obsolete
literal-device artifact shape; `84058ad` repairs that gate to the actually
executed banked-pen/panel outputs. Candidate9812a22 CI38245370738 then passed
all nine target/RTL jobs, but failed three foundation workflow assertions:
the expected logs omitted new Lean/power pipelines, the observer inspected only
the first pipeline in a multi-command block, and literal-device counts still
expected four commands/two binaries instead of the actual eight/four. The
workflow and actual target/RTL observations are unchanged by the ensuing
host-regression repair. The failed run remains
[retained CI](https://github.com/srkftw/lemma/actions/runs/38245370738);
the repaired candidate requires its own CI result before merge.
The final pinned repair check passed 13 focused and 456 foundation host tests
(`build/task006-merge-ci-repair-a2/`); metadata and all18 scaffold tests also passed.
No guest, controller, workflow or physical input changed for this repair.

Historical implementation `9946e7ef` introduced persistent QEMU/RTL sessions,
exact backend-private checkpoints, isolated durable forks, native controller
presentation, canonical 0.2 capacity, banked pen and synthetic panel sequencing.
Those artifacts and genuine Task005 RTL notebook results retain their identities.
Continuation commits `536fea2`/`97e4dcb` reduce checked-copy/registry work;
`0626acc` adds profile0.3 and genuine Lean-controlled cooperative power with an
explicit fifth endpoint quota; `b01d336` fixes fast counters/UART reset state;
`2bf6658` replaces bytewise Lean Loader copying with checked aligned words;
`fff15dc` adds real warm notebook recovery and optional bounded-prefix checkpoints.
Pen/reset is `de21f0c5`; lightweight live input is `d8d7b0cc306a91a113b5a95e964a2a19313f457d`.
Target software and compiler policy remain elaborated Lean → checked Core0 → LLVM
→ freestanding RV64. Core0 kernel-v0.4 extends the admitted hardware binding,
not the accepted language. No managed-runtime rewrite or foreign target helpers.

`lemma-silicon-dev/0.3.0` retains 1650×2200 Gray4, 128MiB external RAM,
32MiB/8192 owned frames, scalar RV64IM/MSU/Sv39/PMP, 100MHz machine clock and
10MHz MTIME. The consumed definition supplies discovery/IRQs/timing to both
bindings. Historical 0.1/0.2 remain distinct. The 4KiB register-RAM synthesis
configuration cannot run this notebook. Both backends still use explicit
ELF-preload development boot; production Lean boot/update recovery is unfinished.

Power-v1, IRQ14, raw button levels and separately authorized syscall68 now reach
Lean kernel policy. Busy display/storage rejects suspend; accepted cooperative
suspend preserves RAM/tasks, clocks, panel and media, applies pen loss/resync,
and masks input until wake. No snapshot or suspend flushes, drains or completes
pending work. Warm and cold causes differ. Electrical power gating, watchdog
and brownout recovery are absent. See [Power-v1](../contracts/006-power-control-v1.md).

The final fast successor is QEMU11.1.1 SHA256
`927bef771d31134b73b76a2c219d1717144feec6986b07df5c58ef85d08ad6e5`.
Actual fixed counters use the declared clock and serialize their private phase,
write/inhibit state and reset baselines. Completed hardware reset clears the
full pen FIFO/time domain; software RESET1 keeps loss/resync semantics.
Device VMState3 requires the aligned pen reset origin; stale/missing/malformed
state rejects. Two proven host elapsed-time statistics are the sole checkpoint
exceptions; CPU/RAM/counter/origin/Power/wrapper state stays exact.
See [the observer relation](../../conformance/lemmasim/QEMU_STATE_EQUIVALENCE.md).
Paper warm state and full processor/CSR/reset-duration parity remain unqualified.
QEMU `cpu_common_post_load` flushes the software TLB. Cached Sv39 translations
and TCG blocks are not serialized, so current fast checkpoint-byte equality and
tested suffixes do not establish arbitrary cache-state exact continuation.
RTL caches/TLBs are captured in the savable model. Selected RV64IM excludes A;
QEMU's RISC-V reservation fields are nevertheless explicitly serialized.

## Actual observations

- Final canonical power workflow `build/l6-power-final-a1/result.json`: **PASS**,
  133.37s, fresh Loader notebook on final927. Busy rejection, held-contact suspend,
  queued wake exact fork, malformed Power rejection without live mutation,
  post-wake pressure ink/Save, new cold every-pixel recovery, failed FLUSH/no Saved
  and another new cold recovery. Cold Ready12.20s virtual/12.17s host on shared host.
- Warm notebook `build/l6-warm-final-a1/result.json`: **PASS**, 27.24s. Queued
  contact → genuine warm Ready → new raw-MTIME ink → Save31 → new cold exact pixels
  and bytes. Frozen checker/guest/source medium and first nine raw inputs are
  identical to retained `build/l6-warm-prepatch-a3/result.json` **FAIL**, where
  old6dc rejected new ink and reported pen loss8. No timestamp normalization.
- Final fast/retained RTL Power probe pair
  `build/lemmasim/task006-power-final-pair-a2/result.json`: **PASS** under the
  predefined partial relation. Only wake TIME has a declared 100000-tick bound;
  other guest records/admitted fields are exact. Same c49a5 probe/DTB/descriptor;
  QEMU927 and actual RTLc36. No whole-machine or microstate-migration claim.
- Current-only counter checker and warm-pen checker: **PASS**, actual prepared927,
  genuine audited Loader probe; fractional phase, inhibit/write/wrap, real reset,
  watchdog/contact forks and malformed origin/state negatives. Debugger CSR/MMIO
  observations do not qualify guest-issued counter instruction/privilege behavior.
- Genuine full Loader initializer/notebook/probe builds, strict audits and full
  notebook capacity checks: **PASS**, `build/task006-loader-plan/maintained-result.json`.
  Loader finite-RAM tests exercise all alignments, read/write cutpoints, RX/BSS,
  real8192-frame allocation/abort cleanup and OOM/bounds. No no-op helper.
- New canonical RTL prefix `build/silicon/task006-loader-cold-a1/result.json`:
  **OBSERVED_PREFIX_NOT_READY**, 100M cycles/354.74s, first sampled user mode38M.
  Earlier matched prefix remained supervisor at100M; retained 242M and 504M cold
  deadline failures remain FAIL. No current canonical RTL notebook Ready claim.
- Bounded RTL checkpoint smoke `build/silicon/task006-boot-checkpoint-a2/result.json`:
  **PASS**, 1M real probe prefix, unchanged snapshot boundary, existing-destination
  rejection, exact145270622-byte original/fork suffix states, teardown. Optional
  `check_silicon_boot.py --snapshot-final NEW_PATH` preserves in-flight work;
  failure to reach Ready remains failure. No unmodified100M prefix rerun.
- Native clock/input `build/lemmasim/task006-input-clock-a3/result.json`: **PASS**,
  exact raw capture and queued/cold/warm23298752-byte containers. Timestamp query
  median19.25→1.45ms over20 RPCs each; full post-inject observation remains.
- Final relevant host set: **PASS**,616 tests plus metadata,613 frozen code inputs
  unchanged. Separate pinned Lake build completed55 jobs. Not target/physical PASS.

The compact inventory retains each exact source-bound result and historical
failures. Relevant final host checks and candidate CI are recorded there/evidence;
no report-only edit inherits a fresh guest compilation or historical green CI.

## Resume and remaining work

Use [README launch/interaction/snapshot/replay commands](../../README.md#task006-persistent-machine-sessions).
Keep user media outside `build/`; prepared-source reuse is validated, init creates
exclusively, restore owns a private durable fork. Live adapters disconnect on
restore. Same-backend exact checkpoints are not cold recovery or cross-backend
microstate migration. Native Linux pins are usable; portable installer/browser
and manual physical tablet checks remain unfinished.

Continue canonical RTL kernel/memory/IPC performance and whole-profile timing,
CSR and paper warm-state mapping, plus fast cached-translation checkpoint coverage;
then production boot/update and a real bounded
Lean companion controller/protocol with an independently durable peer. No companion
command exists. Unexpected live backing-I/O fault decisions are not all recorded
for replay. USB enumeration, Wi-Fi6/BT5.4 digital MAC/baseband/PHY, electrical
power/watchdog/brownout, local Wasm worker/browser barriers, G2 managed runtime
and G5–G7 mathematics/courses/learner/tutor are required unfinished work.

[Physical evidence](../evidence/006-controller-physical.md) is separate: full pen
mapping passes, actual OpenROAD assertion is reproduced and WNS_PATH repair
applied, but 100MHz global setup WNS−3.542208ns and detailed-route timeout remain
FAIL. Paper timeout and SG13G2 LEF58 enclosure/CUTCLASS coverage remain unresolved.
Process DRC/LVS, routed extraction/post-route timing, large memories, compute/full
SoC, pads/analog/RF and physical panel qualification are not closed. Power-v1
physical flow is NOT_RUN. Do not rerun unchanged blocked flows for report updates.
