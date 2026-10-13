# Durable execution identity v3

This additive software format preserves the original exact/1 semantic goal,
domain, assumptions, checker/environment identity and arithmetic outcomes.
The immutable raw-ink records and journal format are unchanged. Existing
submission/1 records remain832 bytes and submission/2 remain1856 bytes; their
original codecs and migration stay separately supported. Current submission/3
is2496 bytes and fits the same two lazily owned4096-byte pages.

The first1856 bytes retain every offset from v2 except the format becomes3.
The additional layout is:

| Offset | Field |
| --- | --- |
| 1856,1864 | execution magic `0x314558454d4d454c`, extension version1 |
| 1872–1919 | six reserved zero words |
| 1920–1983 | active applicable execution slot |
| 1984–2495 | eight64-byte immutable execution slots matching attempt order |

Each slot has eight little-endian UInt64 words: request ID, implementation
version, checked-lowering version, runtime version, resource-contract version,
exact arithmetic budget, resource status and origin. An all-zero slot means
Unknown historical execution. No partial Unknown slot is admitted. The new
IsolatedManaged origin2 requires nonzero bounded request ID and exactly these
closed authorities:

- implementation `lemma-isolated-arithmetic-managed-v1`: `0x0002000100000001`;
- lowering `core0-user-v0.2/lemma-managed-records-v1`: `0x0002000000000001`;
- runtime `lemma-owned-arena-v1`: `0x0001000000000001`;
- resources `lemma-arithmetic-resource-v1`: `0x000100000000001f`,31 live heap
  objects, semantic budget0/8, unchanged10,000,000-MTIME-tick caller deadline.

These are distinctly named implementation/contract registry IDs. They are not
ELF hashes, source digests, a compiler-correctness proof or a complete theorem
environment. A strict independent artifact observer binds this version to the
complete genuine implementation source/signature/effect catalog and all
pre/post LLVM bodies and calls. Existing ordinary record constructor sourceIR,
24-byte checked layout and real arena/lifetime checks remain required. Exact
source/tool/ELF correspondence is separately retained in the artifact receipt.
Unknown or changed implementation closures reject this authority.

The active known slot must exactly equal the last immutable attempt slot,
whose revision, goal and outcome match current applicable evidence. Every
attempt slot's budget matches that precise attempt. Resource status must be0
for a mathematical outcome. Unused attempt slots are all-zero. Editing clears
only current outcome/revision applicability and active execution slot, retaining
all attempt answers, outcomes and execution identities. OOM, process death,
timeout and cancellation publish no mathematical attempt or execution evidence;
the already acknowledged record remains unchanged. Request IDs are scoped to
actual kernel calls, not globally unique persistent transaction IDs.

The guest first strictly validates v1/v2 using their original sizes. Migration
retains the whole v2 prefix and initializes every execution slot Unknown; it
never invents an old request or relabels a historical result with today's
compiler/runtime. It then publishes format3 through the same ordinary guest
Store transaction/barrier. Incompatible or malformed bytes never initialize a
replacement. V3 reads and transaction copies include all312 words. No host
process constructs these live records or performs their recovery.

Arithmetic copied-message protocol2 preserves the v1 field offsets and adds
four demanded contract IDs to the112-byte request, yielding144 bytes. The80-byte
reply adds those same IDs, yielding112 bytes plus the unchanged64-byte kernel
IPC envelope. The server checks all demanded identities before execution; the
client checks complete176-byte Reply envelope, original request, namespace,
page, revision, goal, budget, semantic identity and every execution identity
before publication. Success admits outcomes1–5; declared resource errors
retain outcome0. Protocol1 routines, lengths and admission remain separately
supported. Pending calls still cancel/consume before raw-ink Store work.

Host RAM codec tests and genuine checked lowering are distinct from real RV64
execution, backing durability, cold recovery, exact checkpoints and physical
qualification. The new connected acceptance receipt is added only after the
actual source-bound guest workflow has completed. General managed Lean,
proof-kernel/environment closure, authenticated media and resource-failure
history remain unfinished.
