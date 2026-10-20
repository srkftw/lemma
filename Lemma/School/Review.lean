import Lemma.School.Authoring
import Lemma.School.Model

/-! Human assessment and later-response lifecycle. Original attempts, checker
outcomes and publications are immutable; every judgment is a new human record.
The native binding presents these records and never supplies their authority. -/
namespace Lemma.School.Review
open Lean

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

def active (row : Record) : Bool :=
  !flag row.data "disabled" &&
    #["due","deferred"].contains (optionalStr row.data "status" "due")

private def original (state : State) (attempt : Record) : Except String (Record × Authoring.Unit × Authoring.Activity) := do
  let course ← nat attempt.data "course"
  let revision ← nat attempt.data "revision"
  let pub ← (state.latest "publication" s!"{course}.{revision}").toExcept "original publication absent"
  let unit ← field pub.data "definition" >>= Authoring.decode
  let activity ← (unit.activities.find? (fun a => a.id == optionalStr attempt.data "activity")).toExcept "original activity absent"
  return (pub,unit,activity)

private def access (state : State) (actor : String) (attempt : Record) (write : Bool) : Except String Unit := do
  if write then
    require (actor != attempt.actor) "human assessment requires a distinct reviewer"
    if actor != state.operator then state.authorize actor "review" attempt.actor
  else if actor != attempt.actor && actor != state.operator then
    state.authorize actor "review" attempt.actor

/-- Bind a subsequent response before accepting it. Opening a due item has no
effect; a different publication/activity or pre-due response cannot close it. -/
def admitResponse (state : State) (actor : String) (request : Json) (now : Nat) : Except String Unit := do
  let id := optionalStr request "reviewId"
  if id.isEmpty then return
  let row ← (state.latest "review" id).toExcept "original due review absent"
  require (optionalStr row.data "learner" == actor) "review belongs to another learner"
  require (active row && optionalNat row.data "due" <= now) "review is not due or is closed"
  require (optionalNat row.data "course" == optionalNat request "course" &&
    optionalNat row.data "revision" == optionalNat request "revision" &&
    optionalStr row.data "activity" == optionalStr request "activity") "review response differs from original publication/activity"
  require (optionalStr row.data "sourceAttempt" != optionalStr request "id") "review requires a subsequent response"

def linkResponse (state : State) (actor : String) (request : Json) (now outcome : Nat) : Except String State := do
  let id := optionalStr request "reviewId"
  if id.isEmpty then return state
  let row ← (state.latest "review" id).toExcept "original due review absent"
  let fields ← row.data.getObj?
  let status := if outcome == 1 then "completed" else if outcome == 4 then "awaiting-assessment" else "due"
  state.add "review" id actor now (Json.obj (fields.insert "status" (toJson status)
    |>.insert "responseAttempt" (toJson (optionalStr request "id"))
    |>.insert "assessmentScope" (toJson (if outcome == 1 then "supported exact checker" else "no completed assessment")))) row.artifacts

def handles (op : String) : Bool :=
  #["course-catalogue","reviews","review-queue","review-work","human-assess","feedback","feedback-read","review-state"].contains op

