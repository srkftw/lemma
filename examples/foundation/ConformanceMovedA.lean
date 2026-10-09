/-! First placement of the module-reorganization metamorphic root. -/

namespace Lemma.Examples.Foundation.Conformance.MovedA

def metamorphicModule (x y z : UInt64) : UInt64 :=
  let sum := x + y
  (sum ^^^ z) * 3

end Lemma.Examples.Foundation.Conformance.MovedA
