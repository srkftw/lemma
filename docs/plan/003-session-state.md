# Task 003 session state

- Assignment: `codex/prompts/003-kernel-isolated-services.md`.
- Repository: `/home/sreekumaar/Downloads/lemma`, `srkftw/lemma`; USGCE untouched.
- Branch: `task/003-kernel-isolated-services`, created from merged main
  `ff4045a79a6fda45f9cd8198587357846530a806`, tree
  `5a0df7b44d7b71c6966b8363399acdba41c73bbc`.
- Task 002 PR #2 is actually merged; main push CI `37888343897` passed.
- Execution window began 2026-10-08 22:40 America/Los_Angeles
  (2026-10-09 05:40 UTC). The user's 9–10 hours is a resource limit, not evidence.
- Highest clean cumulative Task003 acceptance: H at isolated committed repair
  `f77a6b1b3609876816000ce86a8a6c1904c3de2a`, tree
  `d79e57eb0961287321d50eebf0b63f5ff8b64a3e`. Fresh cold A-E+F+G+H passed:
  26 images,30 checker reports,34 guest sessions. Independent full raw/artifact/stack/process review passed. Earlier clean G and focused H reviews remain separately scoped.
  I focused O0/O2 execution now passed; its independent review and clean cumulative checkpoint are pending. J/K remain unverified; the latest checkpoint at the end is authoritative.
- The user explicitly extended the original time window until the full milestone
  is verified and authorized merging afterward. Do not merge a partial prefix.
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
- Next executable checkpoint: independent current I review and standalone User
  comparison, coherent I commit, then cold A-I controller `/tmp/lemma-gateI-clean-run.py`
  at that exact clean revision. Focused I O0/O2 passed; J/K unverified.
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

## Gate D integration checkpoint (08:29 UTC)

- Highest accepted prefix remains C at0aeb8f07940c404357ca95e091f13e843af1ca2f;
  current D sources are unaccepted, local and unpushed. No Task003 PR exists.
- Maintained AddressSpace uses owned11-table4KiB Sv39 trees, exact live-PTE
  lookup, purpose/permission checks, leaf pins/full invalidation, inactive-only
  teardown and a supervisor-only metadata alias atVA30000. Kernel AS owner1
  has no U leaves. User-PTE W^X only; S pool management remains RW/NX.
- Loader validates the complete bounded package before allocation, creates
  real text/data/stack frames, copies initializedbytes, zeroes BSS through the
  allocator, fences instructions and publishes an owned sanitized context.
- Process/Operator/Entry genuine module build passed21 jobs after fixing an
  omitted ABI import and the reserved Lean keyword initialize (now bootServices).
  Process selects exact owned Kstack frame and actual saved U origin/SATP.
  Exit restores fixed S continuation before freeing user resources; the normal
  serial loop accepts fresh40-byte run requests without a session lifetime cap.
- Platform typed continuation genuine Lean/RV64 assembly/decoded ABI probe
  passed; Loader and AS LLVM probes passed. These are host/compiler observations,
  not U execution evidence. Guest D observation is still not run.
- Next: freeze sources, build normal supervisorO2 in build/kernel/gateD, run
  check_kernel_user.py against fresh audited image, inspect actual U result and
  baseline reclamation. Then O0 and quarantined real architectural denials.
- Execution window has6h11–7h11 remaining until14:40–15:40 UTC. Preserve the
  final portion for cumulative legacy/foundation checks, clean qualification,
  commit/push/draftPR and actualCI. No dependent E/F work yet.

## Actual Gate D positive prefix (08:35 UTC)

- Normal supervisor O0/O2 each passed3 fresh U runs (0,7,u64max), actual exit
  cause8/PC10024/status200000020/SATP800000000008200d, stored mix result,
  frames483→500 each time. No DF occurred, so U timer delivery/scheduling is
  not claimed. Both independent ELF/text artifacts passed complete fresh audit.
- Address-space development O0/O2 passed real construction/map/walk/pinning,
  aliases and teardown, permission/purpose/generation and corrupt-PTE software
  walk rejection, actual create/lazy-L0 quota rollback and final512 capacity.
  Active-root fixture is bookkeeping only, not CPU activation evidence.
- All4 QEMU PIDs are absent, explicit finite host kill/reap(-9), stderr empty.
  Positive subportion result/inventory at build/kernel/gateD/positive-prefix-result.json
  and positive-hash-inventory.json; compact report binds those hashes.
- Full D still in progress. Next source increment adds quarantined User attack
  roots/typed CSR and NX startup cases, paused private peer setup, actual fault
  capture and containment/reclamation tests at O0/O2. No E–K implementation yet.

## Extended milestone authority and Gate D containment repair

- The user explicitly extended the original time window: “Continue until the full
  milestone is verified.” The later “finish and then merge” authorizes merging
  Task 003 only after full A–K verification and actual GitHub checks. Earlier
  draft-only and time-window handoff restrictions are superseded by this request.
- Gates E–K remain not run. Work stays on the existing branch, without discarding
  local work, changing repository settings, deleting task branches or touching USGCE.
- Actual current-policy counterexample: forbidden U instruction fetch at kernel
  VA 0x80200000 naturally stopped QEMU with kernel-fatal status50. Retained under
  build/kernel/gateD/kernel-fetch-policy-counterexample-O2-run/result.json;
  no host-kill claim applies to that naturally reaped failure.
- Process now validates owned trap stack, U origin and exact SATP before treating
  saved PC as diagnostic data. Hardware U faults terminate44; ordinary ECALL
  returns retain aligned mapped executable-site validation. An SSIP at an invalid
  target may resume the verified U context so hardware reports the precise fault.
- Fixed kernel-fetch and illegal-halfword-fetch cases passed separately at O0/O2,
  actual44 and frames483→500, live host-stop/reap. The pinned CPU supports C/Zca:
  the 0x10002 case is illegal instruction2/stval0, not an IALIGN32 misalignment.
- Review found initialized-data-copy lacked a nonempty witness. A declared16-byte
  image-data header and actual U checks of ABI word/BSS are being added before
  committed clean A–D acceptance. Full D remains in progress until that run passes.
- Next: finish precise data/corpus audit changes, commit coherent D increment,
  run fresh committed check_kernel.py A–D acceptance, then advance to Gate E.

