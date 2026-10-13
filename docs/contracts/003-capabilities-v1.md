<!--
# Managed capabilities v1

This is the Gate H source contract. Builds, artifact audits, source/model proofs
and U-mode observations are separate evidence; this document asserts no pass.
Blocking IPC and buffer services remain later gates.

The fixed managed policy identifier is `lemma-capabilities-v1`. The kernel
derives the caller from the checked running context. A User integer never names
a metadata pointer or grants authority by identifying a global object.

Each live checked AS descriptor reserves +2560..+2623 for its capability header,
+2624..+3647 for 16 entries of64 bytes, and +3648..+4031 for future IPC storage.
The header is magic `0x31504143414d454c`, version1, self descriptor, state
(2 constructing /1 active), capacity16, live-entry count, enrollment slot and
reserved0. Every entry contains state (0 free /1 reserved /2 live), serial,
internal object key, rights, local slot and three zero reserved words.

An all-zero header is legacy/unmanaged. A partial or constructing header must
never make a published task bypass managed dispatch. Historical F/G creation
remains unmanaged and does not allocate the global capability frame. Managed
construction attaches and grants before activation and runnable publication;
ordinary grant failure aborts the unpublished instance. Impossible failures of
checked metadata writes are kernel invariant failures, not observed rollback.

The global handle at authoritative `Layout.capabilityControlValue` resolves to
one owner-1/purpose-1 unmapped allocator frame. Its bounded storage contains16
object rows of128 bytes,8 registered descriptors, a next-capability serial and
counts. Console, Management and Directory are pinned boot objects. A separate
four-endpoint bound counts live and revoking endpoints across all16 rows before
free-slot selection or allocator effects; the global16-object capacity remains
independent. Every endpoint owns one real owner-1/purpose-1 frame for future queue storage; there is
no hosted queue or runtime. Endpoint objects are not pinned. Last close releases
an unreferenced endpoint; owner detach destroys an owned endpoint even if another
task holds aliases. The permanent empty managed registry baseline is498 frames;
per-task capability metadata consumes no additional allocator frame.

Local handles are `(serial <<4) | slot`, serial1..`2^60-1`, slot0..15. The global
serial advances only after successful entry publication. An exhaustion or full
destination leaves source entries, object references, serial and frames unchanged.
Internal object keys independently encode generation and slot; generations never
wrap. Releasing the last generation retires that object slot permanently.

Lookup checks descriptor liveness, managed header/enrollment, local slot/serial,
entry state, object liveness/generation/type, the stored mask and required rights.
Object types are Console1, Endpoint2, Management3, Directory4. Rights are Read1,
Write2, Send4, Receive8, Call16, Duplicate32, Revoke64, Create128, Grant256,
Inspect512 and Discover1024. Closed per-type masks are35,124,928 and1056.
Requested duplicate/transfer rights must be nonzero subsets of source rights;
Duplicate is required in the source. A scoped management Grant authorizes only
the trusted boot-selected peer descriptor, not arbitrary tasks.

Close removes one entry. Revoke requires Endpoint/Revoke, withdraws the entire
object, sweeps at most8 tables of16 entries, releases its queue exactly once and
advances/retires its generation. All aliases lose authority, including the
revoking handle. Detach revokes owned endpoints, closes remaining entries,
clears a matching management scope and withdraws enrollment before AS teardown.
All transitions are single-hart nonpreemptible and bounded.

The shared numeric ABI is `Lemma.User.CapabilityABI`:9 query local slot;10 info
(`type | rights <<8`);11 type/rights check with value0;12 duplicate;13 close;
14 revoke;15 capability Console;16 create Endpoint;17 scoped transfer;
18 scoped peer query (mode0 descriptor /1 checked live-entry count);19 scoped
inspection (field0 local subject refs /1 global live objects /2 actual remaining
frames /3 retired slots, with subject0 required for fields1..3). All unused
operands are zero. The new Console call is `(handle,op,ptr,len,0)`, op0 write/op1
read. Managed legacy Console2 returns72 before memory copies or device effects.

Public failures80 invalid/stale handle,81 wrong type,89 table full,90 object full
and91 generation exhaustion supplement existing16 invalid arguments and72 denied.
Unknown masks and unsupported object types do not turn into authority. Status255
is reserved for kernel invariants and never an ordinary User-request result.

The development-only generation helper monotonically seeds one genuinely free
endpoint slot to its last generation and records actual before/after values.
The ordinary creation/revoke path must then retire it. A late development control
may advance the next serial to its last issuable value, leaving exactly one real
User publication before exhaustion. No User syscall exposes these mutations,
and ordinary production imports neither the helper nor the descriptor alias.
The S-only alias in the managed-development configuration targets the checked
descriptor frame; a U store at31a00 reaches its actual capability header offset
and must produce hardware store-page-fault15 without granting table access.

CapabilityModel proves a local UInt64 attenuation/lookup-mask monotonicity fact
using the exact shared predicate. It does not prove linked-code refinement,
hardware isolation, reference accounting, or the whole lifecycle. Those require
fresh audits and separately retained U-mode attack, ABA, rollback and teardown
observations.

The artifact audit admits two observed LLVM O2 immutable lookup tables only
when their exact genuine reachable source declarations occur in a kernel unit.
`Lemma.User.CapabilityABI.typeMask`
At the historical H checkpoint it contains four 64-bit values `[35, 124, 928, 1056]` (32 bytes); unsigned
`kind - 1 < 4` guards its sole load, with zero as the default.
The private `Lemma.Kernel.Objects.initStep` contains three 64-bit pinned kind
values `[1, 3, 4]` (24 bytes); unsigned `index < 3` guards its sole load and
its result is used only for the object-kind initialization write, with zero
as the default. Exact source identities, signatures, effects, globals, pointer
uses, guards, local object symbols, little-endian bytes and absence of table
relocations are checked. The existing 32-byte PMP table keeps its prior
contract. A kernel closure can contain PMP alone, PMP plus the pure mask,
or all three tables; each present table requires its exact source row and
object inventory. All other globals and lookup tables remain rejected, and
firmware, user and legacy profiles acquire no table admission. Earlier
deployment configurations may account for these same helpers only when their
genuine reachable kernel closure includes them. This accounts for optimizer-
generated read-only data and does not
extend Core0's accepted language, runtime, syscall authority or MMIO access.
The initial H O2 table rejection is retained separately from later validation.

The first clean H cumulative run failed before the normal bootstrap O2 guest
because its shared syscall closure reached the pure type-mask helper while the
auditor incorrectly limited that helper to the capabilities deployment label.
The repair changes source-closure accounting only; target code, profiles,
values, guards and User authority remain unchanged. The failed run is retained.

Current rebuilt H and earlier kernel closures use the additive fifth Reply mask
recorded in `003-ipc-v1.md`; their audit pins all five values and the corresponding
guard and object bytes. Historical four-value H artifacts retain their original
source and audit bindings.

-->
