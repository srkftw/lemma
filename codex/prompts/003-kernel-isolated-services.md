<!--
# Lemma Task 003 — A real supervisor kernel and isolated services

## Mission: build the software the device will keep

Continue Lemma from the working Task 002 machine foundation. Build its first reusable operating-system nucleus, not another diagnostic-only image or a larger catalogue of tests.

The primary finish line is a freestanding RV64 system that boots its own supervisor kernel, allocates and owns physical pages, loads separately compiled user programs into distinct Sv39 address spaces, preempts them with real timer interrupts, handles their syscalls, and connects them through capability-checked IPC. Deliver a real user-space buffer service and a client that create, write, read, and destroy buffers through that IPC. A faulty or non-yielding third program must not stop those services or gain their authority.

This is infrastructure that Lemma's eventual notebook, storage service, verifier, and tutor can use. Put the implementation in maintained kernel, platform, user-library, and service modules. Tests must exercise those modules; they must not contain the only working implementations.

The operator has allocated one 9–10-hour execution window. Treat that as a resource budget, not a guarantee, a reason to idle, or a mandate to claim completion. Spend most of it implementing and debugging the connected system. Reserve the final portion for cumulative verification, commits, and publication. If execution is cut short, leave the highest verified prefix and an exact resume point. Do not stop voluntarily after merely writing the plan or finishing the baseline.

Proceed autonomously through the gates below. Implement a gate, run its targeted tests, inspect the real result, fix failures, and then move forward. Keep dependent work blocked until its prerequisite actually works. Do not wait for user approval between passing gates.

## 0. Checkout, history, and scope authority

Expected checkout: `/home/sreekumaar/Downloads/lemma`.
Expected repository: `srkftw/lemma`.
Leave `/home/sreekumaar/Downloads/USGCE` untouched.

Known Task 002 report-bearing revision:
`7701fa67e93da3071da76660f78b5d1a78d09778`.
Known Task 002 implementation revision:
`09c47ba24577da87390f4c693237fe71ab67c965`.

These are reference identities, not reset targets. Inspect current local changes, remotes, branches, PR status, and ancestry. If Task 002 is now merged, use the updated `main` containing it. Otherwise branch from its current verified implementation, retaining the stack relationship. An unmerged predecessor is not a reason to abandon development or use the starter-only `main`.

Create or resume `task/003-kernel-isolated-services`. Preserve relevant local changes and isolate unrelated work without deleting, silently stashing, force-pushing, or rewriting history. Do not perform the previously requested merges as a side effect of this implementation assignment. Publish this work as its own reviewable change.

Read `AGENTS.md`, the architecture and contracts, Task 002's implementation report, the latest session state, and the relevant backlog. Inspect the frontend, Action IR, CFG lowering, memory model, trap/timer primitives, monitor, and current build/export pipeline. Read enough of the implementation to extend it correctly; do not spend the first half of the session rereading historical logs.

Save this assignment at `codex/prompts/003-kernel-isolated-services.md`. This task explicitly authorizes the supervisor, allocator, task, syscall, scheduler, capability, IPC, and user-service work below. Update task-specific instructions accordingly without weakening permanent Lean/RISC-V/LLVM constraints.

## 1. Permanent architectural boundaries

- Maintain the genuine path from elaborated Lean declarations through checked Core0 and LLVM to RV64 code. Project compiler logic, target policy, algorithms, and service implementations remain Lean-authored.
- No Linux guest, upstream Lean target runtime, OpenSBI default, hosted executable disguised as the guest, target C/C++/Rust/Zig, foreign allocator, or hidden runtime stubs.
- Narrow structured Lean-generated instructions are allowed for boot, CSR access, fences, privilege transitions, trap entry/exit, context restoration, and syscall entry. Do not implement the kernel algorithmically in generated assembly or hand-constructed LLVM and then call it Lean software.
- Keep the existing integer target profile and single hart. Do not silently add floating point, vectors, compressed instructions, atomics, multiprocessor support, or a new compiler backend. Explicitly audit any required machine-profile addition.
- Host shell/Python/Nix may build, launch, inspect, package, and test. The host must not allocate guest pages, select runnable tasks, adjudicate capabilities, perform guest IPC, or implement buffer-service operations on the guest's behalf.
- Preserve the old Core0 profiles and Task 001/002 checks. Introduce a small, versioned kernel/user execution boundary instead of repeatedly cloning the compiler for each new subsystem.
- No `sorry`, `admit`, additional axioms, or `native_decide` used to certify trusted properties. Limited actual lemmas are useful; full formal verification is not a precondition to implementing this milestone.
- No managed Lean object heap, garbage collection/reference-counting runtime, arbitrary Lean application support, general filesystem, networking, tutor, display integration, or physical-board port in the required scope. Page allocation and a small freestanding user arena are not the managed runtime.

