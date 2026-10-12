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
