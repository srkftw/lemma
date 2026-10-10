# Task 003 kernel and isolated services

Current accepted prefix: Gates A–J. The fresh J exit was observed at
`d5bff55786b52daba9857b46edf617397bb8cb78`, tree
`b3a713087ff6b1370a90635e3729e04e3f417b22`: four clean service profiles
and both canonical append source negatives passed full independent validation.
The original inner byte-reference FAILs remain retained. Gate K implementation
is in progress; architectural and complete final-source qualification remain
outstanding. No Task003 push, PR, actual CI or merge has occurred.

The following A–E paragraph is a historical checkpoint; the gate ledger and
session state carry the later source-bound I and J observations.

Fresh clean A–E acceptance passed at O0 and O2:58host tests,20images,24checker
reports,28QEMU sessions and6fresh syscall corpora, in437.64s. All images were
rebuilt from the committed source without copied project outputs. Raw captures,
image/audit/provenance hashes and unchanged clean source were independently
checked.26live guests were explicitly killed and reaped; the2machine-origin
negatives naturally exited with fatal48. All PIDs were absent and stderr empty.

The actual system enters S through its own M substrate, constructs owned Sv39
address spaces, runs separately linked U code, contains architectural user
faults, and implements ABI-v1 identity, console, yield, hardware sleep/time,
exit and bounded page allocation/release. Complete user ranges are validated
before copies or UART input effects; binary data and real two-page input were
observed. Gate E yield/sleep do not establish scheduling or blocked-task behavior.

The syscall audit first rejected a4144-byte chain on a4096-byte owned trap stack.
The repair owns two contiguous frames with independent generations and validates
both before frame access; it is not an audit-limit-only change. A second actual
guest failed because its valid first short UART read was1byte. Kernel-v0.2 adds
one closed fixedFCR0xc7 initialization, while preserving all earlier profiles
and FCR0x07. Fresh actual crossing reads and binary echo then passed. All earlier
failed reports remain retained separately.

See [compact result](003-kernel-isolated-services.json) and
[gate ledger](../plan/003-gates.json). The complete ignored inventory is
`build/kernel/gateE/E-clean-hash-inventory.json`; the aggregate report is retained
in the managed E acceptance worktree under `build/kernel/E-clean/result.json`.
The indexed ownership lemmas certify only their mathematical model, separately
from tests and audits. No whole-kernel/compiler correctness or physical-device
claim is made.

## Historical checkpoints

The following sections describe their original snapshots, not the current
implementation or full milestone. Their source-specific evidence is preserved
in the compact JSON.

Current accepted prefix: Gates A, B and C. Higher gates are not run. This is a
freestanding foundation increment, not a completed operating system.

The distinct boot package links genuinely elaborated Lean firmware and kernel
units, a separate user ELF and a data-only image descriptor. The explicit
bootstrap-M stage executes the maintained kernel policy in M-mode; it does not
establish S/U execution. The normal image excludes development imports. The
frames-development image exposes privileged diagnostic transport over the same
maintained Frames and Batch implementations.

Fresh O0/O2 normal and development builds and complete artifact audits passed.
Each development guest returned 2,214 actual records covering ownership,
read/write, zero reuse, stale references, quota/global exhaustion, recovery,
partial quota/global rollback, a mapping bookkeeping guard and generation
retirement. Capacity restored to512 before the final retirement fixture and
was511 afterward. Installed mappings and translation invalidation remain Gate D.
Both normal profiles accepted the pinned DTB and rejected reserved-memory and
unsupported root-cell fixtures. Every finite observation ended with explicit
host kill/reap of the live guest; no timeout or SIGKILL is labelled normal exit.

The shared UART algorithms were moved into maintained ConsoleDevice. Fresh
legacy monitor acceptance passed18 O0/O2 boots,1598 requests,1411 hardware IRQs,
20 synchronous recoveries and192 records. Scaffold18, Core032, foundation439 and
kernel audit13 host tests passed. Exact closure/index compatibility repairs were
reviewed against generated bodies; the prior failed audits and parser boot are
retained separately and are not relabelled.

The three kernel-checked indexed ownership lemmas concern a mathematical model.
They do not certify the allocator's machine code or LLVM. The target/compiler
trust boundary and physical-device unknowns remain explicit.

See [compact result](003-kernel-isolated-services.json), the gate ledger and
session checkpoint. The full source and artifact hash inventory is retained in
ignored `build/kernel/gateAB/hash-inventory.json`, bound by the compact result.
Acceptance currently used dirty source on merged main `ff4045a79a6fda45f9cd8198587357846530a806`;
clean-worktree qualification and Task003 publication remain outstanding.


Gate C passed fresh normal supervisor O0/O2: the private M dispatcher checked
savedMPP=S and actualcause9, returning its origin witness; actual MTIP count
advanced0->1 and the S pending bit changed1->0 after acknowledgement. S kernel
execution remained nonpreemptible, so this records a latched notification, not a
synthetic or delivered S interrupt or scheduling decision. Unknown calls and
invalid deadlines returned17/22 while the bridge remained usable.

Separate machine-origin development O0/O2 images produced actualcause11 at the
audited startup ECALL PC and terminated with rejection48. Their natural finite
negative-protocol exit is distinct from normal guest cleanup. The initial host
transport/trace formatting failures are retained, never relabelled. The readonly
PMP table introduced by LLVM is admitted only by its exact source identity,
values, guarded load, section flags/size and bytes; unknown globals still reject.

Gate D's ordinary execution and address-space API subportion passed at O0 and
O2. The normal image executed three fresh user arguments per VM under Sv39,
observed actual U-origin ECALL cause8 at auditedPC10024 with status200000020,
read each actual private-data result, restored the stable S root, and reclaimed
all17 process frames (483→500). No delegated U interrupt occurred in these
short runs; they establish no scheduling behavior. Separate development runs
exercised the installed table API, complete walks, wrong-owner/purpose/permission
rejections, aliases, stale handles, four corrupt-PTE walk rejections and actual
create/lazy-table quota rollback, restoring512 frames. Those corrupt-PTE tests
are software-walk rejection tests, not architectural U faults.

Full Gate D remains in progress: actual forbidden loads/stores/fetches and CSR
attempts are next. All four VMs remained live until explicit finite host cleanup
and were killed/reaped; raw captures, complete artifact audits and hash inventory
are retained in build/kernel/gateD. This snapshot is dirty on the C commit and
has not received clean-worktree qualification.

### Clean Gate D checkpoint

The committed source `fb524b945f66241ee36a434abe39b3d854c2d9d2` passed fresh
A–D acceptance in a clean managed worktree:45host tests,18O0/O2 images,22reports
and26QEMU sessions. User faults were actual hardware traps with recovery, not
software-only denials. Initialized ABI data and zero BSS were read by U code.
The compact JSON and ignored full hash inventory bind the actual reports.
Highest complete gate is D; syscalls, scheduling, capabilities, IPC, buffer
service and full qualification remain unfinished at this checkpoint.
