<!--
# Ordinary managed Array UInt64 v1

`lemma-managed-array-v1` is a separate bounded successor grammar, selected by
the additive `core0-user-v0.5` bridge. User1–4 and every historical profile keep
their earlier source authority. Defining or building this component does not
establish a linked User5 deployment or isolated RV64 execution.

The source entry is an exact safe ordinary `UInt64 → UInt64 → UInt64` constant.
Genuine elaboration and the pinned Lean compiler at immutable revision
`5045d0056413266e57c625dcd7c365b10e377c52` produce its complete nonrecursive
ordinary IR closure. The checker accepts only monomorphic `UInt64` and exact
`Array UInt64` source signatures, at most32 source functions, call depth8 and
4096 nodes per function. Source IDs below10000 and generated IDs below65536
remain disjoint. Arrays of any other type, erased ordinary-call arguments,
closures, recursion, joins, arbitrary constructors, static arrays, foreign or
replaced source, unknown IR and unsupported ownership metadata reject.

The initial primitive subset is `Array.emptyWithCapacity`, `push`, `size`,
`set!` and the compiler's `get!InternalBorrowed`; genuine full UInt64 boxing
and unboxing; bounded Nat conversion/observation; selected UInt64 scalar
operations; and exhaustive internal Bool cases. Only the exact known type
argument position of these Array primitives may contain erased IR metadata.
Capacity and Nat values are checked to0..6; larger values return236. Capacity
is not observed by admitted source, and each parent reserves six entries.
Shift counts retain modulo64 semantics. No object handle or runtime address
crosses the scalar source entry, IPC or a durable mathematical record.

An array parent is a real process-owned generational Arena-v1 bytes slot with
exact payload length64: word0 is its distinct cookie, word1 its logical
length0..6, and words2..7 contain owned handles of real Arena scalar boxes.
Every element box has the allocator's exact box tag/length8 and preserves all
64 bits. This follows the pinned upstream `src/include/lean/lean.h`
`lean_box_uint64`, which allocates an eight-byte scalar constructor even on
64-bit targets; pointer tagging cannot represent the whole UInt64 domain.
The parent cookie, complete allocator lifetime/header, generation, length,
child tag and access bounds are checked before observations. Scalar boxes
cannot contain references, so admitted graph depth is exactly one and cycles
are impossible. The old allocator has not acquired a general traced-object
or garbage-collection contract.

Actual IR `box` allocates a child; `push`/`set!` consume one owned parent root
and one owned child root. Every valid update creates a distinct parent. The
new parent really retains each copied child, takes ownership of its new child,
then consumes the old parent root. Remaining aliases preserve their values.
An array IR increment calls real checked parent retain. Its decrement calls
the specialized graph release, which decrements a shared parent alone or
preflights/releases at most six children before the allocator clears and
regenerates the final parent. Plain allocator release cannot substitute for
this graph-root operation. Borrowed lookup results are tied to a still-live
array local and cannot be consumed, returned or used after that owner dies.
All owned references must be released or transferred at a source return.

The genuine compiler-derived `owner._boxed_const_1` default has no fabricated
source declaration. Admission requires the exact ordinary owner, safe source
signature, zero initializer parameters, result`tobject`, no sorry dependency,
and exactly a UInt64 literal-zero binding, full UInt64 box binding and return
of that box. The complete genuine initializer IR and owner source signature
are retained with the ordinary source closure. The compiler treats it solely
as an unobservable static-default token at that owner's borrowed get! default
operand. Unboxing, returning, inserting, calling with, retaining or releasing
that token rejects. There is no no-op static/default reference-count helper.

Both out-of-bounds `get!` and `set!` select **controlled-panic236**. They return
an error status and cannot publish a default or apparently successful
mathematical value. For `set!`, the consumed parent root and replacement child
are really released; separately retained aliases survive. This policy is an
explicit freestanding choice: the pinned `Init/Prelude.lean` borrowed get
extern and `Init/Data/Array/Set.lean` set extern route to `lean_array_get_panic`
and `lean_array_set_panic` in `src/runtime/object.cpp`. The latter decrements
the replacement and passes the array to `lean_panic_fn`; that routine returns
its default only when the upstream panic policy does not exit. The pure source
`setIfInBounds` unchanged-array equation and upstream nonfatal default return
are not claimed as successful behavior of this controlled-panic profile.

The actual31-slot allocator remains authoritative. Each live parent and boxed
element consumes a slot; a valid update needs one new parent after its source
boxing. Slot exhaustion and pushing beyond six elements return237; cancellation
returns238; malformed lifetime/refcount overflow returns239. Helpers attempt
all remaining owned/unpublished cleanup while preserving the first failure.
Cancellation-independent release validates graph metadata before child access.
Underlying mapped-memory or syscall faults propagate their real status. A fault
can prevent rollback/reclamation; the failed computation supplies no trusted
result and process death remains the final kernel page-ownership boundary.
No successful reclamation is inferred after such a fault.

The finite-memory Action fixture tests actual runtime allocation, full64 values,
COW child references, graph generation/reclamation, literal31-object OOM,
bounds, cancellation and malformed child types. The compiler component fixture
starts from genuinely elaborated ordinary arrays and lowers checked source IR
to structured CFG/LLVM plus genuine scalar Action runtime functions. These are
separate host/component results. Target link/provenance/stack audits, an actual
isolated User5 service, and connected notebook persistence require their own
observations. Strings, general arrays, closures, recursion, managed collection
and the proof kernel remain unfinished.

The first production selection is `lemma-managed-array-bulk-deployment-v1` on
the unchanged canonical silicon0.3 binding. Store remains User1, notebook
User2, and independently linked Arithmetic becomes User5/Protocol5. Ordinary
`ManagedArraySubmission` builds a full-width boxed array, retains it across a
COW update, reads both versions, and releases both graphs. The scalar result
stays behind the existing exact fraction/overflow/resource preflight. It does
not make Array pointer identity mathematical authority. Doc6 preserves old
evidence identities during decoding; editing clears current applicability and
keeps its history. The [connected receipt](../evidence/006-managed-array-integration.json)
records three whole-image builds/audits and five actual isolated requests in a
QEMU course/ink/Save/new-cold/failure workflow. New Array heap-OOM containment,
RTL timing and browser execution still require observations. The separate
[migration receipt](../evidence/006-array-document-migration.json) observes an
actual acknowledged Doc5 course opening under this guest: only the document
version and execution-extension version words change. Earlier ByteArray
execution identities, mathematical results, assistance and raw ink survive.
A subsequent actual Array check appends its own identity; independent cold
recovery preserves the mixed history. Doc6 learner events require the same
strict policy/event validation as Doc5. The original missing-version observer
failure remains retained alongside the corrected observation.

-->