- The declared initial-data normalO2 witness passed3 fresh actual U runs; the
  linked16B[0,1] data object/package is audited, U reads ABI1 and zero BSS at
  0x20010, and all process frames return to500. Evidence:
  build/kernel/gateD/data-witness-normal-O2-run/result.json.
- Kernel builder now explicitly realizes the immutable Lean source, verifies
  its locked NAR hash/size and UInt source hash, and records actual Nix commands
  in build/provenance/audit evidence. Each CI job therefore obtains its own audit
  source input. Full clean D remains pending at this coherent candidate commit.

## Clean Gate D checkpoint

- Exact source fb524b945f66241ee36a434abe39b3d854c2d9d2, tree e9d21676f615560d05340d1fdf26695968a0282c,
  fresh managed worktree, no copied project outputs, clean before/after.
- check_kernel.py --work-dir build/kernel/D-clean --clean --timeout300
  --qemu-timeout90 --deadline2400 actually exited0 in280.32s:
  45host tests,18fresh images,22checker reports and26QEMU sessions.
- O0/O2 normal three-run data/BSS/exit/reclaim, allocator/AS APIs,23 malformed
  package cases and late-quota rollback passed. CSR/NX/kernel-fetch/illegal
  halfword each ran3fresh instances; paired peer isolation ran4faults with
  normal continuations. All raw hashes/stderr/source identities independently
  checked, all PIDs absent;24live host-kill/reap and2natural fatal48 negatives.
- Report SHA256 c077b8b57a134c17101a634875e64a23f4aa7ec7a8e076eda3671a3683d7d0e2;
  full1720file inventory build/kernel/gateD/D-clean-hash-inventory.json, SHA256 c6dbb1c4711d2b860397e8e5799291140752df4d5886f3b3daf4a6746c828400.
- Highest complete gate D. E–K not run; full milestone and merge remain pending.
- Next: User.Syscall/Memory, owned-buffer UserCopy, compiled syscall dispatcher,
  genuine U ABI boundary tests and precise O0/O2 trap-stack budgets.

## Gate E syscall construction and actual stack rejection

- User.Syscall/Memory, full-range UserCopy and the ordinary syscall dispatcher
  passed genuine Lean elaboration and production LLVM/RV64 probes. These are
  compiler/audit observations, not Gate E guest acceptance.
- The first complete O0 syscall development artifact built, then audit exited1:
  Entry.dispatch requires4144 bytes against actually owned4096 bytes. The
  rejection occurred before QEMU launch. Exact retained report:
  build/kernel/gateE/first-syscall-O0/audit-failure.json, SHA256
  a90a1ba2a600c68b0090dd5cd7d300650cefef7dfeabb09df9e1df732ea4ada7.
- Remediation allocates two physically contiguous, independently versioned
  purpose1 frames, zeros both before publication, records both handles in the
  descriptor and revalidates their owner/purpose/pins/contiguity before reading
  a trap frame. Teardown happens only on the restored S reaper stack.
- An independent audit review also found unsanctioned destination-SP writes
  could evade primitive frame accounting. The auditor is being tightened to
  allow only exact per-symbol machine-boundary switches and fixed self-SP
  adjustments; narrow negative regressions retain the counterexamples.
- Highest verified gate remains D at its exact clean checkpoint. E remains in
  progress with no guest pass yet; F–K are not run. Next: freeze the stack
  repair, build and audit fresh O0/O2 artifacts, run actual pair-allocation and
  syscall boundary guest checks, then repeat affected D regressions.

## Actual repaired-stack Gate E O0 run and UART prerequisite

- The repaired complete O0 artifact passed audit with4256/8192-byte trap chain,
  4768/61440-byte S boot chain,1088/65536-byte M chain and1328/8192-byte U chain.
  Owned-pair source/IR bindings were checked; this did not pass Gate E by itself.
- The actual U corpus reached identity/time/sleep, allocation, binary output,
  invalid crossing input with unchanged sentinel, and pageB reallocation.
  Its first successful request32 then returned one byte. The user expected16
  and ended before echo/recovery; the checker failed correctly. QEMU remained
  live and was explicitly killed/reaped(-9); stderr was empty.
- Retained actual failure: build/kernel/gateE/stack-repaired-candidate/
  user-syscall-development-O0-run/result.json. The failed candidate report and
  raw bytes remain intact. No O2 or other candidate image pass is inferred.
- Pinned QEMU source archive matches the locked flat SHA256. serial.c shows
  disabled FIFO and legacyFCR0x07/trigger1 both advertise one byte; receiving
  the full host payload into its pipe does not mean16 bytes are in the UART.
  Source investigation report: build/kernel/gateE/host/uart-short-read-investigation.json.
- Repair introduces only a closed kernel-only fixedFCR0xc7 trigger14 operation
  in versioned core0-kernel-v0.2, preserving old profiles and0x07 semantics.
  It initializes once before the input protocol. The crossing test will require
  one actual read to deliver9..16 bytes, then record any completion reads
  separately before checking the full16-byte independently chosen echo.
- A verified U halfword ECALL now terminates its instance44 rather than making
  its user-selected PC a kernel-fatal condition. No such ECALL pattern appeared
  in the inspected D/E payloads; that is not a general proof. A narrow typed
  quarantine fixture using overlapping00730013/00000000 words is planned for
  direct cause8/halfword-PC containment evidence before full qualification.
- Highest complete gate remains D; E is in progress, F–K not run. Next is fresh
  complete O0/O2 pair/syscall evidence after this versioned UART correction.

## Gate E versioned UART focused candidate passed

- Fresh dirty-candidate builds/audits and actual guests passed for E syscall and
  frame development at both O0/O2. Source and acceptance inventories remained
  equal before/after the166.20s run. Report: build/kernel/gateE/fifo14-candidate/result.json,
  SHA2567c41215665530322d956c285b3650ec7cafef7a2ca463cf4e7dff372962f1557.
- Each E guest ran three fresh U corpora with binary output/input, one actual
  successful9..16-byte two-page read, separate completion counts when needed,
  and exact reclamation. All four guests were explicitly killed/reaped; stderr
  was empty and all PIDs absent. This focused candidate is not clean acceptance.
- The compiler FIFO14 fixture/export/LLVM probe passed on its second external
  driver attempt; first syntax failure remains intact. The complete held kernel
  and user LLVM probes also passed, report SHA256
  1b1889cb59d7a0e04e95ec2c232a307f166091b61ede2bce967eb20e9b0b14b4.
