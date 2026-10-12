# Owned object arena v1

`Lemma.User.Runtime.Arena` is a bounded runtime foundation executed by ordinary
elaborated Lean through the existing checked `user-v0.1` scalar Action lowering.
It allocates an actual owned User page through syscall7 and releases it through
syscall8. It is not ordinary managed-Lean language support: the frontend still
rejects general inductive constructors, Lean arrays/strings, closures and
recursive managed programs. This contract does not close G2 or the proof kernel.

The Loader-owned User data page reserves `0x20e00..0x20e17` for phase, cancellation
and live-object count. This lies beyond the notebook's state and bounded IPC
packets (`incoming=0x20c00`, maximum256 bytes). The owned heap page is `0x400000`,
beyond the notebook's existing working pages ending at `0x32afff`. Another User
task has a separate Sv39 mapping and no authority over this page. Handles are
process-local values; they never enter a durable mathematical record or IPC
authority grant. A restarted process may have new local handle values.

The page's first128 bytes hold the arena identity `0x31414e4552414d4c`, version1
and zero reserved bytes. Thirty-one128-byte slots fill the rest of the page:

| Slot offset | Meaning |
| --- | --- |
| 0 | free0, live1, retired2 |
| 8 | generation1..`0x07ffffffffffffff` |
| 16 | references1..65535 when live |
| 24 | boxed scalar1 or byte array2 |
| 32 | box length8 or byte-array length0..64 |
| 40..63 | zero reserved |
| 64..127 | payload |

Handles are `generation << 5 | slot`. Slot31, zero generation, stale generation,
wrong tag, malformed length/reference count and nonlive slots reject before
payload access. Allocation chooses the lowest free slot. The kernel zeroes a
new owned page before mapping it; each object allocation independently zeros
its complete64-byte payload before returning a handle. Byte and aligned-word
access enforce the declared length without wrapping arithmetic. The object
count counts live allocations, not references.

Retain increments the real reference count. Release decrements it; final
release clears payload and object metadata, advances the generation and makes
the slot free. The last generation retires the slot permanently. No retain or
release operation is a no-op. These scalar boxes contain no traced references;
cycles and collection of object graphs are not admitted. The single-threaded
process may be preempted, but this API supplies no simultaneous-thread atomicity.

Cancellation blocks allocation and reads/writes. Release and destroy remain
available for cleanup. Destroy requires zero live objects and releases the
owned page. Its process control phase becomes terminal2: creating a fresh zeroed
page cannot resurrect an old generation. Process death uses the kernel's existing
owner cleanup. All runtime state resides in ordinary guest RAM; this does not
establish an omitted-state-free QEMU checkpoint or cross-backend migration.

Status236 rejects a handle/access shape;237 reports slot exhaustion;238 reports
cancellation;239 reports malformed lifetime/header state or reference overflow.
Actual allocation/quota/mapping syscall errors propagate unchanged. Entry shape checks explicitly present in the byte-array API (length, value or
word alignment) run first. Other access checks validate live state/cancellation
before handle/tag/generation; release omits the cancellation restriction.
Allocation validates the live count before selecting a free slot. No successful handle exists until allocation and initialization
have completed. Bounded folds inspect at most31 slots and clear at most14 words.
The full target audit must independently validate the resulting stack and code.

`Lemma.Mathematics.OwnedSubmission.check` allocates a56-byte temporary object
containing the original goal and six typed scalar inputs. The exact checker
reads these actual object words and computes the same admitted rational/polynomial
algorithm. The caller owns a real Box64 for the output; the worker retains a
borrowed reference, writes the exact outcome, releases its reference and returns.
The caller reads the completed box and releases both its own reference and the
coefficient object. The borrowed reference cannot be a no-op. One owned page is
reused; no result or coefficient object leaks after a check. The pure result
selector remains available to cold record validation.

A routine OOM/cancellation returns before the submission, immutable history or
learner events are changed. The notebook's existing course admission error path
reports the actual status, redraws raw ink and keeps the store and writing alive.
It does not fabricate an unexplained Indeterminate result under a sufficient
recorded work budget. The v2 record and journal formats remain unchanged. This
checker still runs inside the isolated notebook process; a separately linked
verifier and verifier-death containment remain unfinished.

Focused semantic and genuine-lowering checks are:

```sh
nix develop --no-write-lock-file --command lake build Lemma.Applications.Notebook
nix develop --no-write-lock-file --command lake env lean tests/runtime/OwnedArena.lean
nix develop --no-write-lock-file --command lake env lean tests/mathematics/ExactMath.lean
```

The fixture's OS model is test evidence, not target execution. A strict audited
RV64 build and actual guest course workflow require their own observed results.
