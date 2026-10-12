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
