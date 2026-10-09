# Task 003 session state

- Assignment: `codex/prompts/003-kernel-isolated-services.md`.
- Repository: `/home/sreekumaar/Downloads/lemma`, `srkftw/lemma`; USGCE untouched.
- Branch: `task/003-kernel-isolated-services`, created from merged main
  `ff4045a79a6fda45f9cd8198587357846530a806`, tree
  `5a0df7b44d7b71c6966b8363399acdba41c73bbc`.
- Task 002 PR #2 is actually merged; main push CI `37888343897` passed.
- Execution window began 2026-10-08 22:40 America/Los_Angeles
  (2026-10-09 05:40 UTC). The user's 9–10 hours is a resource limit, not evidence.
- Highest complete Task 003 gate: C. A/B committed141f309; C passed actual O0/O2
  acceptance below. D–K are not run.
- Baseline: incremental Lean build 53 jobs, scaffold metadata valid, scaffold 18,
  Core0 host 32 and foundation host 438 tests all passed. Focused Task 002 monitor
  passed 18 O0/O2 boots, 1,598 requests, 1,415 actual IRQs, 20 synchronous
  recoveries and 192 retained records. Source was merged main with the untracked
  assignment file; this is not cold clean qualification.
- Baseline evidence: `build/kernel/baseline/baseline-summary.json`,
  SHA-256 `f937d76f0e46e86ed3b0ce5373b73bbd84588520454e2a2baea385994f76f785`;
  `monitor/gate9-results.json`,
  SHA-256 `4354fa2b8eeb084e6e1ee82b9fb6c720397d9b69078a15151fde65bacbc92ffb`.
  Full 161-file inventory and closed command logs are under that baseline directory.
- Implementation ownership during this session: root production layout, allocator,
  firmware policy, console, runner and integration; compiler worker execution
  profiles, lowering and production exporter; platform worker typed M/S/U glue
  and boot DTB validation; integration worker host builder/auditor. No production
  module may import `Compiler.Test`, examples or mutation modules.
- Next executable checkpoint: build genuinely elaborated production kernel and
  separately compiled user module with the new exporter; audit the privilege/object
  separation, then boot and test the real frame allocator before supervisor entry.
- Do not relabel baseline or earlier Task 002 artifacts as Task 003 passes. Do not
  infer completion of a gate from its modules. Preserve legacy profiles and checks.

## Current implementation checkpoint (06:10 UTC)

- Added closed firmware/kernel/user execution profiles, exact primitive catalog,
  effect metadata and static frontend admission. Targeted compiler build and
  30 frontend probes passed; four probe roots passed real LLVM O0/O2 lowering.
  This is compiler-boundary evidence, not guest acceptance.
- Typed startup/context/CSR/PMP/SRET/SFENCE glue compiled and assembled for RV64.
  Production firmware policy now validates fixed M frame, saved S origin,
  ECALL PC and private call number; hardware IRQ path parks MTIMECMP, counts
  real IRQs and latches SSIP. No guest firmware execution claimed yet.
- Runtime frame allocator owns 512 actual 4KiB frames with 32-byte records,
  zero-before-grant, per-task quotas, generation handles, mapping-release guard
  and exhausted-generation retirement. Fixed callback index/count ordering
  before target export. Lake module build passed; no guest allocator run yet.
- Console polling algorithms factored into maintained ConsoleDevice; legacy
  fixture names delegate. Regressions remain due after this factoring.
- Layout reserves boot parser metadata+0x800..0x900, frame records+0x1000,
  accounting+0x100; physical-access bounds reject unrelated reserved memory.
- Production exporter and host builder/auditor are being connected. Next exact
  command: `nix develop --no-write-lock-file --command ./scripts/build-kernel.sh
  --stage bootstrap-m --opt-level O2 --output-dir build/kernel/bootstrap --clean`.
  Inspect help before invoking if arguments changed. Gate A remains in progress.

