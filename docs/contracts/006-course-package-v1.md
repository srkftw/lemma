<!--
# Bounded offline course package v1

`lemma-course-package/1` adds typed Lean authoring and a non-executable binary
artifact. `Package.Course`, `Package.Node`, `Package.Kind` and `Package.Goal`
are ordinary hosted Lean data declarations. `Package.encode` validates them
before returning bytes. Hosted publication uses ordinary Lean I/O; neither its
runtime nor its strings implement target code. The guest decoder is ordinary
first-order Lean Action source admitted by the existing `core0-user-v0.2`
checker and checked LLVM lowering. No language/runtime profile is broadened.

The first original sequence contains explanations, examples, worked material,
fraction/polynomial exercises, an explicit Unsupported exercise, hints and an
explainable review paragraph. It does not import a commercial textbook or grant
new rights. Mandatory source, edition and rights anchors travel in the package.
The repository's unresolved redistribution/license status is preserved.

## Bounds and integrity

An image is128..32768 bytes with1..16 nodes and at most16384 text bytes. Each
field is0..512 bytes. Required fields are nonempty. Version1 admits ASCII32..126
and LF10; UTF-8 outside that subset returns Unsupported. Identity is1..65535;
edition is1..4294967295. Every integer is an aligned little-endian UInt64.

CRC32/ISO-HDLC uses reflected polynomial `edb88320`, initial/final XOR
`ffffffff`. The CRC covers the entire image with bytes80..95 treated as zero.
The CRC word and its32-bit inverse must have zero upper32 bits. This detects
ordinary corruption. It is not authentication, a signature or proof evidence.
The format has no executable content, automatic recognition or tutor authority.

## Header and nodes

The128-byte header contains:

| Offset | Value |
| --- | --- |
| 0,8 | magic `315352554f434d4c`, version1 |
| 16,24,32 | exact total bytes, package identity, edition |
| 40,48,56 | node count, node size192, nodes offset128 |
| 64,72 | text offset `128+192*count`, exact text bytes |
| 80,88 | CRC32,32-bit inverse |
| 96,104,112,120 | title, source, edition and rights text spans |

A text span packs a32-bit byte offset into the low word and a32-bit byte length
into the high word. Spans are canonical, contiguous and non-overlapping: first
the four header fields, then every node's eight fields in node order. Empty
optional fields still identify the current cursor. The final cursor must equal
the exact image length; aliases, gaps and unclaimed trailing bytes reject.

Each192-byte node has:

| Offset | Value |
| --- | --- |
| 0,8 | node identity `ordinal+1`, kind |
| 16,24,32,40 | goal, checker, domain, assumptions references |
| 48,56 | separate logical and pedagogical prerequisite bitmasks |
| 64,72 | source-node identity equal to identity, recommended checker budget |
| 80..104 | four reserved zero words |
| 112..168 | title, body, example, worked, exercise, hint, source, review spans |
| 176,184 | two reserved zero words |

Kinds are explanation1, worked2, exercise3 and review4. Title, body and source
are mandatory for every node; an exercise also requires exercise text. Bit `i`
references earlier zero-based node `i`. Both masks must be less than
`1<<ordinal`, preventing cycles/self references. They are independent graphs:
a pedagogical suggestion does not create a logical prerequisite. Authoring
rejects duplicate edges as well as forward/self edges.

Only exercise nodes carry checker references. Version1 references the existing
pinned original goals:1 is `1/2+1/3=N/D` over Q;2 is `(x+1)*(x+1)=C0+C1*x+C2*x*x`
over Q[x]. Both require checker `0001000000000001`, domain equal to goal,
assumptions0 and budget8. Their existing checker keeps explicit denominator and
resource behavior. Goal3 is an explicitly Unsupported exercise with domain3,
checker0, assumptions0 and budget0. Unknown kinds, goals, checker versions and
assumptions return Unsupported. Presentation nodes carry zero checker fields.
This format does not authorize arbitrary new mathematical goals.

## Guest decoding and Store boundary

`PackageTarget.validate(address,bytes)` reads the complete private package and
returns its node count. It performs no writes, allocation, checker invocation,
document mutation or storage completion. `select` returns a borrowed node
address after complete validation, `goal` reads its pinned goal reference, and
`character` reads one explicitly selected text byte. A borrowed address must
not survive a change to the caller's private package buffer. These reads create
no trusted result and never silently change a submitted goal.

Error order is argument admission, magic/version, header shape/resources, full
CRC, then ordered text/node validation. Codes are Malformed240,
Unsupported241, ResourceLimit242, IntegrityFailure243 and SelectionAbsent244.
A real checked access error keeps its original status and stops the same read
prefix. Invalid argument spans cause no reads. A missing selection is distinct
from an unsupported checker or failed integrity check.