- Host checks: Lake55jobs, kernel58, Core032, repaired foundation440, scaffold18
  and scaffold metadata passed. The earlier foundation439 suite failed four
  static CI assumptions after adding the kernel job; retained failure logs were
  not relabeled. Tests now scope the original foundation job separately and
  require the exact bounded kernel lane. A host sleeping-process fixture now
  waits for bounded actual readiness before testing interruption ownership.
- Highest verified gate remains D pending fresh committed-source A–E acceptance.
  Next: commit this coherent E candidate; create a fresh worktree at that commit;
  run check_kernel.py --work-dir build/kernel/E-clean --clean --timeout300
  --qemu-timeout90 --deadline2400 and independently inspect all raw evidence.

## Clean Gate E checkpoint

- Exact implementation0f34b21c5b1f6482f507b131bd28851b9b26fed0, tree
  85874c8a207af2103a717febfdbccde50147ec5f, fresh managed worktree
  /home/sreekumaar/.codex/worktrees/lemma-kernel-e-acceptance/lemma.
- Actual check_kernel.py E-clean exit0,437.64s:58host tests,20fresh O0/O2
  images,24checker reports,28QEMU sessions and6fresh syscall U instances.
  Complete A-D regressions also passed, including actual architectural faults,
  loader rollback and frame pairs with independent generation histories.
- Independently reread source identity/inventories, hashes and raw captures:
  equal to the clean tested commit,26live host kill/reap(-9),2natural M-origin
  fatal48, all PIDs absent and all stderr empty. Aggregate SHA256
  83ead347364c6fc940cf69778d860f1c388a73346f088386c6d62f5876406962.
- Full hash inventory: build/kernel/gateE/E-clean-hash-inventory.json. This
  is an A-E acceptance checkpoint, not full milestone qualification or CI.
- Highest complete gate E. Next: owned8-slot Task table, copied U contexts,
  timer-driven round-robin Scheduler and independently linked compute/sleeper/
  noncooperative tasks. F-G lifecycle APIs must restore the stable S root and
  reaper stack before reclaiming an instance. F-K remain not run; no Task003 PR,
  remote push, actual CI or merge has occurred.

## Gate F construction checkpoint (not acceptance)

Source is on `465aeb5a38198da972f6989c5cc2e9afc9127380` with uncommitted Gate F work. The highest verified gate remains E. The held new Task/Scheduler and preserved legacy Entry source closures passed genuine elaboration and O0/O2 strict object stack probes (`build/kernel/tasks-F-final-probe/probe-report-complete.json`, SHA256 `66c58e3d3d982d63c635d4dcb12c7761272104a6b420ef5be161125037bbec1d`). Six independent user build/audits and two full tasks-development package builds/audits are running; no F guest has run yet. The new host observation checker is `scripts/check_kernel_tasks.py`; its malformed-observation rejection tests passed separately. Continue with actual O0/O2 guests, then a narrowly isolated timer-disabled negative. Do not infer scheduler acceptance from object builds.

The E independent review also completed: `build/kernel/E-clean/independent-summary.json` in the E acceptance worktree has SHA256 `3fdb8a90d955f2f739d3443b78c6d5c264b19face43ff59c1082846f1aba6807`; source/820 generated and 86 raw artifacts/60 object stack rereads matched. This later summary is separately hashed and was created after the earlier E inventory.

## Gate F strong runtime checkpoint; mandatory negative pending

The compiled scheduler uses a1ms runnable quantum and100ms idle maximum (earlier sleeping deadlines still shorten it). Compute now executes8 rounds of32×4096 scalar churn steps within the already accepted bounded-loop profile. Initial100ms O0/O2 sessions passed the earlier protocol but did not interrupt Compute arithmetic; stronger1ms sessions were correctly rejected because their SSIP PCs were only syscall returns. Those failed `tasks-{O0,O2}-attempt2` reports remain retained.

Fresh `artifacts-attempt4` O0/O2 builds/audits passed. Actual strong `tasks-O0-attempt3` and `tasks-O2-attempt3` sessions passed:12 instances each,1283/1491 records,570/679 actual M IRQs,47/35 interruptions inside audited Compute arithmetic, independently checked results/canaries, all-sleeping WFI,8-slot exhaustion, stale IDs and complete reclamation to499. Both live guests were explicitly killed/reaped(-9), PIDs absent, stderr empty; exact raw coverage was rechecked after cleanup. Report hashes are in the ledger.

Latest checks: Lake55 jobs, kernel host85, Core0 host32, foundation host440, scaffold18 and metadata all passed. These are current-source development observations, not clean final qualification. Six standalone artifacts at `build/user/gateF-attempt2` are historical before the quantum/workload changes; do not relabel them. Fresh recaptures are deferred until the stronger protocol is accepted.

The host-only `check_kernel_timer_negative.py` and4 negative-evidence rejection tests are ready. Commit all coherent F source/checker work, create an isolated worktree at that exact commit, replace ONLY the validated successful Firmware.call5 arm path using `timer_disabled_source(original)` (ACK SSIP, compareMAX, write actual deadline, normal reply), and build/audit both profiles. Run the negative CLI with its matching strong positive report and exact candidate commit. It must retain the inner positive checker FAIL and establish missing preemption after genuine Compute yield/Sleeper sleep/final Busy dispatch; no arbitrary startup failure or timeout is acceptable. Highest complete gate remains E until that observation is real. User authorization remains full A–K verification followed by merge; no partial merge.

## Gate F timer control complete; G authorized construction

Both isolated negatives passed at committed F source `bf8e3dc...` with only the canonical call5 firmware mutation retained. Each fresh O0/O2 image passed its complete artifact audit; each inner positive Session is still FAIL on the exact8-second read deadline after16 actual records/1408B, Compute yield, Sleeper sleep and Busy dispatch, with zero preemption. Both PIDs626140/627490 were live until explicit kill/reap(-9), absent afterward, and stderr empty. The independent summary hashes154 generated files and6 raw files; all source, runner and positive-control bindings were reread. The ledger contains exact report hashes.

Six fresh standalone User builds/audits on clean committed F source also passed; all14 artifacts per image match the terminal full packages exactly (`build/user/gateF-final-source/result.json` and `comparison.json`). Strong runtime artifacts honestly retain their precommit465aeb5/dirty provenance; exact compiled-source hashes match committed F. Do not rewrite those identities.