- First actual production export failed closed on a legitimate private helper;
  fixed authorization uses Lean's canonical private-to-user name and keeps the
  raw emitted identity. Second actual build compiled all three units, then
  failed on a malformed generated user linker brace; the generator is repaired.
  Failures and partial artifact inventories are retained separately under
  `build/kernel/bootstrapA-failed-attempt1` and `...-attempt2`. Attempt 3 is
  currently running with production/compiler source frozen.
- `scripts/run_kernel.py` now provides bounded raw K1 observation with fresh
  artifact audit/source binding and explicit process cleanup. No runtime PASS
  exists yet. Next command after builder/auditor success: `nix develop
  --no-write-lock-file --command python3 scripts/run_kernel.py --image
  build/kernel/bootstrapA/image.elf --output-dir build/kernel/bootstrapA-smoke
  --timeout 30 --clean`.

## Actual first guest checkpoint (06:30 UTC)

- Attempt 7 production bootstrap O2 build and complete artifact audit passed.
  Boot ELF SHA256 `deed5ef908b4e4d36c4ec0aa84366f920a361e96e67eab2f8ebf887f11d2c943`;
  97 function symbols/9,884 FUNC bytes. Independent user ELF has 4 functions,
  152 FUNC bytes, 4KiB BSS; package280 bytes. Source still dirty ff4045a base.
- Actual smoke FAIL, not a gate pass: guest returned
  `K1 00000000000000e0 000000000000003d 0000000000000000 0000000000000000 0000000000000000`
  (BootInfo.invalidStructure=61). Raw/result retained in bootstrapA-smoke;
  explicit host stop/reap completed. Initial runner import error was fixed before
  this actual run. Compiler/library freeze cleared after terminal observation.
- Root is adding actual parser cursor/depth/memory-complete diagnostics. Platform
  worker fixes parser and rejects reserved-memory; it also owns forthcoming S
  trampoline, explicit mstatus mask and mie=0x82 correction. Compiler worker
  adds closed failure-preserving Action.loop + S SSIP pending read. Integration
  worker adjusts only precise legacy UART helper catalogs after factoring.
- Added three kernel-checked indexed ownership model lemmas (separate live
  owners have disjoint pages, free is not live, indexed pool envelope). Model
  proof is separate from allocator/LLVM execution. No target Gate B PASS yet.
- Next: genuine current build after parser diagnostic/fix, audit, then the exact
  run_kernel smoke command above. Do not advance guest acceptance past failing A.

## Gate B snapshot checkpoint (06:50 UTC)

- Repaired bootstrap actual O2 smoke passed: DTB0x87e00000, stage0, 512 slots,
  pool0x82000000. Evidence `build/kernel/bootstrapA-trace2-smoke/result.json`.
  It is a fresh-protocol/live-process observation followed by SIGKILL/reap (-9),
  not normal VM exit. Full allocator behavior and U execution were not-run there.
- Exact pinned QEMU/libfdt output has nonzero property alignment padding. The
  guest now bounds/skips at most3 property-gap bytes; it retains zero node-name
  padding checks. Root reserved-memory is rejected to avoid pool overlap.
  BootInfoSHA2565edea70b265b4b534082fe61423adcb4c4c488c42be356d499361f5cc322bff1.
- Firmware machine context review found SSIE alias overwritten by mie0x80; typed
  startup nowwrites0x82, explicitlyclearsmstatus0x1baa, and enters a controlled
  supervisor trampoline. Pending bridge reads actual SIP.SSIP as0/1. No new S
  runtime claim yet. QEMUrv64 has H read-only mideleg bits0x1444, so raw expected
  readback is0x1446 (not desiredwrite2), with additional sources disabled.
- Closed Action.loop + kernel-only readSupervisorPending implemented.47 genuine
  probes and four LLVM O0/O2 modules passed; Task001 complete legacy checker
  passed at build/core0/compiler-loop-regression. No guest new-op pass yet.
- Explicit normal vs frames-development exporter/build/audit configurations bind
  exact roots/manifests. Normal/fwu exports reject development imports. Six unit
  exports/two boot exports/eight rejection probes passed;13 host audit tests pass.