`PackageStore.load(context)` is a concrete guest loader through existing copied
Store IPC. Its80-byte caller-owned context has endpoint0, outgoing8(192 bytes),
incoming16(256 bytes), authorized namespace24, identity32, edition40, dedicated
staging buffer48, capacity56, initial request ID64 and reserved zero word72.
All four spans must be disjoint and aligned8; arithmetic bounds and request-ID
exhaustion reject before I/O. The existing namespace1/2 grant is the authority.

The package object key is `4350000000000000 | (identity<<32) | edition`, separate
from notebook page/ink/submission keys. The loader reads the first128 actual
object bytes, bounds the declared size against staging capacity, and reads the
rest with at most255 further128-byte copied IPC requests. IDs are initial+i;
short replies reject before copying, and transport/framing/application failures
are not retried or acknowledged as success. Full validation and exact requested
identity/edition precede return. Success is a validated read, never a new Saved
acknowledgement. Failure may leave partial staging bytes; the caller retains its
active package/document separately. This first loader is blocking per caller;
cooperative notebook publication and pen-responsive package UI remain open.

The opt-in `Server.courseMain` endpoint enforces append-only editions in this
reserved key range. The historical Store main/step/application remain unchanged.
Before Begin or Commit, the guard searches the real current index, including
retained tombstones. An existing key returns ReadOnly223 before staging or
backing changes; Delete always returns ReadOnly223 when the stage is free, or
Busy231 when owned. Invalid keys reject before index reads. Commit validates
the entire package and exact key identity/edition before entering the existing
Engine append path. Ordinary object updates and namespace authority retain
existing behavior. This is endpoint policy, not physical write protection.

`PackageStore.install(context,bytes,transaction)` validates its complete private
buffer before Begin, sends at most256 copied128-byte chunks with exact count and
accepted-offset checks, and calls real Commit. Only an application-success
reply in ready mode with a positive durable sequence returns Installed. The
original Engine performs both barriers before publishing its index/receipt.
A failed barrier may leave observed unacknowledged backing bytes. Upload
failure may abort its bounded uncommitted stage once; uncertain Commit never
causes automatic retry/abort or an Installed receipt. No durable format changes.

`lemma-course-command/1` is a local owner raw-console frame of eight aligned
little-endian words: magic `31504b43414d454c`, version1, operation, package
identity, edition, payload bytes, transaction-or-node and expected CRC32.
Install1 carries128..32768 exact body bytes and a positive transaction; Load2
has no body and a node ordinal0..15; DeleteProbe3 has no body and a positive
transaction. Unsupported framing reports its status and terminates only the
unprivileged installer. Its private pages and Console/Store grants never grant
block or notebook memory authority. This transport is RTL-only in the current
canonical profile, local-owner integrity only, and does not authenticate a peer.

## Same-Action IPC base reuse

The next internal optimization is `lemma-ipc-call-base-reuse/1`. The existing
CallBeginWithLimit operation validates capability authority and the complete
User payload range first, then `idle` validates a fresh full address-space
base and current IPC metadata. Six later metadata transitions borrow exactly
that base within this same syscall Action. Every mutable pending state,
transaction, next ID, operation, endpoint and reply field is reread in its
original order. UserCopy still resolves the scratch handle and checks live
ownership/generation, duplicate rows, exact tracked/walked PTEs and complete
User permissions before copying. Queue checks, object limits, replies and
publication order remain. Legacy public Storage helpers and CallBegin retain
their original complete checks. The Store protocol and durable format stay v1.

This borrow cannot cross a return, wait, syscall, scheduling or reset boundary.
The single hart's S trap disables S interrupts; pending timer notification is
not scheduler execution. Private M timer service updates timer/notification
state, never allocator, descriptor, page-table or object memory. Other User
tasks cannot run during the Action and have no mapping of this kernel metadata.
DMA ownership checks admit only pinned granted User spans, never these kernel
purpose1 descriptor frames. Raw host inputs/backing adapters supply device
samples/bytes and cannot write descriptor RAM. A reset restarts the machine;
it cannot resume a stale borrowed base. IPC staging touches only the reserved
IPC tail; object/queue transitions use disjoint frames. None can alter the
validated descriptor layout, frame grant or mappings between uses.

The exact closed generated helper bodies, caller inventory and checked success
routes are separately observed. No general cached-pointer interface is admitted.
The finite fault fixture projects only independently validated identical
successful duplicate base-read subsequences; every remaining read, failure,
write, returned count and authoritative byte stays exact. It covers fixed
address-specific injected failures, alias/range/partial-page cases and both512/
8192-frame configurations. It does not establish equivalence for an external
agent mutating kernel metadata or a new transient/ECC read-error profile; such
models need a separately admitted lifetime/error contract before this borrow
can be used. Current memory-access alignment/bounds failures remain checked.

The qualified component reduced actual expanded CallBegin boundary requests
from1920 to1446 (24.6875%), and legacy512-frame requests from1220 to1082. These
are hosted actual-Action counts, not target cycles or host simulator speed.
Genuine kernel4 LLVM/RV64 component lowering passed with only the real private
firmware boundary unresolved. Whole-image requalification, fresh RTL cycle/host
measurements and completed course install/cold recovery remain required.

