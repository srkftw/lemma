import Lemma.Compiler.LLVMNameSets

namespace NameSetTests
open Lemma.Compiler.LLVM

def oldEqual (lhs rhs : Array String) : Bool :=
  lhs.size == rhs.size && lhs.all rhs.contains && rhs.all lhs.contains

def oldIntersect (lhs rhs : Array String) : Array String :=
  lhs.foldl (init := #[]) fun result name =>
    if rhs.contains name then
      if result.contains name then result else result.push name
    else result

def words : Nat → Array (Array String)
  | 0 => #[#[]]
  | n+1 => (words n).flatMap fun word =>
      #["", "entry", "β"].map fun atom => word.push atom

def compare (a b : Array String) : IO Unit := do
  unless NameSets.equal a b == oldEqual a b do
    throw <| IO.userError "indexed name equality differs from historical relation"
  unless NameSets.intersect a b == oldIntersect a b do
    throw <| IO.userError "indexed intersection changed membership, order or duplicate removal"

end NameSetTests

def main : IO Unit := do
  let arrays := (List.range 5).toArray.flatMap NameSetTests.words
  unless arrays.size == 121 do throw <| IO.userError "finite corpus enumeration differs"
  for a in arrays do
    for b in arrays do NameSetTests.compare a b
  NameSetTests.compare #["a","a","b"] #["a","b","b"]
  let names := (List.range 192).toArray.map fun i => "branch." ++ toString i
  let reversed := names.reverse
  for a in #[names,reversed,names ++ names,#["missing"] ++ names] do
    for b in #[names,reversed,names.extract 63 129,#["missing"]] do
      NameSetTests.compare a b
  NameSetTests.compare (names ++ Array.replicate 192 "branch.0") (names ++ Array.replicate 192 "branch.1")
  IO.println "LLVM_NAME_SETS1:PASS 14641 finite pairs, ordered/duplicate/empty/Unicode and large reversed/sparse names; executable comparison, not a proof"
