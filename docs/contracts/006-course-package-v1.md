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

Generic Store currently permits replacements. The reserved range is therefore
a loader convention, not an enforced immutable-media policy yet. Guest package
installation must add an append-only server guard, durable publication and
normal transport/permission handling before claiming immutable installed
editions. Host publication refuses an existing output directory but does not
install or recover a guest journal. No disk format or notebook format changes.

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

Current component checks do not establish CPU execution, notebook selection,
guest installation, durable cold reopen or full G2/G4-G7 completion. Any future
evidence must bind the exact package identity, edition, integrity value, node
source anchor, original goal, document/submission revision and existing checker
environment. Current submission formats remain untouched; no legacy evidence
is relabelled as dynamically package-bound. Immutable installation, package
selection/rendering in the existing notebook, durable learner references,
permissioned tutor context, general course declarations and proof-kernel
closure remain separate work.

-->
