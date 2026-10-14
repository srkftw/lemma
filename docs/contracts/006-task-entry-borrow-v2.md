<!--
# Same-Action scheduler entry borrow v2

This additive Kernel4 component preserves the existing `Task.context`,
`Scheduler.enter`, `Scheduler.step`, every previous deployment and their
historical receipts. Only the separately selected Closure entry2 deployment may
use `Task.entryContextV2`, `Task.entryDispatchesV2`, `Scheduler.entryV2` and
`Scheduler.stepEntryV2`. Its selected whole-image audit and RV64 execution are
separate obligations; component checks do not establish Ready or a cycle gain.

The original task-table lookup and first complete AddressSpace.base validation
run before the task-state read, with identical failure precedence. Generation,
owner, purpose, registry, root, translation, stack adjacency/pins/top/canaries and
current running state remain checked. A successful frame index below8192 gives
pool+index*4096 in the aligned interval [0x82000000,0x84000000-4096]; the new local
pure checks expose that existing range to LLVM. They do not remove a physical
read/write or authorize a User integer.

The returned context has base+2048. Exactly the original zero/sstatus/scratch
writes at base+2048/+2312/+2328 occur. These offsets are disjoint from descriptor
authority/directory/root, Loader metadata and fixed frame records. The same S
Action reads the already validated root and task dispatch count, omitting three
complete duplicate descriptor scans. No mapping, allocation/release, scheduling,
DMA alias, descriptor mutation or reset may intervene. The borrowed base/root/
context ends before typed U entry. Its returning continuation independently reads
current task, kernel root and active root and retains the original reaping/error
policy. Only the descriptor identity survives as the original scalar handle.

The finite Action comparison supplies identical declared firmware replies to
both source programs. It compares every remaining effect/value, result, memory
write and partial prefix; it does not equate hardware timestamps or predict
cycles. Abstract returned Access statuses are separate from a non-returning
architectural fault. Stable-address fault cases are checked at the first retained
access. No equivalence is claimed for a transient RAM fault first arising only
on an omitted duplicate read. Reset aborts the old Action; exact same-backend
checkpoints resume the same admitted critical section with its complete metadata,
not a cache across syscalls or a cold-recovery shortcut.

The strict artifact guard must bind complete actual pre/post bodies, signatures,
first successful-context CFG gates and exact incoming callers. Only entryV2 may
call the two Task helpers, only stepEntryV2 may call entryV2, and only the new
versioned power step may call stepEntryV2. Old/nonselected artifacts take their
original route; a partial new family, different caller/configuration/root or
escaping borrowed context/root fails closed. Production boot/power pins require
genuine selected role exports before the whole audit can pass.

The whole-image stack and IPC caller checks retain their historical incoming
sets. Only a successful complete selected Entry2 pre-IR check may additionally
admit `Task.entryContextV2` into `Process.validateStackAt`, and
`Task.entryContextV2`/`Task.entryDispatchesV2` into `Task.lookupRecord`. Every
original fresh-base argument, status, effect, polling, capture and foreign-caller
gate remains required. A helper name or configuration label alone grants nothing.

The fresh initializer and missing Notebook whole builds share the original
377-input production archive. Their ordinary full audits separately bind the
qualified stack/IPC observer corrections, without changing the original producer
provenance or recompiling the unchanged initializer. The first archive-layout
and intermediate incoming-caller audit failures retain their original results.
Successful whole audits establish artifact closure; new CPU execution and
comparable cold-workload cycles remain separate measurements.

The actual refined component has1352 finite failure/corruption/boundary cases,
ordinary Lean layout lemmas and genuine Kernel4→LLVM20O2→RV64 objects. Expanded
entry requests are410→173 (three79-read scans); legacy fixture362→293 (three23-read
scans). The context function has213→86 O2 instruction sites, with the same three
actual reads and writes. These are component/static observations. Original new
canonical native boot still failed its500M bound; no unchanged cold run or
post-hoc deadline increase is authorized by this component.
-->
