/-! Semantically identical relocated declaration for the module metamorphic check. -/

namespace Lemma.Examples.Foundation.Conformance.MovedB

def metamorphicModule (x y z : UInt64) : UInt64 :=
  let sum := x + y
  (sum ^^^ z) * 3

end Lemma.Examples.Foundation.Conformance.MovedB
