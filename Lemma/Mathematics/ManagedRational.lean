/-! Ordinary Lean source for the initial managed record workload.
The caller establishes the exact/1 operand/domain bounds before entering this
function. Its ordinary structures and calls pass through genuine Lean IR,
checked object layout/lifetime lowering, LLVM and the owned User-page arena. -/
namespace Lemma.Mathematics.ManagedRational

structure Fraction where
  numerator : UInt64
  denominator : UInt64

@[noinline] def make (numerator denominator : UInt64) : Fraction :=
  ⟨numerator, denominator⟩

@[noinline] def differenceFromFiveSix (submitted : Fraction) : UInt64 :=
  submitted.numerator * 6 - 5 * submitted.denominator

/-- Under the caller's nonnegative bounded domain, zero means exact equality
to 1/2 + 1/3. Every product is <=6,000,000. Unsigned subtraction can wrap for
unequal values but cannot produce zero except when these exact products agree.
Zero denominator and sign/magnitude validation remain explicit caller policy. -/
@[noinline] def compareFiveSix (numerator denominator : UInt64) : UInt64 :=
  differenceFromFiveSix (make numerator denominator)

end Lemma.Mathematics.ManagedRational
