import Lemma.School.LearnerChoice
open Lean Lemma.School

/-! Deliberately synthetic pure component fixture. Native API tests use genuine
published courses and exact-checker attempts. The numerical job checker exercises
the separate actual-worker suggestion path; this fixture does not claim one. -/
private def fixture : Except String State := do
  let state : State := { school := "school-a", deployment := "fixture", operator := "owner" }
  let data := object [("course",toJson (1:Nat)),("revision",toJson (1:Nat)),("policy",toJson (1:Nat))]
  let artifact := Digest.sha256String "synthetic component fixture artifact"
  let state ← state.add "publication" "1.1" "owner" 1 data #[artifact]
  let state ← state.add "enrollment" "learner.1.1" "owner" 2 Json.null
  let state ← state.add "attempt" "original-attempt" "learner" 3 data #[artifact]
  let suggestion := object [("course",toJson (1:Nat)),("revision",toJson (1:Nat)),
    ("policy",toJson (1:Nat)),("learner",toJson "learner"),("overrideAllowed",toJson true),
    ("origin",toJson "deliberately synthetic pure component fixture")]
  let state ← state.add "suggestion" "synthetic-suggestion" "owner" 4 suggestion #[artifact]
  state.add "suggestion" "synthetic-forbidden" "owner" 5
    (object [("course",toJson (1:Nat)),("revision",toJson (1:Nat)),("policy",toJson (1:Nat)),
      ("learner",toJson "learner"),("overrideAllowed",toJson false)]) #[artifact]

private def request (op id kind reference : String) : Json := object <|
  [("op",toJson op),("school",toJson "school-a"),("actor",toJson "learner"),
   ("id",toJson id),("learner",toJson "learner"),("course",toJson (1:Nat)),
   ("revision",toJson (1:Nat)),("policy",toJson (1:Nat)),("reason",toJson "I choose a different approach"),
   ("referenceKind",toJson kind),("reference",toJson reference)] ++
  if op == "goal-set" then [("newGoal",toJson "Reconstruct the distributive argument independently")] else []

private def change (json : Json) (key : String) (value : Json) : Json :=
  match json.getObj? with | .ok fields => .obj (fields.insert key value) | .error _ => json

def main : IO Unit := do
  let state ← IO.ofExcept fixture
  let goal := request "goal-set" "goal" "attempt" "original-attempt"
  let challenge := request "interpretation-challenge" "challenge" "attempt" "original-attempt"
  let override := request "suggestion-override" "override" "suggestion" "synthetic-suggestion"
  let (next,goalRow) ← IO.ofExcept (LearnerChoice.apply state "learner" 6 goal)
  let (next,challengeRow) ← IO.ofExcept (LearnerChoice.apply next "learner" 7 challenge)
  let (next,overrideRow) ← IO.ofExcept (LearnerChoice.apply next "learner" 8 override)
  let (retried,old) ← IO.ofExcept (LearnerChoice.apply next "learner" 99 (change goal "now" (toJson (99:Nat))))
  let query := object [("op",toJson "learner-choices"),("school",toJson "school-a"),("actor",toJson "learner")]
  let choices ← IO.ofExcept (LearnerChoice.query next "learner" query)
  let grant (action : String) := object [("subject",toJson "teacher"),("action",toJson action),
    ("resource",toJson "learner"),("revoked",toJson false)]
  let readable ← IO.ofExcept (next.add "grant" "read-grant" "owner" 9 (grant "read"))
  let writable ← IO.ofExcept (readable.add "grant" "correct-grant" "owner" 10 (grant "correct"))
  let teacherGoal := change (change goal "actor" (toJson "teacher")) "id" (toJson "teacher-goal")
  let (_,teacherRow) ← IO.ofExcept (LearnerChoice.apply writable "teacher" 11 teacherGoal)
  let teacherQuery := change (change query "actor" (toJson "teacher")) "learner" (toJson "learner")
  let checks : List (String × Json) := [
    ("all-three-operations",toJson (choices.size == 3 && optionalStr goalRow.data "op" == "goal-set" &&
      optionalStr challengeRow.data "op" == "interpretation-challenge" && optionalStr overrideRow.data "op" == "suggestion-override")),
    ("original-prefix-unchanged",toJson ((next.records.extract 0 state.records.size).map toJson == state.records.map toJson)),
    ("retry-time-excluded-no-duplicate",toJson (retried.records.size == next.records.size && toJson old == toJson goalRow)),
    ("artifact-closure-retained",toJson (overrideRow.artifacts == state.records[0]!.artifacts)),
    ("original-reference-exact",toJson ((field overrideRow.data "original" >>= fun r => nat r "sequence").toOption == some 4)),
    ("read-only-cannot-write",toJson !(LearnerChoice.apply readable "teacher" 10 teacherGoal).isOk),
    ("read-grant-can-read",toJson (LearnerChoice.query readable "teacher" teacherQuery).isOk),
    ("correct-grant-preserves-actor",toJson (teacherRow.actor == "teacher" && optionalStr teacherRow.data "learner" == "learner")),
    ("correct-without-read-cannot-read",toJson !(LearnerChoice.query
      {writable with records := writable.records.filter (fun r => r.key != "read-grant")} "teacher" teacherQuery).isOk),
    ("forbidden-override-rejected",toJson !(LearnerChoice.apply state "learner" 6
      (change override "reference" (toJson "synthetic-forbidden"))).isOk),
    ("attempt-is-not-suggestion",toJson !(LearnerChoice.apply state "learner" 6
      (request "suggestion-override" "bad" "attempt" "original-attempt")).isOk),
    ("peer-evidence-rejected",toJson !(LearnerChoice.apply state "other" 6
      (change (change challenge "actor" (toJson "other")) "learner" (toJson "other"))).isOk),
    ("idempotency-content-conflict",toJson !(LearnerChoice.apply next "learner" 9
      (change goal "reason" (toJson "different reason"))).isOk),
    ("policy-mismatch-rejected",toJson !(LearnerChoice.apply state "learner" 6 (change goal "policy" (toJson (2:Nat)))).isOk),
    ("unbounded-goal-rejected",toJson !(LearnerChoice.apply state "learner" 6
      (change goal "newGoal" (toJson (String.ofList (List.replicate 513 'x'))))).isOk),
    ("blank-reason-rejected",toJson !(LearnerChoice.apply state "learner" 6 (change goal "reason" (toJson "  \n"))).isOk),
    ("unknown-field-rejected",toJson !(LearnerChoice.apply state "learner" 6 (change goal "changeChecker" (toJson true))).isOk)]
  IO.println (Json.mkObj checks).compress
