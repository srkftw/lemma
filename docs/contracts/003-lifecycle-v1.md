<!--
# Task 003 lifecycle observation contract v1

The maintained Task/Scheduler policies remove a faulted task from lookup and
execution before reclaiming it. A verified U architectural fault produces
code44; an invariant violation remains kernel fatal50. Trap return first
restores the stable kernel SATP and scheduler stack, clears the current task,
and then runs the checked reaper. Address-space teardown checks mapping pins,
flushes translations and frees complete owned page sets. Registers, BSS and
stacks initialize afresh from a validated image; a restart allocates a new
generation and monotonic private owner. Current profiles contain no inherited
capability grants; future grants require their own explicit boot policy.

The separate `tasks-fault-development` configuration has the three F images
and one separately linked Fault image. Only that image has the closed typed
supervisor-CSR startup. The normal configurations have no CSR exception or
physical observation commands. Compiler.Test, peer development roots and
undeclared helpers remain forbidden even when an imported module is unused.

The Fault user first checks zero data/BSS/stack, writes fresh nonce-derived
secrets through user memory primitives, and emits e8(id,nonce,initialBSS,
initialStack). Successful return executes the audited CSR instruction in U.
The checker requires its actual cause2, exact PC/opcode and U status, then
fault return5, code44 and complete inactive reclamation. Ordinary status exit
is insufficient evidence. The same VM and live Busy peer survive every cycle.

Development FE records contain a checked live descriptor ID, physical byte
address of VA0x20000, physical byte address of VA0x3fffc020, and private owner.
The latter address includes offset32. Observations occur before first user
dispatch. Actual same physical data/stack reuse must accompany fresh owners,
identities, distinct secrets and zero checks; allocation algorithm assumptions
do not certify reuse.

Development command0x34(image,nonce,0,0) applies real quota pressure to the
trusted next owner. It holds17-ceil(textBytes/4096) actual data-purpose frames,
stores their generation handles in a separately owned scratch page, and checks
first/last sentinels before and after ordinary loader construction. That
construction fails late with quota38. No failed task is published; the owner
advances once, free-slot count is unchanged, and every partial loader page is
reclaimed. Held sentinels and generations remain valid. All held frames and
scratch are released before returning38.

E9(image,38,beforeHolding,afterFailedLoad) records measured accounting;
afterFailedLoad equals beforeHolding-heldCount-1. EA(owner,heldCount,
ownedAfterFailedLoad,afterRelease) requires ownedAfterFailedLoad=heldCount and
afterRelease=beforeHolding. F7 acknowledges command0x34 with38/value0. These
are quarantined trusted diagnostic operations, not user-selected owners,
quotas or simulated allocator results. Unexpected success is cleaned and then
fatal; unexpected status or accounting never passes the fixture.

The host observer is bounded and fail-closed. It retains complete raw input,
output and stderr, exact source/image/runner hashes and live-kill/reap evidence.
Its arithmetic reference and malformed-evidence tests are host tests; actual
runtime acceptance remains a separately recorded observation, not a compiler
correctness or physical-board proof.

-->
