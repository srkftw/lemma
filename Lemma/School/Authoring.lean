import Lean
import Lemma.Courses.Package
import Lemma.School.SourceRegistry

/-! Declarative teacher JSON and Lean definitions share this representation.
Compilation invokes the existing course package encoder/guest decoder contract;
there is no effectful extension execution or separate visual-editor curriculum. -/
namespace Lemma.School.Authoring
open Lean
open Lemma.Courses

deriving instance ToJson, FromJson for Package.Goal
deriving instance ToJson, FromJson for Package.Kind
deriving instance ToJson, FromJson for Package.Node
deriving instance ToJson, FromJson for Package.Course

inductive ActivityKind where
  | preparation | definition | routine | invalidArgument | independentReasoning | transfer | review
  deriving BEq, Repr, ToJson, FromJson, Inhabited

inductive Assistance where
  | none | hint | worked
  deriving BEq, Repr, ToJson, FromJson, Inhabited

structure Assessment where
  checker : String
  criteria : Array String
  independent : Bool
  referenceTheorem : Option String := none
  deriving Repr, ToJson, FromJson

structure Activity where
  id : String
  node : Nat
  kind : ActivityKind
  goal : Package.Goal
  assistance : Assistance
  assessment : Assessment
  deriving Repr, ToJson, FromJson

inductive RelationKind where
  | prerequisite | related | equivalence | review
  deriving BEq, Repr, ToJson, FromJson, Inhabited

structure Relation where
  fromActivity : String
  toActivity : String
  kind : RelationKind
  origin : String
  confidencePermille : Option Nat := none
  reviewed : Bool := false
  reviewHistory : Array String := #[]
  deriving Repr, ToJson, FromJson

structure ReviewPolicy where
  version : String
  delaySeconds : Nat
  activityId : String
  uncertainty : String
  deriving Repr, ToJson, FromJson

structure Unit where
  format : String := "lemma-school-unit/1"
  course : Package.Course
  learningGoals : Array String
  notationGuide : Array String
  sources : SourceRegistry.Registry
  anchors : Array SourceRegistry.Anchor
  activities : Array Activity
  relations : Array Relation
  review : ReviewPolicy
  deriving Repr, ToJson, FromJson

private def rejectUnknown : Nat → Json → Json → String → Except String _root_.Unit
  | 0, _, _, path => .error s!"authoring JSON nesting exceeds editor budget at {path}"
  | fuel+1, supplied, canonical, path => do
    match supplied, canonical with
    | .obj fields, .obj allowed =>
      for (key,value) in fields.toList do
        let expected ← match allowed.get? key with
          | some found => pure found
          | none => throw s!"unsupported authoring construct at {path}.{key}; preserve it before changing editors"
        rejectUnknown fuel value expected (path ++ "." ++ key)
    | .arr values, .arr expected =>
      if values.size != expected.size then throw s!"authoring array shape differs at {path}"
      for index in [:values.size] do
        rejectUnknown fuel values[index]! expected[index]! s!"{path}[{index}]"
    | _, _ => pure ()

/-- Diagnose fields an editor/compiler cannot represent instead of silently
losing them through a permissive generic JSON decoder. Missing optional fields
retain their declared defaults; supported constructs round-trip canonically. -/
def decode (value : Json) : Except String Unit := do
  let unit : Unit ← fromJson? value
  rejectUnknown 64 value (toJson unit) "unit"
  return unit

private def require (condition : Bool) (message : String) : Except String _root_.Unit :=
  if condition then .ok () else .error message

private def prerequisiteCycle (relations : Array Relation) (start : String) : Bool := Id.run do
  let mut frontier := #[start]
  let mut visited : Array String := #[]
  for _ in [:relations.size+1] do
    let mut next := #[]
    for current in frontier do
      for edge in relations do
        if edge.kind == .prerequisite && edge.fromActivity == current then
          if edge.toActivity == start then return true
          if !visited.contains edge.toActivity && !next.contains edge.toActivity then next := next.push edge.toActivity
      visited := visited.push current
    frontier := next
  return false

