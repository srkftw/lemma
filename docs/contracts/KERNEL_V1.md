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

AddressSpace creates an independent owned 4KiB Sv39 tree with ASID zero. Its
descriptor is a generation-tagged owner1 frame; tables belong to the instance's
owner. User leaves carry exact live handles and logical R1/RW3/RX5 permissions.
Text-purpose frames admit RX, data R/RW and stacks RW. Intermediate leaves,
reserved PTE bits, unknown frames, stale handles and unsupported permissions
reject. Lookup checks the actual three-level walk against tracked ownership and
the exact PTE. Removal clears the PTE, flushes translations, then drops its pin.
Destroy requires an inactive root and releases leaves, tables and descriptor.

Stable supervisor mappings cover the image, metadata/boot stack, immutable
package/DTB, pool management alias, UART and finisher, with U clear. VA30000 is
an additional S-only RW/NX alias of the metadata page. User addresses are in
10000..40000000, excluding device holes. The loader reserves its text/data/stack
layout and leaves surrounding user stack guards unmapped. The S management
alias remains RW/NX even for executable user frames: the claim is user-PTE W^X,
not strict global W^X. No user mapping grants physical or device authority.

The guest loader validates every descriptor in a package of1..8 images before
allocation, including selection, unique IDs, payload bounds/overlap, entry
alignment/containment, fixed virtual layout and flags. It copies bytes into real
owned frames, obtains zeroed BSS/stacks from Frames, fences instruction fetch,
and publishes a sanitized U context only on success. A partial construction
unwinds on the stable S root. The separately compiled user root takes one u64
argument and returns the two-word Action result through the ordinary LP64 ABI.

The first process boundary suspends one S caller in reserved context80500000,
below the live boot stack floor80501000. Its owned U trap stack and frame are
validated before dereference. Hardware-saved SPP, SATP and PC establish origin;
unknown ECALLs return17 and advance only a validated ordinary ECALL site.
The dispatcher chooses the exact fixed S context for exit/fault return; typed
restoration installs/flushed its SATP before the caller reclaims user storage.
This single-process boundary is not yet a scheduler or capability system.
