# Task006 frame allocation work reduction

The maintained Lean allocator now uses `lemma-frame-index/1`, documented in
`docs/contracts/004-owned-memory-v1.md`. It retains the complete 8192-frame
pool and every checked zeroing write. A lower-bound free cursor preserves the
lowest-slot and lowest-contiguous-run choices, including fragmented holes.
Exact counters replace record scans for ordinary owners1..64; larger valid
owner IDs retain the original complete scan. Single, pair, quad and release
transactions maintain and roll back the private index alongside ownership.

The compiled source is
`Lemma/Kernel/Memory/Frames.lean`, SHA256
`45b1522901b4fa3ba35aa7230a98b785ce8115a244126e0a652faa63bf941758`.
No language profile, user ABI, durable format, handle encoding or guest pool
capacity changed. These are algorithm and fixture results, not a compiler
correctness proof or a completed canonical notebook acceptance result.

## Observed work

Both rows execute genuine allocator Actions against independent sparse RAM;
the baseline is the actual source from `d219650b1cef7f3c3eff080f2ab78c2bcf21c504`,
compiled as the host-only `FramesBefore` fixture module. The workload is520
successful owner2 allocations in the actual8192-frame configuration. The
counts are ownership-record reads and bounded callback invocations, not CPU
cycles or all memory operations.

| Work | Before | Indexed allocator |
| --- | ---: | ---: |
| Ownership-record reads | 135980 | 1040 |
| Bounded callbacks | 401700 | 33800 |

An additional baseline `ownedCount 2` observed8192 record reads/callbacks.
The new indexed count uses no record reads or scan callbacks. The new fixture
also observes266240 checked page-word writes. The old source already clears512
words/page. Eight consecutive checked writes now share each zeroing callback;
all512 writes/page remain in the original increasing-address/first-error order.

Receipts are `build/task006-frame-index-comparison-a1/observed.log` and
`build/task006-frames-tests-control-retention-a2.log`. The latter passes lowest
single/pair/quad choices, fragmented holes, pins, generation retirement,
multiowner counts, quota-before-OOM, arbitrary larger owners, failed publication
and release cleanup, exact zeroing-error prefixes and malformed-index rejection.
Literal record-array checks independently reconstruct all64 owner counts and
the cursor property. Initialization/allocation/release preserve literal cookies
throughout existing peripheral/descriptor controls at0x80400a00..0x80400fff.

## Real RV64 qualification and retained failures

`build/kernel/task006-frame-index-frames-control-fixed-a1` was freshly elaborated,
checked-lowered and compiled O2 through pinned Lean4.34.1 revision
`5045d0056413266e57c625dcd7c365b10e377c52` and LLVM20.1.8. Its strict freestanding
audit passed. Image SHA256 is
`169b23e34aa716d638bc09bb4130e11ed82524d139b2bee7a5beda8ad7a6841d`.
The actual512-frame RV64 development transport campaign passed ownership,
zero-reuse, quota, global exhaustion and recovery in18.745363 host seconds;
receipt: `build/kernel/task006-frame-index-frames-control-fixed-run-a1/result.json`.
It does not substitute for actual8192-frame canonical notebook acceptance.

The first canonical attempt used notebook image
`a83c2e25bc2dbaa9619b5c3daa0297d718d236d03830c616283f2f950b42b5b6`
and backing-runtime-a1. It **failed** at9394398 target cycles after33.648598
runtime host seconds, with actual fatal50 finisher0x323333 before user mode.
An initial counter placement at0x80400a00 overlapped the existing VirtIOBlock
control state; subsequent construction observed corrupted private accounting.
The correction places all64 cells immediately after the full ownership array
at0x80441000..0x804411ff. The failed state is retained unchanged at
`build/silicon/task006-frame-index-canonical-a1/failed-boundary-checkpoint`,
with original result `cold/result.json` in that campaign directory. No medium
operation or Ready occurred. That owner was destroyed and reaped.

The initial rejected numeric condition, source-inventory races, expanded-font
audit failure and new course table audit failure retain their original logs
and output directories. A3's exact failed auditor files/hashes and failure
receipt are saved at
`build/task006-frame-index-notebook-control-fixed-a3-original-audit` before
the separately tested course observer repair. No failed artifact is a passing
notebook build. The next changed-source canonical campaign retains the already
declared2B-cycle/7200-second cold bound; cold Ready, pen/edit/navigation/Save,
independent cold recovery and unsuccessful Save remain separately required.

Focused reproduction uses unused paths:

