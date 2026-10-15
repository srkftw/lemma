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
Rejected archives preserve the current scheduling timer, run budget, input
capture and launch observations as well as authoritative machine state. The
synchronous machine validator runs before cancelling a live run. Once a valid
archive is adopted, the worker clears old Ready/save observations before any
asynchronous private copy; a failed copy cannot expose the previous launch's
success. These are repairs within control contract2, not a new state format.

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

## Typed course installation on the existing browser machine

The optional `lemma-course-console-command/1` transport is now exposed in
Developer and Laboratory modes. A bundle advertises it only for a complete,
exact Course, CourseAwait or PackageClosure initializer/notebook deployment;
the launch validator checks both inventoried build identities. Student requests
reject before a machine read, pause, clock or storage operation. This adds an
owner input control to browser session contract2 and does not grant new guest
capabilities or implement teacher identity/authentication.

Select an `.lcp` file and a positive decimal transaction, then choose **Send to
guest installer**. The browser copies the untrusted declared identity, edition
and CRC32 into the existing 64-byte little-endian command frame and appends the
exact file bytes. The guest checks the package, immutable publication rules and
Store durability. The host performs only the transport's 128–32768-byte and
field-range admission. It neither computes a successful integrity result nor
installs an object in the journal. Transactions through `2^63-1` and virtual
cycles through `2^64-1` retain exact BigInt/string values.

Admission pauses scheduling and queues ordered112-byte UART events at one
observed virtual cycle. Every event retains the existing256-character bound
and enters ordinary raw capture. It advances no guest clock and completes no
backing operation. Resume lets the real guest installer run. A rejection reports
the exact accepted prefix; that prefix remains queued. After a partial packet,
the typed control requires Close and a new cold Open before retry. It also
requires cold Open before a new installation from a restored continuation,
because the resumed parser can already contain an admitted prefix. The existing
raw-event replay continues those bytes without resending the operation. This
is an explicit external-input policy, not a flush/drain or a restriction on
authoritative machine snapshot capture.

The UI reports transport admission separately from the latest complete new
guest installer `0x4b1` report. Only operation1/status0 with a nonzero durable
sequence displays **Guest reports installed**. Error reports remain failures;
load/delete records, partial lines and retained pre-reset history cannot claim
installation. Identity, edition, sequence and CRC remain exact decimal strings.
This observer reports the guest's result and does not manufacture a receipt.

The prepared four-process local package is launched with:

```sh
./scripts/lemmasim browser-build --profile lemma-silicon-dev/0.3.0 \
  --reuse-wasm --wasm-build build/wasm/task006-canonical-native-port-a1 \
  --wasm-input-bundle build/browser/task006-surface-bulk-closure-a4 \
  --guest-bundle build/native/task006-package-closure-entry2-a1 \
  --output-dir build/browser/AN_UNUSED_PACKAGE_BUNDLE
./scripts/lemmasim browser-serve \
  --bundle build/browser/task006-package-closure-entry2-a1 --port 8790
```

This preserves the exact existing RTL/Wasm core and packages the freshly
elaborated/audited Kernel4, Store1, Notebook2, Closure7 and PackageInstaller1
images. The native helper builds the guest; this is not browser compilation.
The current new-CPU browser cold run and installed-course acceptance are
unfinished. Fifteen browser host checks and the full293-test pinned simulator
host suite passed; these do not establish guest installation or cold Ready.
The original failed4948899 CI host expectation and skipped target acceptance
remain retained separately from its narrow owner-mode fixture correction.


The new package-enabled browser cold gate has now reached actual Ready at
977550000 cycles,503905647 retired,192MiB heap and5265.484 seconds in machine
calls (5429.657 elapsed, including host pauses). It imported the untouched
edition1/2 medium into a new origin and ran fromCPU0 without restore or
initialization. The guest created the missing notebook through four actual
backing barriers. Its entire256MiB result and all3.63M controller pixels match
the independently observed native cold result at978M. The snapshot stores
Gray4 values; equality uses the declared exact17*n display-channel mapping.
The first last-UART-row and pixel-representation observers failed; the corrected
byte assertions completed, then their diagnostic print failed on a renamed
key. That process failure and its retained completed observations are explicit
in the existing evidence. This is no exact same-boundary suffix comparison.
The typed new4063-byte edition3 request is now admitted and executing; admission
still does not claim guest installation or complete course/math acceptance.