Security claims must be exact. This task aims at architectural U-mode memory/privilege isolation and kernel-enforced authority on the pinned VM. It does not establish security against a compromised kernel, malicious hardware, DMA, speculative side channels, or a proof of whole-system correctness.

## 2. What counts as significant completion

All of the following must work together for the full milestone:

1. A Lean-authored M-mode bootstrap transfers into the real S-mode kernel without external firmware doing its work.
2. The kernel creates and owns page tables and task memory at runtime.
3. At least three separately instantiated U-mode tasks have separate stacks and address spaces; at least two use the same virtual data address backed by different physical frames.
4. Actual hardware-timer delivery preempts a task that does not voluntarily yield.
5. Syscalls validate user arguments and return normally, block/resume, or terminate the caller without confusing those outcomes.
6. Kernel-held capabilities authorize endpoint and management operations. User-provided integers do not determine rights or sender identity.
7. A U-mode buffer server services at least two clients through the same reusable IPC path, enforcing buffer ownership and quotas.
8. A controlled task fault terminates that task, wakes affected peers appropriately, and reclaims its resources without destroying unrelated services.
9. A continuously usable guest shell or command client exposes this functionality. It is not capped at an arbitrary 256-command session inherited from a test harness.
10. The exact release-shaped image and its constituent modules are built, audited, tested, and published with bounded evidence.

A list of empty APIs, state-machine models without target execution, host-simulated scheduling, or success banners is not this deliverable.

## 3. Implementation shape and resource priorities

Prefer a compact hierarchy along these lines, adapting names to existing conventions:

```text
Lemma/Platform/RiscV/     boot, CSR boundary, page-table encoding, trap entry/return
Lemma/Platform/LemmaVM/   the pinned board/device adapter and image layout
Lemma/Kernel/Memory/     page ownership, frame allocator, address spaces, user copy
Lemma/Kernel/            task table, syscalls, scheduling, capabilities, endpoints
Lemma/User/              startup, syscall bindings, buffers, IPC clients, event loop
Lemma/Services/Buffer/   reusable buffer protocol and independently linked server
Lemma/Applications/     shell/control client and a real buffer-service client
```

Do not build empty directories merely to match this tree. Deliver connected implementations. Normal code under those directories must not import `examples/`, `tests/`, `Lemma.Compiler.Test`, or mutation modules. Production algorithms currently trapped in examples should be moved or factored once, with legacy examples becoming clients; do not copy them into a competing implementation.

Choose bounded, configurable capacities: for example eight task slots, a page pool sized from the reserved RAM map, 32 capabilities per task, and small bounded message queues. These are configurable capacity choices, not permission to special-case task IDs, request numbers, or fixed demo addresses. A full table returns a defined error and leaves state consistent.

Use fixed-layout records or scalar field accessors over owned storage where the current compiler requires them. Do not port a general object runtime merely to obtain a task record. Keep layout descriptions authoritative in one place and derive offsets/serialization where practical. Extend Core0 only to unblock an actual kernel operation needed in the next gate.

The target image must be runnable independently of the acceptance script. Provide real build/run entry points, a boot package, a serial interface, and a small user-program build path. A test runner is a consumer of this system, not its operating environment.

Maintain `docs/plan/003-session-state.md` and a compact gate ledger. Record the branch, tested source identity, highest passing gate, actual failure, and next executable command. Update at gate boundaries and before context compaction, not after every tiny edit. Resume from these records without restarting completed gates.

