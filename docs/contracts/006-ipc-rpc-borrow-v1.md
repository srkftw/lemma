<!--
# Same-Action Receive/Reply descriptor reuse, version 1

`lemma-ipc-rpc-base-reuse/1` preserves IPC-v1 packet limits, copied bytes,
transactions, one-use reply authority and error precedence. The trusted
`IPC.dispatchWithLimit` uses `receiveWithLimit` and the new `replyLocal` path.
Historical public `receive`, `reply` and `dispatch` retain their original
bodies. There is no new User pointer, cached authority, heap or syscall ABI.

Each new borrowed base comes from a successful full `idle` or
`checkedTransaction` validation in that same nonpreemptible Supervisor Action.
The descriptor identity, root, layout, leaf registry, frame generations,
ownership and pins read by `AddressSpace.base` remain immutable through this
Action. No mapping, frame allocation/free, descriptor replacement, task switch
or suspension may intervene. No alias survives the call. The single hart runs
no other User task during the Action. Interrupt handlers do not change these
protected fields, and admitted controller DMA buffers cannot alias them.

Reply capability grants and revocation may change their own disjoint capability
rows and object/queue state. They do not change the protected address-space
base closure. Their original complete capability/object checks still execute;
no grant, ownership or generation result is reused. `pendingAt` re-reads every
live transaction field. Each UserCopy preflights the owned scratch handle and
both user-page permissions afresh. Its existing aligned-word and byte-tail
paths are unchanged. Zero-before-publication, pinning, quotas, expired-head
withdrawal, namespace authority, partial-copy failures and cleanup are preserved.

The closed pre-LLVM observer qualifies sixteen actual emitted function bodies,
their signatures/effects, all helper callers, and each base's exact derivation
from the current successful metadata result. The older CallBegin guard admits
these additional callers only after that full guard passes. Unknown callers,
changed effects, stale metadata, wrong descriptors and missing functions reject.

The finite RAM fixture compares actual maintained old/new Actions for both
512 and 8192 frame profiles. Whole memory, results and the ordered remaining
request/status/byte trace must match. Only identical successful duplicate
`AddressSpace.base` read subsequences may be projected away. Faults at every
distinct reached address retain their first applicable failure and prior writes.
This fixture models stable protected RAM: it does not establish equivalence for
transient errors on a later duplicate read, asynchronous descriptor mutation or
unimplemented ECC. Those states are not admitted by this optimization contract.

In the 8192-frame fixture, a 256-byte call packet and 128-byte reply reduce
Receive requests 3185 to 2711 and Reply requests 3347 to 3031. These are host
observations of Lean Actions, not RTL cycles, fast-backend timing parity or a
completed cold course load. The original 100-million-cycle cold Load failures
remain failures. The private 2-million-cycle retained-boundary diagnostic is a
PC sample distribution only: Frames/AddressSpace samples may also be transitive
copy work, so direct copy-function counts do not prove causal dominance.

Run the focused genuine compilation and exact emitted-corpus guards with:

```sh
nix develop --no-write-lock-file --command python3 scripts/check_ipc_rpc_borrow.py \
  --output-dir build/kernel/unused-ipc-rpc
python3 scripts/check_ipc_rpc_guards.py \
  --component build/kernel/unused-ipc-rpc/component/rpc \
  --output build/kernel/unused-ipc-rpc/guards.json
```

The first command takes `build/task006-lake.lock`, seals all original consumed
inputs and bounds the Action fixture to 240 seconds, other commands to 120
seconds and the complete component campaign to 600 seconds. Whole guest audits
and actual cold-load target/host measurements remain separate requirements.
-->
