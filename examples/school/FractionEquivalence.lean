import Lemma.School.Authoring

/-! Original source-grounded activity for the real School24 calculator service.
The theorem is a fixed cross-product equality, not a handwriting checker. -/
namespace Lemma.School.FractionEquivalence

theorem equivalentRepresentations : (10 : Nat)*6 = 5*12 := by decide

def definition : Except String Authoring.Unit := do
  let unit ← Authoring.decode (← Lean.Json.parse (include_str "fraction-equivalence-unit.json"))
  Authoring.validate unit
  return unit

end Lemma.School.FractionEquivalence

def main : IO UInt32 := do
  match Lemma.School.FractionEquivalence.definition with
  | .error error => IO.eprintln error; return 1
  | .ok unit =>
    match Lemma.School.Authoring.preview unit with
    | .error error => IO.eprintln error; return 1
    | .ok result => IO.println result.compress; return 0
