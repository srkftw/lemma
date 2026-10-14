/-! Exact rational cross-products through ordinary dynamically selected Lean
closures. The Action caller establishes canonical/sign/domain/budget bounds
before this ordinary source can authorize a mathematical outcome. -/
namespace Lemma.Mathematics.ManagedClosureSubmission

@[noinline] def product (capture factor : UInt64) : UInt64 := capture * factor

@[noinline] def select (selector numerator denominator : UInt64) : UInt64 → UInt64 :=
  if selector = 0 then product numerator else product denominator

@[noinline] def apply (function : UInt64 → UInt64) (factor : UInt64) : UInt64 := function factor

@[noinline] def compareProducts (selector : UInt64) (first second : UInt64 → UInt64) : UInt64 :=
  if selector = 0 then
    if apply first 6 = apply second 5 then 1 else 2
  else if apply first 5 = apply second 6 then 1 else 2

/-- Both execution paths compare exactly n*6 and d*5. Selection depends on the
actual submitted numerator; no sample of a polynomial or floating point enters. -/
@[noinline] def compareFiveSix (numerator denominator : UInt64) : UInt64 :=
  let selector := numerator &&& 1
  let first := select selector numerator denominator
  let second := select (selector ^^^ 1) numerator denominator
  compareProducts selector first second

end Lemma.Mathematics.ManagedClosureSubmission
