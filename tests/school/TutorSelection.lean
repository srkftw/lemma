import Lemma.School.Recommendation

/- Pure policy boundary tests only. Synthetic records below do not establish
worker admission; the hosted worker/authority scenario supplies that evidence. -/
open Lean Lemma.School

private def require (ok : Bool) (why : String) : Except String Unit :=
  if ok then .ok () else .error why
private def add (s : State) (kind key : String) (data : Json)
    (artifacts : Array String := #[]) : Except String State :=
  s.add kind key "owner" (s.clock+1) data artifacts
private def fixture : Except String State := do
  let s : State := {school:="a",deployment:="a",operator:="owner"}
  let s ← s.add "attempt" "independent" "alice" 1 (object [
    ("course",toJson (803:Nat)),("revision",toJson (2:Nat)),("outcome",toJson (1:Nat)),
    ("independent",toJson true),("assisted",toJson false)])
  let s ← add s "model-selection" "active" (object [("version",toJson (9001:Nat))])
  let .obj fields := Recommendation.prepare s "alice" 803 2 s.clock
    | throw "preparation shape"
  let prepared := Json.obj (fields.insert "learner" (toJson "alice")
    |>.insert "course" (toJson (803:Nat)) |>.insert "revision" (toJson (2:Nat))
    |>.insert "policy" (toJson (2:Nat)) |>.insert "activity" (toJson "practice"))
  let s ← add s "recommendation-input" "input" prepared
  let input := object [("kind",toJson "school-linear-worker/1"),("preparation",toJson "input"),
    ("learner",toJson "alice"),("course",toJson (803:Nat)),("revision",toJson (2:Nat)),("activity",toJson "practice")]
  let s ← add s "job" "job" (object [("status",toJson "completed"),("result",toJson "result"),("input",input)])
  add s "suggestion" "alice.job" (object [("learner",toJson "alice"),("course",toJson (803:Nat)),
    ("revision",toJson (2:Nat)),("policy",toJson (2:Nat)),("activity",toJson "practice"),
    ("model",toJson (9001:Nat)),("preparation",toJson "input"),("job",toJson "job"),
    ("scoreQ20",toJson (700000:Int))]) #["result","parameters"]

private def run : Except String Unit := do
  let s ← fixture
  let hint := "Compare each coefficient with the product table."
  let select := fun s learner course revision policy now text =>
    Recommendation.deliverySelection s learner "practice" course revision policy now text
  let chosen := select s "alice" 803 2 2 s.clock hint
  require (optionalStr chosen.provenance "mechanism" == "committed-rv64-selector") "committed selector not consumed"
  require (chosen.text == "Review this hint, then try practice. " ++ hint) "selected advice or original hint lost"
  require (chosen.artifacts == #["result","parameters"]) "parameter/result provenance lost"
  for result in #[select s "bob" 803 2 2 s.clock hint,
      select s "alice" 803 3 2 s.clock hint,select s "alice" 803 2 3 s.clock hint,
      select s "alice" 803 2 2 (s.clock+86400001) hint] do
    require (result.text == hint && result.artifacts.isEmpty) "other context or expired result escaped baseline"
  let rolled ← add s "model-selection" "active" (object [("version",toJson (9002:Nat))])
  require ((select rolled "alice" 803 2 2 rolled.clock hint).text == hint) "rollback retained old model advice"
  let updated ← s.add "attempt" "new-independent" "alice" (s.clock+1) (object [
    ("course",toJson (803:Nat)),("revision",toJson (2:Nat)),("outcome",toJson (2:Nat)),
    ("independent",toJson true),("assisted",toJson false)])
  require ((select updated "alice" 803 2 2 updated.clock hint).text == hint) "new independent evidence did not invalidate input"
  let long := String.ofList (List.replicate 190 'x')
  require ((select s "alice" 803 2 2 s.clock long).text == long) "long hint was truncated or discarded"
  let stopped ← add s "job" "job" (object [("status",toJson "cancelled")])
  require ((select stopped "alice" 803 2 2 stopped.clock hint).text == hint) "uncommitted job affected help"
  let empty : State := {school:="a",deployment:="a",operator:="owner"}
  require ((select empty "alice" 803 2 2 0 hint).text == hint) "missing model/evidence lost authored baseline"

def main : IO Unit :=
  match run with
  | .ok _ => IO.println "PASS actual Lean tutor-selection policy; synthetic records are unit fixtures"
  | .error why => throw (IO.userError why)