Use focused tests while developing and cumulative checks at integration checkpoints. Reuse the existing fault/report framework. Do not spend the session adding hundreds of repetitive validator tests, new report formats, or duplicate audit engines. Implement the feature and the smallest tests that genuinely distinguish correct from broken behavior.

If parallel workers are available, use them for bounded independent work such as the user ABI library, buffer-service protocol, or adversarial tests after their interfaces are established. Do not presume those tools exist. Integrate in one place and rerun actual target tests.

# Gate A — Establish a usable base and build separation

Run the existing scaffold and host suites in the pinned Nix environment and reproduce a real Task 002 monitor run. Use the existing script help to obtain the right focused invocation. The cumulative Task 002 acceptance remains required before final publication, but do not run its entire 482-boot campaign after every file change.

The existing commands include:

```sh
nix develop --no-write-lock-file --command lake build
nix develop --no-write-lock-file --command python3 scripts/check_scaffold.py
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/scaffold -v
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/core0 -v
nix develop --no-write-lock-file --command python3 -m unittest discover -s tests/foundation -v
```

Add a separate normal kernel build target. Distinguish M-mode firmware glue, S-mode kernel, U-mode images, and intentionally adversarial test images in manifests and symbol provenance. They may share one boot container, but their privilege, linking, entry points, and memory ranges must remain explicit.

Do not link service implementations into the kernel and then merely label calls to them as IPC. Implement a way to build at least one user image independently, at a declared virtual layout. A small build-generated segment descriptor is sufficient; a general ELF loader is not necessary. The target must validate descriptors and perform the actual allocation, copying, zeroing, mapping, and start operation later.

EXPLICIT EXIT: The previous system still boots, a distinct kernel image is generated from the new maintained entry point, and the build can identify separately compiled user code without importing test-only runtime behavior.

# Gate B — Real page ownership and kernel storage

Implement the physical frame allocator and fixed-capacity kernel object storage used by all later gates. Do not leave allocations as host-filled addresses or counters that never control real memory.

Start with 4 KiB frames and a deterministic bitmap/free-list scheme. Reserve the firmware, kernel image, boot package, DTB/boot information, stacks, metadata, guard intervals, and MMIO explicitly. Derive the available pool from the pinned machine contract and verify it against boot information; never presume all advertised RAM is free.

Maintain per-frame ownership and purpose: free, kernel metadata, page table, task image/data/stack, or another admitted role. Allocation must zero a page before granting it to a different task. Freeing requires the correct live owner and no remaining installed mappings. Prevent double free, out-of-pool free, freeing reserved pages, and reusing pages before address-translation invalidation is complete.

Kernel algorithms need actual mutable storage. Add a narrowly authorized kernel memory primitive/interface for this purpose, with explicit effects, audited address bounds, and a clear trusted-code boundary. Do not grant user programs the same physical-memory primitive. Keep policy and allocator loops in compiled Lean rather than hiding them in code-generation helpers.

Track task quotas and global remaining capacity. Multi-page construction must unwind cleanly after a partial allocation failure. Keep generation-tagged IDs where object-slot reuse would otherwise alias stale references. Define generation exhaustion rather than wrapping silently.

Test allocation, write/read, release, zero-on-reuse, exhaustion/recovery, wrong-owner and double-free failures, and reserved-region denial on the actual guest. Add one useful model invariant connecting allocated/free ownership to non-overlap; distinguish its proof from emitted-code correctness.

EXPLICIT EXIT: The guest allocator supplies and reclaims real frames, preserves its accounting, never hands a reserved or already-owned frame to another owner, and is the allocator used by subsequent page-table/task construction.

# Gate C — Enter supervisor mode with our own machine services

Build a minimal M-mode substrate and transfer into the S-mode kernel. Keep the already working M-mode monitor as a separate regression target, not the new kernel's runtime dependency.

Specify initial privilege state, trap delegation, PMP policy, timer routing, boot arguments, stack locations, and which firmware calls S-mode is permitted to make. Implement exactly the bridge needed by this kernel, not a whole SBI implementation. Do not claim SBI compatibility for a private call protocol.