A new clean managed `lemma-kernel-f-acceptance` worktree at exact F commit is running `/tmp/lemma-gateF-clean-run.py` (shell session41374): cold A-E regression, then fresh full O0/O2 strong F guests. It copies no previous project outputs and writes `build/kernel/F-clean/result.json` transactionally. Preserve the separate timer-negative checkout and artifacts.

Gate G construction is now authorized because focused F and mandatory timer controls actually passed. Platform owns FaultEntry/Pressure/shared TasksEntry transport factoring; compiler owns exact four-image registry/configuration and typed per-image startup; auditor owns narrow Fault-only CSR admission; root owns User.Development.Tasks.Fault and the G observer. New image index3/ID4 returns from validated zero data/BSS/user-stack checks into the existing typed actual supervisor-CSR probe. No G guest has run. No H/I/J implementation has started; the full A-K milestone plus confirmed merge remains the user objective.

## Cold F complete; G artifact checkpoint

- Fresh clean A-E+F controller exited0 at exact `bf8e3dc`/tree `ec56befa`.
  Its scope requires the separately retained canonical timer negatives and six
  independent user builds. Independent reader checked 22 images, 26 reports,
  30 sessions, 92 raw files and 12,737 packets with all PIDs gone.
- Cold O0: 1,189 records, 533 real M interrupts, 49 Compute arithmetic
  interruptions; O2: 1,500 records, 684 interrupts, 34 arithmetic interruptions.
  Both 12-instance runs restored499 frames and observed actual all-sleeping WFI.
- Report and independent reader hashes are in `003-gates.json`. No historical
  focused precommit artifact was relabelled as clean checkpoint output.
- G modules compile; host evidence rejection tests pass. Genuine exporter
  negative probes uncovered an unused Compiler.Test import accepted by the G
  direct exporter; the narrow G-only rejection is repaired and all14 real
  export probes now pass. The failed pre-repair report is retained.
- G four-image O0/O2 builds are running with source frozen. The new lifecycle
  checker requires actual fault instructions, repeated fresh owners/identities,
  same physical data/stack reuse with zeroed secrets, continued independent
  peers, real late loader quota failure/rollback, and complete baseline cleanup.
  No G runtime success is yet claimed.

## Focused Gate G complete; next H

- O0/O2 full four-image builds and audits passed. Independent Fault builds
  matched all14 ELF/object/payload/IR/unit/generated artifact bindings.
- Final lifecycle attempt2 O0: 2,217 packets, 995 actual M IRQs, 17.208412s;
  O2: 2,697 packets, 1,222 IRQs, 12.333771s. Each has18taskinstances,
  13actualCSRfaults/code44, 10samephysicaldata/stackreusepairs with
  fresh User zero checks and four real late quota38 rollbacks.
- The same Busy instance progresses through every cycle. All tasks are removed
  and reclaimed on the restored kernel root/stack; both final baselines499.
  All raw packet grammar/hashes, command/ACK order, 112source/8runner bindings,
  actual fault PC0x10060/stval0x10002573, stack bounds and killed/reaped PIDs
  were independently checked. Focused provenance is honestly bf8e3dc+dirty.
- A duplicate-EA evidence-parser gap was repaired with a negative fixture and
  fresh attempt2 O0/O2 sessions; attempt1 remains historical evidence.
  Pinned kernel host suite99 and scaffold metadata/18tests pass.
- Commit this coherent G source, then run fresh cold A-E+F+G in an isolated
  worktree. No cached earlier result will certify that new snapshot.
- H design reserves descriptor+2560..+3647 for16capentries and a header,
  one owned global16objectframe, monotonic local handle serials and bounded
  object-wide revoke. Managed creation publishes after reviewed boot grants;
  managed legacy console must deny before device effects. H is not yet built.
  User authorization remains full A-K verification and then confirmed merge.

## Cold Gate G complete; H artifact freeze

- Fresh managed G acceptance worktree at exact e61766a/treea746, with no copied
  outputs, completed its controller in562.352068s:24images,28checker reports,
  32actual QEMU sessions. Report SHA256
  d1d8005299b052a503a0b38da782a9fef2eca792d25db629c18ee1ee2d863f17.
  Clean F O0/O2 observed1291/1453records; G2339/2703records. Independent raw,
  object-stack and cleanup reread remains a separately hashed review.
- H lower policy now owns16caller-local entries,16global objects and a separate
  four-endpoint bound. Managed construction grants before publication; cleanup
  withdraws capabilities before address-space teardown. Genuine Lean builds
  pass. Root User capability corpus and25observer rejection tests pass at host.
  No H guest has run, and no I-K implementation is claimed.
- Strict O2 probe rejected two compiler-produced immutable UInt64 lookup tables
  beyond the earlier PMP table. This failure is retained. The H-only auditor
  now checks exact source identities, CFG guards, values, sole use, local object
  symbols, readonly bytes and absence of relocations; broader admission remains
  rejected. Fresh focused probes and full artifact captures are pending.
- Source is uncommitted H work on e61766a. All maintained target sources are held
  while the final focused probe/full O0/O2 package builds run. Next actual guest
  command: `nix develop --no-write-lock-file --command python3
  scripts/check_kernel_capabilities.py --image
  build/kernel/gateH/artifacts/capabilities-development-O0/image.elf
  --output-dir build/kernel/gateH/capabilities-O0-attempt1 --timeout120 --clean`.
  Require both actual profiles and independent review before advancing to IPC.

- Cold G independent summary subsequently passed: SHA256
  7bb914cc1e43125dc06e078cccc3fbe700060c7d208673974d8e369421af17a3;
  32uniquePIDs,30livekill/reap(-9),2naturalM-origin48,empty stderr and
  82independently recomputed object stack graphs. No H result is inherited.
- Held H focused genuine export/O0/O2/object probe passed, report SHA256
  babf11bd883035745b9cd8e242e4d6ef59fb8d6016e0fa36eb6e89f317253cf0;
  O0/O2 trap4528/1248 within actual8192. Kernelhost121/scaffold18/metadata
  passed. Full H packages and eight standalone User audits are running.

## Expanded Gate H focused runtime complete

- Both fresh attempt2 capability packages built and passed strict full artifact
  audits. Eight standalone user images match all112artifact bytes/hash bindings
  and124compiled-source bindings. Comparison SHA256
  4d413ba2e0e55b48135f13896b2c6bece4dffb18942fedb45c2ff4791186010a.
