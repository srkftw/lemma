import Std.Data.HashSet.Basic

/-! Host compiler helpers only. Iteration remains in the original array order;
no hash-table traversal contributes to emitted code or diagnostics. -/
namespace Lemma.Compiler.LLVM.NameSets

private def membership (names : Array String) : Std.HashSet String :=
  names.foldl (fun result name => result.insert name) {}

/-- Preserve the historical equal-length/mutual-membership relation, including
its behavior for repeated names. This is not multiset equality. -/
def equal (lhs rhs : Array String) : Bool :=
  if lhs.size != rhs.size then false else
  if lhs.size ≤ 8 then lhs.all rhs.contains && rhs.all lhs.contains else
  let left := membership lhs
  let right := membership rhs
  lhs.all right.contains && rhs.all left.contains

/-- First occurrences from the left array, in that same order, which also
occur on the right. The result never depends on hash iteration order. -/
def intersect (lhs rhs : Array String) : Array String := Id.run do
  let right := membership rhs
  let mut seen : Std.HashSet String := {}
  let mut result := #[]
  for name in lhs do
    if right.contains name && !seen.contains name then
      seen := seen.insert name
      result := result.push name
  return result

end Lemma.Compiler.LLVM.NameSets