Prefer reusing the verified machine timer through a small M-mode forwarding path. A timer interrupt may latch a supervisor notification and return; S-mode acknowledges it and requests the next deadline through the declared interface. Distinguish M timer interrupts, forwarded notifications, elapsed deadlines, and scheduler decisions. Do not fake a supervisor interrupt by directly calling its handler. An alternative timer path is acceptable only when supported and verified in the pinned VM, without an unexamined extension dependency.

Machine handlers must preserve interrupted S/U state, use reserved M-mode storage, and not dereference arbitrary S/U pointers. Validate the origin and number of firmware calls. Keep machine interrupt work independent of user mappings. Establish and read back the PMP configuration that permits S-mode's required accesses; do not assume S-mode can access memory with whatever reset PMP state happens to exist.

Initially keep S-mode kernel execution nonpreemptible. Machine timer interrupts may still occur, but scheduling happens at controlled supervisor return points. Keep this distinction explicit: disabling supervisor interrupts is not disabling all machine interrupts.

EXPLICIT EXIT: Actual instruction execution reaches S-mode, normal kernel code runs there, its firmware calls are bounded, timer notifications reach the expected level, and invalid privilege/call transitions fail with recorded diagnostics. A printed string saying “S-mode” is insufficient evidence.

# Gate D — Sv39 address spaces and one real user process

Implement reusable address-space creation, map, lookup, unmap, and destroy operations using Gate B's allocator. Begin with 4 KiB leaf pages, ASID zero, and conservative full translation invalidation; do not add huge pages or ASID allocation yet.

Audit exact `satp`, PTE, `sfence.vma`, privilege, and instruction-fetch synchronization requirements against the pinned implementation and applicable specifications. Define supported virtual/physical ranges, canonical-address validation, reserved bits, access/dirty-bit policy, and allowed leaf permissions. Reject unsupported PTE shapes rather than accidentally treating them as valid mappings.

Keep user text read/execute, user data/stack read/write and non-executable, kernel pages supervisor-only, and guard pages unmapped. Do not make a convenient U-accessible identity mapping of all RAM. Do not grant U-mode direct device mappings or enable DMA-capable devices in this milestone. A supervisor-only direct map is acceptable, but it must not silently provide a writable alias to executable pages if you claim strict W^X.

Maintain a small stable kernel virtual layout mapped into each task address space as supervisor-only. Ensure the trap vector and entry storage remain accessible while any user page table is active. Correctly order page-table writes, address-space installation, invalidation, and frame reuse. Flush instruction state where copied executable bytes require it.

Implement a real loader for the bounded boot-image format. Validate entry alignment and containment, segment sizes and file ranges, integer overflow, overlap, user virtual limits, permission combinations, and memory budgets. Copy initialized bytes and zero remaining data/BSS on the guest. Reject malformed packages without leaking allocated resources. User code must not execute out of a host-supplied privileged buffer.

Enter U-mode through controlled restoration of a sanitized context. User code uses its own stack, not the kernel stack. Prove isolation behavior with actual attempted loads/stores/instruction fetches, including kernel memory, another task's private frame, read-only text, non-executable data, and guard pages. The failure must be a real architectural fault where applicable—not solely a cooperative source-level guard.

EXPLICIT EXIT: A separately linked Lean-authored U-mode image executes under Sv39, can access its own pages, cannot access the denied mappings, and its pages can be torn down without damaging the supervisor.

# Gate E — A reusable user ABI and safe syscall boundary

Implement `Lemma.User` bindings and the corresponding kernel syscall dispatcher. These are the API future user services will link against.

Define syscall numbers, register arguments, bounded result/error representation, clobbers, pointer/length conventions, and ABI version. Do not equate the function-call ABI with a syscall ABI without defining the latter. Initial calls should cover identity, bounded console access, yield, sleep/time, exit, and controlled page allocation/release; add capability and IPC calls through the same interface in later gates.

Build S-mode trap entry and return for user-origin traps. Preserve all interrupted integer state required by the declared profile, not just callee-saved registers. Keep trusted trap frames and kernel stacks inaccessible to U-mode. Distinguish user-origin traps from kernel-origin exceptions before choosing a stack or treating registers as a user frame. Sanitize return privilege/status rather than trusting user-controlled words. Unknown user syscalls return an error; an unexpected kernel fault must not be mislabeled as a harmless user error.