```sh
nix develop --no-write-lock-file --command lake env lean tests/kernel/FramesScans.lean
nix develop --no-write-lock-file --command python3 scripts/build_kernel.py \
  --configuration frames-development --stage bootstrap-m --opt-level O2 \
  --output-dir build/kernel/frame-index-new --timeout 300
nix develop --no-write-lock-file --command python3 scripts/audit_kernel.py build/kernel/frame-index-new
nix develop --no-write-lock-file --command python3 scripts/check_kernel_frames.py \
  --image build/kernel/frame-index-new/image.elf \
  --output-dir build/kernel/frame-index-run-new --timeout 120
```

## Local allocation authority and packed toolbar

The next maintained increment reuses a freshly validated descriptor only within
one nonpreemptible allocation Action, and reads task-table pins from the grant
which that same Action just resolved. `mapUserAt` retains all live duplicate-row
reads, ownership, generation, purpose, permission, actual PTE, pinning and
publication/rollback checks. It does not cache authority between syscalls.

The literal finite-RAM fixture executes the previous algorithm and current
production Actions, comparing complete authoritative memory after success and
rejection. Receipt: `build/task006-allocation-reuse-after-change-a1.log`.

| Operation | Previous read64 calls | Current read64 calls | Previous/current ownership reads |
| --- | ---: | ---: | ---: |
| Legacy allocation |106|83|32 /26|
| Expanded allocation |230|151|102 /64|
| Task table |9|6|6 /4|

These are host Action counts. The fixture also checks malformed descriptor and
registry bindings, duplicate rows, incorrect live grants, pins/generations,
read/write/invalidation failures, exact rejection precedence and provisional
allocation rollback. Existing two-page bulk-copy/deadline/context boundary tests
pass at `build/task006-local-authority-boundaries-a1.log`.

The guest background packs full toolbar words while preserving scalar row
crossings, small geometry, odd-width padding and partial tails. The independent
toolbar test compares1,725,440 literal pixels across twelve widths, then checks
every1,815,000 Gray4 byte at1650×2200 against the scalar construction. Receipt:
`build/task006-toolbar-words-a2.log`.

| Complete canonical background | Checked word writes | Checked byte writes |
| --- | ---: | ---: |
| Prior construction |211862|120104|
| Packed toolbar |224950|15400|

All display pixels, the444 framebuffer frames and every full upload remain.
The complete image still has3,630,000 pixels and3588 tiles:3468 full tiles and
120 edge tiles. These exact work counts explain the changed algorithm; they
do not independently establish a worst-case processor-cycle bound.

`tests/kernel/LocalAuthorityCompile.lean` passes genuine elaboration, profile
checking and maintained LLVM lowering for allocation/task and surface Actions
in `build/task006-local-authority-compile-a2`. The complete fresh supervisor O2
notebook build and strict audit pass separately at
`build/kernel/task006-canonical-hotpath-notebook-a3`. Its image SHA256 is
`b79b020dd52428bb2a115b5a81cb07df9ab64079cab66a0a9655ce3e38b40af7`;
build/audit logs are `build/task006-canonical-hotpath-notebook-build-a3.log`
and `build/task006-canonical-hotpath-notebook-audit-a3.log`. This image also
contains the separately owned mathematical-course/review increment, so a cold
boot comparison must account for its additional code/loading work.

The first hotpath build invocation selected the wrong bootstrap stage and
failed before compilation. The corrected a2 build compiled, but its original
strict audit rejected the new `Mathematics.validateEventStep` five-entry LLVM
table. Its exact failed observer, manifest and failure/log remain at
`build/task006-canonical-hotpath-notebook-a2-original-audit`. After independent
metadata/domain/bound/load mutation tests qualified that narrow observer, a
fresh source-valid a3 build emitted exactly the same target ELF bytes and
passed the complete audit. The earlier a2 result stays failed.

## Actual canonical campaigns remain separate

`task006-frame-index-canonical-a2` continues its original immutable guest
`186e8370b36152344b1a19339d5430e68358102640879fa2736fe55fe7f471e0`.
At the observational100M-cycle checkpoint, actual privileged-cycle counters
were519357 U,97495547 S and1985088 M. At213M they were598136 U,
209112068 S and3289788 M; the notebook owned405 frames, versus158 at100M.
Only three backing reads had occurred, with no display refresh. These real
counters locate substantial work in supervisor allocation/validation; fixed
PC samples alone are not cycle attribution. Later samples advance through the
actual user background and `Surface.gatherWord` upload path. `gatherWord`
already uses aligned word reads and is not a newly delivered optimization.

