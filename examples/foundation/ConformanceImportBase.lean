/-! Baseline declaration for the unreachable-import metamorphic check. -/

namespace Lemma.Examples.Foundation.Conformance.ImportBase

def metamorphicImport (x y : UInt32) : UInt32 :=
  ((x + y) ^^^ x) * 5

end Lemma.Examples.Foundation.Conformance.ImportBase