Normal `ecall` sites in actual user programs must work. Do not limit syscalls to the handful of privileged test PCs used by Task 002. Resume according to the declared instruction/ABI profile, rather than incrementing arbitrary fault PCs and hoping execution continues.

Implement `copyFromUser`/`copyToUser` through validated page walks and owned mappings, preferably using the supervisor direct map while keeping SUM clear. Validate every spanned page and requested permission. Check overflow, zero-length policy, noncanonical addresses, mixed valid/invalid pages, supervisor-only pages, and maximum copy sizes. Do not validate only the first byte. Prevent mappings from changing while a copy is in progress under the single-hart policy.

For bounded operations promising all-or-nothing effects, prevalidate before mutating or consuming a message. Do not partially overwrite a destination and then return a misleading ordinary error. Never retain a borrowed user pointer across a blocking syscall; copy into owned storage or reconstruct/validate it on wake.

EXPLICIT EXIT: Real user programs call through the user library into the supervisor, receive correct results, cannot use malformed pointers to read/write kernel memory, and continue after recoverable errors. Kernel and user execution are distinguished by actual traps and mappings, not names.

# Gate F — Real preemptive tasks, not cooperative callbacks

Implement the task control block, runnable queue, blocked state, task exit/fault state, per-task kernel stack, saved user context, and an idle path. Use allocated kernel storage and generation-tagged task identities. Multiple tasks must be instances of reusable loaders and task APIs, not branches in one large monitor program.

Begin with equal-priority round-robin and a bounded quantum. A simple correct scheduling policy is the intended reusable foundation; priority classes, EDF, multicore, and sophisticated fairness are not required tonight.

Connect the timer to rescheduling. A non-yielding user task must be interrupted and another runnable task selected. Perform the real register, page-table, stack/context, and control transfer; changing `currentTask` in a table is not switching execution. Preserve context across both involuntary preemption and syscalls that block or yield.

Support sleep deadlines and wakeups with a bounded table/queue. Avoid lost wakeups when checking a condition and blocking. Define how pending ticks are consumed after a nonpreemptible kernel section, and avoid incrementing “hardware interrupt” counts for events that were synthesized or coalesced. Handle no-runnable-task idle safely, including the interrupt-enable/WFI race under the selected model.

Implement a continuously usable entry/event loop without recursive stack growth or a silent fixed lifetime budget. A closed, compiler-recognized nonreturning loop over a statically resolved Lean step function is acceptable. Document its possibly nonterminating semantics; do not incorrectly promise LLVM that it always returns. Individual kernel operations and critical sections remain bounded.

Use at least three tasks: two doing different computations and one CPU-bound task that does not yield. Include real sentinel/context tests, private-memory values at identical virtual addresses, sleep/wakeup, task exit, and alternating address-space switches. Instrument switches with task generation and cause, but never use test task names to influence scheduling. Disabling the timer must cause the noncooperative progress test to fail for missing preemption.

EXPLICIT EXIT: Independently executing U-mode tasks make progress under timer-driven scheduling, retain distinct memory and register state, block/wake correctly, and do not require voluntary yield for system responsiveness.

# Gate G — Resource lifecycle and fault containment

Make task failure an ordinary lifecycle event handled by compiled kernel code, not a reason to restart QEMU.

On a user fault, capture the task ID/generation, cause, faulting PC, and permitted diagnostic fields; remove the task from execution; reclaim owned mappings and pages in the safe order; and continue another task. On a kernel invariant failure, preserve a distinct fatal outcome.

Do not reclaim a task's active kernel stack while still executing on it. Move cleanup onto a scheduler/reaper stack or use another explicit deferred-reclamation mechanism. Do not free page tables still installed in `satp`. Flush stale translations before assigning the same frame to a new owner.

Support bounded restart from an existing validated image descriptor, under trusted boot/supervisor authority. Reinitialize registers, BSS, stacks, owned pages, and inherited grants according to a documented policy. A restarted task receives a new generation, not the identity of the previous instance.

