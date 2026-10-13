<!--
# Ordinary managed String and UTF-8 v1

`lemma-managed-string-v1` is admitted only through the additive
`core0-user-v0.6` `Action.managedString2` bridge. User1–5 and all earlier
profiles retain their original language authority and machine permissions.
This is a bounded String subset, not a general Lean runtime or proof kernel.

An entry is a safe, closed ordinary `UInt64 → UInt64 → UInt64` definition.
Genuine elaboration and the pinned Lean compiler at
`5045d0056413266e57c625dcd7c365b10e377c52` supply its actual ordinary IR.
The checker admits at most32 nonrecursive functions, call depth8 and4096 IR
nodes per function. It recognizes exact monomorphic UInt64, UInt8, ByteArray,
String and Option String signatures. It rejects static strings and byte arrays,
closures, recursion, joins, general constructors, foreign/replaced source,
unknown IR, duplicate SSA IDs and unsupported ownership metadata. Genuine
Bool and Option cases require exactly the compiler's representation names,
types, constructor tags and layouts; no fabricated declaration or AST supplies
source behavior.

The primitive subset contains bounded ByteArray allocation/push/set/get/size,
strict UTF-8 validation, String.ofByteArray, append, length, utf8ByteSize and
toByteArray, selected UInt64 scalar operations and bounded Nat conversions.
ByteArray/Nat bounds remain0..48. Each String holds at most40 UTF-8 bytes.
The accepted byte grammar follows [RFC3629 sections3–4](https://www.rfc-editor.org/rfc/rfc3629.html#section-3).
Strings can include NUL. Length counts Unicode scalar values, not grapheme
clusters. The automaton rejects overlong encodings, continuation leads,
surrogates, truncated sequences and values above U+10FFFF. The erased proof
argument of String.ofByteArray never substitutes for target validation.

A String owns one real generational Arena-v1 bytes slot, exact payload64:
word0 cookie `0x3152545352414d4c`, word1 byte length, word2 cached scalar
count and40 bytes at offset24. Every observation validates allocator state,
generation, tag, payload extent, cookie, complete UTF-8 bytes and cached count.
Option.some owns a distinct16-byte slot with cookie `0x3154504f5254534c`
and one owned String child. The graph depth is exactly one. Option.none is
immediate zero and allocates no object. This does not introduce a no-op
reference-counting helper: there is no allocation to reclaim for that value.

String construction consumes its ByteArray. Append consumes the left String
and borrows the right; it allocates/copies before releasing the consumed root,
so retained aliases preserve their bytes. String.toByteArray consumes its
String reference and returns a distinct copied ByteArray. This matches the
actual pinned compiler's owned argument. Retain and release use real allocator
reference counts and generation changes. An Option projection remains borrowed
from its live exact some owner until a real retain grants an independent root.
The compiler's conditional retain/decrement on that tagged projection is
admitted only with this witness. A source return cannot leak owned roots or
return a dangling borrowed value.

The allocator remains31 slots in one process-owned page. Exhaustion or a
String beyond40 bytes returns237, malformed UTF-8 or typed handle236,
cancellation238 and malformed lifetime/refcount overflow239. No resource
failure supplies a successful mathematical value. Cleanup attempts remaining
owned references and unpublished objects while retaining the first error;
underlying memory/syscall faults retain their actual status. A fault may prevent
reclamation, so no successful rollback is inferred. Kernel process death remains
the final owned-page boundary. Cancellation-independent typed release validates
real lifetime metadata rather than treating cleanup as a no-op.

The initial isolated deployment is `lemma-managed-string-bulk-deployment-v1`
on canonical silicon0.3: StoreUser1, NotebookUser2 and ArithmeticUser6.
`ManagedStringSubmission` writes16 hexadecimal UTF-8 bytes for each complete
UInt64 value, constructs actual Strings and Options, copies/decodes all64 bits
and releases their real roots. The existing exact rational domain, sign,
zero-denominator, overflow and semantic-budget preflight remains authoritative.
The helper does not claim arbitrary text parsing or unbounded integer arithmetic.

Protocol6 keeps the144-byte request and112-byte reply extent and demands the
new closed implementation/lowering/runtime/resource identities. IDs name
versioned contracts rather than hashes. Independent complete catalog and
pre/post LLVM preimages bind their implementation. Document7 keeps2496 bytes,
original goals/answers/anchors, eight attempts and64 learner events. Migration
from a strictly validated Doc1–6 changes only the necessary version words;
old Known/Unknown origins2–5 and histories remain exact. A new request appends
origin6. Editing erases current applicability while preserving prior evidence.
The guest checker has no storage, ink, panel or tutor authority.

Component model, genuine source/LLVM/RV64 object audits, linked isolated
execution, connected save/cold recovery and native/browser timing are separate
observations. The component has real UTF-8, alias/graph lifetime,31-slot OOM
and cancellation checks and rejects actual compiler/artifact mutations. No
library/object result alone closes the isolated workflow, G2 or proof-kernel gate.


The [connected receipt](../evidence/006-managed-string-integration.json) binds
three genuine whole-image builds and strict audits to an isolated Protocol6
course workflow, edited evidence, unsupported and semantic-resource outcomes,
bounded hints, acknowledged Save, independent cold display/bytes and failed
barriers. A separately compiled Laboratory mode fills31 real heap slots;
its first ByteArray allocation in the ordinary String pipeline returns237,
preserving mathematical bytes while pen, Save and cold recovery continue.
This does not claim completed String construction after OOM. Real invalid and
non-ASCII UTF-8 vectors currently have host Action-model and compiled component
qualification; the integrated mathematics pipeline uses ASCII hexadecimal.
The immutable native/browser bundles retain complete consumed-source archives;
actual browser String execution and RTL timing remain separate.

-->
