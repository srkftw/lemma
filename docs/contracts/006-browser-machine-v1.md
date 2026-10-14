<!--
# Local RTL browser embodiment v1

`lemmasim-browser-bundle/1` is a local development distribution of the existing
`lemma-silicon-dev/0.3.0` machine, not a new emulator. Verilator5.052 generates
`lemma_soc` with its actual processor, TLB/cache, fabric and device circuits.
Emscripten6.0.9 compiles that circuitry and `Machine` to Wasm. The guest remains
the separately audited, genuinely elaborated Lean/LLVM RV64 image. The native
helper compiles guest images; no browser-local Lean compiler is supplied.
ELF-preload development boot remains explicit. Production boot/update is absent.

The portable build copies the pinned Verilator runtime and disables only Linux
CPU-affinity branches for Emscripten's single evaluation thread. Its original
and patched source hashes are recorded. No instruction execution, notebook,
ink, recovery or mathematics moves into JavaScript. Browser code transports raw
pointer events and presents the controller's Gray4 output with WebGPU or the
same-byte 2D fallback. Device loss replaces the presentation canvas only.
Mouse pressure is explicitly synthetic. Pointer cancellation supplies loss/
resynchronization flags. Coordinate conversion has bounded integer results.

## Time and observational state

`lemma-browser-session-modes/2` preserves contract1's guest authority and adds
ordinary retry of an incomplete opaque private backing copy. Captured-outcome
binding, typed raw input, inspection and offline replay remain privileged.
New workers require their matching version2 bundle; archived version1 frontend
bundles remain version1. The worker reports the active OPFS medium name and
whether its private copy is ready. A successful copy/flush/rebind publishes the
new name; a failed copy keeps the old name and blocks clocks. The frontend
adopts a new active name once, preserves later next-name edits, and retains the
name after Close. Open then constructs a new CPU and runs guest recovery from
that persistent file. Exposing a name never creates a guest Saved receipt.
Student retry copies opaque bytes and never interprets a document or journal.


`lemma-browser-session-modes/1` is an additive browser control admission
contract. New sessions default to Student; the operator explicitly selects
Developer or Laboratory before opening. The worker fixes that selection until
Close. Sending another mode on a live control, an unknown mode or an unlisted
action rejects before a machine read, clock, pause or backing operation.
Ordinary pointer/power input, cold/warm reset, pause/resume, checkpoint/private
restore and opaque backing import/export remain available in every mode.
Developer and Laboratory additionally admit bounded runs, typed raw input,
inspection, raw/outcome capture, pending-outcome binding/retry and offline replay.
The UI hides those controls in Student mode; the worker independently enforces
admission even for direct messages. Laboratory has no additional browser fault
inputs on this profile yet; unsupported faults reject. This selects operator
tools, not an identity/authentication system or additional guest capabilities.
All modes retain the same guest isolation, mathematical checker and assessment
authority. Teacher/tutor permissions remain a separate unfinished guest workflow.

One worker owns the machine. A 50000-cycle run quantum yields cooperatively;
animation frames and tab scheduling do not advance virtual time. All clocks,
addresses and operation IDs cross the JavaScript interface as literal decimal
strings or BigInt. Only bounded geometry, byte counts and run quanta use Number.
New asynchronous storage/import/restore operations exclude competing controls.
Raw input enters the actual machine event queue at the observed cycle.
Presentation reports running/paused independently of observed guest Ready.
Only a complete newly emitted K1 record can establish Ready for a boot; warm
and cold reset retain UART history, whose previous Ready is excluded. Restoring
a continuation does not infer readiness from that retained history. These
presentation observations never create a guest milestone or advance time.

The ordinary UI additionally presents the latest complete newly emitted guest
publication record: `0x423` is Pending, `0x421` is Saved and `0x424` is Failed.
Its value, page, namespace and detail remain literal decimal strings. This
`compiled-guest-report` observation does not inspect a journal, complete I/O,
create a receipt or establish that every current edit is saved. A backing
completion without a corresponding guest report cannot produce a Saved label.
Initialization-to-notebook replacement, reset and restore establish a new UART
observation boundary; retained history cannot authorize a new publication.
Close clears the label. Developer inspection retains the original kind and
all four fields; ordinary presentation explicitly says “Guest reports Saved”.

Snapshot exports use the unchanged `LMSSRTL1` state contract. MEMFS lacks hard
links, so Wasm exclusively creates the artifact and copies it in bounded chunks;
this artifact publication is separate from a medium barrier. Snapshotting does
not flush the medium or drain guest work. Corrupt/incompatible state rejects
before live adoption. A valid restore owns a private MEMFS backing fork. The
browser copies its opaque bytes to an exclusively created OPFS fork, flushes
that copy, and rebinds only after full byte equality. A storage failure after a
valid restore leaves the machine paused; Resume cannot use MEMFS as durable
backing. Retry private binding or export that machine's actual backing bytes.

