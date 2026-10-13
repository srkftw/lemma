<!--
# Isolated exact arithmetic IPC v1

This is an additive scalar Lean software service on `lemma-silicon-dev/0.3.0`.
It does not complete ordinary managed-Lean source lowering, the proof kernel,
the full mathematical document language, or the verifier environment gate.
The existing exact signed-rational/degree-two polynomial domain and overflow
bounds remain those in `006-exact-mathematics-v1.md`; record format v2 and
its durable 1856-byte history/events remain unchanged.

The canonical power notebook and initializer package three separately linked
RV64 images: Store, Notebook and Arithmetic. The kernel boots the notebook
with argument 2 (normal) or 3 (initialize). Historical arguments 0/1 and legacy
two-image deployments retain their meanings. Arithmetic receives only its
EndpointReceive grant and ConsoleWrite grant. Notebook receives a distinct
sixth EndpointCall grant. The arithmetic service has no storage, panel, pen,
power, tutor or other process-memory authority.

`lemma-notebook-arithmetic-v1` names this deployment. Objects table revision 3
has the existing 16×128-byte rows at header offset 256 and unchanged key encoding,
generations, registry and publication order. Header `(version,encodedLimit)`
is exactly `(1,0)`, `(2,5)` or `(3,6)`. Endpoint capacities are 4/5/6; Reply
capacities are 8/8/7. Only the immutable software constructor selects revision 3.
Unknown versions and mismatched limits fail before queue allocation. A full
quota returns ObjectFull 90; malformed table/count/pinning/provenance returns
fatal 255. Existing owner/purpose/generation/zero-before-publication and frame
OOM/quota precedence remain required.

The copied request is 112 bytes: fourteen little-endian UInt64 words in order:
magic `0x3150434854414d4c`, protocol 1, exact checker identity, namespace, page,
submission revision, goal, signed numerator, denominator, three signed
coefficients, budget, request ID. Namespace is 1/2, page 1..64, nonzero revision
and request ID at most `0x7ffffffffffffffe`, goal 1..3, budget 0/8. No pointer,
proof term, capability or host-provided authority enters the packet.

The copied reply is 80 bytes: magic, protocol, checker, namespace, page, revision,
goal, mathematical outcome, budget, request ID. Kernel IPC supplies the actual
sender, receiver-local Reply authority and status. The client requires Reply
kind, exact 144-byte envelope, original request ID, nonzero sender, no remaining
Reply authority, reserved zero and every original identity/environment field.
Success admits outcomes 1..5 only. Declared resource errors 33,38,236..239 require
outcome 0. Malformed replies fail InvalidPacket 101; death 96, timeout 93 and
cancellation 94 remain transaction outcomes, not mathematical evidence.

A CHECK begins a real nonblocking call with a predeclared 10,000,000-MTIME-tick
(1 second) deadline. Every notebook turn polls without blocking pen. The current
owned 1856-byte record is changed only after a validated reply for its current
namespace/page/revision/goal and after active ink and Store work reach their
ordinary boundary. Editor/navigation actions are held while the request is
active. The historical scalar IPC ABI has one outstanding call per process.
Starting ink cancels and consumes a pending arithmetic call before any Store
call; writing takes priority and mathematical bytes remain unchanged.
Closing COURSE cancels and consumes the terminal transaction; an
already accepted result is discarded. Cancellation does not manufacture an
attempt event. Persistent abandonment/cancellation learner events remain a
separate missing record-format feature.

A successful result uses the ordinary Store copy and barrier path; neither IPC
acceptance nor a controller reply is durable Saved. A service error closes the
course only after active ink/store work finish, preserves all acknowledged
mathematics and history, reports the actual error to the Developer console,
and leaves raw ink/Store usable. The current small course UI has no dedicated
pending-check status label; Developer observations expose request/reply state.

Only exact Laboratory configurations select additional server boot modes:
`lemmasim-silicon-power-arithmetic-oom-development` fills 31 real owned Boxes;
`lemmasim-silicon-power-arithmetic-fault-development` executes a User read at
unmapped 0x500000; `lemmasim-silicon-power-arithmetic-stall-development` runs
2000 real 100000-tick sleeps (at least twenty seconds), then attempts an actual
late reply using the retired authority. The one-second caller deadline is
unchanged. A late reply must fail and cannot create evidence. All keep the canonical geometry/pool/Store/pen.
The public launcher requires Laboratory mode for these names. They cannot
change a normal deployment through an independent arbitrary mode flag.

Tests of host RAM Actions, emitted-code audits, actual RV64 isolation and exact
RTL timing are separate qualifications. QEMU counters are instruction counting,
not canonical pipeline/bus timing. This service does not close the known QEMU
cached-state continuation hole or portable microstate checkpoint gate.

-->