- Actual O0/O2 maintained guest checkers passed31.901705s/18.588865s:
  803/633rawpackets,318/213actualMIRQs,5instances each,76Tester/20Peer
  syscall replies and44distinct successful publication serials. All failed
  table/object/transfer/serial publications preserve accounting. Protected
  descriptor-header stores cause realU page faults15 in two fresh Tamper tasks.
- Tester leaves one owned endpoint with a surviving Peer alias, then exits after
  genuineMAXserial publication and91exhaustion. Ordinary detach reclaims the
  queue plus all task pages; Peer observes80stale denial before exiting.
  The same non-yielding Busy continues throughout. Final physical baseline498.
  Both actualVMs were live until explicit host kill/reap(-9), with emptystderr.
- Earlier attempt1 O0/O2 passes are retained as the earlier corpus; they do not
  establish owner-death cleanup. Expanded observers handle valid timer ordering
  of cross-task logs and enforce exact source/object/reference/serial effects.
  Kernelhost127, targetedLake54jobs and12H evidence negatives passed.
- Focused provenance honestly remains e61766a+dirty. Independent raw/stack
  review is pending; commit coherent H only after that review, then run a cold
  exact-source A-E+F+G+H checkpoint while implementing IPC against this boundary.
  No I-K guest pass, Task003push, PR, actualCI or merge has occurred.

- Independent expanded H review also passed: summary SHA256
  20437edea941cebe88f6f7a216d29732c726f4092c4031798e5f7d4b555d32d3.
  Source124/artifact93/runner8/raw3 bindings perimage,13actualcommandACKs,
  real storeinstructions/faults and independent call-graph stack bounds match.
  AllPIDs absent; ownerF6 exactly22+1pagesO0/20+1O2; Peer stale denial follows.
  Highest focused gateH; highest committed clean cumulative gateG. Commit the
  coherent H source now, then cold H controller `/tmp/lemma-gateH-clean-run.py`.
  IPC may advance from the observed H prefix; its gates still require real runs.

## Committed H and I construction

- Coherent H commit52c9586988159f546df2c485ad16f645f68d3f3b/tree
  0ab4bcf26ab535fe49c2e52ec2aa0ec243af260c. Focused reports retain their
  real parent+dirty provenance; no precommit report is relabelled as clean.
- New managed `lemma-kernel-h-acceptance` worktree at that exact clean commit
  is running cold controller `/tmp/lemma-gateH-clean-run.py`, shell session67719.
  It must build/observe fresh A-E+F+G+H and retain unchanged source/consumer
  inventories. No cached outputs were copied; its running state is not PASS.
- GateI User.IPCABI and User.IPC wrappers compile (12jobs). Lower contract uses
  the already KernelownedASdescriptor tail128metadata+256packet, existing
  UserCopy checked scratch handles, four copied queue slots/Endpoint and8Reply
  objects with type5/right1. Known capability rights2047 and oldCore0profiles
  are preserved. Kernel objects/storage/cancellation and Task/Scheduler blocking
  integration are in progress. No I guest or J/K completion is claimed.

## Cold H regression stopped; precise audit repair

- Exact clean52c cold H controller67719 terminatedFAIL after369.677132s.
  A-E completed10O0images, then normal/bootstrap-m/O2 BootInfo checker rejected
  its artifact before QEMU: `readonly PMP table global/content/use inventory
  differs`. No stopped integration result is a clean H pass.
- Actual postoptimization IR has PMP4 and exact pure CapabilityABI.typeMask4;
  Objects.initStep is absent. Genuine source closure manifests typeMask and
  its unsigned(kind-1)<4 guard/default0/soleload. The old non-H audit route
  admitted only PMP despite the shared syscall dispatcher reaching this helper.
- Compiler worker is repairing only precise table accounting in the isolated
  H checkout, retaining original source/artifacts/failure. User/Firmware tables
  stay rejected. Require fresh actual normal O2 audit/guest and then a cold
  A-E+F+G+H rerun at a minimal committed host repair. Main checkout's independent
  I construction continues without claiming I or clean H acceptance.

## Cold H repair and held IPC checkpoint

- The first cold H run at52c9586 remains FAIL: the shared legacy kernel's
  exact reachable typeMask table was absent from its readonly routing. Minimal
  host-only repair f77a6b1b3609876816000ce86a8a6c1904c3de2a, tree
  d79e57eb0961287321d50eebf0b63f5ff8b64a3e, admits only exact immutable
  helpers backed by genuinely reachable kernel source rows. Unknown tables,
  changed guards/bytes and User/Firmware helpers remain rejected.
- Fresh committed clean A-E+F+G+H at that repair passed836.177351s:
  26images,30checker reports,34guest sessions. Report `/home/sreekumaar/.codex/worktrees/lemma-kernel-h-acceptance/lemma/build/kernel/H-clean-repair/result.json`
  SHA25605f01eb2aa37feefecac2f67b894e9b3489262ea3dbcdadb6ac7dd5bbbd6b17e. Independent full
  raw/artifact/stack/process review passed; no earlier review was inherited.
  The isolated repair is preserved independently while the primary branch's
  dirty IPC work includes its equivalent source-conditional audit.
- I is in construction. Maintained descriptor IPC tail, four-packet queues,
  one-use Reply objects, checked syscall dispatch, blocked contexts and epoch
  wakeup now compile through real Lean/Core0; diagnostic O0/O2 RV64 objects
  pass. Selected IPCEntry trap chain8016B atO0 fits unchanged8192B.
  User Server, two distinct clients and Fault actors compile and are held;
  host observer checks actual binary payloads, sender/request identity, serials,
  rollback, Ready retries and fault/reply order. Host kernel142/scaffold18
  passed; these are not target acceptance. Strict linked I audit is pending.
- Next actual integration: build ipc-development supervisor O0/O2 only after
  the source/CFG audit is complete, then run `scripts/check_kernel_ipc.py` on
  each fresh image. I guest execution not_run; J/K not_run. Continue through
  the fully verified milestone and authorized guarded merge.

- Fresh H independent review PASS:26 images,94 actual object stack graphs,
  30 reports,34 distinct reaped/absent PIDs,104 raw files and19,218 K1 records.
  F/G arithmetic and actual PC preemptions recomputed; H76/20 replies, eight
  snapshots,serials1..44, two SD faults,14 actual sent control packets perVM,
  owner queue/remote-alias cleanup, MAX publication/91 and final498 checked.
  `H-clean-repair/independent-summary.json` SHA256
  56c5e4a7868bef6f2c4708b986b955ecba9ceead4061d6aa66a91773f5be667a.
  J contract is design-only; no dependent J implementation has begun.

