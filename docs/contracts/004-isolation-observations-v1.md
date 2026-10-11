# LemmaSim ordinary-client isolation observations v1

The closed `lemmasim-isolation-development` deployment adds one separately
linked `Lemma.User.Development.NotebookIsolation.main` to the same store and
notebook specifications as `lemmasim-notebook`. It selects the existing
`NotebookKernel.isolationBoot` path, scheduler, Sv39 loader, capability tables,
IPC and device syscall handler. It introduces no second kernel or privileged
User instruction startup. The ordinary production deployment admits no fixture
image. The initializer remains separate and this deployment cannot format.

The third client receives document Call and console Write grants only. It
serializes the actual replies below through its console capability. Any reply
that differs aborts the fixture; the independent observer also rejects the
retained behavioral result. A successful source export is not execution proof.

| Test | Actual operation | Required reply |
| --- | --- | --- |
| 1 | Raw block capacity, using the document endpoint | 72, wrong device endpoint authority |
| 2 | Raw block write, missing capability | 80, invalid handle |
| 3/4 | Paper geometry / pen sample, using document endpoint | 72, wrong device endpoint authority |
| 5 | Endpoint creation using document authority | 81, wrong capability type |
| 7 | Real namespace1 IPC request with missing capability | 80, invalid handle before service delivery |
| 101/102/106 | Real IPC delivery of open/begin/delete requests for namespace3 | transport0 and128 reply bytes |
| 201/202/206 | Service application replies to those namespace3 requests | 220, unsupported namespace framing |
| 298/299 | Queued IPC transaction / guest20.27second attempted request | transport0, nonzero transaction / actual monotonic time |
| 300 | Real namespace1 eight-byte chunk from a foreign full sender/transaction | 232, staging owner mismatch |

The document grant deliberately authorizes namespaces1/2 as one notebook
family. Namespace3 rejection is format admission, not a claim of finer-grained
namespace1/2 capabilities. The original eight-byte payload is
`0xd15ca11ed15ca11e`; it must never become a document transaction. The foreign chunk is attempted at guest20.27seconds, after the ordinary first
stroke pen-up at20.25seconds. Actual IPC acceptance is observed separately.
The independent checker requires Notebook Pending before the attempt and actual
queued IPC before the first stroke Saved ACK. Test300 proves the actual
sender-owner check rejects this client during that notebook commit interval.
Pending UI state does not alone establish that the store staging buffer was
populated at the exact instant of that request.

After guest monotonic time reaches42seconds, the client reports its planned
load then executes `User.Memory.read64 0x400000`. This page is not allocated in
its address space. The required observation is real User load page fault13,
original trap SPP clear, normal task termination44, and ordinary frame reaping.
A returned load, a source failure, a privileged startup exception, or a host
memory edit cannot satisfy this boundary.

Kernel-only cells `[0x80400f00,0x80400f20)` hold this deployment's selection and
initial queue identity. They follow the DTB scratch reservation ending at
`0x80400f00`. No User mapping or grant exposes them. Normal boot explicitly
clears selection. At boot, immediately before this client's actual fault, and
after its task lookup confirms reaping, compiled kernel observations revalidate
the VirtIO queue frame as owner1/purpose1, and record its actual handle, physical
base, outstanding kind, purpose, mapping count, remaining frame count and actual
guest monotonic time. The
handle/base must remain identical and post-reap free frames must increase. These
are observations of a retained live kernel DMA allocation. Driver outstanding
state alone does not prove an in-flight DMA death experiment.

This experiment additionally selects a named, finite Laboratory medium policy:
the first actual write at/after virtual40seconds waits3virtualseconds before the
device consumes its DMA iovec. Normal media disable this optional delay. Actual
`write-delay-begin`/`write-delay-end` observations identify the same sector offset
and byte length. The independent observer requires both compiled kernel fault
and completed-reap times strictly inside that device interval, with actual write
kind2 and the same kernel-owned queue frame. The actual delayed write must then
consume its retained DMA bytes, followed by normal guest durable publication.
No host sleep, QMP stop/drain, driver counter alone, or post-hoc disk rewrite can
satisfy these checks. The declared delay policy belongs in the run identity.

`conformance/lemmasim/check_notebook_isolation.py` requires an existing second
notebook with acknowledged raw writing in the input image. It independently
recovers the before/after committed records, preserves every namespace2
object/transaction/sequence/kind/payload, rejects namespace3 publications,
checks every actual rejection/trap/reap/queue observation, and requires normal
notebook stroke acknowledgements before and after client reaping. The ordinary
raw two-stroke fixture must enter the real pen FIFO, become exactly50 fresh
indexed raw samples, and produce completed controller-visible black writing.
Physical sector addresses may move under legitimate checkpointing; document
bytes and object identity may not change. The checker never supplies recovery
results to the guest. Literal observer unit tests exercise failure decisions and
are not target execution evidence. A fresh linked QEMU run is required.

Observation tags: `42f` client grants/identity; `430` actual reply cases; `432`
planned load/address/time; `433` queue phase/handle/base/outstanding; `434`
phase/purpose/mappings/free frames; `435` erroneous returned load; `436`
phase/actual guest ticks/outstanding kind/reserved0. Existing
`d4`, `f4`, `f6`, `421` retain their real trap/reaping/document ACK meanings.