- Development FramesEntry imports maintained Entry/Frames/Batch and supplies
  continuous bounded40-byte request transport. Normal Entry imports no development
  code. Batch32 uses kernel scratch0x80400400, count0x80400500; rolls back actual
  frames after partial quota/exhaustion failure before exposing its handle list.
  Callback/ge syntax errors were fixed before genuine export; no B guest pass yet.
- Legacy UART aliases required explicit lambda wrappers; repaired. Precise Gate6/7/8
  host catalogs updated. Gate9 fingerprints are deliberately stale until fresh
  closure/body comparison and18 boots after this freeze. GateA current-regression
  portion remains pending; do not label A complete yet.
- All agents have frozen maintained sources for normal/development O2 snapshot.
  Root is building build/kernel/gateAB/normal-O2 then frames-development-O2; next
  audit each, smoke normal, run reserved-DTB rejection andcheck_kernel_frames.py.
  Highest complete gate stillnone; A artifact+actualsmoke portions passed, Bnotrun.

## Actual Gate A/B O2 observations and final snapshot (07:08 UTC)

- Fresh normal and frames-development O2 builds and complete artifact audits
  passed in `build/kernel/gateAB/normal-O2` and `frames-development-O2`.
  Normal boot observed K1(a,87e00000,0,512,82000000). The development guest
  passed actual ownership/read/write, full-page zero reuse, quota, unique global
  exhaustion/recovery, stale/double/wrong-owner release and partial quota rollback.
  Results retain explicit host SIGKILL/reap; no normal VM exit claim.
- Custom root reserved-memory/pool DTB actually rejected before frame init with
  K1(e0,62,87e0009c,1,0), retained at normal-O2-reserved-dtb-run.
- Strengthened final checker adds live wrong-owner read/write/resolve, readonly
  content unchanged, global partial batch rollback, maximum-owner rejection,
  development mapping bookkeeping guard and terminal generation retirement.
  Retirement legitimately reduces capacity to511 after first restoring512.
  Installed mappings/invalidation remain Gate D, not proved by the fixture.
- Ownership model now excludes the retired UInt64 owner sentinel from live
  grants. That source change deliberately makes the old O2 inventory stale.
  The new maintained BootInfo checker initially failed closed before launching
  QEMU because of this stale inventory; result preserved, no guest spawned.
- All439 foundation host tests passed after precise UART closure/index updates.
  Global source freeze begins for final-normal-O0, final-frames-development-O0,
  fresh O2 snapshots and18 legacy monitor boots. Highest complete gate stillnone
  until the current snapshot/legacy observations terminate successfully.
- Next actual root command is running final-normal-O0 build; then development
  O0 build and current frame checker. DTB checker takes the fresh normal image.

## Passed A/B integration (07:16 UTC)

- Accepted current snapshots: accepted-normal-O0/O2 and
  accepted-frames-development-O0/O2; all builds, fresh complete artifact audits,
  normal guest boots, two three-case DTB corpora and2214-record frame corpora
  passed. SIGKILL/reap is explicit finite host cleanup, not a guest normal exit.
- Fresh legacy monitor passed18 boots/1598requests/1411actualIRQs/20sync
  recoveries/192records; all PIDs reaped. Earlier zero-boot audit failure retained
  as final-legacy-monitor-first-failure. The stale definition count140->143 and
  old host test indices were repaired only after exact source/IR comparison.
- Current host checks: scaffold18, Core032, foundation439, kernel audit13 PASS.
  OwnershipModel source kernel-checked after excluding the retired-owner sentinel.
- Prefix result and full source/artifact inventory: build/kernel/gateAB/prefix-result.json
  and hash-inventory.json, compact checked-in report docs/evidence/003-kernel-isolated-services.json.
  Tested sources are dirty on ff4045a; no clean-worktree qualification yet.