Test repeated create/exit/fault/restart cycles, quota exhaustion, partially constructed task failure, zeroed page reuse between owners, and resource counts returning to the baseline. Task-fault tests must execute real faulting user instructions. Keep the adversarial generator quarantined from production images.

EXPLICIT EXIT: A task can fail and be replaced repeatedly while unrelated user work continues, with no growing leak, stale identity, surviving private data in newly granted pages, or use of reclaimed execution state.

# Gate H — Kernel-enforced capability tables

Implement capability lookup, object typing, rights checks, controlled duplication/attenuation, close, and a bounded revocation scheme. Start with endpoints, console access, and management operations actually needed here.

A handle is an index/generation into the caller's kernel-held table, not an object address, user-supplied permission mask, or a global object ID that grants access merely because it is known. Handles need not be cryptographically secret: the authority comes from the checked table belonging to the caller. The kernel derives caller identity from the running task. Object liveness and generation must also be checked so a dead object cannot be confused with a replacement in the same slot.

Grant initial authority through a reviewed boot policy. Do not give every task the power to create/manage arbitrary tasks or endpoints just to make the examples easy. The normal client gets only the grants it needs. Read-only or send-only grants must actually lack broader operations.

Use one comprehensible revocation design. For example, derived entries may share a revocation-root generation so invalidating that root invalidates descendants. Merely deleting one handle while its duplicates retain authority is “close,” not global revocation. State the chosen semantics and implement them, including bounded generation exhaustion. Do not build a general unbounded capability graph.

Reserve destination slots before publishing a transferred/duplicated capability. On failure, leave the source and object accounting unchanged. Reference counting here means kernel-object lifetime bookkeeping, not importing the general Lean runtime.

Test forged handles, cross-task numeric handle reuse, stale generations, wrong object type, insufficient rights, attenuation, close versus revoke, and full-table rollback through real U-mode syscalls. Hardware isolation must stop users from editing the capability tables directly. Add one directly relevant monotonicity or lookup invariant where tractable.

EXPLICIT EXIT: Actual kernel checks—not the user's choice to behave—determine whether operations are authorized, and capability lifecycle survives task/object reuse.

# Gate I — Blocking IPC and request/reply

Implement bounded message endpoints using the task scheduler and capability tables. The normal server and client in the next gate must use this exact path.

Start with copied messages rather than shared memory or zero-copy grants. Use a fixed header, bounded payload, request ID, and clear status/result contract. Set explicit message/queue capacities. The receiver sees a kernel-authenticated sender identity or equivalent reply authority, not a sender PID copied from the payload.

Provide nonblocking send/receive and a bounded blocking operation with a deadline. A synchronous call/reply interface is valuable: a one-shot reply token bound to the caller generation and request prevents replay or replying to a different waiting caller. Unsupported modes must fail explicitly, not fall back to a busy loop.

Specify the linearization point for enqueue, dequeue, reply, cancellation, and timeout. For this single hart, short nonpreemptible transitions are acceptable. Prevent lost wakeups, double completion, duplicated dequeue, stale timer wakeups, and delivery to a replacement task. Recheck user destinations safely before delivery. An invalid receive buffer must not silently destroy a queued message unless that destructive behavior is explicitly designed and tested.

On peer death or endpoint revocation/destruction, complete blocked operations with a distinct error and release pending kernel-owned storage. Define what happens when reply and timeout become pending together. Do not claim a timed-out request was never processed if the receiver already accepted it; at-most-once completion is not exactly-once application execution.

Exercise two clients and a server exchanging different runtime payloads, queue-full backpressure, empty receive, timeout, invalid memory, unauthorized send/receive, cancellation, caller death, server death, revoke while blocked, and duplicate replies. Keep no borrowed user pointer alive in the kernel's queued message representation.

EXPLICIT EXIT: Separately executing user programs communicate through bounded, authorized, blocking IPC; idle receivers actually sleep; failures wake the right tasks; and unrelated endpoints remain usable.

# Gate J — Deliver the first useful user service and application

Build a real buffer server under `Lemma/Services/Buffer`, a typed client library under `Lemma/User`, and a user-space command client. Their code must be separately compiled and loaded into U-mode address spaces.

