# Managed sums v1

`core0-user-v0.3` adds `lemma-managed-sums-v1` on the existing isolated User
memory/syscall boundary. User1/User2, firmware, Boot and Kernel profiles reject
its `Action.managedSums2` bridge. Existing managed-records-v1 remains a separate
bridge, source grammar, cookie and artifact catalog; no historical result is
assigned this implementation identity.

The entry is an ordinary safe Lean definition `UInt64 → UInt64 → UInt64` at an
exact direct source constant. Elaboration and the pinned upstream Lean compiler
produce the real IR; the checked bridge discovers its complete nonrecursive
call closure. No supplied IR or handwritten mathematical interpreter grants
admission. Closed calls have depth at most8, at most32 source definitions,
4096 IR nodes per definition and disjoint source/SSA variable ranges bounded
by10000/65536. Unknown forms reject before LLVM emission.

Admitted payload sums have2..8 nonrecursive, nonindexed constructors, each
with1..7 explicit UInt64 fields. Parameters, dependencies, nested or reference
fields, nullary/tagged forms, closures and unsafe/foreign/replaced definitions
reject. Actual compiler constructor/tag/payload metadata must equal genuine
elaborated source metadata. UInt64 add/sub/mul retain modulo2^64 semantics;
UInt64 equality and Bool false/true tag cases have exact0/1 representation.
Admitted cases explicitly cover every source constructor once; defaults,
joins/jumps, RC increment/reuse and absent IR forms remain unsupported.

Every constructor obtains a real generational reference from the owned31-slot
Arena-v1 page. Its checked payload layout is8+8n bytes (16..64); the first word
is `(closed_type_id <<8)|constructor_tag`. Record cookies remain separate.
Initialization has a compile-time field mask; every field is written once
before publication. Cases validate the actual type, tag, arena handle,
constructor count and packed length catalog before choosing a branch.
Projections require a specific checked constructor and validate the complete
cookie, payload length, index and generation. Borrowed objects cannot be
released or returned; an owned return transfers its reference. A genuine
`dec1` calls real final release. Every failed helper attempts remaining owned
cleanup while preserving the first failure. Cookie publication failure
attempts release; errors/OOM/cancellation create no mathematical evidence.
Arbitrary repeated memory faults can prevent cleanup and remain real faults;
no rollback or successful reclamation is invented.

The first production algorithm is bounded exact/1 rational comparison to5/6,
returning an ordinary `Comparison.equal numerator denominator` or
`Comparison.unequal difference`. Its existing caller checks denominator,
encoding, integer bounds, sign and semantic budget before the ordinary entry.
Distinct24/16-byte payloads, generated source tag cases, borrowed projections
and final release are present in actual IR and emitted LLVM. Polynomial and
other outcomes keep their declared exact/1 algorithms. This is a managed sum
slice, not a general Lean runtime, proof kernel or bytearray/closure port.

`lemma-managed-sums-deployment-v1` uses the unchanged silicon0.3 hardware,
Kernel4, Store/User1, Notebook/User2 and Arithmetic/User3, selected by exact
`sums-notebook`/`sums-initialize` configurations. Protocol3 requires a distinct
implementation/lowering/runtime tuple. Document4 retains2496 bytes and extends
the versioned execution registry: legacy origin2 must match its original tuple;
new origin3 must match the exact sums tuple. v3 migration preserves all existing
Known/Unknown attempts; v1/v2 migration stays Unknown. Edits clear active
applicability only. No integer identity is described as an ELF or source hash;
complete genuine source/call/LLVM preimages and final artifacts independently
bind the named implementation authority.

General variable-sized heap, ByteArray, strings, recursive sums, closures,
shared references and general calling conventions remain open. A compiler
fixture or host runtime fixture does not establish isolated RV64 execution,
exact simulator timing parity, mathematical understanding or a proof-kernel
check. Those obligations require their own real guest observations.