The changed hotpath guest starts once from actual reset in
`build/silicon/task006-hotpath-canonical-a1/session`, after strict audit and
public preparation validate consumed identities. Its exact native binary is
`build/silicon/task006-backing-runtime-a3/obj/lemma-rtl`, SHA256
`44442fc19ba05bc6ff315116fcad84421e1d851464cb080267da3409982c10b9`.
Runtime identity is
`255030a218bf67acc26a5807e1b3eb8ab97ff2d768501df0d037775e50abf90e`.
Each campaign has its own privately copied initialized medium, source-bound
symbols, PC samples, plan, result and owner. Source medium SHA256 is
`c79dca00a597781d134ffdc3573eb1edc01915244b9c78efb7cac1eb6c188f46`.

Both retain the original2B-cycle/7200-second diagnostic ceilings. There is no
independently proved pipeline workload bound; a timeout remains a failure.
The new observer records guest Ready separately and continues to a real
completed full refresh and acknowledged initial commit. Complete independent
expected pixels and raw pen/edit/navigation/Save/cold recovery are still
required. The existing notebook observer now decodes actual native P5 output
alongside QEMU P6; tests reject malformed lengths/geometry. The independent
empty-notebook observer covers the entire background and complete footer,
including saved/pending distinction. No expected pixel enters the machine.

## Same-Action managed dispatch validation

`Capability.managed` now calls the private read-only `headerAt` with the exact
descriptor base it validated earlier in the same S Action. The second tag read
and all eight capability-header fields, live registered-descriptor identity
and active-state check remain. Historical zero headers keep their eight-word
test. Source SHA256 is
`8b0019f5413ce9b13725683701191dd8095e4042ef407d8175fee31bfcaacf29`.

The independent previous/current Action fixture compares status, result and
complete authoritative RAM, including malformed descriptor/header/registry
fields and first-read errors. Receipt:
`build/task006-allocation-capability-reuse-a5.log`. The latter also checks a
genuinely zero legacy header before object-table initialization and first read
failures on every capability-header word.

| Managed validation | Previous read64 | Current read64 | Ownership reads |
| --- | ---: | ---: | ---: |
| Legacy |72|49|18 /12|
| Expanded |184|105|82 /44|

The genuine elaboration/profile/LLVM probe passes at
`build/task006-capability-compile-a3`; its exact fresh-base/status/pair/read-only
compiled guard passes separately in
`build/task006-capability-compile-a3/borrow-audit.json`. The narrow audit
checks both admitted callers and all eight live header-read addresses; negative
fixtures reject different descriptors, substituted bases, reversed/ignored
status gates, writes, scheduling and bypasses. The98 focused kernel audit
tests pass at `build/task006-capability-borrow-kernel-host-a1.log`. These are
structural/compiler and Action results. The combined fresh supervisor O2 image
with the separately maintained owned-arena mathematics increment passes its
complete strict audit at `build/kernel/task006-owned-arena-notebook-a1`;
image SHA256 is
`ef898c1872d91e4feea3ff72aeb04cad6c70fb86670974a0e7db36af930e6bb2`.
That original canonical audit did not invoke the historical IPC graph and
therefore did not run the new header-helper guard. Its original narrower PASS
and exact observer are retained at
`build/task006-owned-arena-notebook-a1-original-audit`. The canonical kernel
hook is now explicit for every unit reaching managed dispatch. Applying that
guard to a1's unchanged genuine unit passes separately at
`build/task006-capability-canonical-gate-a1.json`; it is not a new full or
current-source audit. A fresh source-bound image and real workflow
qualification remain separate.

The retained observational checkpoint
`task006-frame-index-canonical-a2/profile-boundary-a3` is at997000000 cycles:
560106454 retired instructions, U91987167/S892584189/M12428636 cycles,
three medium reads and zero controller completions. Its4438384 framebuffer
writes include the original3630000-pixel clear, leaving808384 actual uploaded
pixels. This identifies upload/validation work after background construction.
It is neither Ready nor completed full display. The declared ceilings remain
unchanged, and no failed campaign is reclassified.

The next connected kernel increment removes repeated checks within a single
surface transfer and trap capture. Its maintained finite-RAM fixtures compare
the previous bodies with the new production paths, including complete memory,
result/error priority, cross-page/unaligned/range fallback, corrupt descriptor,
registry/PTE/generation/permission, scratch/descriptor alias, owned-stack and
task-row faults, and partial write prefixes. On the actual444-leaf notebook
address-space shape, metadata32+pixels512 reads drop1260→668 and ownership reads
136→71; checked word writes remain68. A one-leaf shape drops356→216 and130→68.
Trap capture drops427→239 reads and188→96 ownership reads, retaining39 checked
word writes. Logs are `build/task006-upload-readpage-reuse-a2.log` and
`build/task006-trap-capture-reuse-a1.log`. These are Action work counts, not RTL
cycle or host-time claims.