The server owns its backing memory and implements create, write-at-offset, read, append, length/status, and destroy. Use explicit lengths and binary-safe bytes, not an ASCII-only fake buffer. Apply per-client quotas, generation-tagged buffer IDs, ownership checks based on the kernel-authenticated caller, and overflow-safe bounds. Define append failure and partial-write semantics; bounded failed operations should not silently corrupt existing data.

The server obtains memory through the real user memory-allocation path. Do not give it a hidden host-created array or let the kernel implement its buffer methods. The kernel should know IPC messages, not Buffer.Create or Buffer.Append semantics. The service must use the shared syscall/IPC library instead of a special privileged entry point.

Handle abandoned client resources explicitly through a bounded lifecycle-notification or lease/session policy. A dead client's buffers are owned by the server, so kernel reclamation of the client's own frames does not automatically release them. Test the chosen cleanup policy without destroying another live client's buffers.

This is intentionally a volatile buffer service: useful for future document/input staging, but NOT durable storage. Its replies must not use “saved to disk,” “durably committed,” or other persistence claims. Treat restart as loss of volatile contents and a new service epoch. A caller must receive a clear error for an old buffer handle rather than read a new object's data by accident.

Expose a normal guest command interface such as:

```text
help
version
ps
mem
buffer create <capacity>
buffer append <handle> <bytes/text>
buffer read <handle> <offset> <length>
buffer destroy <handle>
service restart buffer
```

A bounded binary control protocol is an acceptable alternative, but provide a practical client and readable output. A Unicode mathematical string encoded as UTF-8 can be used as arbitrary bytes; there is no need to implement text layout or recognition.

Do not give the shell unrestricted task-management authority by default. Destructive diagnostic commands need a separate development grant/profile, visibly absent from an ordinary client. Preserve UART input progress while tasks run: use bounded polling integrated with scheduler/timer service initially; a new PLIC driver is not required merely to obtain console input.

Demonstrate two clients using independent buffers, a denial when one tries the other's handle, a CPU-bound competitor being preempted, a faulting client being terminated, and the surviving client reading unchanged content. Then restart the buffer server, observe pending-call failure and the epoch change, reconnect through the declared service-discovery policy, and create a fresh buffer. Do not promise old volatile content survives.

EXPLICIT EXIT: Real user applications use reusable kernel APIs to operate a separate service. Altering the source service algorithm changes the guest result. The same normal image handles fresh input streams after boot; it is not generated around known answers.

# Gate K — Integrate, qualify, and publish the actual software

Build one normal kernel boot package and a separate adversarial-test configuration. The normal package must not contain mutation switches, arbitrary physical-memory probes, special test PC approvals, or host termination shortcuts exposed to ordinary user programs. Development shutdown may exist behind an explicit privileged diagnostic capability.

At O0 and O2, run a mixed session proving allocator use, protected user execution, ordinary syscalls, involuntary preemption, sleep/wakeup, capability enforcement, blocking IPC, buffer operations, and task/service failure recovery. Use independently chosen runtime inputs and retain actual user/kernel observations.

Run targeted architectural attack tests using real U-mode instructions: privileged CSR access, forbidden mapping access, attempted code write/data execution, invalid pointers crossing a page boundary, forged handles, and illegal return-state requests. Compiler rejection alone is not proof of hardware isolation. A failure that kills the entire VM instead of the offending user task does not pass the containment test.

Review the highest-risk boundaries once more: M/S/U routing; trap-stack selection; context and `satp` switching; PTE permissions/invalidation; complete user-range validation; allocation rollback; object generations; blocking wakeups; reply/timeout races; active-stack reclamation; and service-level buffer ownership. Turn any discovered defect into one concise permanent regression.

Audit all constituent image code and metadata. Record which code executes at each privilege level, which machine primitives are admitted there, all objects and helpers, and the reason for each kernel-visible mapping. Do not weaken old audits into a broad “anything named kernel passes.” Scope the test-only binary exceptions precisely.

Run legacy Task 001 and cumulative Task 002 acceptance at final integration. Use the new production image in Task 003 acceptance, not a sibling test implementation. Reuse transactional report generation and stale-evidence protection. Keep a passing result attached to its exact source/configuration; do not carry a PASS flag across an untested code change.

