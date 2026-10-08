/-!
The source-level bounded-iteration construct recognized by `core0-v0.3`.

This definition has ordinary total Lean semantics for direct-source evaluation.
The compiler recognizes only the exact `boundedFoldU32` declaration, a canonical
literal budget no larger than `maximumBudget`, and a closed top-level callback.
The target lowering is an actual loop; this host recursion is not copied into the
guest dependency closure.
-/

namespace Lemma.Core0.Bounded

/-- Largest source budget accepted by the v0.3 checker. -/
def maximumBudget : Nat := 256

/-- Bit distinguishing semantic budget exhaustion from an ordinary `UInt32`
accumulator result. -/
def exhaustionTag : UInt64 := 0x8000000000000000

/-- Execute exactly `remaining` steps, presenting indices in ascending order. -/
def foldU32 : Nat → UInt32 → UInt32 → (UInt32 → UInt32 → UInt32) → UInt32
  | 0, _, accumulator, _ => accumulator
  | remaining + 1, index, accumulator, step =>
      foldU32 remaining (index + 1) (step index accumulator) step

/--
Fold indices `0 .. count-1` when the runtime count fits the declared static
budget.  Exceeding the budget invokes no callback and returns the high-bit tag
with the zero-extended initial accumulator in bits 0..31.  Thus exhaustion is
neither clamping nor a fabricated successful accumulator.
-/
def boundedFoldU32 (budget : Nat) (step : UInt32 → UInt32 → UInt32)
    (count initial : UInt32) : UInt64 :=
  if count.toNat ≤ budget then
    (foldU32 count.toNat 0 initial step).toUInt64
  else
    exhaustionTag ||| initial.toUInt64

/-- Number of callback invocations prescribed by the source contract. -/
def executedIterations (budget : Nat) (count : UInt32) : Nat :=
  if count.toNat ≤ budget then count.toNat else 0

@[simp] theorem foldU32_zero (index accumulator : UInt32)
    (step : UInt32 → UInt32 → UInt32) :
    foldU32 0 index accumulator step = accumulator := rfl

@[simp] theorem foldU32_succ (remaining : Nat) (index accumulator : UInt32)
    (step : UInt32 → UInt32 → UInt32) :
    foldU32 (remaining + 1) index accumulator step =
      foldU32 remaining (index + 1) (step index accumulator) step := rfl

/-- A successful call can invoke its callback no more often than its static
budget.  Semantic exhaustion executes zero callbacks. -/
theorem executedIterations_le_budget (budget : Nat) (count : UInt32) :
    executedIterations budget count ≤ budget := by
  simp only [executedIterations]
  split <;> simp_all

/-- Semantic exhaustion is an explicit tagged outcome and does not evaluate the
callback.  The theorem is parametric in `step`, making that non-observation clear. -/
theorem boundedFoldU32_exhausted (budget : Nat)
    (step : UInt32 → UInt32 → UInt32) (count initial : UInt32)
    (h : budget < count.toNat) :
    boundedFoldU32 budget step count initial = exhaustionTag ||| initial.toUInt64 := by
  simp [boundedFoldU32, Nat.not_le.mpr h]

/-- Zero runtime iterations preserve the initial accumulator as an ordinary
untagged result for every declared budget. -/
theorem boundedFoldU32_zero (budget : Nat) (step : UInt32 → UInt32 → UInt32)
    (initial : UInt32) :
    boundedFoldU32 budget step 0 initial = initial.toUInt64 := by
  simp [boundedFoldU32]

end Lemma.Core0.Bounded