- Next: commit passing A/B increment, clear freeze, add real S firmware bridge
  witness/readback checks and bounded actual MTIP->SSIP acknowledgement acceptance.
  User execution, installed mapping invalidation, scheduling, IPC and services remain not-run.

## Gate C implementation/audit checkpoint (07:43 UTC)

- A/B coherent implementation committed as141f309804be9d526199b516ca4515beaf87a5e6.
  Branch remains local/unpushed; no Task003 PR exists yet. This commit preserves
  the highest passing prefix. Current C changes are not accepted evidence.
- Root MachineServices bridge reads/verifies actual PMP/delegation/status/SATP
  startup fields and uses genuine S ECALL origin witness, hardware timer count,
  WFI/pending SSIP, bounded deadline validation and acknowledge/rearm. Normal
  Entry stage1 emits A,C0,C1,C2; stage0 retains bootstrap behavior.
- Typed startup_case machine-origin-probe is separate development config using
  normal exact roots but forbidding Development imports, bootstrap-m only.
  It installs M vector/mscratch, ECALLs in M(a7=3), expects rejection/fatal48;
  unexpected-return fatal52 is distinct. Default startup renderings unchanged.
- Genuine exporter12exports/11rejections PASS; hostchecker/audit20 tests PASS;
  platformLeanrender+RV64 assembly/disassembly PASS. No C guest pass yet.
- Actual first supervisorO2 attempt failed BEFORE QEMU launch: artifact audit
  rejected optimizer-generated readonly switch.table for pure expectedPmp.
  Raw failed observation retained; pid=null/records=[], no guest was spawned.
  Integration worker implements narrow known4entry table/guard/load admission;
  arbitrary mutable/foreign tables/nonvolatile RAM accesses remain rejected.
- Current target/compiler sources frozen except exact auditor/test repair.
  Rebuild after repair due bound host inventory; next command builds fresh
  normal supervisorO2 then check_kernel_supervisor.py --case supervisor, and
  machine-origin-development/bootstrap-m then --case machine-origin; repeatO0.
- D is planned only. Opaque owned-AS descriptors, independent4KiB kernel maps,
  user-PTE W^X (explicit trusted S RW management alias), lazyL0s, pagepins/full
  flush and inactive-root teardown agreed. Platform proposes saving suspended S
  caller at reserved boot-context80500000 and restoring it before reclamation.
  No D implementation/guest acceptance yet; prerequisites remain enforced.

## Actual Gate C passing prefix (08:01 UTC)

- Qualified normal supervisor O0/O2 each passed four genuine records: stage1,
  S-origin witness534543414c4c0001, validatedPMP1b1b1f1818/medelegb1ff/mideleg1446,
  actualMhardwarecount0->1, SIPpending1->0, recoverable17/22/22 and validrearm.
  Explicitlive-hoststop/reap(-9); this is not a deliveredS trap or scheduler test.
- M-origin development O0/O2 each passed actual synchronousMECALLcause11 at
  auditedPC800001a4 and realQEMUexit48, emptyUART/stderr, processreaped naturally.
  Hosttransport unexpectedkeyword and pinnedQEMU0x-prefixedPC parser errors were
  repaired after actual failures; failed outputs remain separate. Expectedexit48
  is specific to the negative protocol, not a normalimage shutdown shortcut.
- Complete artifacts audited, including exact compiler-produced4entry PMP
  readonly table/guardedload and32byteAM/align8 object section, bound byte/hash
  extraction. All other globals/nonvolatileRAM/writable/foreign sections reject.
  Current kernel host22PASS; actual table/content/unguarded/writable negatives included.
- C result/fullinventory at build/kernel/gateC/prefix-result.json andhash-inventory.json;
  compact checked-in report updated. Source remainsdirty on A/Bcommit141f309 until
  coherent C commit. No Task003push/PR, no clean qualification, D–Knot-run.
- Freeze clears only after C commit. Next dependent work: reusable owned Sv39
  AddressSpace module, typed suspendedS continuation, generic descriptor loader
  and first separately linked U program. Then actualhardwaredenial/teardown.
