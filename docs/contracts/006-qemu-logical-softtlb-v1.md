<!--
# QEMU logical SoftTLB experiment, version 1

Status: actual narrowly qualified data-translation/SFENCE increment. The original
`GAP_CONFIRMED` observation in `conformance/lemmasim/QEMU_STATE_EQUIVALENCE.md`
remains. This contract does not establish total exact QEMU continuation.

The opt-in host binding `lemma-silicon-fast-softtlb/0.1.0` uses the pinned
QEMU 11.1.1 source and the unchanged canonical 0.3 hardware/guest contract. It is
a separately identified derivative, not a replacement of any historical
profile, VMState 3 device schema, binary or tool. Its TLB resize windows use
precise virtual instruction-clock time rather than host realtime. A seqlock
read combines the published icount/bias with the executing CPU budget minus
its decrement/extra counters without modifying either; SFENCE helpers cannot
use the ordinary clock API while `can_do_io` is false. Allocation
failure rejects instead of silently choosing another cache size. These are
explicit new backend semantics. Ordinary default derivations remain unchanged.

The experimental QMP pair `lemma-save-machine-softtlb` and
`lemma-load-machine-softtlb` accepts `filename` for ordinary machine state and
`cache-filename` for the logical sidecar. Both are exclusively owned files.
The paired paused capture uses the upstream initially all-dirty RAM bitmap
and copies every RAM page while execution stays inactive. Only this selected
operation skips migration dirty-log start/stop: the ordinary transaction calls
`tcg_commit_cpu` and flushes the original TLB. Ordinary legacy saves retain their
existing behavior. The paired operation never flushes or restores the original
cache to manufacture a matching boundary.

One paused, single-CPU QMP operation captures the pair without an intervening
guest edge or external-event admission. The sidecar binds the exact complete
ordinary machine file SHA256 and precise virtual boundary. Restore is admitted
only in a new private fork. Sidecar format, bounds, checksum, boundary and all
memory-region identities must validate before any cache adoption. A failed
machine restore remains a failed isolated fork; it must never resume.

`LMTLB01` sidecar schema 1 declares page size, MMU-mode count, all primary and
victim slots and exact primary capacity, dirty-mode bits, flush counters,
large-page range, eviction index, occupancy and resize-window metadata. Valid
slots retain all read/write/execute comparator tags, target physical page,
transaction attributes, page size/protection and slow flags. Empty slots have
an explicit empty marker; their uninitialized unused full-entry storage is not
logical state. Host pointers, addends, RAMBlock addresses and section pointers
are never serialized. Region type/name/owner include explicit presence bits
for unnamed mappings.
Physical placement, region offset, size, readonly state and RAM/ROMD/MMIO kind
identify each logical mapping. A SHA256 covers every actual mapped segment and
every hole of its complete physical page, including leaf regions hidden by an
unnamed subpage dispatch wrapper. Unknown/IOMMU layouts reject.
Restoration validates that identity and rebinds host references at their actual
new addresses while preserving saved tags and semantic flags. It does not
reevaluate guest PTEs or call `tlb_set_page_full` to refill or evict entries.

Schema 1 binds explicit stopped/running/work-queue witnesses and the migrated
halt, interrupt-request and exception fields. These must also match the restored
ordinary CPU stream before adopting any logical cache array.

This first schema rejects unrepresented pending CPU work and live execution
explicitly. That restriction is part of the experimental admission, not a
hidden claim that an arbitrary cached boundary is clean. CPU interrupt and
exception state remain in the bound ordinary migration stream. Further pending
acceleration work must receive its own logical representation before broader
admission. Snapshot callers must not flush the original machine to satisfy a
boundary check. Public Fast/Session adoption is not authorized by preparation.

TBs, jump-cache hits, generated instruction visibility and executable-page dirty
tracking remain separate unresolved dependencies. Rebuilding them cannot be
declared semantically irrelevant by inspection alone. Required real guest cases
include warmed translation followed by PTE change without SFENCE, subsequent
SFENCE, execution translation changes and jump-cache bypass, self-modification
without/with FENCE.I and interrupts between those operations. Debugger CSR/PTE
writes are insufficient substitutes for guest-issued instructions. A passing
logical SoftTLB result must name the narrower tested property and retain every
failed or unqualified case.

The actual bounded `logical-guest-a5` result used genuinely elaborated checked
kernel-v0.4 Actions, LLVM 20.1.8 and an audited RV64IM test ELF. At 1,000,000 ns,
mode 1 primary slot 80 retained VA0x82050000 -> PA0x82103000 despite the guest's
unfenced leaf PTE change to page B. Original and private restored fork both
read 111 without SFENCE and 222 after actual guest SFENCE, then reached the
predeclared 300,000,000 ns boundary within 120 s per interval. Every final declared
logical slot/metadata field agreed exactly. The sidecar retains the actual
stopped/running/work witness and pending interrupt-request 2/exception-index -1.
This does not qualify interrupt delivery or handler continuation.

The initial completed host build used a kept pinned Nix-configured tree and
finished in 563.135 s within 1,200 s. Later bounded host increments preserve their own
executable/source identities. The guarded maintained installer reproduces all
eight tested derivative source files exactly. Default `logicalSoftTlb=false`
actually evaluates to the identical pre-change derivation. Complete fresh Nix
packaging was not rerun after its retained original failures. See the complete
small receipt in `docs/evidence/006-qemu-logical-softtlb.json`.

The ordinary container and sidecar remain intact. Each file hash and any
binding/header differences are reported explicitly; no byte mask, tolerance,
original-state flush or hidden clean-boundary retry certifies this experiment.
-->
