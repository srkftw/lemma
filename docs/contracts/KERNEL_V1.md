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
