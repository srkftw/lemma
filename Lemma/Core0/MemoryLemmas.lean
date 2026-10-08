import Lemma.Core0.MemoryModel

/-!
Local proof obligations for the v0.4 finite-memory model.

These theorems establish facts about the catalog and executable Lean model; they
are not a proof that generated LLVM or RV64 machine code refines that model.  The
separate lowering audit checks the emitted guard/control-flow shape and guest
tests compare observed outcomes, complete ordinary-memory post-state, and
canaries.  The model event trace remains a source/model observation rather than
a separately instrumented target trace.  That evidence
narrows but does not close the compiler-correctness gap.
-/

namespace Lemma.Core0.Memory

/-- The checked-in fixed region catalog has valid, non-wrapping physical
intervals and compatible base/width alignment.  Lowering also rejects the table
unless this executable predicate is true. -/
theorem regionTable_valid : tableValid = true := by
  simp [tableValid, regionTable, regionIntervalValid, Width.bytes,
    RegionId.scratch, RegionId.input, RegionId.output, RegionId.events,
    RegionId.image, RegionId.stack, RegionId.uart, RegionId.finisher]

/-- Proposition-level form of the lowering/model's subtraction-first bounds guard. -/
def OrderedBounds (length width offset : Nat) : Prop :=
  width ≤ length ∧ offset ≤ length - width

/-- The ordered guard establishes containment without assuming a potentially
wrapping `offset + width` test. -/
theorem orderedBounds_intervalContained {length width offset : Nat}
    (h : OrderedBounds length width offset) :
    offset + width ≤ length := by
  exact Nat.add_le_of_le_sub h.1 h.2

/-- Combining region validity with the ordered access guard keeps the complete
physical interval inside the UInt64 address space. -/
theorem orderedBounds_physicalInterval {base length width offset : Nat}
    (hRegion : base + length ≤ 2 ^ 64)
    (hAccess : OrderedBounds length width offset) :
    base + (offset + width) ≤ 2 ^ 64 := by
  have contained : offset + width ≤ length :=
    orderedBounds_intervalContained hAccess
  exact Nat.le_trans (Nat.add_le_add_left contained base) hRegion

/-- A modeled rejected store returns the same region-byte arrays and therefore
cannot modify ordinary memory or guard bytes. -/
theorem rejectedStore_preservesMemory (state : Model.State) (width : Width)
    (region : UInt8) (offset value : UInt64)
    (hRejected : (Model.accessStatus .write width region offset == Status.ok) = false)
    (result : Model.Outcome × Model.State)
    (hResult : Model.store state width region offset value = .ok result) :
    result.2.regions = state.regions := by
  simp only [Model.store, hRejected, Bool.false_eq_true, ↓reduceIte] at hResult
  simp only [Model.deniedTransition] at hResult
  cases hResult
  rfl

/-- Rejected writes preserve the complete observable event trace.  The model
records only successful physical loads/stores; guard failures are outcomes, not
memory events. -/
theorem rejectedStore_preservesEvents (state : Model.State) (width : Width)
    (region : UInt8) (offset value : UInt64)
    (hRejected : (Model.accessStatus .write width region offset == Status.ok) = false)
    (result : Model.Outcome × Model.State)
    (hResult : Model.store state width region offset value = .ok result) :
    result.2.events = state.events := by
  simp only [Model.store, hRejected, Bool.false_eq_true, ↓reduceIte] at hResult
  simp only [Model.deniedTransition] at hResult
  cases hResult
  rfl

end Lemma.Core0.Memory
