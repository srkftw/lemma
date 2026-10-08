import Lemma.Core0.IR

/-!
Small mathematical anchors for the versioned Core0 scalar profiles.

These lemmas justify local facts used by the executable model and lowering: fixed-width
normalization stays in range and is idempotent, a source shift count reduced modulo the
operand width is legal for LLVM, and every supported unsigned widening conversion is
reversed by truncation.  They do not constitute a compiler-correctness proof.
-/

namespace Lemma.Core0.ScalarLemmas

/-- The mask emitted before every fixed-width LLVM shift. -/
def shiftCountMask (ty : Ty) : Nat :=
  ty.width - 1

/-- Reduction modulo `2^width` produces a value representable at that width. -/
theorem fixedWidthNormalize_lt (width value : Nat) :
    value % (2 ^ width) < 2 ^ width := by
  exact Nat.mod_lt value (Nat.two_pow_pos width)

/-- Re-normalizing an already normalized fixed-width value has no effect. -/
theorem fixedWidthNormalize_idempotent (width value : Nat) :
    (value % (2 ^ width)) % (2 ^ width) = value % (2 ^ width) := by
  exact Nat.mod_mod value (2 ^ width)

/-- The pinned unsigned shift semantics reduce the count modulo the operand width;
this bound is the premise needed before emitting an LLVM shift instruction. -/
theorem maskedShiftCount_lt (ty : Ty) (count : Nat) :
    count % ty.width < ty.width := by
  apply Nat.mod_lt
  cases ty <;> decide

/-- For every admitted scalar width, the emitted bit mask is exactly the pinned
Lean shift-count reduction modulo the operand width. -/
theorem shiftCountMask_eq_mod (ty : Ty) (count : Nat) :
    count &&& shiftCountMask ty = count % ty.width := by
  cases ty
  · simp only [shiftCountMask, Ty.width]
    rw [Nat.mod_one, Nat.and_zero]
  · simpa [shiftCountMask, Ty.width] using
      (Nat.and_two_pow_sub_one_eq_mod count 3)
  · simpa [shiftCountMask, Ty.width] using
      (Nat.and_two_pow_sub_one_eq_mod count 5)
  · simpa [shiftCountMask, Ty.width] using
      (Nat.and_two_pow_sub_one_eq_mod count 6)

/-- Consequently, the exact emitted count is always inside LLVM's shift domain. -/
theorem shiftCountMask_lt (ty : Ty) (count : Nat) :
    count &&& shiftCountMask ty < ty.width := by
  rw [shiftCountMask_eq_mod]
  exact maskedShiftCount_lt ty count

/-- Widening a `UInt8` to `UInt32` and truncating it restores the original value. -/
theorem u8ToU32ToU8 (value : UInt8) :
    value.toUInt32.toUInt8 = value := by
  cases value with
  | ofBitVec value =>
    apply congrArg UInt8.ofBitVec
    apply BitVec.eq_of_toNat_eq
    simp [UInt8.toUInt32]

/-- Widening a `UInt8` to `UInt64` and truncating it restores the original value. -/
theorem u8ToU64ToU8 (value : UInt8) :
    value.toUInt64.toUInt8 = value := by
  cases value with
  | ofBitVec value =>
    apply congrArg UInt8.ofBitVec
    apply BitVec.eq_of_toNat_eq
    simp [UInt8.toUInt64]

/-- Widening a `UInt32` to `UInt64` and truncating it restores the original value. -/
theorem u32ToU64ToU32 (value : UInt32) :
    value.toUInt64.toUInt32 = value := by
  cases value with
  | ofBitVec value =>
    apply congrArg UInt32.ofBitVec
    apply BitVec.eq_of_toNat_eq
    simp [UInt32.toUInt64]

end Lemma.Core0.ScalarLemmas
