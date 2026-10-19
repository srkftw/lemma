import Lemma.School.Model
import Lemma.School.Digest

/-! Learner preferences and challenges are append-only declarations. They name
the exact original evidence and publication policy; they neither rewrite that
evidence nor confer a different mathematical verdict or assistance grant. -/
namespace Lemma.School.LearnerChoice
open Lean

structure Input where
  op : String
  id : String
  learner : String
  course : Nat
  revision : Nat
  policy : Nat
  reason : String
  referenceKind : String
  reference : String
  newGoal : Option String := none
  deriving ToJson

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

private def authorize (state : State) (actor learner action : String) : Except String Unit := do
  require (validId learner) "invalid learner choice owner"
  if actor != learner then state.authorize actor action learner

private def fields (request : Json) (allowed : Array String) : Except String Unit := do
  for (name,_) in (← request.getObj?).toList do
    require (allowed.contains name) s!"unsupported learner choice field {name}"

private def decode (actor : String) (request : Json) : Except String Input := do
  let op ← str request "op"
  require (#["goal-set","interpretation-challenge","suggestion-override"].contains op)
    "unsupported learner choice operation"
  fields request (#["op","school","actor","now","id","learner","course","revision","policy",
    "reason","referenceKind","reference"] ++ if op == "goal-set" then #["newGoal"] else #[])
  let learner ← match field request "learner" with
    | .ok value => value.getStr?
    | .error _ => pure actor
  let newGoal : Option String ← if op == "goal-set" then
      (str request "newGoal").map some
    else pure none
  let input : Input := {
    op, id := ← str request "id", learner, course := ← nat request "course",
    revision := ← nat request "revision", policy := ← nat request "policy",
    reason := ← str request "reason", referenceKind := ← str request "referenceKind",
    reference := ← str request "reference",
    newGoal }
  require (validId input.id && validId input.learner) "invalid learner choice request identity"
  require (input.course > 0 && input.course ≤ 65535 && input.revision > 0 && input.revision ≤ 0xffffffff)
    "learner choice publication outside supported course profile"
  require (input.policy > 0 && input.policy ≤ 0x7ffffffffffffffe) "invalid learner choice policy version"
  require (!input.reason.trimAscii.toString.isEmpty && input.reason.utf8ByteSize ≤ 1024)
    "learner choice reason must contain 1..1024 UTF-8 bytes"
  require (#["attempt","suggestion"].contains input.referenceKind &&
    !input.reference.isEmpty && input.reference.utf8ByteSize ≤ 256)
    "learner choice requires a bounded attempt or suggestion reference"
  if let some goal := input.newGoal then
    require (!goal.trimAscii.toString.isEmpty && goal.utf8ByteSize ≤ 512)
      "learner goal must contain 1..512 UTF-8 bytes"
  if op == "suggestion-override" then
    require (input.referenceKind == "suggestion") "recommendation override requires a suggestion reference"
  return input

private def publication (state : State) (input : Input) : Except String Record := do
  let row ← (state.latest "publication" s!"{input.course}.{input.revision}").toExcept
    "learner choice publication absent"
  require ((← nat row.data "policy") == input.policy) "learner choice publication policy differs"
  require ((state.latest "enrollment" s!"{input.learner}.{input.course}.{input.revision}").isSome)
    "learner choice owner is not enrolled in this publication"
  return row

private def reference (state : State) (input : Input) : Except String Record := do
  let row ← (state.latest input.referenceKind input.reference).toExcept "learner choice original reference absent"
  let owner ← if input.referenceKind == "attempt" then pure row.actor else str row.data "learner"
  require (owner == input.learner) "learner choice original belongs to another learner"
  require ((← nat row.data "course") == input.course && (← nat row.data "revision") == input.revision)
    "learner choice original publication differs"
  require ((← nat row.data "policy") == input.policy) "learner choice original policy differs"
  if input.op == "suggestion-override" then
    require (flag row.data "overrideAllowed") "original suggestion forbids override"
  return row

/-- The request ID is scoped by an unambiguous school/learner tuple. Time is
excluded from normalized request identity, so an acknowledged choice can be
retried later without appending another declaration. Current authorization and
enrollment still precede that retry. -/
def apply (state : State) (actor : String) (now : Nat) (request : Json) : Except String (State × Record) := do
  require ((← state.checkSchool request) == actor) "learner choice actor differs from request"
  let input ← decode actor request
  authorize state actor input.learner "correct"
  let publication ← publication state input
  let key := Digest.sha256String (toJson #[state.school,input.learner,input.id]).compress
  if let some old := state.latest "learner-choice" key then
    require (old.actor == actor && (← field old.data "request") == toJson input)
      "learner choice request idempotency conflict"
    return (state,old)
  let original ← reference state input
  let artifacts := (publication.artifacts ++ original.artifacts).foldl (fun refs digest =>
    if refs.contains digest then refs else refs.push digest) (#[] : Array String)
  let data := object [
    ("schema",toJson "lemma-learner-choice/1"),("request",toJson input),
    ("op",toJson input.op),("learner",toJson input.learner),
    ("course",toJson input.course),("revision",toJson input.revision),("policy",toJson input.policy),
    ("reason",toJson input.reason),("newGoal",toJson input.newGoal),
    ("original",object [("kind",toJson original.kind),("key",toJson original.key),
      ("sequence",toJson original.sequence),("actor",toJson original.actor),
      ("recordDigest",toJson (Digest.sha256String (toJson original).compress))]),
    ("effect",toJson (if input.op == "goal-set" then
      "declared learner preference; published course requirements and assessment remain unchanged"
      else if input.op == "interpretation-challenge" then
      "learner requests reconsideration; original observation, checker and interpretation are retained"
      else "learner overrides a permitted recommendation; no checker result or assistance permission changes"))]
  let next ← state.add "learner-choice" key actor now data artifacts
  return (next,next.records.back!)

/-- Inspectable declaration history. A client can project the latest declared
goal from this ordered history; no private peer evidence is exposed by default. -/
def query (state : State) (actor : String) (request : Json) : Except String (Array Record) := do
  require ((← state.checkSchool request) == actor) "learner choice actor differs from request"
  fields request #["op","school","actor","now","learner"]
  require ((← str request "op") == "learner-choices") "unsupported learner choice query"
  let learner ← match field request "learner" with
    | .ok value => value.getStr?
    | .error _ => pure actor
  authorize state actor learner "read"
  return state.records.filter (fun row => row.kind == "learner-choice" && optionalStr row.data "learner" == learner)

end Lemma.School.LearnerChoice