Commit coherent passing increments, then perform final clean-worktree verification without copying prior project outputs. A later evidence-only commit can reference the tested implementation; do not rerun forever to chase an evidence file's own commit hash. Distinguish source tree, implementation commit, report-bearing head, and synthetic PR merge identity.

Add bounded pinned CI for the new image and relevant tests, with retained logs/artifacts and narrow permissions. The build must realize its pinned dependencies rather than assume a warm Nix store. Missing mandatory artifacts must prevent acceptance, even if artifact upload itself merely warns.

Write `docs/evidence/003-kernel-isolated-services.md`, a compact JSON result and full hash inventory. Update the backlog only for demonstrated work and keep the managed runtime and remaining G1/G2/G3 obligations explicit. Update README and agent instructions with build, boot, interaction, verification, and recovery commands that actually exist.

Push normally and open a draft PR against `main` when it contains the base. Otherwise open a clearly identified stacked PR against Task 002. Do not force-push, merge, delete branches, change repository permissions, or launch paid infrastructure. If remote access fails, preserve the local commit and report the precise failure; continue independent local work where possible.

## Priority rules when the session becomes constrained

The main scope is Gates A–K. Do not replace difficult kernel work with easy documentation volume. Keep the service objective in view when deciding compiler extensions. Do not enforce an arbitrary minimum of thousands of tests or tens of thousands of lines; require distinguishing behavioral coverage for the operations actually introduced.

Prioritize in this order: an actual S-mode kernel and isolated user execution; working preemption and lifecycle; capability/IPC enforcement; the connected buffer service; polished diagnostics. If a gate is failing, fix the smallest cause rather than bypassing the boundary or attempting every later subsystem simultaneously.

There are no bonus features to chase before the core works. Do not start block storage, filesystems, persistent journaling, a graphical notebook, or a managed Lean runtime merely because they appear in the long-term plan. Those become much easier to implement on the completed process/service foundation and deserve their own coherent assignment.

If the remaining session budget is insufficient for another dependent gate, finish the current verified increment, run its regression set, commit it, and leave an exact continuation. A failed higher gate must not corrupt the highest passing one or make the report imply that the full operating system is finished.

## Required final handoff

Return:

- Repository, base, branch, full commit, pushed state, PR URL, and actual CI status.
- Gates A–K as passed/failed/blocked/not-run, with the highest complete integration.
- The maintained modules and APIs now usable by future Lemma software.
- What truly executes in M-mode, S-mode, and U-mode; what isolation was tested; and remaining trusted assumptions.
- One actual transcript of two clients using the buffer service while a noncooperative task is preempted and a faulty task is contained, or the exact last completed integration transcript.
- Real test commands and observed results, plus clean-worktree and artifact evidence.
- Proof/model claims separately from execution tests; no whole-compiler or whole-kernel correctness claim.
- Explicitly unimplemented runtime/persistence/physical-device features, and the next concrete construction step.

Do not measure success by added lines, check counts, or new documents. The desired result is operating-system software that Lemma will retain: owned memory, address spaces, tasks, syscalls, scheduling, authority, IPC, and a functioning isolated service.

Start by inspecting the current checkout and implementation. Then build through the gates while their prerequisites pass.

## Primary technical references to pin and consult

These are starting references, not a substitute for the exact repository-pinned sources. Record applicable revisions and resolve differences before encoding architecture assumptions:

- RISC-V machine-level specification: https://docs.riscv.org/reference/isa/v20260120/priv/machine.html
- RISC-V supervisor-level specification: https://docs.riscv.org/reference/isa/v20260120/priv/supervisor.html
- RISC-V ELF psABI: https://riscv-non-isa.github.io/riscv-elf-psabi-doc/
- LLVM 20 language reference: https://releases.llvm.org/20.1.0/docs/LangRef.html
- QEMU RISC-V virt reference: https://www.qemu.org/docs/master/system/riscv/virt.html

The QEMU master documentation is not the exact pinned implementation; use the repository's locked QEMU source/DTB for machine-specific addresses and behavior. Do not upgrade the toolchain just to match a documentation page.
-->