Native and Wasm implementation identities are distinct. Their archive headers
need not match and cannot be interchanged. For this pinned little-endian port,
the same generated Verilator serializers encode the logical signals in the
same declared order and widths; their context-pointer overload writes context
values, not pointer addresses. The bounded comparison therefore requires exact
wrapper and generated-state sections, plus applicable output/event suffixes.
The original source closures and each implementation identity remain recorded.
This does not establish all possible architectural/cache/device boundaries or
QEMU timing parity. QEMU's untranslated-cache checkpoint hole remains open.

The public worker `run` action accepts a positive additional cycle budget as a
literal unsigned decimal string or BigInt; a JavaScript Number and UInt64
overflow are rejected. Each scheduled machine call is at most50000 cycles,
with an exact final remainder. One worker timer owns scheduling and pauses at
the declared limit without animation-frame or UI polling dependencies.
Optional `stopOnReady` observes the existing complete new0x420/opened-page0x425
records and their actual completed controller sequence. It does not synthesize
Ready. A real initializer-to-notebook CPU replacement carries the unused budget
across the clock reset. Continuous Resume clears the budget; pause, snapshot
and export cancel scheduled work without advancing the machine. Inspection
reports requested/used/remaining/limit as decimal strings.

Legacy `hostSeconds` remains elapsed time for the current guest launch,
including pauses. Separate opened-worker-session timing reports elapsed time,
time inside actual `lemma_run` calls, synchronous machine-backing call time
within those calls, and run-call time outside those backing calls. These host
durations are not guest CPU time or a WCET proof. Raw-event JSON and backing
outcome exports have separate user actions and one file per action; the older
combined `capture` protocol action remains compatible.

Controls, worker observations and controller-pixel 2D presentation register
before asynchronous GPU capability requests. An unresolved adapter/device
promise leaves them usable. A detached replacement canvas switches only after
device/pipeline qualification; switching or device loss cancels active contact
with the existing raw loss/resynchronization flags before pointer rebinding.
The same retained controller plane is presented after the renderer changes.

## Origin persistence and faults

The backing interface is `lemma-backing-io/1`. A worker holds an exclusive OPFS
SyncAccessHandle for the complete256MiB raw medium. Only its successful `flush`
completes the guest barrier; an enqueued asynchronous operation or an in-memory
copy cannot acknowledge Saved. Errors map explicitly: quota28, permission13,
closed handle9, cancellation125, missing file2, otherwise I/O5. Partial returns
are captured. A throwing write is followed by an observation of changed bytes;
unknown/non-prefix changes poison the machine instead of inventing rollback.
A failed preflight read happens before issuing the write and has a known empty
changed prefix. Read and barrier errors reach the actual controller.

Opening an origin medium acquires an exclusive handle before a machine exists.
Failure in initial truncate/flush/size validation attempts to close that handle
and preserves the original storage error, including when cleanup itself fails.
No CPU, scheduled run, export or guest success is created by a failed open.
The newly created file and any bytes already changed remain present; this is
lease cleanup, not rollback. A wrong-size medium still rejects without format.
These initialization errors are outside the machine's guest backing-outcome
tape because no machine operation has been admitted yet.

Backing outcome logs capture before machine publication. Replay constructs a
new instance with the exact log and restores an isolated checkpoint; its new
OPFS file receives only recorded effects. It does not execute live I/O against
the original medium or peer. A raw capture binds checkpoint hashes to the
number of already admitted events, so a replay schedules only the later suffix.
It stops at the recorded final cycle. Arbitrary reset-spanning captures are not
advertised: explicit browser resets clear the raw checkpoint bindings. Pending
external callbacks cannot be snapshot boundaries under this synchronous contract.

Origin eviction and physical power-loss guarantees remain unqualified. An
export contains actual backing bytes, including observed unacknowledged changes,
not the volatile controller overlay. Cold reopen invokes actual guest journal
recovery; restoring a checkpoint is a separate operation. Initialization and
raw import require a new medium name and cannot format an existing medium.
No beforeunload hook acknowledges or saves pending work.

The prepared bundle is local. Existing software's project-wide redistribution
license is unresolved. Dependency notices preserve upstream terms and do not
relicense target sources. Native installers, teacher/package permissions,
tutor communication, whole-machine browser acceptance and physical conformance
remain separate required work; a successful Wasm build or boot prefix is not
those results.

-->