/-- Actionable validation precedes preview, compilation and publication. Related
and review edges may cycle; only hard prerequisites are required acyclic. -/
def validate (unit : Unit) : Except String _root_.Unit := do
  require (unit.format == "lemma-school-unit/1") "unsupported unit format; preserve unsupported editor constructs instead of dropping them"
  require (!unit.learningGoals.isEmpty && unit.learningGoals.size ≤ 32) "unit needs 1..32 learning goals"
  require (unit.learningGoals.all (fun goal => !goal.isEmpty)) "learning goal is empty"
  require (unit.notationGuide.size ≤ 32 && unit.notationGuide.all (fun text => text.utf8ByteSize ≤ 512)) "notation exceeds authoring budget"
  require (unit.anchors.size ≤ 128 && unit.relations.size ≤ 256) "anchor/relation count exceeds authoring budget"
  SourceRegistry.validate unit.sources
  let mut anchorIds : Array String := #[]
  for anchor in unit.anchors do
    SourceRegistry.validateAnchor unit.sources anchor
    require (!anchorIds.contains anchor.id) s!"duplicate anchor: {anchor.id}"
    anchorIds := anchorIds.push anchor.id
  require (!unit.activities.isEmpty && unit.activities.size ≤ 16) "unit needs 1..16 activities"
  let mut activityIds : Array String := #[]
  let mut activityNodes : Array Nat := #[]
  for activity in unit.activities do
    require (!activity.id.isEmpty && !activityIds.contains activity.id) s!"duplicate or empty activity: {activity.id}"
    require (activity.node < unit.course.nodes.size) s!"activity {activity.id}: node index out of range"
    require (!activityNodes.contains activity.node) s!"activity {activity.id}: another activity already owns this node"
    activityIds := activityIds.push activity.id
    activityNodes := activityNodes.push activity.node
    let node := unit.course.nodes[activity.node]!
    require (anchorIds.contains node.sourceAnchor) s!"activity {activity.id}: missing source anchor {node.sourceAnchor}"
    require (!activity.assessment.criteria.isEmpty) s!"activity {activity.id}: assessment criteria missing"
    require (activity.assessment.criteria.all (fun text => !text.isEmpty)) s!"activity {activity.id}: empty assessment criterion"
    if activity.assessment.independent then
      require (activity.assistance == .none) s!"activity {activity.id}: independent assessment forbids answer-generation assistance"
      require node.hint.isEmpty s!"activity {activity.id}: independent node contains a public hint"
      require node.worked.isEmpty s!"activity {activity.id}: independent node contains a public worked solution"
    match activity.goal with
    | .fractionAddition => require (activity.assessment.checker == "lemma-exact/1:fractionAddition") s!"activity {activity.id}: incompatible exact fraction checker"
    | .binomialSquare => require (activity.assessment.checker == "lemma-exact/1:binomialSquare") s!"activity {activity.id}: incompatible exact polynomial checker"
    | .unsupported => require (activity.assessment.checker == "teacher-review/1") s!"activity {activity.id}: unsupported mathematics requires explicit teacher review"
    if let .exercise goal := node.kind then
      require (goal == activity.goal) s!"activity {activity.id}: package/checker goal mismatch"
  for relation in unit.relations do
    require (activityIds.contains relation.fromActivity && activityIds.contains relation.toActivity)
      s!"relation {relation.fromActivity}->{relation.toActivity}: unknown activity"
    require (!relation.origin.isEmpty) "curricular relation needs origin"
    if let some confidence := relation.confidencePermille then
      require (confidence ≤ 1000) "relation confidence must be 0..1000 permille"
    if relation.kind == .prerequisite then
      require relation.reviewed s!"hard prerequisite {relation.fromActivity}->{relation.toActivity}: review required"
      require (!prerequisiteCycle unit.relations relation.fromActivity) s!"hard prerequisite cycle at {relation.fromActivity}"
  require (activityNodes.size == unit.course.nodes.size) "every guest node requires exactly one activity/assessment policy"
  for relation in unit.relations do
    if relation.kind == .prerequisite then
      let source ← match unit.activities.find? (fun activity => activity.id == relation.fromActivity) with
        | some activity => pure activity
        | none => throw "prerequisite source activity is missing"
      let target ← match unit.activities.find? (fun activity => activity.id == relation.toActivity) with
        | some activity => pure activity
        | none => throw "prerequisite target activity is missing"
      require ((unit.course.nodes[target.node]!).logicalPrerequisites.contains source.node)
        s!"hard prerequisite {relation.fromActivity}->{relation.toActivity} is absent from the compiled guest node"
  for target in unit.activities do
    for sourceNode in (unit.course.nodes[target.node]!).logicalPrerequisites do
      let source ← match unit.activities.find? (fun activity => activity.node == sourceNode) with
        | some activity => pure activity
        | none => throw s!"node {sourceNode} has no activity policy"
      require (unit.relations.any (fun relation => relation.kind == .prerequisite &&
        relation.fromActivity == source.id && relation.toActivity == target.id))
        s!"compiled prerequisite {source.id}->{target.id} needs reviewed authoring provenance"
  require (unit.review.version == "lemma-review-schedule/1" && unit.review.delaySeconds > 0 && unit.review.delaySeconds ≤ 31536000)
    "review policy requires supported version and delay 1..31536000 seconds"
  require (activityIds.contains unit.review.activityId) "scheduled review activity does not exist"
  require (!unit.review.uncertainty.isEmpty) "review policy must disclose estimate uncertainty"
  let review ← match unit.activities.find? (fun activity => activity.id == unit.review.activityId) with
    | some activity => pure activity
    | none => throw "scheduled review activity does not exist"
  require (review.kind == .review) "scheduled review must point to a review activity"
  match Package.encode unit.course with
  | .ok _ => pure ()
  | .error error => throw error.render

def toPackage (unit : Unit) : Except String Package.Course := do
  validate unit
  return unit.course

def compile (unit : Unit) : Except String ByteArray := do
  validate unit
  match Package.encode unit.course with
  | .ok bytes => return bytes
  | .error error => throw error.render

/-- Preview and teacher editing consume precisely the definition compiled above. -/
def preview (unit : Unit) : Except String Json := do
  let bytes ← compile unit
  return Json.mkObj [("definition", toJson unit), ("packageBytes", toJson bytes.size),
    ("packageSha256", toJson (Digest.sha256Bytes bytes)),
    ("scope", toJson "Hosted Lean authoring; exact existing guest package format; informal proofs require teacher review")]

/-- Assessment rubrics/reference theorems are withheld. Independent activities
admit no tutor context. Callers must still enforce school/learner grants. -/
def tutorContext (unit : Unit) (activityId : String) : Except String Json := do
  validate unit
  let activity ← match unit.activities.find? (fun activity => activity.id == activityId) with
    | some activity => pure activity
    | none => throw "unknown activity"
  require (!activity.assessment.independent && activity.assistance != .none) "independent/no-assistance activity withholds tutor context"
  let node := unit.course.nodes[activity.node]!
  return Json.mkObj [("activityId", toJson activity.id), ("title", toJson node.title),
    ("body", toJson node.body), ("exercise", toJson node.exercise), ("hint", toJson node.hint),
    ("sourceAnchor", toJson node.sourceAnchor)]

end Lemma.School.Authoring
