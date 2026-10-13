/-! Ordinary Lean full-width submission values. The isolated server retains
canonical sign, denominator, semantic budget and overflow checks before entry.
The immutable source Array and its edited copy have independently owned roots.
-/
namespace Lemma.Mathematics.ManagedArraySubmission
@[noinline] def payload (capacity numerator denominator : UInt64) : Array UInt64 :=
  (Array.emptyWithCapacity capacity.toNat).push numerator |>.push denominator
@[noinline] def read (values : Array UInt64) (index : UInt64) : UInt64 :=
  values[index.toNat]!
@[noinline] def changed (values : Array UInt64) (index value : UInt64) : Array UInt64 :=
  values.set! index.toNat value
@[noinline] def compareFiveSix (numerator denominator : UInt64) : UInt64 :=
  let original := payload 2 numerator denominator
  let edited := changed original 0 numerator
  let n := read original 0
  let d := read edited 1
  if n * 6 = d * 5 then 1 else 2
end Lemma.Mathematics.ManagedArraySubmission
