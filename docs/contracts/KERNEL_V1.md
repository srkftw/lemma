# Kernel foundation contracts v1

This additive contract preserves all historical Core0 profiles. New checked
profiles are `core0-firmware-v0.1`, `core0-kernel-v0.1` and `core0-user-v0.1`.
Their exact scalar/effect/operation catalogs are maintained in Core0.Execution
and the production unit manifests. Genuine elaborated declarations remain the
source; arbitrary externs, indirect callbacks and unknown helpers are rejected.

Kernel/firmware physical accesses use width1/8, subtraction-safe bounds and
alignment checks before a volatile load/store. Firmware may access its private
storage; kernel policy may access metadata, boot stack and the frame pool, and
read the declared image/package/DTB intervals. User units receive virtual
accesses only. Compiler bounds are an authority boundary, not a proof of
architectural user isolation. Firmware/syscall transport returns actual ABI
status/value in a0/a1. It does not manufacture success for a failed ECALL.

`Action.loop` is restricted to kernel/user profiles and a statically resolved,
monomorphic zero-argument Action step. It repeats while step status=0, retaining
no recursive target stack growth. A nonzero status returns the original failure
and value. The loop may diverge; emitted functions promise neither `willreturn`
nor `mustprogress`. Each bounded operation retains its own fail-closed budget.

The authoritative LemmaVM Layout reserves firmware, M storage, S image,
metadata, stack, package, pool and DTB separately. The available pool is512
4KiB frames at0x82000000..0x82200000. The guest DTB parser validates the exact
advertised128MiB RAM and rejects reserved-memory nodes before allocation.
Pinned QEMU/libfdt property padding is not necessarily zero; at most3 property
alignment bytes are bounded/skipped. Node-name padding remains canonical zero.

Frames.allocate(owner,purpose) zeroes the complete page before publishing a
generation-tagged handle `generation*512+index`. Owner1 is kernel; other valid
owners are quota-limited to32 pages. Owner0/MAX and purposes outside1..5 reject.
Resolve checks live owner and generation. Release requires that exact identity
and map count0. Callers must invalidate translations before dropping the last
mapping pin. Reuse increments a55-bit generation; final-generation release
permanently retires the slot and does not restore available capacity.

Batch.allocate builds1..32 frames in bounded kernel scratch storage, rolls back
every partial grant on failure, and publishes the count only on complete success.
Its returned handle array is ephemeral until the next batch; trusted callers
copy it before another transaction. No user pointer controls that storage.

Normal roots exclude development imports. The separate frames-development
configuration exposes raw privileged probes and metadata fixtures for acceptance.
Its mapping-count fixture tests bookkeeping only; actual installed mapping,
invalidation and U-mode containment require Gate D evidence.

The ownership model's non-overlap, free-not-live and pool-envelope lemmas are
separate mathematical properties, not compiler or emitted allocator proofs.

The private firmware ABI accepts S-origin ECALLs from the supervisor envelope:
1 acknowledges SSIP and arms a future deadline1000..10000000 ticks away;
2 reads machine time;3 returns a saved-privilege origin witness;4 returns actual
M timer IRQ count. Unknown calls return17, invalid deadlines22. M handlers use
only their fixed private stack/frame, park the timer and latch SSIP. S execution
is initially nonpreemptible; pending notification is distinct from delivered
S interrupts and scheduler decisions. No SBI compatibility is claimed.

Startup reads back five PMP NAPOT intervals, exception delegation0xb1ff,
interrupt delegation0x1446 (desiredSSIP2 plus pinned QEMU H read-only0x1444),
status and SATP. Machine-origin-development is bootstrap-only and adds exactly
one typed M ECALL rejection boundary; normal roots cannot select it implicitly.
LLVM's immutable PMP comparison table is audited by exact source, contents,
guarded load and32-byte readonly object-section provenance.
