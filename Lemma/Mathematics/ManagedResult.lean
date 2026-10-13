/-! Ordinary first-order exact-comparison result values. The bounded caller
establishes the same nonnegative rational domain as exact/1 before entry.
The genuine Lean compiler emits allocation, scalar field writes, tag cases,
borrowed projections and decrement1; no Action body defines this algorithm. -/
namespace Lemma.Mathematics.ManagedResult

inductive Comparison where
  | equal (numerator denominator : UInt64)
  | unequal (difference : UInt64)

@[noinline] def compare (numerator denominator : UInt64) : Comparison :=
  if numerator * 6 = denominator * 5 then .equal numerator denominator
  else .unequal (numerator * 6 - denominator * 5)

@[noinline] def outcome (comparison : Comparison) : UInt64 :=
  match comparison with
  | .equal numerator denominator => if numerator * 6 = denominator * 5 then 1 else 2
  | .unequal difference => if difference = 0 then 1 else 2

@[noinline] def compareFiveSix (numerator denominator : UInt64) : UInt64 :=
  outcome (compare numerator denominator)

end Lemma.Mathematics.ManagedResult
