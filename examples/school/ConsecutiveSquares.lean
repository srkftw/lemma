import Lemma.School.Authoring

/-! A real authoring extension using the same decoder, validation and package
compiler as the teacher editor. The reference theorem does not check ink. -/
namespace Lemma.School.ConsecutiveSquares

theorem expansion (n : Nat) : (n+1)*(n+1) = n*n+(2*n+1) := by
  simp [Nat.add_mul, Nat.mul_add, Nat.add_assoc, Nat.two_mul]

theorem square_gap (n : Nat) : (n+1)*(n+1)-n*n = 2*n+1 := by
  rw [expansion]
  exact Nat.add_sub_cancel_left (n*n) (2*n+1)

def definition : Except String Authoring.Unit := do
  let unit ← Authoring.decode (← Lean.Json.parse (include_str "consecutive-squares-unit.json"))
  Authoring.validate unit
  return unit

end Lemma.School.ConsecutiveSquares

def main : IO UInt32 := do
  match Lemma.School.ConsecutiveSquares.definition with
  | .error error => IO.eprintln error; return 1
  | .ok unit =>
    match Lemma.School.Authoring.preview unit with
    | .error error => IO.eprintln error; return 1
    | .ok result => IO.println result.compress; return 0