## Actual raw-owner launch and commands

The original fully audited course images and their exact sealed source roots
can launch through the ordinary native machine. Use an unused session directory
and a new medium for the initializer; never initialize existing user media:

```sh
python3 -c 'from pathlib import Path; f=Path("build/courses/course-medium-new.raw").open("xb"); f.truncate(268435456); f.close()'
scripts/lemmasim session --backend rtl --profile lemma-silicon-dev/0.3.0 \
  --workload initializer --mode developer --headless --paused \
  --session-dir build/courses/course-session-new \
  --disk build/courses/course-medium-new.raw \
  --native-bundle build/native/task006-array-table-prefix-a2 \
  --guest-build build/kernel/task006-course-initialize-a3 \
  --guest-source-root build/courses/task006-course-whole-sources-a1/initializer
# In a second terminal, after the first publishes its session directory:
scripts/lemmasim session-control --session-dir build/courses/course-session-new \
  --request '{"action":"resume"}'
scripts/lemmasim course-install --session-dir build/courses/course-session-new \
  --package build/courses/task006-package-qualified-a5/package/arithmetic.lcp \
  --transaction 7
scripts/lemmasim course-load --session-dir build/courses/course-session-new \
  --identity 1 --edition 1 --crc 1743257817 --node 2
scripts/lemmasim course-delete-probe --session-dir build/courses/course-session-new \
  --identity 1 --edition 1 --crc 1743257817 --transaction 12
```

The exclusive raw-medium creation refuses an existing path. These commands
admit raw bytes only. Their
`RAW_COMMAND_ADMITTED` status is not a storage acknowledgement. Actual guest
K1 records distinguish installerReady4b0, outcome4b1, validatedPresent4b2 and
selectedReference4b3. An Install outcome must have application status0 and a
positive durable sequence. A validated reference is not verification evidence.
For a cold read, launch workload notebook with the notebook build/source role
on the already initialized medium; do not use a snapshot or initialize again.

## Evidence and remaining integration

The public command is:

```sh
nix develop --no-write-lock-file --command python3 scripts/build_course_package.py \
  --output-dir build/courses/course-package-new
```

It retains source/tool identities, typed publisher bytes, independent Python
zlib/format checks, actual imported-Action read/IPC fixtures and genuine checked
LLVM/RV64 component objects. The decoder has no undefined helper/runtime. The
Store loader component leaves exactly the existing `lemma_exec_syscall` machine
boundary unresolved; this is a component, not a linked freestanding image.
Normal target builds must supply/audit that real structured boundary.

Authors can call `PackagePublish.publishCourse(directory, course, declaration)`
from an ordinary hosted Lean main. The original alternative-edition example
executes directly and validates its changed hint against the unchanged guest
decoder:

```sh
nix develop --no-write-lock-file --command flock build/task006-lake.lock \
  lake env lean --run tests/courses/Author.lean \
  --output-dir build/courses/course-author-new
```

This is an explicitly native authoring helper, not browser-local compilation or
an installed guest course UI. The CLI is in `PackagePublishMain.lean`; the
publisher library exports no competing root `main`. A new immutable edition
changes artifact data; it does not change the checker goal semantics or target
decoder. Publication refuses retained output directories.

The additive `lemma-course-array-bulk-deployment-v1` has exact canonical0.3
notebook/initializer configurations, preserving the older image roots. It links
existing notebook and checker processes, guarded Store, and a fourth separately
linked installer. Both original whole images have passed the ordinary complete
artifact audit against sealed331-input roots. Their original failed observers
are retained. This audit establishes linked provenance and admitted code;
actual installer/Store startup is separately observed at56 million RTL cycles.

The first actual4040-byte install failed to produce a Commit/outcome at its
original100-million-cycle bound (561.824 seconds). No backing I/O followed input
admission. A second observation at the same declared100M boundary preserved an
observational checkpoint: all4040 bytes had been received/validated, the UART
queue was empty, and the next copied Store chunk was offset1920/count128. Body
input drained by66M; subsequent samples mostly execute kernel frame/page-table/
IPC checks and zeroing. The per-read Console allocation is not the main blocker.
This retained failure is not Installed or cold recovery. A future change needs
its own prospective workload bound and actual completed scenario. Notebook package selection,
durable cold reopen and full G2/G4-G7 completion remain unqualified. Any future
evidence must bind the exact package identity, edition, integrity value, node
source anchor, original goal, document/submission revision and existing checker
environment. Current submission formats remain untouched; no legacy evidence
is relabelled as dynamically package-bound. Actual completed immutable installation, package
selection/rendering in the existing notebook, durable learner references,
permissioned tutor context, general course declarations and proof-kernel
closure remain separate work.

-->