- I artifact review found a historical H audit limitation: four kernel backend
  jump tables(112entries/896B) and Firmware.call(5entries/40B) lacked the later
  per-owner/per-slot/local-target provenance checks. The actual H measurements
  above remain historical results. New narrow checks cover all linked read-only
  bytes; final cumulative acceptance must run the tightened current audit.

- Focused I attempts1/2 are retained FAIL. First: A delivered-timeout request
  expired queued behind B, so no Server acceptance and onlyserials1..27.
  Second: longer holds exhausted B Inbox receive0.5s. Attempt3 uses bounded
  actual Reply-capability withdrawal polling for late replies and B1s maximum
  receives; unchanged checker still requires actual acceptance before timeout,
  cancel and caller fault, and actual retirement before late Reply denial.
  Fresh full O0/O2 attempt3 is running; no J target implementation yet.

## Focused Gate I actual execution complete

- Fresh attempt4 O0/O2 linked packages, strict full artifact audits and actual
  IPC guests passed168.810781s with unchanged producer/consumer snapshots.
  Controller SHA256c367ea25e07f1b24488a687901c02b2a3549143015ae5a5a6d0054e4f07ee8e7.
  O0 1417records, report4fc000ad1080a0fa4e2278ae729f6f41a9efe1d020bbcffaf87de9ea3bed70e5;
  O2 1369records, report28d3e8e043d80d6c195c87a9db06d5f30e2da4d641c4a88af749780bc344f4f4.
- Each actual VM:52 A/11 B responses,13 binary payloads/authenticated senders,
  all28publication serials,13 accepted Calls, actual timeout/cancel/caller fault
  after acceptance, late Reply80, actual server SD fault then pending Call96,
  six instances reaped, three Endpoint queue frames released and final498.
  Both live VMs actually killed/reaped(-9), stderrempty and rawcoveragechecked.
- Attempt3 retained FAIL: retiredStep incorrectly expected rights1 from
  Capability.check, whose public result is status/value0; Server accepted the
  target Call then fixture exited95. Only that User fixture result guard fixed.
  Attempts1/2 also remain FAIL; none is relabeled as an attempt4 result.
- Current151 kernel host tests and scaffold metadata/18 tests pass. These do not
  establish compiler correctness or replace actual guests. Independent reviews
  and ten current standaloneUser builds/audits/comparisons are running.
  Hold target/producers/HEAD until terminal; then coherent I commit/cold A-I.

## Focused I independent checks complete

- Platform source/artifact/raw/stack review PASS at focused attempt4 only:
  report build/kernel/gateI/independent-platform-review.json SHA256
  b675570b32cf811db2788ddb3a2bae94eb8817d4f60701723cfe68862bf152e1.
  Actual O0/O2 replays, all caller/payload/transaction identities, one saved-PC
  advance, Runnable-last completion, two SD faults, six reaps and498 frames
  recomputed. Actual O0 trap stack8016/8192; O2 1856.
- Separate source-risk review PASS, report
  build/kernel/gateI/focused-attempt4/source-risk-report.json SHA256
  595dea17731d38e780510b42c0712cc57ca0244455eaaa3d48f9ac2badaef9f2.
  Late Reply80 can be logged before the Caller logs timeout93; both are after
  genuine delivery/retirement. Distinct console log order is not assumed.
- Ten fresh standaloneUser builds/audits PASS197.433s; all140 exact byte
  bindings equal full focused packages and132 producer inputs unchanged.
  build/user/gateI/independent-attempt1/verification.json SHA256
  2456243ae597f6fc7031d4ed8c931e78c5aa0a4051949150afad9d86f1b2adc5.
  These remain truthful precommit52c9586 plus dirty-source observations.
- Coherent I source is ready to commit. Next cold exact clean A-E+F+G+H+I
  checkpoint is separately required; highest complete gate remainsH until
  that actual run completes. J/K runtime and CI/publication remainnot_run.

## Committed I cold checkpoint in progress

- Coherent IPC implementation commit
  ea5037b486f76fc0dc9ccb3b725d9a3fb2a47e76, tree
  8aad67e3fd2979cfffaf7446a84ad67b8a33a4ae. All prior focused reports
  retain their parent+dirty provenance and exact source inventories.
- Fresh managed lemma-kernel-i-acceptance checkout at that exact source runs
  /tmp/lemma-gateI-clean-run-attempt2.py, shell session24130, output
  build/kernel/I-clean-attempt2. No project outputs were copied.
- First controller launch failed closed before any target build: a mistakenly
  untracked root controller log violated clean-source qualification. Original
  FAIL build/kernel/I-clean/result.json is retained, with log moved into
  ignored build/kernel/I-clean-launch-failure. The second run is distinct.
- Highest complete integration remainsH until actual cold A-I completes.
  J target/producers are held. Root prepared only host command framing, mixed
  UART transport and a readable terminal; five framing tests passed, with no
  J guest or service pass inferred. Worker read-only J interfaces are agreed.
- Normal service design boots directly: first Server argument is actual
  nextEpoch1; CLI1/Peer2/CPU3 are public boot-policy arguments. Framed commands
  provide fresh runtime inputs; there is no acceptance-only launch packet.

## Cold I strict audit counterexample

- Exact ea5037b cold A-I attempt2 stopped FAIL694.544497s during A-E
  frames-development/bootstrap-M/O2, before any F-I guest. Report SHA256
  c7de712285e51d63fe3afe345a261f296e11bc47e5ab81cdaa6619ddca3a53e8.
  Nested A-E report SHA256
  b542e7ea64753269807d68e609b03f32411317237f137ffff7ad535390bc3c14.
- Strict backend audit found one unaccounted exact source table:
  Lemma.Kernel.Development.FramesEntry.operation, five u64 arguments,
 22entries/176bytes, LLVM cases0..6 and8..21(default hole7). Independent
  actual-object review confirms unsigned<=21 guard, scaled8B entries, one
  indirect branch, local targets in its492-byte owner and zero addends.
- Failed artifact Session pidnull/argvempty/rawempty: it did not launch QEMU.
  Earlier passing O0 and first O2 observations remain partial results only.
  Isolated clean source and original failure are preserved without mutation.
