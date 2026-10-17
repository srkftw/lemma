<!--
# Ordinary managed bytes v1

The additive successor `core0-user-v0.4` inherits User virtual memory/syscalls,
scalar Actions and the separately versioned records/sums bridges. Its new
`Action.managedBytes2` bridge accepts an exact source constant with two UInt64
parameters and a UInt64 result. Genuine pinned upstream Lean IR, rather than a
supplied IR/AST or foreign runtime, determines the complete ordinary call and
ownership closure. The closure has at most 32 definitions, depth 8 and 4096 nodes
per function; source IDs below 10000 and generated SSA IDs below 65536 remain
separate. Only safe monomorphic nonrecursive definitions are admitted.

The initial bytes subset supports source UInt64, UInt8 and ByteArray values;
`ByteArray.emptyWithCapacity`, `push`, `set!`, `size`, and `get!`; exact byte
conversions; selected UInt64 scalar operations; borrowed observations, consuming
calls/updates, owned returns, exhaustive internal Bool cases, and exact single
reference increment/decrement operations. Static objects, generic Array,
closures, joins, arbitrary loops/recursion, constructors, reference payloads and
unsupported ownership forms fail closed. Arithmetic shifts retain Lean's
modulo64 shift count. No pointer or runtime object address crosses a source
entry or is fabricated from a scalar.

The only Nat values admitted in bytes IR are literals 0..48, size results 0..48,
and UInt64.toNat values dynamically checked to 0..48. Their representation is an
unboxed logical UInt64 value; genuine IR's decrement of such a known scalar
needs no allocated Nat object. Arbitrary Nat operations, bignums, persistent
Nat objects and runtime replacements are denied. This is an explicit bounded
contract extension, not a discarded or no-op reference-counting helper.

Each ByteArray has a real process-owned Arena generational 64B slot: its payload
word0 is a distinct cookie, word1 is logical length, and bytes16..63 hold up to 48
bytes. Full tag/generation/size/cookie/length checks precede observations. The
existing 31-slot owned page and real reference count remain authoritative; old
record/sum cookies cannot be read as ByteArray. New arrays begin zeroed.
Capacity is not observable in ordinary Lean; requested capacity 0..48 is accepted
and this backend reserves 48 bytes. Larger capacities/Nat conversions return 236.

The first implementation always allocates a distinct output on a valid
push/set, copies at most 48 bytes, and consumes exactly one input reference.
Actual `inc` uses Arena.retain. Actual final `dec` uses Arena.release, clearing
payload/metadata and advancing generation. Source aliases retain their bytes.
Successful unchanged out-of-bounds set! returns the same owned reference;
get! out-of-bounds returns controlled 236 instead of a foreign panic runtime.
Length 48 push or real exhausted 31-slot allocation returns 237; cancellation 238
and invalid lifetime 239 remain distinct. Unpublished outputs and owned inputs
are cleaned up on normal resource/cancellation failure. An underlying mapped
memory fault propagates its real status; corrupted allocator state is never
repaired into trusted mathematical evidence. Process isolation and death
cleanup remain kernel obligations.

Component fixture, emitted LLVM/object audit and isolated RV64 service execution
must be reported separately. This subset does not close general managed Lean,
arrays/strings/closures, a proof kernel, course packages, mathematical precision,
or complete G2. Changing the checker implementation requires a separate new
execution registry/protocol/document version; existing Sums/Document4 identities
and receipts remain unchanged.

-->
