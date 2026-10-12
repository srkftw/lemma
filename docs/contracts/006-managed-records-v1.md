# Managed ordinary records, version1

`lemma-managed-records-v1` is an additive `core0-user-v0.2` bridge, not the
finished G2 managed language. All earlier Core0 profiles reject `Action.managed2`.
The inherited User syscall/effect authority is unchanged. It introduces no
foreign allocator, Lean runtime, interpreter or synthesized source declaration.

The distinct `core0-kernel-v0.5` profile inherits Kernel-v0.4 and extends only
the 32-bit PLIC priority interval's exclusive upper bound from `0x0c00003c`
to `0x0c000040`, admitting priority15 for the opt-in BLE device profile. It
grants no new memory, syscall or 64-bit device interval. Historical kernel
profiles retain their exact priority bounds. Merely defining this profile
does not qualify the future hardware/probe deployment.

The bridge accepts a closed ordinary Lean `UInt64 → UInt64 → UInt64` definition.
Its structures and calls come from genuine upstream compiler IR at pinned Lean
revision `5045d0056413266e57c625dcd7c365b10e377c52`. The frontend discovers the
reachable IR call closure, checks each ordinary safe source signature and
constructor declaration, then lowers admitted forms into checked Action IR and
LLVM. Missing IR, source replacement, external code and unsupported forms reject.
Generated names identify their exact original source closure; they are never
inserted as fictitious Lean declarations.

The initial objects are nonrecursive, monomorphic, nonindexed structures with
one constructor and one to seven explicit `UInt64` fields. They have an eight
byte shape cookie followed by aligned scalar fields, total16..64 bytes. Shape
IDs are deterministic from sorted type names within the closed entry. Genuine
IR constructor size, projections, field initialization and borrowed argument
metadata must match the source layout. Objects cannot cross entry roots or
be exposed as syscall parameters. A shape table is not an arbitrary target type
cast: every field operation validates the generational arena reference, byte
length, cookie and bounds.

Allocation uses the actual process-owned arena page and its31 generational
slots. Constructor fields are zeroed before initialization; no partially
initialized object may be projected, called or returned. Ordinary borrowed
parameters do not transfer ownership. An owned return transfers one reference;
other references must have been released. Admitted genuine IR `dec1` performs
real arena release. Failure attempts cleanup of remaining owned references and
retains the first failure status while attempting all remaining releases, never
mathematical evidence. Process exit
and kernel teardown remain the ultimate page-ownership boundary. Controlled
arena OOM is status237. No allocation or reference-counting helper is a no-op.

Admitted expression forms are `UInt64` constants, add/subtract/multiply modulo
2^64, direct checked ordinary calls, constructors, initial scalar field writes,
scalar projections, nonconditional/nonpersistent decrement1 and return. Calls
have a maximum depth8 and closure size32; each body has4096 IR nodes and a
disjoint bounded SSA namespace. Recursion, joins/branches, reference increments,
reuse, erased arguments, static lifted objects, general inductives, arrays,
strings, closures, polymorphism and unsupported upstream IR reject. This subset
does not claim a general garbage collector or the complete managed runtime.

The first ordinary workload constructs a `Fraction`, borrows it in a direct
ordinary call and computes `6*n - 5*d`. The surrounding exact-domain checker
rejects denominator zero, unsupported signs and excessive resource/precision
bounds before it calls the bridge. Its products are bounded by6,000,000, so
equality to zero is exact despite the underlying unsigned subtraction. The
mathematical domain remains `exact/1`; compiler/runtime versions are distinct
from checker/goal/revision/environment identities. Heap errors cannot create a
Verified result. A restricted arithmetic checker is not a proof-kernel port.

Initial qualification is genuine source elaboration, legacy/dynamic/layout
rejection and an LLVM20 RV64 object with only the accounted syscall unresolved.
That does not establish target execution. The current separately linked
Arithmetic image selects User-v0.2 and emits a closed genuine-IR/layout/lifetime
catalog; Store and Notebook retain User-v0.1. Older source-bound Arithmetic
artifacts retain their User-v0.1 identity. Isolated guest integration, stack
audits, controlled failure and connected course/Save/cold acceptance require
their own observations and source-bound receipts.

The independent Arithmetic image, complete notebook and matching initializer
now have actual full RV64 artifact audit PASS receipts. The arithmetic compiled
frame-chain bound is576 bytes. Their immutable prepared bundle is
`build/native/task006-managed-a1`; the connected guest campaign is separate.
See [the source/tool-bound receipt](../evidence/006-managed-records.json).