- Compiler worker is authorized for only precise host auditor/negative-fixture
  repair, plus actual current-configuration table preflight. Targets remainheld
  and J/K notrun. Commit this narrow repair then a distinct clean rerun; never
  bypass unknown bytes or relabel the failed output.

## Narrow cold-I host repair preflight

- Final auditor pins only the existing frames-development operation declaration,
  five u64 arguments, exact effects,22 entries and LLVM cases0..6/8..21. Hole7
  targets the genuine default whose status17/value0 PHIs reach the aggregate
  return. Source/configuration/signature/effects/domain/guard/target/whole-byte
  checks remain fail-closed; no target/compiler/language/backend setting changed.
- All13 current configurations,22 genuine closures and44 fresh O0/O2 objects
  passed218.185742s with132 source inputs unchanged. Verification report
  build/compiler-gateI/cold-table-repair-verification.json SHA256
  a5a078374516a1dc972839741eab85b1fe695427f5d58fe1e400fe853a4e9d68.
- Original failed Frames artifact read-only recheck passed with its bytes
  unchanged. The original cold attempt remains FAIL, not a repaired guest pass.
  Seven focused fixtures,165 total kernel host tests(includes twelve held
  untracked J transport tests), scaffold metadata and18 tests passed.
- New clean package/guest acceptance remains required after the repair commit.
  Held J host preparation is excluded from that minimal commit; J target held.
- Independent final repair review PASS;21 mutations of actual original evidence
  rejected,44 survey object/optimized-IR bindings independently hashchecked.
  build/kernel/gateI/repair-review/result.json SHA256
  c8a1011893fb86dd9138a1c74e230a3e80c42f29043794b3e09d614b17ddb489.
  This is audit repair evidence, not a new clean guest acceptance result.

## Exact committed I repair checkpoint running

- Minimal four-file host/ledger repair commit22183c167ca62102a4a8db10a95ee77b27137f10,
  tree685a03cbf162aed80854ea19e0edf39e9bae6f3a. Fresh managed checkout
  /home/sreekumaar/.codex/worktrees/lemma-kernel-i-repair-acceptance/lemma
  is clean at that revision, with no copied project outputs.
- External controller/tmp/lemma-gateI-clean-run-repair-attempt1.py shell17618
  runs fresh A-E/F/G/H/I into build/kernel/I-clean-repair-attempt1. Log is
  under ignored build/kernel/I-clean-controller-logs/repair-attempt1.log.
  Independent full reviewer prepared; current-source ten standaloneUsers
  built/audited separately, with140 package-byte comparisons pending actual
  fresh full I packages. No former failed output is inherited or relabeled.
- Primary root prepares host-only Buffer command/reference consumers. These
  files are excluded from the repair checkpoint. J target remains held until
  terminal actual coldI PASS and independent review. K remains not_run.

## Clean A-I accepted checkpoint (2026-10-10 00:57 UTC)

- Exact clean committed repair22183c167ca62102a4a8db10a95ee77b27137f10,
  tree685a03cbf162aed80854ea19e0edf39e9bae6f3a, cold controller PASS1499.380590s.
  Fresh28images/32checkerreports/36actual guest sessions. Report SHA256
  bca9adc9d1aed14895a77cccbe4caa8803397981b96a96a128fc6840251e805d.
- Full independent review PASS:108object stack graphs,110rawfiles,22080K1
  packets, all36PIDs absent,132producer/37consumer snapshots unchanged.
  Review SHA256c3af9111c2edc845e5b68350657bcc39e2fed9cb95be373f17d56f82d1178364.
  Maximum task trap stack8016/8192 remains a strict bound, with176bytes margin.
- Ten separately built clean current IPC Users passed audits and all140 exact
  package-byte comparisons. Verification SHA256
  cad20271acfac919ff2e550bee27c70fc7100e75ac45af1623d3ed25fb457171.
  No copied artifacts or independent User guests claimed.
- Highest complete gate isI. Earlier cold FAILs remain preserved unchanged.
  J target implementation is now released; K and publication remainnot_run.
  Final-source legacy, A-K acceptance and actual CI are required before merge.


## Gate J focused candidate (2026-10-10 02:03 UTC)

- Held J source includes separately linked Server/CLI/Peer/CPUBound and a
  development-only fault client. Genuine four-application O0/O2 exports/ELFs and
  strict kernel stack probes passed; no cached I result certifies J.
- Independent normal O2 review reproduced six genuine Lean export/object sets,
  all four User images/payloads and the whole boot ELF. Source145/artifact93
  bindings matched; dispatch stack1856/8192, Server page budget23/32. Review
  SHA2565321038fc6694942b59204a05dda8a2f5d032da141ed76b27812aa17c73c8edc.
- Actual development O2 PASS306 commands, one contained fault,43 global denials,
  one lease expiry,1104 CPU arithmetic preemptions, one pending-call restart and
  complete teardown to497. Independent raw review is running.
- First normal O2 command returned0, but independent validation found177 reply
  tuple/list serialization differences. Narrow list snapshot repair plus real
  JSON-roundtrip host fixture passed. Original report and rejection preserved;
  its old runner hashes are stale, so it is not clean acceptance.
- Fresh normal O2 retry completed306 commands but correctly FAILED complete raw
  cleanup at truncated K1 frame offset662216 after host kill. Diagnose and repair
  host-only bounded cleanup; never discard the suffix or relabel this FAIL.
- Normal O0 initial build failed before target export because Nix source copying
  observed a transient concurrent Lake .olean.tmp. Serialized retry built. Dev
  O0 and Dev O2 built. Keep all prior attempts. Current full kernel host suite
  actually passed217 tests; scaffold18 and metadata passed.
- Highest complete gate remains I. J requires complete four-profile live checks,
  clean committed-source lane and actual source-algorithm mutation evidence. K
  target attacks, final-source legacy/full acceptance, CI, publication and merge
  remain pending. All target/auditor sources held until J focused repair settles.


## Four-profile J focused result and actual O0 denial race (02:23 UTC)

- Fresh repaired-cleanup observer returned0 for normalO0, normalO2 and DevO2,
  each306 ordinary commands with complete raw replay and explicit live kill/reap.
  DevO0 returned1: third caller missed actual full-storage denial. Combined
  focused-four-profile-attempt1.json SHA256
  e7c8a5f172c76bceec22908b64a0d57330b34a2c7c164d61898ac31a2dbd8132
  remains FAIL. These precommit consumer-bound reports are not final acceptance.
