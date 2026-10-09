import Lemma.User.CapabilityABI
import Init.Data.UInt.Bitwise

/-! Local rights invariants for the exact UInt64 predicate used by the target.
These are source-level facts, not a proof of compiler refinement, memory
integrity, or the full capability/object lifecycle. Runtime audits and U tests
remain separate evidence. This model is not imported into the target image. -/
namespace Lemma.Kernel.CapabilityModel

def attenuation (source requested : UInt64) : UInt64 := source &&& requested

theorem attenuation_is_subset (source requested : UInt64) :
    attenuation source requested &&& source = attenuation source requested := by
  unfold attenuation
  rw [UInt64.and_assoc, UInt64.and_comm requested source, ← UInt64.and_assoc]
  simp

/-- The runtime accepts a requested duplicate mask only when it is already a
subset. Therefore the published requested mask cannot gain a source right. -/
theorem accepted_duplicate_subset (requested source : UInt64)
    (h : Lemma.User.CapabilityABI.rightsSubset requested source = true) :
    requested &&& source = requested := by
  simpa [Lemma.User.CapabilityABI.rightsSubset] using h

/-- Any operation authorized by an accepted attenuated mask was also authorized
by the source mask. This uses the actual target's rightsSubset predicate. -/
theorem accepted_operation_was_authorized (operation requested source : UInt64)
    (hDuplicate : Lemma.User.CapabilityABI.rightsSubset requested source = true)
    (hOperation : Lemma.User.CapabilityABI.rightsSubset operation requested = true) :
    Lemma.User.CapabilityABI.rightsSubset operation source = true := by
  have duplicate := accepted_duplicate_subset requested source hDuplicate
  have operationSubset := accepted_duplicate_subset operation requested hOperation
  have contained : operation &&& source = operation := by
    calc
      operation &&& source = (operation &&& requested) &&& source := by rw [operationSubset]
      _ = operation &&& (requested &&& source) := UInt64.and_assoc _ _ _
      _ = operation &&& requested := by rw [duplicate]
      _ = operation := operationSubset
  simp [Lemma.User.CapabilityABI.rightsSubset, contained]

end Lemma.Kernel.CapabilityModel
