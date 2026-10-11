# LemmaSim owned memory and stacks v1

Task 004's `core0-kernel-v0.3` compilation floor permits the reserved 32 MiB
physical pool `[0x82000000,0x84000000)`. The historical kernel compilation
profiles retain `[0x82000000,0x82200000)`. The shared 128 MiB RAM reservations
remain disjoint: firmware `[0x80000000,0x80010000)`, private firmware storage
`[0x80100000,0x80110000)`, supervisor image `[0x80200000,0x80300000)`, kernel
metadata `[0x80400000,0x80500000)`, supervisor resume/reaper stack
`[0x80500000,0x80510000)`, boot package `[0x80600000,0x80700000)`, and boot DTB
`[0x87e00000,0x88000000)`. Unlisted RAM is not automatically allocatable.

LemmaSim's `lemma-boot-clear-v1` layout field binds the entire reserved metadata
interval `[0x80400000,0x80500000)` to the ELF's zero-file-byte RW `PT_LOAD` BSS.
The existing Lean-authored structured M startup clears aligned 64-bit words
before publishing the new hart/DTB handoff. Whole-machine QEMU reset retains
RAM, so every boot must discard old task/object/device handles before rebuilding
frame ownership. The strict ELF audit independently checks the bounds, actual
clear-loop words, stride and handoff stores. Historical profiles retain their
original 128-byte boot BSS. QEMU whole-machine reset quiesces devices before
restarting the CPU; a live driver reset still uses its explicit quiescence path.
Developer `system_reset` may drain/flush block nodes and proves warm reboot and
refresh recovery. It is separate from Laboratory process power cut, which
discards the filter's volatile writes without a clean shutdown.

Before initializing frames, the compiled boot path selects count, owner quota
and kernel-stack pages in three little-endian 64 control words starting at
`0x804006a0`. Current non-LemmaSim kernel launches select512/32/4; the explicit
512/32/2 constructor remains accepted for historical allocator fixtures.
Historical Task003 evidence still means its original two-page allocation.
The current `lemma-kernel-layout-v2` manifest records four pages for every
owned kernel trap stack. LemmaSim selects
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

Within one single-hart S critical section, registry and stack pin counts are
read through the physical metadata slot whose exact owner, generation and
purpose have just been resolved. This removes a second resolution of the same
grant. Running/blocked context and trap-frame validation similarly share one
freshly validated descriptor base within their call, while retaining exact
SATP/root agreement, current stack handles and pin counts, contiguous frames,
published top, canaries and hardware privilege checks. The low-level
`validateStackAt`/`validateExpandedStackAt` helpers require that base from the
same call; no user endpoint exposes them. Validation results are never cached
across syscalls or supervisor critical sections.

Lookup validates the complete directory before reading live rows. It then reads
each page's physical address once and scans its at most128 live VA words; the
legacy inline list uses the same bounded word scan. Finding one matching row
does not stop the scan. A second match anywhere in the live list, including
another registry page, rejects the descriptor. There is no stale mapping cache.
The selected row still undergoes exact owner, generation, purpose, permission,
tracked-PTE and real page-table validation. Single-hart supervisor critical
sections prevent a registry mutation between directory validation and scanning.

Expanded user allocation accepts aligned pages in `[0x40000,0x800000)`, except the
reserved finisher page at `0x100000`. Legacy allocation keeps the old upper bound
`0x100000`. The 1024 total-leaf ceiling includes text/data/stack pages and reports
explicit exhaustion. A default task's owned base cost is 13 initial tables +
8 registry pages + 1 data + 4 user stack + 4 kernel stack = 30 frames, plus text
and any additional low-address page tables. Its descriptor costs one separate
owner-1 frame. The 32 MiB global pool is not a promise of 32 MiB per application.

Current task trap stacks, including the existing kernel development profiles,
own four adjacent 4 KiB purpose1 frames with independent
handles. Two 16-byte sentinel reservations leave 16352 bytes of usable call-stack
space. The published top is physicalBase+16368; vector entry consumes 288 bytes
below that top. Canary words at physicalBase and physicalBase+16376 are checked
before context use. These sentinels are overflow detection, not hardware guards;
the current supervisor direct map supplies no per-task unmapped guard. The
LemmaSim User stacks separately own four purpose-5 frames mapped at
`[0x3fffa000,0x3fffe000)`, with true unmapped lower/upper guard pages at
`0x3fff9000` and `0x3fffe000`. The package v2 descriptor and loader agree on
this four-page interval; the saved User top remains `0x3fffe000`. Historical
package v1 stacks remain two pages at `0x3fffc000`, with their existing guards.
The expanded address-space API also rejects attempts to map the new guard pages.
Teardown validates every surviving handle, withdraws top first, releases each
handle once, and runs on the stable supervisor reaper stack.

Supervisor handlers keep SIE clear: one S vector is counted and nested S interrupt
entry is not permitted. M trap entry uses its separate firmware stack. Final
compiled O0/O2 selected-path audits must account the vector and require at least
25 percent margin in the usable capacity. Non-LemmaSim managed tasks now charge
11 initial tables+1 data+2 User stacks+4 kernel stacks=18 privately owned frames;
the separate owner1 descriptor makes19 global frames, before text pages. The
owner quota stays32, so the buffer server's four reserved arena pages permit
at most10 text pages. These formulas replace current checks' old16/17 counts;
they do not relabel the retained Task003 observations. They are finite artifact
call-chain bounds, not a whole-program stack proof or physical measurement.

Checked bulk copies may transfer 4096 bytes through one owned kernel scratch
page. A nonempty 4096-byte range starting at any offset 0..4095 crosses at most
two 4 KiB user pages. Both pages, permissions and the complete scratch destination
are validated before any writes/input consumption. Increasing this limit past
4096 requires a new full-page preflight. The legacy console retains its explicit
256-byte ABI; IPC retains its own packet bounds.

When both physical user aliases, the scratch address, page split and byte length
are eight-byte aligned, copying uses at most512 checked64-bit transfers. Each
word stays wholly within a preflighted user page and the owned scratch span.
Unaligned spans and partial-word tails use the original bounded byte path.
Neither path writes anything until full destination validation succeeds. The
host-only literal Action fixture `tests/kernel/BulkCopyAndDeadline.lean` checks
4096 bytes across two pages, a13-byte unaligned crossing, read-only/missing
second-page rejection without partial writes, stale/wrong scratch handles and
duplicate rows in both registry layouts. CPU timing and stack bounds are
separate artifact/boot observations.

The workload checker can retain read-only allocator observations using
`conformance/lemmasim/check_owned_memory.py`. Each physical read is at most
64 KiB. Ready and final-before-reap observations read the bounded ownership
array, accounting counter, task descriptors and eight registry pages per live
task; periodic observations read one rotating ownership slice at intervals of
at least 30 seconds. Registry words are VA, owned handle, exact PTE, permissions
at byte offsets 0, 8, 16, 24, matching `AddressSpace.commitLeaf` and `lookup`.
The observer checks generation, owner, purpose, mapping counts, directory/root
identity and exact recorded PTEs without pausing or writing guest memory. A cold
boot that quits between monitor turns gets separately labelled actual Ready
and final reads at that boundary. Missing or contradictory observations fail;
the maximum observed allocation is not a whole-run high-water proof. A selected
real guest call-closure review checks that normal raw append and raster paths
do not load complete page history or allocate pages. Toolbar/page-loading paths
remain separate, and this review is not a whole-program memory proof.
