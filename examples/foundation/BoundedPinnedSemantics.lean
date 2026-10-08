import examples.foundation.BoundedConformance

/-!
Direct host-Lean probes for the source construct.  This module intentionally
does not import the custom frontend or checked evaluator.
-/

open Lemma.Examples.Foundation.Bounded

private def emit (name : String) (value : UInt64) : IO Unit :=
  IO.println s!"PINNED_BOUNDED:{name}:{value.toNat}"

def boundedPinnedSemanticsProbe : IO Unit := do
  emit "sum-zero" (sumFold 0 10)
  emit "sum-four" (sumFold 4 10)
  emit "sum-body-changed" (sumFoldChanged 4 10)
  emit "sum-exhausted" (sumFold 17 10)
  emit "nested-four" (nestedFold 4 10)
  emit "maximum" (maxBudgetFold 256 0)
  emit "maximum-plus-one" (maxBudgetFold 257 9)

#eval boundedPinnedSemanticsProbe
