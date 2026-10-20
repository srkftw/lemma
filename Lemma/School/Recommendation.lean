import Lemma.School.Model

/-! Bounded preparation for the existing Q10 review scorer. It consumes actual
independent attempts and separately identified exact/human assessments. Missing
evidence selects the authored baseline; it is never imputed as a correct answer. -/
namespace Lemma.School.Recommendation
open Lean

def prepare (state : State) (learner : String) (course revision now : Nat) : Json := Id.run do
  let mut evidence := #[]
  let mut errors := 0
  let mut latestAvailable := 0
  for attempt in state.records.toList.reverse do
    if evidence.size < 8 && attempt.kind == "attempt" && attempt.actor == learner &&
        optionalNat attempt.data "course" == course && optionalNat attempt.data "revision" == revision &&
        flag attempt.data "independent" && !flag attempt.data "assisted" then
      let outcome := optionalNat attempt.data "outcome"
      let human := state.latest "human-assessment" attempt.key
      let humanDisposition := human.map (fun r => optionalStr r.data "disposition") |>.getD ""
      let exact := outcome == 1 || outcome == 2
      if exact || #["accepted","needs-revision"].contains humanDisposition then
        let humanSequence := if exact then 0 else human.map (·.sequence) |>.getD 0
        let available := max attempt.time (if exact then attempt.time else human.map (·.time) |>.getD attempt.time)
        latestAvailable := max latestAvailable available
        let error := if exact then outcome == 2 else humanDisposition == "needs-revision"
        if error then errors := errors+1
        evidence := evidence.push (object [("attempt",toJson attempt.key),("attemptSequence",toJson attempt.sequence),
          ("assessmentSequence",toJson humanSequence),("scope",toJson (if exact then "exact typed outcome" else "versioned human judgment")),
          ("availableAt",toJson available),("error",toJson error)])
  let mask := if evidence.isEmpty then 0 else 3
  let errorRate := if evidence.isEmpty then 0 else errors*1024/evidence.size
  let gap := if evidence.isEmpty then 0 else min 1024 ((now-latestAvailable)*1024/604800000)
  return object [("schema",toJson "lemma-review-input/1"),("features",toJson #[errorRate,gap]),
    ("presenceMask",toJson mask),("independentSamples",toJson evidence.size),("evidence",toJson evidence),
    ("capturedAt",toJson now),("availability",toJson "only already available independent assessments"),
    ("missingness",toJson (if mask == 0 then "no independent assessed work; do not run model" else "both declared features present")),
    ("baseline",toJson "use the permitted authored example; learner controls practice and review"),
    ("scope",toJson "bounded review selector input; human judgment stays human; no mastery or learning-effect claim")]

/-- The numerical result chooses a small practice action. It never supplies a
mathematical answer or changes the authored hint, checker or assessment. -/
structure DeliverySelection where
  text : String
  provenance : Json
  artifacts : Array String := #[]

private def baseline (hint reason : String) : DeliverySelection := {
  text := hint
  provenance := object [("schema",toJson "lemma-tutor-selection/1"),
    ("mechanism",toJson "authored-baseline"),("reason",toJson reason)] }

/-- Consume only an already committed, explicitly selected worker result for
this learner and immutable activity. A new independent assessment invalidates
its input; absent evidence, rollback, expiry or a long hint retains the exact
authored baseline. The one-day advisory lifetime uses school scheduling time,
so unknown offline downtime follows the authority's existing freeze policy. -/
def deliverySelection (state : State) (learner activity : String)
    (course revision policy now : Nat) (hint : String) : DeliverySelection := Id.run do
  let some selection := state.latest "model-selection" "active"
    | return baseline hint "no selected numerical model"
  let some row := state.records.toList.reverse.find? (fun r => r.kind == "suggestion" &&
      optionalStr r.data "learner" == learner && optionalStr r.data "activity" == activity &&
      optionalNat r.data "course" == course && optionalNat r.data "revision" == revision &&
      optionalNat r.data "policy" == policy)
    | return baseline hint "no committed suggestion for this activity"
  if now < row.time || row.time + 86400000 < now then
    return baseline hint "suggestion outside its scheduling-time lifetime"
  let model := optionalNat row.data "model"
  if model == 0 || optionalNat selection.data "version" != model then
    return baseline hint "suggestion model is no longer selected"
  let some preparation := state.latest "recommendation-input" (optionalStr row.data "preparation")
    | return baseline hint "immutable independent input absent"
  if optionalStr preparation.data "learner" != learner ||
      optionalStr preparation.data "activity" != activity ||
      optionalNat preparation.data "course" != course || optionalNat preparation.data "revision" != revision ||
      optionalNat preparation.data "policy" != policy || optionalNat preparation.data "presenceMask" != 3 then
    return baseline hint "independent input missing or belongs to another context"
  let current := prepare state learner course revision now
  if optionalNat current "presenceMask" != 3 ||
      (field current "evidence").toOption != (field preparation.data "evidence").toOption then
    return baseline hint "independent assessed evidence changed"
  let some job := state.latest "job" (optionalStr row.data "job")
    | return baseline hint "committed numerical job absent"
  let input := (field job.data "input").toOption.getD Json.null
  if optionalStr job.data "status" != "completed" ||
      optionalStr input "kind" != "school-linear-worker/1" ||
      optionalStr input "preparation" != preparation.key ||
      optionalStr input "learner" != learner || optionalStr input "activity" != activity ||
      optionalNat input "course" != course || optionalNat input "revision" != revision ||
      !(row.artifacts.contains (optionalStr job.data "result")) then
    return baseline hint "committed result provenance differs"
  let some score := (field row.data "scoreQ20" >>= Json.getInt?).toOption
    | return baseline hint "numerical score absent"
  let action := if score >= 524288 then "practice" else "reconstruct"
  let promptPrefix := if action == "practice" then "Review this hint, then try practice. "
    else "Try reconstruction, then compare this hint. "
  let text := promptPrefix ++ hint
  if hint.isEmpty || text.toUTF8.size > 196 then
    return baseline hint "authored hint leaves no room in the admitted text packet"
  return { text, artifacts := row.artifacts, provenance := object [
    ("schema",toJson "lemma-tutor-selection/1"),("mechanism",toJson "committed-rv64-selector"),
    ("suggestion",toJson row.key),("suggestionSequence",toJson row.sequence),
    ("job",toJson job.key),("result",toJson (optionalStr job.data "result")),
    ("model",toJson model),("preparation",toJson preparation.key),("scoreQ20",toJson score),
    ("action",toJson action),("overrideAllowed",toJson true),
    ("scope",toJson "practice advice; authored hint retained; no mathematical verification or learning-effect claim")] }

end Lemma.School.Recommendation