- The DevO0 guest did execute an actual protected-text SD15 and reclaim the
  fault task. But Peer woke after its deadline and released its temporary page
  before Fault's first create, so that create correctly succeeded and no actual
  204 was witnessed. Preserve the complete1728-event failure capture.
- Repair only the development client's bounded probe: until it receives actual
  204, successful creation is recorded, destroyed through ordinary IPC, recorded
  against actual page release, and retried. After actual denial, a later real
  success may verify bytes and execute the fault. No guessed longer hold or
  kernel Buffer-method knowledge; normal Peer remains unchanged.
- Cleanup helper held9daf36a6320679069db980678432e9dd753de0da7ef9cc37a521921b56cf4187,
  root full223 host tests and18 scaffold passed. The remaining fail-closed base
  cleanup exception-retention gap is being repaired after these guests ended.
  New complete target builds/observers and clean committed qualification are
  required after both repairs. K target remains held.


## Repaired J O0 observations (2026-10-10 02:35 UTC)

- Repaired development O0 actual306 ordinary commands passed with34 global
  denials, one contained fault, one lease expiry,1048 arithmetic preemptions,
  one pending-call restart and final497 frames. Normal O0 passed306 with562
  arithmetic preemptions. Both have full strict raw replay and live kill/reap.
  Independent absolute-path validation passed actual exit0; summary
  build/kernel/gateJ/independent-repaired-focused-validation-attempt1.json.
- An initial root revalidation supplied a relative image path and got a
  busy_unit.path string difference; diagnostic retained. The actual maintained
  controller uses absolute paths. No checker change or original rebinding.
- Independent source review found a concrete host-observer false rejection:
  an application fresh-time lease scan can release a page after acceptance321.
  Existing324 classification incorrectly assumes all releases under acceptance
  are Destroy. Narrow observer settlement/reference repair is underway, with
  source-derived ordered regression; target Server policy remains unchanged.
- These are focused precommit results, not a clean J pass. Highest remainsI.
  Fresh held-consumer O0/O2 normal/development, clean J acceptance and actual
  isolated service algorithm mutation remain mandatory before K is released.


## Practical terminal failures and host repair (2026-10-10 02:58 UTC)

- Held strict lease/Destroy settlement and byte-failure background settling
  passed229 pinned kernel host tests,18 scaffold and metadata. Target unchanged.
  Summary lease-settlement-complete-host-summary.json SHA256
  9f612ca00b917d085d23286afb0ffd4914fde48f0d0128e4c117b1c0226f2b98.
- Actual normal readable terminal attempt1 sent help before service readiness
  and received no client frame. Operator interrupt was retained asFAIL; QEMU
  killed/reaped. Its122k-frame already-consumed prefix was redundantly decoded
  during live5s cleanup and that stage failed. No earlierPASS was rewritten.
- Narrow CLI publication wait added. Attempt2 observed actual0x300 at wire18
  before any input, then blocking input() stopped output draining. Raw bytes
  are19*88+65536 exactly: an entire unread64KiB pipe. QEMU naturally exited50,
  with763 full K1 plus64-byte Server323 prefix and no sent input. No complete
  D4/DC/DD/DF diagnostic provides a PC/cause/status. Exact UART transmit11 and
  eventual fatal50 route is a pinned source inference, not a measured trap.
  Read-only diagnosis f05468419aede539984cd2b13d98fa73eac053bb182cc615a1052e4d0d043732.
- Host-only fixes underway: one parser owner pumps guest output while waiting
  for bounded UTF8 operator lines; cleanup reuses its actual contiguous parsed
  prefix while retaining full postkill raw decode/equality/hashes/replay. Remove
  the decoder's quadratic whole-tail slicing without changing its grammar.
- No target policy change justified by these failures. All original artifacts
  remainFAIL. Highest complete gateI; J clean/source-mutation and K remainopen.

## Held host transport repair (2026-10-10 03:08 UTC)

- The linear UART decoder and validated contiguous parsed-prefix cleanup cursor
  passed236 pinned kernel host tests,18 scaffold tests, metadata and diff checks.
  Evidence: build/kernel/gateJ/host/transport-prefix-host-summary.json, SHA256
  d97bcd4b2de1b4de53763600e2d87638b6f17a71a4ef7cccc0998dd7904a6143.
- Independent read-only review found no concrete parser or acceptance regression.
  The cursor only saves live freeze work; complete postkill raw decoding, exact
  observed-prefix equality, frozen stdout/stderr hashes and strict replay remain
  mandatory. Native-child fixtures cover a4096-frame parsed prefix, partial K1
  and LMO1 tails, malformed cursor fields and changed already-parsed bytes.
- The first CLI output pump passed its host tests, but root review identified
  possible input starvation from an unconditional stdout-ready continue. Fair
  bounded input delivery is being repaired before another actual terminal run.
  No new target execution or clean J acceptance is claimed here.

## Practical terminal passed; clean J next (2026-10-10 03:13 UTC)

- Fair one-frame input pumping passed4 pinned CLI host fixtures and independent
  read-only review. Final full kernel host suite passed237 tests; scaffold18,
  metadata and diff checks passed. All source and transport files are held.
- Actual normal O2 terminal attempt3 passed12 ordinary commands. It observed
  publication before first input, read back binary00ffcebbe28891, displayed
  UTF8 lambda/summation, destroyed handle621 and received stale status201.
  QEMU766112 remained live, then was explicitly killed/reaped with return-9;
  PID absent. All6063460 retained UART bytes decode at the frozen boundary.
  Result SHA25632e60d30a5e6997d99c9729046e5c0db6f3ca00c8137ca975f706ce6e35a9375.
- Independent raw/input/response/source/runner/artifact validation passed;
  build/kernel/gateJ/independent-readable-terminal-attempt3.json SHA256
  d0edd338cccfe318ca52e3116a5dc12d4288e1c5f88544932171ba05f28dfeaa.
  This is practical interaction evidence, not a cumulative acceptance claim.
- Commit the J candidate, run the maintained four-profile J lane in a fresh
  exact clean worktree, and observe canonical append-copy source mutation at
  O0/O2 using those exact clean controls. Highest complete gate remainsI;
  Gate K target changes are held until both J exit obligations actually pass.
