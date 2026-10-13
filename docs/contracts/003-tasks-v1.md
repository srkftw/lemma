<!--
# Task and scheduling contract v 1

This contract extends the Task 003 syscall/ownership boundary with compiled Lean
task policy. The implementation is in `Task`, `Scheduler`, and the explicit
`Development.TasksEntry` transport. Acceptance requires fresh guest observations;
source elaboration or an object audit alone does not establish scheduling.

The single hart uses eight equal-priority slots in one allocated, zeroed,
supervisor-only owner-1 frame. Each slot occupies 512 bytes. A public task identity
is the generation-tagged, checked address-space descriptor handle, never its
address, slot number, image name, or a user-chosen owner. The private monotonic
owner allocator and reusable loader construct each task. State publication is
last; a construction failure abandons the reserved slot only after loader
rollback. Public lookup excludes dying tasks before reclamation. Reusing a slot
does not reuse its old public identity.

States are free 0, building 1, runnable 2, running 3, sleeping 4, blocked 5, and dying 6.
The blocked state is reserved for the later IPC contract; this gate does not
claim IPC. Selection scans at most eight slots from the rotating cursor. Image
index, name, and launch argument do not affect selection. The perpetual entry
is a compiler-recognized `Action.loop`; each table scan and kernel operation is
bounded. The loop has no fixed guest lifetime and does not grow a recursive
stack. Unsupported or corrupt state is a distinct kernel invariant failure.

Each task has an owned adjacent pair of 4 KiB kernel trap-stack frames and an
owned two-page user stack. Context capture validates the current descriptor,
generation, stack ownership/purpose/pins/adjacency, exact trap-frame address,
origin/status and translation before reading user frame contents. It copies
all 36 eight-byte context words to descriptor-owned supervisor storage. Selection
fixes x 0, U return privilege/status, translation and trap-stack authority while
preserving user register values. The fixed supervisor continuation and stable
kernel root are restored before clearing the current task and reaping anything.
The loader rejects active-root destruction and invalidates mappings before
assigning their physical frames to another owner.

The active quantum is 10000 ticks (1 ms at the pinned 10 MHz machine clock).
Idle uses a 1000000-tick (100 ms) maximum with earlier sleeper deadlines. Only real
M timer traps increment the hardware count. They latch SSIP and disable the
expired comparator. Supervisor policy stays nonpreemptible with SIE clear;
pending SSIP preempts U, including immediately after an ordinary bounded
syscall returns. Each scheduling decision consumes a latched notification once
and arms a new relative comparator in M. Notifications arriving during bounded
kernel work can coalesce into that decision; no extra hardware interrupts are
invented. Scheduling statistics count observed U SSIP returns separately.

Yield advances only a validated ordinary ECALL and makes the caller runnable.
Sleep accepts 1000..10000000 ticks, checks addition overflow using actual machine
time, writes its successful result/deadline into the saved context and publishes
sleeping state in the same nonpreemptible transition. A bounded scan makes a
task runnable only when its absolute deadline is due. The earliest sleeper can
shorten the next quantum; an interval below 1000 rounds upward. No-runnable-task
idle arms first, checks actual pending, then uses WFI. Spurious returns repeat
the nonrecursive entry loop. This is a tested selected-machine policy, not a
hard real-time latency guarantee.

An ordinary exit uses its ABI status word as the exit code. Computation results
in development user records are separate from that status. User architectural
faults become dying/code 44; invariant failures remain fatal 50. Cleanup runs on
the stable supervisor boot/reaper stack. Owned task pages are the 17-frame fixed
overhead plus the actual rounded-up text size; the empty development table has
499 of 512 frames available (the stable kernel root and task table retain 13).
The default per-user-owner quota is 32; the descriptor itself belongs to owner 1.

Compute runs eight rounds of32×4096 bounded scalar steps so live register
values can be observed across actual arithmetic-loop preemption.

The development package contains independently linked Compute, Sleeper and
Busy images. Their registry IDs are 1..3 and loader indices 0..2. Each has its own
ELF, source closure, symbols, text/data, and address space. Busy's genuine
reachable source contains a nonreturning loop and no syscall. Startup still
contains the ordinary exit boundary, which that loop does not reach.

The development-only control protocol is five little-endian unsigned 64 words.
One initial `0x 30` packet supplies the three fresh launch arguments. Subsequent
polling consumes at most 40 bytes per scheduling step and preserves partial
packets. `0x 31` queries one live task or all, `0x 32` requests trusted termination
(diagnostic cause 0x 100), and `0x 33` creates an instance of a validated registry
image. Unused fields must be zero. Query and termination of stale/dying handles
return 74, invalid image returns 81, full table returns 38, malformed arguments
return 16, and unsupported control returns 17. These are supervisor development
commands, not grants available to user programs. K 1 records are exact 88-byte
frames; the host controller accounts for their actual raw bytes and kills and
reaps the continuous guest after its finite observation protocol.

-->