`tests/kernel/LocalAuthorityCompile.lean` genuinely elaborates and checked-lowers
the maintained surface service and capture through LLVM, alongside earlier
allocation/capability/background roots. The successful new probe is
`build/task006-transfer-compile-a3`; the first attempt retained a diagnostic
missing `core0_io_fence` declaration and did not produce a valid transfer module.
The probe now declares the normal existing device-order primitive, without
adding a target helper or changing its semantics. The closed kernel audit
checks exact descriptor/alias/stack arguments, success gates, read-only paths,
live row checks and disjoint word stores. Eleven mutations of the real emitted
LLVM fail at `build/task006-transfer-compile-a3/local-borrow-mutations.json`.
The prior UserCopyScans and BulkCopyAndDeadline Action suites pass at
`build/task006-transfer-usercopy-legacy-a1.log` and
`build/task006-transfer-bulk-legacy-a1.log`;328 existing kernel host checks pass
at `build/task006-transfer-kernel-host-a1.log`, with four additional narrow host
checks recorded separately. A fresh full guest audit and canonical cold workflow
are still required for this increment.

The slower joint packed-background campaign retains a393000000-cycle
observational checkpoint at `task006-hotpath-canonical-a1/profile-boundary-a1`:
218297431 retired instructions, U35498165/S351699125/M5802702 cycles,
three medium requests,6327 traps/956 timer traps and zero completed panel
refreshes. Its3630000 framebuffer writes are exactly the initial controller
clear; no actual upload had occurred at that boundary. This motivates trap
validation reuse independently of the subsequent upload work. Both ongoing
cold campaigns retain their original2B-cycle/7200-second diagnostic ceilings;
no independent pipeline worst-case boot bound has yet been established.

The allocator-only canonical cold campaign `task006-frame-index-canonical-a2`
has now terminated with its original **FAIL**: the predeclared 7200-second host
ceiling was exceeded at 1,681,000,000 target cycles (7204.94 seconds). It never
reported notebook Ready or completed a panel refresh. Its source-bound guest
remains `186e8370b36152344b1a19339d5430e68358102640879fa2736fe55fe7f471e0`;
native runtime identity remains
`0f994c57ca1b1760100898faa13d4819f93c46d75ca67db6aac6b50977b4cb0c`.
The original result has SHA256
`1a4e3ba30489644c835e410dd445dc9edbf936f1f847baaa8a604a8b5bfcec22`
and is retained without rewriting. The observational
`failed-boundary-checkpoint` retains 953,324,175 retired instructions,
U108,643,610 / S1,553,300,194 / M19,056,188 cycles, 24,262 traps and 3,584 timer
traps. The 5,703,536 framebuffer writes comprise the initial 3,630,000-pixel
controller clear and 2,073,536 uploaded pixels; no complete display or pixel
correctness is inferred. Three medium operations occurred, with no write or
barrier acknowledgment. The last recorded native resident-memory high-water mark was 148,052 KiB;
the runtime reported 14 threads. The runtime source used to decode these offline counters was
recovered from `aa494919` only after matching its exact consumed SHA256
`4aa2084633e824f06ca11101cb59f377bb180cb85291e9a4ca8c322409fd1bdd`.
The paused task-owned session was destroyed through the ordinary public
lifecycle, and its owner/runtime processes were reaped. The checkpoint, source,
`failed-boundary-statistics.json` and `terminal-cleanup.json` remain in the
campaign directory. This failure does not qualify cold Ready or scenario A.

Before the next changed-source campaign, the fixed workload accounting at
`build/task006-canonical-work-bound-a1.json` records the unchanged canonical
3,630,000 pixels, 1,815,000 Gray4 bytes and 444 framebuffer frames. Full upload
requires 3,588 tiles: 3,468 full 32x32 tiles, 68 right 18x32 tiles, 51 bottom
32x24 tiles and one 18x24 corner. That gives 114,816 metadata bytes and at most
243,984 checked copy-word stores and 229,632 PIO words. A port-ready full quality
snapshot takes 7,260,000 clocks; its synthetic sequencer takes 39,930,007 clocks.
The actual controller quality deadline is 250,000 MTIME ticks (2,500,000 machine
cycles). Startup retains 131,072 metadata clear-word stores, 32,768 frame-record
initialization stores and 512 zero-before-publication stores per allocated
frame. Normal boot owners 1 through 4 use the maintained owner index; the
8,192-record owner fallback is absent from that successful allocation path,
and full-pool teardown scans remain. These are independent fixed operation and
controller bounds, **not a whole-guest worst-case cycle bound**. The CPU,
interrupt, IPC and backing waits still lack that independent bound. The
retained 2B-cycle/7200-second campaign ceilings remain diagnostic resource
ceilings; any terminal timeout remains a failure.
