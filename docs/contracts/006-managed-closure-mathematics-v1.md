<!--
# Isolated exact mathematics through owned scalar closures v1

This additive development deployment connects `lemma-managed-closure-v1` User7
to the existing exact/1 mathematical document and separately linked arithmetic
process. It does not add arbitrary precision, sampling authority, recursion, a
general Lean runtime or the proof kernel. Existing Records/Sums/Bytes/Array/String
profiles, formats, protocol sizes and original execution histories stay distinct.

Ordinary `ManagedClosureSubmission.compareFiveSix` computes the exact rational
cross-products n*6 and d*5. Its selection depends on the submitted numerator's
low bit. The genuine Lean compiler eta-expands `select`: each of two PAPs owns
three full64 scalar boxes (selector, numerator, denominator) and one real64-byte
closure/environment object. The exact generated `select._boxed` adapter unboxes
and consumes all four parameters, calls the actual scalar owner, then boxes the
full result. The checked finite CFG dispatcher applies this owner; no runtime
interpreter, foreign `lean_apply`, refcount stub or host checker enters the guest.
All captures are retained/reclaimed according to the actual source-derived
ownership, including captured values unused on the selected branch.

The positive-rational Action first checks canonical sign/magnitude encoding,
zero denominator, the original one-million operand bounds and semantic budget8.
Negative-zero requests NeedsClarification, zero denominator Invalid, out-of-domain
or budget exhaustion Indeterminate, and a bounded negative answer Invalid.
Only bounded nonnegative inputs enter the closure cross-product pipeline: n*6
is at most6,000,000 and d*5 at most5,000,000, so unsigned wrapping cannot authorize
Verified. The original degree-two goal remains exact coefficient equality in
Q[x] through OwnedSubmission; no evaluation at sampled points can establish
polynomial identity. Goal3 remains Unsupported.

One process-owned Arena page holds31 generational128-byte slots. Each rational
submission has two4-slot closure graphs and an actual application argument box,
so its ordinary peak is9 live objects. Result boxing happens after consuming an
application root and argument. All graphs are reclaimed before a normal reply.
The server checks the actual live count0 before publication and emits guest
observation0x45d(request,count,mode,status). Laboratory OOM retains31 independent
owned pressure boxes; ordinary source allocation really returns237 and the
prepublication check requires those31 roots remain. Invalid shape236,
cancellation238 and lifetime239, page allocation failures33/38, actual death96,
transaction cancellation94 and the unchanged one-second deadline93 cannot
publish a mathematical result or attempt. Unrecoverable memory faults do not
claim successful cleanup. The general runtime contract remains
[MANAGED_CLOSURE_V1.md](MANAGED_CLOSURE_V1.md).

Protocol7 retains the original exact checker, namespace/page, revision, goal,
operands, budget and request identity. It appends the four closed execution
identities and the original domain/assumptions. Request160B uses domain144 and
assumptions152; reply128B uses domain112 and assumptions120. The existing64B
IPC envelope and maximum192B payload are unchanged. Server admission requires
domain=original goal and assumptions0. The client requires the complete immutable
copied reply to match every original identity, execution contract, domain and
assumption field; it admits outcome1..5 only with status0. Declared resource
errors require outcome0. Old1..6 packets cannot obtain Protocol7 authority.

| Authority | Name | UInt64 |
| --- | --- | --- |
| Implementation | lemma-isolated-arithmetic-closure-v1 | 0x0007000100000001 |
| Lowering | core0-user-v0.7/lemma-managed-closure-v1 | 0x0007000000000001 |
| Runtime | lemma-owned-arena-closure-graph-v1 | 0x0001000500000001 |
| Resources | lemma-arithmetic-closure-resource-v1 | 0x000500000000001f |

These are closed implementation-version names, never artifact hashes. Complete
source signatures, genuine owner/adapter IR, checked Actions, finite dispatcher,
pre/post LLVM bodies and calls are independently pinned by the ordinary audit.
Actual source/tool/object/ELF correspondence belongs to each artifact receipt.
The exact selected configurations are closure-bulk-notebook, closure-bulk-initialize,
closure-arithmetic-oom-development and closure-arithmetic-fault-development under
the `lemmasim-silicon-` prefix. All use the canonical0.3 machine and StoreUser1,
NotebookUser2, ArithmeticUser7 and Kernel4. Only the Laboratory OOM/fault selectors
supply arithmetic modes1/2. The service receives only its EndpointReceive and
ConsoleWrite grants; it has no ink, Store, panel, tutor or another address-space
capability. Notebook checking remains asynchronous and pen work has priority.

Document8 keeps the existing2496-byte layout, exact semantic goal/domain/revision,
learner events, assistance and eight immutable attempt slots. Execution extension6
admits origin7 only with the tuple above. Old origins2..6 delegate to their original
closed validators; all-zero remains explicitly Unknown. After strictly validating
a Document7 record, migration changes only words at byte8 and1864. It cannot
relabel, fill or erase an old identity or manufacture an old request. Earlier
selected parsers still reject8. Editing clears only active applicability and
preserves all histories. Publication requires a reply for the current original
revision/goal/domain/assumptions and a complete admitted execution identity.
The same guest Store transaction and barrier, followed by its actual controller
Saved state, publish durable bytes; IPC success alone is not Save.

Saved is a durable-data state and can precede queued guest tile uploads. The
Laboratory failure observer uses one declared virtual second of actual clock
progress, then reads a complete private QEMU checkpoint through the exact
11.1.1 migration decoder. It verifies the real Notebook dirty queue is empty,
dirty bounds are clear, and raw/save/recovery work has drained before comparing
all controller pixels with a new cold CPU. This is read-only boundary inspection;
it does not render ink, modify guest RAM or supply a mathematical result. The
original premature-frame FAIL and its source-bound queue diagnosis stay separate.

Host finite-RAM fixtures, checked LLVM/component mutation audits, actual isolated
RV64 IPC, notebook Save/cold recovery and RTL/Wasm timing are distinct results.
Concrete receipts must identify which of those ran. This contract alone does not
establish execution or close full runtime/proof-kernel/G2–G7 work.
-->
