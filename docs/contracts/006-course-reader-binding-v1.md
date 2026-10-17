<!--
# Cooperative package reading and selection provenance v1

`lemma-course-reader/1` adds a read-only User client of the existing Store
operation5. It changes no durable Store format, namespace grant, package format,
legacy loader or mathematical authority. The notebook integration is pending;
this component does not establish an installed-course user workflow.

The128-byte private context has endpoint0, outgoing8, incoming16, namespace24,
package identity32, edition40, staging48, capacity56, first request64, phase72,
pending transaction80, copied bytes88, declared length96, requested count104,
next request112 and terminal error120. The context,192-byte outgoing packet,
256-byte incoming packet and bounded staging span are aligned, nonwrapping and
pairwise disjoint. Real kernel calls independently validate owned user spans,
handles, generations, grants and quotas. Configuration/spans remain immutable
for one reader lifetime; the caller never uses active package/document storage
as staging. No host address or validation token is saved in the context.

`start` rejects a retained pending handle, initializes only state words and
reserves256 consecutive IDs. Phase0 can issue one READ; phase1 can only poll its
existing handle. A step neither waits nor sleeps and copies at most128 bytes.
WouldBlock retains both handle and private bytes. Ordered counts/offsets and
exact framed replies are checked using the ordinary Store client. Failures stop
without another request. A partial staging write preserves the actual ordered
prefix/error from the existing Format.copy contract; failed bytes never permit
publication. Under aligned64-bit copying, an admitted failed word publishes
none of that word. These are existing copy semantics, not a new optimization.
Injected checked-access outcomes qualify the Action error/order interface.
Architectural User page/access faults retain the existing isolated-process
trap behavior; this component has not exercised those faults on a CPU.

At most256 READs each have the existing30-second IPC ceiling. The integrating
caller also owns its workflow deadline and invokes cancellation on leaving or
canceling the task. Cancellation calls cancel once, consumes one terminal result
and discards it, including a reply accepted before cancellation. It never copies
that discarded result into staging. Reset drops User/kernel lifetimes; exact
same-backend checkpoints retain context, pending transactions and owned bytes.

Phase2 means raw bytes are complete. `finish` separately runs the entire genuine
bounded package validator, requiring exact identity/edition after CRC, text,
entry, prerequisite and pinned-domain validation. Only phase3 permits a caller
to publish an immutable resident selection. This initial validator is bounded
to32768 bytes and is not an incremental parser or measured responsiveness
claim. Context/access faults terminate with the actual error; callers discard
partially written state. Neither phase3 nor reading creates Installed/Saved.

`lemma-course-selection-binding/1` is128 bytes of provenance: magic0/version8,
package16, edition24, CRC32, node40, source anchor48, kind56, goal64, checker72,
domain80, assumptions88, budget96, source text span104, rights text span112 and
original submission revision120. Source/rights spans refer to immutable package
bytes, and the CRC binds every original source/edition/rights anchor and text.
CRC detects corruption; it is not authentication or a rights grant.

Capture first validates the actual entire package and selected node. Only the
declared exact exercises1/2 admit a checking-selection binding. Authored material
and the explicitly unsupported exercise3 return Unsupported before writes.
An unpublished disjoint binding receives its commit tag last. A write failure
cannot create a successfully captured selection. `applicable` requires exact
revision, goal, domain and assumptions and returns false for an edited/different
object while preserving history. Malformed/version/resource errors remain
distinct. A selection binding is never Verified evidence. The original
mathematical document's goal/checker/environment/execution identity and actual
guest result/resource outcome remain required and are not rewritten by these
Actions. An integrating durable format must retain one binding per actual
attempt and preserve unknown historical provenance explicitly.

```sh
nix develop --no-write-lock-file --command python3 scripts/check_course_reader.py \
  --output-dir build/courses/course-reader-new \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp
```

The qualifier requires an original genuinely Lean-published reference package,
observes its CRC independently with zlib, exercises imported target Actions,
archives their complete transitive source/compiler inputs, checks the actual
elaborated dependency/effect closure and emits LLVM/O2/RV64 objects. The only
unresolved boundary is the existing syscall bridge. Host fixture transport
bytes are raw opaque package bytes and literal packet outcomes. The fixture
does not mount a journal, recover documents, check mathematics or run a CPU.
Real notebook selection/rendering/attempt binding/save/cold remains pending.
-->
