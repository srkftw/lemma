import Std.Data.HashMap

/-!
The extra host library is intentionally unreachable from the scalar root below.
The Core0 dependency closure must therefore match the baseline root's behavior
without admitting any `HashMap` implementation into target code.
-/

namespace Lemma.Examples.Foundation.Conformance.ImportExtra

def metamorphicImport (x y : UInt32) : UInt32 :=
  ((x + y) ^^^ x) * 5

end Lemma.Examples.Foundation.Conformance.ImportExtra
