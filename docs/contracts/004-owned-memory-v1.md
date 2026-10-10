# LemmaSim owned memory and stacks v1

Task 004's `core0-kernel-v0.3` compilation floor permits the reserved 32 MiB
physical pool `[0x82000000,0x84000000)`. The historical kernel compilation
profiles retain `[0x82000000,0x82200000)`. The shared 128 MiB RAM reservations
remain disjoint: firmware `[0x80000000,0x80010000)`, private firmware storage
`[0x80100000,0x80110000)`, supervisor image `[0x80200000,0x80300000)`, kernel
metadata `[0x80400000,0x80500000)`, supervisor resume/reaper stack
`[0x80500000,0x80510000)`, boot package `[0x80600000,0x80700000)`, and boot DTB
`[0x87e00000,0x88000000)`. Unlisted RAM is not automatically allocatable.

Before initializing frames, the compiled boot path selects count, owner quota
and kernel-stack pages in three little-endian 64 control words starting at
`0x804006a0`. Historical boots explicitly select 512/32/2. LemmaSim selects
8192/8192/4 only after machine-descriptor/boot consistency validation. Unsupported
combinations fail with invariant status 39. This is a boot-only constructor with
no user syscall/capability route. Changing a live allocator's configuration is
outside the contract. The guest frame allocator validates the configured count
and quota whenever used. It derives loop counts, handle encoding, generation
limits, metadata ranges and global accounting from that count. Its static loop
ceiling is 8192; a historical boot iterates 512, not the ceiling.

The 32-byte ownership records occupy `[0x80401000,0x80441000)` at full capacity,
inside the existing 1 MiB metadata reservation. Handles encode
`generation*count+index`; generations retire before overflow. The allocator
checks the entire construction, zeroes pages before publication, reports quota
or exhaustion without releasing another owner's data, and requires zero pins
before release. Four-page contiguous allocation validates all four generations
and accounting before zeroing/publication. Failed unpublished metadata commits
roll back all four records; this rollback is not exposed as a user operation.

Expanded address spaces use 13 initial page-table frames, compared with 11 in
the historical configuration. The added frames hold S-only PLIC mappings.
The existing UART page table also maps VirtIO, paper and pen in the expanded
configuration. Fifteen aligned 2 MiB S-only RW/NX leaves map the extra 30 MiB of
pool RAM; the original first 2 MiB table stays unchanged. The trusted writable
supervisor alias for user executable frames remains an explicit limitation.
Historical address-space descriptors retain version 1 and 32 inline user-leaf
rows. LemmaSim descriptors use version 2 and 1024 rows in eight separately owned
purpose-1 metadata pages, 128 rows per page. These pages have no U mapping and no
DMA grant. The descriptor's registry count at +1408 and eight 16-byte
handle/physical-address directory entries at +1424..+1551 fit before the saved
user context at +2048. Every descriptor validation checks all eight live owner,
generation, purpose, physical-address and zero-pin facts and rejects duplicate
directory pages. Publication follows allocation/zeroing; rollback and teardown
release all eight pages after removing user leaves. Registry rows retain exact
generation handles and PTEs. Row access is direct; lookup scans at most the current
mapped-leaf count, independent of document history. Allocation exhaustion leaves
existing mappings intact.

Expanded user allocation accepts aligned pages in `[0x40000,0x800000)`, except the
reserved finisher page at `0x100000`. Legacy allocation keeps the old upper bound
`0x100000`. The 1024 total-leaf ceiling includes text/data/stack pages and reports
explicit exhaustion. A default task's owned base cost is 13 initial tables +
8 registry pages + 1 data + 2 user stack + 4 kernel stack = 28 frames, plus text
and any additional low-address page tables. Its descriptor costs one separate
owner-1 frame. The 32 MiB global pool is not a promise of 32 MiB per application.

LemmaSim task trap stacks own four adjacent 4 KiB purpose 1 frames with independent
handles. Two 16-byte sentinel reservations leave 16352 bytes of usable call-stack
space. The published top is physicalBase+16368; vector entry consumes 288 bytes
below that top. Canary words at physicalBase and physicalBase+16376 are checked
before context use. These sentinels are overflow detection, not hardware guards;
the current supervisor direct map supplies no per-task unmapped guard. The
existing separately mapped user stacks retain their real unmapped adjacent pages.
Teardown validates every surviving handle, withdraws top first, releases each
handle once, and runs on the stable supervisor reaper stack.

Supervisor handlers keep SIE clear: one S vector is counted and nested S interrupt
entry is not permitted. M trap entry uses its separate firmware stack. Final
compiled O0/O2 selected-path audits must account the vector and require at least
25 percent margin in the expanded usable capacity. They are finite artifact
call-chain bounds, not a whole-program stack proof or physical measurement.

Checked bulk copies may transfer 4096 bytes through one owned kernel scratch
page. A nonempty 4096-byte range starting at any offset 0..4095 crosses at most
two 4 KiB user pages. Both pages, permissions and the complete scratch destination
are validated before any writes/input consumption. Increasing this limit past
4096 requires a new full-page preflight. The legacy console retains its explicit
256-byte ABI; IPC retains its own packet bounds.