def execute (state : State) (actor : String) (request : Json) (now : Nat) : Except String (State × Json) := do
  let op ← str request "op"
  let limit := optionalNat request "limit" 20
  let after := optionalNat request "after" 0
  require (limit > 0 && limit <= 50) "page limit must be 1..50"
  match op with
  | "course-catalogue" =>
    let mut rows : Array Json := #[]
    let mut cursor := after
    let mut more := false
    for row in state.records do
      if row.kind == "publication" && row.sequence > after &&
          ((state.latest "enrollment" s!"{actor}.{optionalNat row.data "course"}.{optionalNat row.data "revision"}").any
            (fun enrollment => !flag enrollment.data "revoked")) then
        if rows.size < limit then
          let unit ← field row.data "definition" >>= Authoring.decode
          rows := rows.push (object [("course",toJson (optionalNat row.data "course")),
            ("revision",toJson (optionalNat row.data "revision")),("title",toJson unit.course.title),
            ("policy",toJson (optionalNat row.data "policy")),("artifact",toJson (optionalStr row.data "artifact")),
            ("publicationSequence",toJson row.sequence)])
          cursor := row.sequence
        else more := true
    return (state,object [("courses",toJson rows),("next",toJson cursor),("more",toJson more)])
  | "reviews" =>
    require (optionalStr request "learner" actor == actor) "due reviews belong to the admitted learner"
    let mut items : Array Json := #[]
    let mut cursor := after
    let mut more := false
    for row in state.allLatest "review" do
      if row.sequence > after && optionalStr row.data "learner" == actor && active row &&
          optionalNat row.data "due" > 0 && optionalNat row.data "due" <= now then
        if items.size < limit then
          let course ← nat row.data "course"
          let revision ← nat row.data "revision"
          let publication ← (state.latest "publication" s!"{course}.{revision}").toExcept "original due publication absent"
          let unit ← field publication.data "definition" >>= Authoring.decode
          let activity ← (unit.activities.find? (fun activity => activity.id == optionalStr row.data "activity")).toExcept "original due activity absent"
          items := items.push (object [("id",toJson row.key),("sourceAttempt",toJson (optionalStr row.data "sourceAttempt")),
            ("course",toJson course),("revision",toJson revision),("edition",toJson revision),
            ("courseTitle",toJson unit.course.title),("title",toJson unit.course.nodes[activity.node]!.title),
            ("activity",toJson activity.id),("node",toJson activity.node),("ordinal",toJson (activity.node+1)),
            ("policy",toJson (optionalNat row.data "policy")),("reviewPolicy",toJson (optionalStr row.data "reviewPolicy")),
            ("due",toJson (optionalNat row.data "due")),("status",toJson (optionalStr row.data "status" "due")),
            ("sequence",toJson row.sequence)])
          cursor := row.sequence
        else more := true
    return (state,object [("reviews",toJson items),("next",toJson cursor),("more",toJson more)])
  | "review-queue" =>
    let learner ← str request "learner"
    if actor != state.operator then state.authorize actor "review" learner
    let rows := state.records.filter (fun r => r.kind == "attempt" && r.actor == learner && r.sequence > after &&
      ((state.latest "human-assessment" r.key).isNone || flag request "includeAssessed"))
    let page := rows.extract 0 limit
    return (state,object [("attempts",toJson page),("more",toJson (decide (rows.size > limit))),
      ("next",toJson (page.back?.map (·.sequence) |>.getD after))])
  | "review-work" =>
    let id ← str request "attempt"
    let attempt ← (state.latest "attempt" id).toExcept "attempt absent"
    access state actor attempt false
    let (pub,unit,activity) ← original state attempt
    let work := (field attempt.data "request" >>= fun r => str r "observationArtifact").toOption
    let activityDecisions := state.records.filter (fun r => r.kind == "decision" && r.actor == attempt.actor && r.sequence < attempt.sequence &&
      match field r.data "input" with
      | .ok input => optionalNat input "course" == optionalNat attempt.data "course" &&
          optionalNat input "revision" == optionalNat attempt.data "revision" &&
          (field input "ask" |>.toOption).any (fun ask => optionalNat ask "task_id" == activity.node+1)
      | .error _ => false)
    let linked := field attempt.data "assistanceDecisions" >>= fromJson? (α := Array Record)
    let decisions := linked.toOption.getD activityDecisions
    return (state,object [("attempt",toJson attempt),("prompt",toJson unit.course.nodes[activity.node]!),
      ("rubric",toJson activity.assessment),("sources",toJson unit.sources),("anchors",toJson unit.anchors),
      ("publication",toJson pub),("workArtifact",toJson work),("assistance",toJson decisions),
      ("assistanceScope",toJson (if linked.isOk then "exact immutable guest-work attribution" else
        "legacy activity history; not exact work attribution")),
      ("activityAssistanceHistory",toJson activityDecisions),
      ("localToolObservations",(field attempt.data "localToolObservations").toOption.getD (toJson (#[] : Array Json))),
      ("localToolCurrentWorkExposure",toJson (flag attempt.data "localToolCurrentWorkExposure")),
      ("localToolApplicationUncertain",toJson (flag attempt.data "localToolApplicationUncertain")),
      ("localToolScope",toJson "original local advisory calculation observations; no proof or remote tutor claim"),
      ("assessments",toJson (state.records.filter (fun r => r.kind == "human-assessment" && r.key == id)))])
  | "human-assess" =>
    let id ← str request "attempt"
    let attempt ← (state.latest "attempt" id).toExcept "attempt absent"
    access state actor attempt true
    let (pub,unit,activity) ← original state attempt
    let previous := state.latest "human-assessment" id
    let version ← nat request "version"
    let expected := previous.map (·.sequence) |>.getD 0
    if let some prior := previous then
      if version == optionalNat prior.data "version" && stable prior.data == stable request then
        return (state,object [("assessment",toJson prior),("reused",toJson true)])
    require (optionalNat request "previousSequence" == expected &&
      version == (previous.map (fun r => optionalNat r.data "version") |>.getD 0)+1) "assessment version conflict; reopen current judgment"
    let disposition ← str request "disposition"
    require (#["accepted","needs-revision","clarification"].contains disposition) "unsupported human disposition"
    let comment ← str request "comment"
    require (!comment.isEmpty && comment.utf8ByteSize <= 4096) "human comment must contain 1..4096 bytes"
    let judgments : Array String ← field request "criteria" >>= fromJson?
    require (judgments.size == activity.assessment.criteria.size &&
      judgments.all (#["met","not-met","unclear"].contains ·)) "one met/not-met/unclear judgment required per original rubric criterion"
    require (disposition != "accepted" || judgments.all (· == "met")) "accepted judgment must satisfy every original rubric criterion"
    let data := object [("request",request),("learner",toJson attempt.actor),("attemptSequence",toJson attempt.sequence),
      ("version",toJson version),("previousSequence",toJson expected),("disposition",toJson disposition),
      ("comment",toJson comment),("criteria",toJson judgments),("rubric",toJson activity.assessment),
      ("publication",toJson (optionalStr pub.data "artifact")),("policy",toJson (optionalNat pub.data "policy")),
      ("scope",toJson "human-review/1; original checker result unchanged; no proof-kernel verification")]
    let mut next ← state.add "human-assessment" id actor now data attempt.artifacts
    let response := field attempt.data "request" |>.toOption
    let reviewId := response.map (fun r => optionalStr r "reviewId") |>.getD ""
    if !reviewId.isEmpty then
      let review ← (next.latest "review" reviewId).toExcept "linked review absent"
      require (optionalStr review.data "responseAttempt" == id) "review has a different subsequent response; assess its current response"
      let fields ← review.data.getObj?
      next ← next.add "review" reviewId actor now (Json.obj (fields.insert "status" (toJson (if disposition == "accepted" then "completed" else "due"))
        |>.insert "assessmentSequence" (toJson (state.records.size+1))
        |>.insert "assessmentScope" (toJson "versioned human review"))) review.artifacts
      if let some future := next.latest "review" id then
        let fields ← future.data.getObj?
        next ← next.add "review" id actor now (Json.obj (fields.insert "due" (toJson (now+unit.review.delaySeconds*1000))
          |>.insert "status" (toJson "due") |>.insert "disabled" (toJson (disposition != "accepted")))) future.artifacts
    return (next,object [("assessment",toJson (next.latest "human-assessment" id)),("reused",toJson false)])
  | "feedback" =>
    let rows := state.records.filter (fun r => r.kind == "human-assessment" &&
      optionalStr r.data "learner" == actor && r.sequence > after)
    let page := rows.extract 0 limit
    return (state,object [("feedback",toJson page),("more",toJson (decide (rows.size > limit))),
      ("next",toJson (page.back?.map (·.sequence) |>.getD after))])
  | "feedback-read" =>
    let sequence ← nat request "sequence"
    let row ← (state.records.find? (fun r => r.sequence == sequence && r.kind == "human-assessment")).toExcept "feedback absent"
    require (optionalStr row.data "learner" == actor) "feedback belongs to another learner"
    let next ← state.add "feedback-read" s!"{actor}.{sequence}" actor now (object [("sequence",toJson sequence),
      ("stage",toJson "opened-in-native-workspace; guest presentation separate")])
    return (next,toJson next.records.back!)
  | "review-state" =>
    let id ← str request "id"
    let row ← (state.latest "review" id).toExcept "review absent"
    require (optionalStr row.data "learner" == actor) "review belongs to another learner"
    let status ← str request "status"
    require (#["deferred","withdrawn"].contains status && active row) "only active review may be deferred or withdrawn"
    let reason ← str request "reason"
    require (!reason.isEmpty && reason.utf8ByteSize <= 1024) "review change requires a bounded reason"
    let fields ← row.data.getObj?
    let due := optionalNat request "due" (optionalNat row.data "due")
    require (status != "deferred" || due > now) "deferred review needs a future due time"
    let next ← state.add "review" id actor now (Json.obj (fields.insert "status" (toJson status)
      |>.insert "due" (toJson due) |>.insert "reason" (toJson reason))) row.artifacts
    return (next,toJson next.records.back!)
  | _ => throw "unsupported review operation"
where
  stable (data : Json) : Json :=
    let request := (field data "request").toOption.getD data
    match request.getObj? with | .ok fields => Json.obj (fields.erase "now") | .error _ => request

end Lemma.School.Review
