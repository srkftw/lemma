<!--
# Same-Action IPC polling base, version1

`lemma-ipc-poll-borrow-v1` preserves the IPC-v1 ABI, metadata, completion,
transaction ordering and error precedence. It removes only a second complete
address-space descriptor validation during a single nonpreemptible Supervisor
poll. It adds no persistent cached authority or borrowed User pointer.

The public `IPCStorage.pending` establishes a fresh `AddressSpace.base`, preserves
error80, and invokes `pendingAt`. The public `IPC.poll` establishes a fresh base,
preserves its fatal255 result, and invokes `pollAt`. A pending-only or public-poll
reachable closure is valid independently of Task polling.

`Task.pollIPCStep` freshly reads state, managed flag and descriptor. It performs
`lookupRecord`, then a complete fresh `AddressSpace.base` of that same descriptor,
checks the returned row against the current row, and reads the wait epoch and
transaction. Only those two checked readonly reads may occur before `pollAt`.
No mutation, schedule or suspension occurs between validation and the helper.
`pollAt` calls `pendingAt`; every IPC magic/version/self/state/next/transaction/
operation/endpoint field remains a fresh checked read. Hardware time, readiness,
completion precedence and the complete blocked-task completion tail are unchanged.

The strict preIR auditor independently checks exact role, signatures, effects,
fresh descriptor/base arguments, row equality, error gates, readonly prefix and
all helper callers. Five complete bodies are pinned after rebinding emitted
callees to genuine source identities. The Task caller authority is added only
when that complete borrowed path is actually reachable and qualified. The
public wrappers alone grant no Task lookup or scheduling authority. Helpers
cannot be called from User or arbitrary Kernel source.

The independent finite-RAM fixture captures the prior ordinary Task source and
calls the actual maintained private callback. It checks exact status/value,
whole memory and the ordered request trace, with only the redundant complete
base-validation trace removed. Read/write/time failures, malformed directories,
bank duplicates, metadata and task mutations are covered. These component
checks establish neither RTL timing nor complete cold boot acceptance.

-->
