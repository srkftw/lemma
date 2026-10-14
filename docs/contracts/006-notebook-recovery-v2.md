<!--
# Clocked13 recoverable Notebook failure policy v2

This is an explicitly selected software successor on the unchanged Clocked13
hardware and Kernel6 privilege boundary. The two closed configurations are
`lemmasim-silicon-usb-clocked-retry-bulk-notebook` and
`lemmasim-silicon-usb-clocked-retry-bulk-initialize`. They select the new
`Notebook.mainRecoverableSumsBulk`, `Store.ServerRecovery.mainRecoveryCourse`
and recovery-only kernel dispatcher. Every historical deployment, root body,
durable encoding and captured actor retains its original identity and behavior.
The Store and Notebook use scalar User2; isolated Arithmetic remains User3.

A genuine failed Store mutation pins its exact owned record, length, key,
publication stage, acknowledged sequence and failure ticket. Bounded offline
ink uses the other owned buffer while visible status remains Failed. Only a
fresh idle toolbar Save may use one of three recovery attempts. Exhaustion,
foreign replies, concurrent activity and ambiguity do not discard that source
or fabricate Saved. A recovery control reply reports Pending or an observed
mount epoch/sequence; it is never a document acknowledgement.

The new Kernel6 block operations are5 begin(ticket,epoch),6 take(ticket,epoch)
and7 read the logical guest recovery epoch. Existing dispatchers reject them.
They require the real Store block capability and bind the full task descriptor,
ticket and expected epoch. Ordinary block requests cannot overwrite recovery.
Only a witnessed loss of actual controller configuration during an opaque
request can quarantine it. A new qualified reset event and guest-issued
endpoint0 configuration must precede the new HELLO; host attach alone does not
supply either fact. The driver allows three attempts and ten million timer
ticks per attempt. Its logical guest epoch is distinct from the host connection
epoch recorded by the native recovery adapter.

The driver retains and revalidates the complete original72-byte request or
584-byte WRITE, including fresh owned generation/purpose, header, writer,
sequence, sector, length and CRC. HELLO must name the same writer/capacity and
next sequence equal to the original sequence or its successor. READ requires
the original sequence. It retransmits the exact retained request at the old
opaque sequence. Only a matching independently produced success receipt,
including full WRITE bytes and CRC, resolves quarantine and advances the guest
epoch. USB ACK, HELLO, host attach, pending completion and an error receipt never
release poison or establish durability. Failed/partial peer receipts remain
uncertain; this version does not turn them into successful recovery.

Store controls14 begin and15 status use protocol3, namespace1, object0,
nonzero caller ticket, zero offset/count and exactly64 application bytes. A
reply repeats the stamped request and application identity, observed journal
sequence and an eight-byte epoch. Detail1 is Pending,2 complete,3 failure.
Idempotent begin/status retain the full sender/namespace/ticket binding. The
old Protocol1/2 controls and on-disk format remain unchanged.

The sole Store service starts recovery only in read-only mode3 with no current
operation, staged owner, pending reply, submitted block or active checkpoint.
After actual opaque-frame reconciliation, the real Lean Engine scans through
READs into two additional private pages and the unused private index. No
format, WRITE or BARRIER occurs during that scan. Mode3 remains public throughout
scan and adoption. A failed final READ cannot publish ready/complete. Context
adoption contains no await/IPC; checked memory faults stop the service before
normal settle or ready publication, even if a prefix was copied. Complete valid shadow preflight then issues one actual guest block durability
BARRIER. Pending or failed completion leaves mode3 and the original context.
Only a matching successful barrier permits adoption, cache invalidation and
publication of mode1 with the observed sequence. That sequence alone is not Saved.

Notebook keeps a separate last full-publication ACK floor; Engine context40
alone may reflect an uncertain publication. The remounted sequence must cover
that floor and the retained known sequence. At the exact known sequence it may
start a new ordinary Pending save. At exactly known+1, it first READs every byte
of the retained object, requires every reply's same observed journal sequence,
compares all owned bytes, and requires zero bytes from an additional READ at
the exact retained length. A matching prefix, stale epoch, shorter/longer/different
record or any larger sequence stays Failed. At the exact old sequence a coherent observation may resubmit the genuinely
uncommitted record through the normal Begin/Chunk/Commit chain. At known+1,
barrier-backed complete payload/EOF equality resumes the original retained
record completion exactly once: it does not issue another PUT for that record
or increment its journal sequence. Subsequent page/root stages still use
ordinary new transactions and matching replies. A fully reconciled final root
may complete its original Saved only after that real barrier and complete
identity/byte/length checks; mount or Inspect alone never does so.

Host process reattachment uses the separately versioned
[Native live USB recovery contract](006-usb-live-recovery-v1.md). Its global
command namespace, epoch/binding capture barrier and tape-only private forks
remain load-bearing. It does not implement a journal or guest policy. Partial
writes may persist; failure is never rollback or permission to assert old-medium
equality. Actual reconnect, peer receipt, shadow scan, full publication, offline
ink and independent new-CPU cold recovery require connected observations.

The current Action fixtures and genuine component lowering are separate from
complete LLVM/object/link audits and RV64 execution. Original syntax, fixture,
observer and command failures remain retained. This contract does not certify
full USB timing/MAC/electrical conformance, private live-peer checkpointing,
QEMU microstate migration or physical durability.

Fresh normal/initializer Recovery images at `recovery-whole-pair-a2` passed
ordinary complete artifact audits with equal sealed362 input sets, within the
prospective900-second aggregate (533.012 seconds). The first whole build's
96.125-second Arithmetic registry failure remains retained; only the exact new
configuration pair was added to the existing full implementation identity gate.
The strict schema7 package binds those guest archives and original native64d255
inputs. These results establish build/package authority; connected recovery,
full new Saved and new-CPU cold remain NOT_RUN in this receipt. The later
historical component checker correctly rejected newly added unrelated Course
modules outside its original input inventory; no broad new-file grant was made.
-->
