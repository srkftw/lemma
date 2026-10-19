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

end Lemma.School.Recommendation
