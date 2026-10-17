<!--
# Ordered page-word UserCopy implementation v1

This implementation changes the bounded copying algorithm inside the existing
Kernel UserCopy APIs. It adds no language profile, permission, mapping cache,
DMA operation, allocation helper or foreign target runtime. Maximum length4096,
zero-length behavior, ABI statuses and scratch/user admission order remain the
original contract. A nonempty range spans at most two pages. Both user leaves
are fully checked before any destination byte changes; every call freshly
validates the descriptor, complete ordered VA duplicate scan, actual PTE,
owner/generation/purpose, directory/pin checks and requested permission through
the unchanged Frames/AddressSpace routines.

Aligned transfers copy the first physical span, then the second physical span,
in the original increasing logical byte order. Each64-byte block performs eight
consecutive read64/write64 pairs in ordinary Lean Actions. A tail performs the
remaining zero to seven words. Source and destination64-byte pool/alignment
guards expose a local proof to LLVM; the same checked Access primitives remain
in the genuine lowered code, and every other input follows the complete generic
block. Unaligned and partial-word transfers retain the original byte path.
The read-page alias API remains limited to the same nonpreemptible Action, with
fresh scratch and range checks and ordinary fallback outside that page.

Read failure retains its priority over that word's write. A write failure keeps
all preceding writes and performs no later read/write. Primitive status failures
still return kernelFatal with no successful count; unrecoverable hardware/global
faults do not claim successful cleanup or return. Copying may overwrite aliases,
including scratch/descriptor storage, only in the same original ordered sequence.
No scheduling or metadata mutation may intervene while a physical alias is held.
The optimization never removes ownership, quota, handle, generation, PTE or pin
validation, and does not replace the physical access boundary with raw host work.

The test-only `tests/kernel/UserCopyPageBefore.lean` is a genuine ordinary Lean
snapshot of the preceding implementation. It never enters a production import
or target root. `UserCopyPageWords.lean` executes the actual old/new Actions in
independent finite byte RAM, requiring exact results, RAM and ordered primitive
requests, including10,108 injected fault prefixes descriptor/scratch aliases and both legacy/expanded pools.
`UserCopyPageLower.lean` genuinely elaborates both roots, checks Actions/CFG/LLVM
and exports the real module for LLVM20 O2 RV64IM object inspection. Historical
UserCopyScans also checks ordered metadata/duplicate/fault/permission behavior.
These are tests/audits, not a proof of compiler correctness or guest cycle timing.

The canonical3,840-byte packet has unchanged1,105 primitive operations in the
expanded two-mapping fixture; callbacks fall496→76. Actual emitted static code
has49 instructions for the eight-word guarded callback, including fallback,
versus70 in the prior one-word callback. Full-frame UserCopy still performs one
complete mapping-list validation per syscall. Real guest performance, fresh
whole-image audits and native/browser workflow results require separate receipts.
Old compiled images and checkpoints keep their original source/runtime identity.

## Exact artifact observer successor

The first fresh whole Closure initializer compiled in67.086s but its ordinary
audit failed at144.569s because the Surface borrow observer required the old
now-unreachable `fromWordStep` callback. That FAIL and complete unchanged361
input archive remain retained. This is a demonstrated observer gap; the target
implementation and its finite fault-prefix comparison did not change.

The dedicated `usercopy_page_words.py` observer admits the new three-argument
page-span call only with exact pre/post bodies, signatures/effects and seven
private caller closures. It checks eight ordered read64/write64 pairs, original
read values,64-block/7-word-tail bounds and the optimized sixteen ordered
volatile64-bit accesses. The ordinary IR audit invokes it for both phases.
The existing seven-argument callback path retains its original checks/pins, and
the new Surface path retains all eleven scratch/page/fallback gates. Actual
genuine new and historical exports pass;43 actual mutations reject. This
artifact qualification does not claim compiler correctness or new guest speed.

-->
