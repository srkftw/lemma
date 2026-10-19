import Lean
import Lemma.Courses.Package

/-! Owner-local school/client admission. Hosted Lean owns enrollment/session
checks and construction of the existing immutable assistance package. The
unchanged guest independently validates its own live action/session/revision
and visibly labels assistance. A school binding is not yet a guest credential.
There is no claim of authenticated transport or checked student mathematics. -/
namespace Lemma.School.Client
open Lean

structure SessionBinding where
  school : String
  actor : String
  enrollment : String
  session : String
  guestSession : Nat
  authority : String := ""
  bindingRecord : Nat := 0
  course : Nat
  revision : Nat
  policy : Nat
  generation : Nat
  expires : Nat
  cancelled : Bool := false
  deriving BEq, Repr, FromJson, ToJson

/-- The guest's 721/722/723 ASK is copied verbatim. Its clock and revision
are separate from the school clock and immutable course revision. -/
structure GuestAsk where
  session : Nat
  consent : Nat
  revision : Nat
  object : Nat
  sequence : Nat
  source : Nat
  edition : Nat
  task_id : Nat
  cutoff : Nat
  now : Nat
  deadline : Nat
  grants : Nat
  modality : Nat := 1
  deriving BEq, Repr, FromJson, ToJson

structure AssistInput where
  school : String
  actor : String
  session : String
  course : Nat
  revision : Nat
  policy : Nat
  generation : Nat
  now : Nat
  ask : GuestAsk
  independent : Bool := false
  deriving BEq, Repr, FromJson, ToJson

def admit (binding : SessionBinding) (input : AssistInput) : Except String Unit := do
  if binding.school.isEmpty || binding.actor.isEmpty || binding.enrollment.isEmpty || binding.session.isEmpty then
    throw "school session has an empty identity or enrollment"
  if binding.school != input.school then throw "cross-school assistance rejected"
  if binding.actor != input.actor then throw "assistance actor is outside enrollment"
  if binding.session != input.session then throw "school session differs"
  if binding.course != input.course || binding.revision != input.revision then
    throw "assistance course publication differs from joined publication"
  if binding.policy != input.policy then throw "assistance policy differs from joined policy"
  if binding.generation != input.generation then throw "school execution generation is stale"
  if binding.cancelled then throw "school session is cancelled"
  if binding.expires <= input.now then throw "school session expired"
  if input.independent then throw "assistance prohibited during independent assessment"
  let ask := input.ask
  if ask.session != binding.guestSession then throw "guest ASK session differs from joined client context"
  if input.course == 0 || input.course > 65535 || input.course == 60001 || input.revision == 0 || input.revision > 0xffffffff then
    throw "course publication is outside the existing guest package profile"
  if ask.source != input.course || ask.edition != input.revision then
    throw "guest ASK source/edition differs from the enrolled course publication"
  if #[ask.session,ask.consent,ask.revision,ask.object,ask.sequence,ask.task_id].any (· == 0) then
    throw "guest ASK contains an empty identity"
  if #[ask.session,ask.consent,ask.revision,ask.object,ask.sequence,ask.task_id,ask.cutoff,ask.now,ask.deadline].any (· > 0x7ffffffffffffffe) then
    throw "guest ASK integer exceeds admitted signed clock/identity range"
  if ask.sequence > 0xffffffff then throw "guest immutable assistance edition exhausted"
  if ask.task_id > 16 then throw "guest ASK node is outside package profile"
  if ask.grants != 1 || ask.modality != 1 then throw "school baseline admits text assistance only"
  if ask.now < ask.cutoff || ask.deadline < ask.now then throw "guest ASK expired or has future observation"
  if ask.deadline - ask.cutoff > 3000000000 then throw "guest ASK exceeds the admitted three-billion-tick assistance window"

private def wordBytes (values : Array Nat) : ByteArray := Id.run do
  let mut bytes := ByteArray.empty
  for value in values do
    for i in [:8] do bytes := bytes.push ((value >>> (8*i)).toUInt8)
  return bytes

private def hex (bytes : ByteArray) : String :=
  String.ofList <| bytes.data.toList.flatMap fun byte =>
    let digit (n : Nat) : Char := Char.ofNat (if n < 10 then 48+n else 87+n)
    [digit (byte.toNat / 16),digit (byte.toNat % 16)]

private def authorityBytes (binding : SessionBinding) : Except String ByteArray := do
  let raw := binding.authority.toUTF8
  if raw.size != 64 then throw "school authority requires an exact SHA256 identity"
  if binding.bindingRecord == 0 || binding.bindingRecord > 0x7ffffffffffffffe ||
      binding.generation == 0 || binding.generation > 0x7ffffffffffffffe ||
      binding.policy == 0 || binding.policy > 0x7ffffffffffffffe then
    throw "school binding record/generation/policy outside admitted range"
  let digit (b : UInt8) : Except String UInt8 :=
    if 48 <= b && b <= 57 then .ok (b-48) else
    if 97 <= b && b <= 102 then .ok (b-87) else .error "school authority must be lowercase SHA256 hex"
  let mut output := ByteArray.empty
  for i in [:32] do output := output.push ((← digit raw[2*i]!) <<< 4 ||| (← digit raw[2*i+1]!))
  if output.data.all (· == 0) then throw "empty school authority identity"
  return output

private def schoolWords (binding : SessionBinding) (ask : GuestAsk) : Except String ByteArray := do
  return (← authorityBytes binding) ++ wordBytes #[binding.bindingRecord,binding.generation,ask.deadline,binding.policy]

private def encoded (input : AssistInput) (packet : ByteArray) (text marker : String) : Except String ByteArray := do
  let body := "UNVERIFIED ASSISTANCE: " ++ text
  let node : Courses.Package.Node := {
    kind := .explanation, title := "School hint", body,
    sourceAnchor := s!"school={input.school};course={input.course};edition={input.revision};node={input.ask.task_id};policy={input.policy}",
    review := "Authored school assistance; no independent outcome or mathematical verification is inferred." }
  let course : Courses.Package.Course := {
    identity := 60001, edition := input.ask.sequence.toUInt64,
    title := "SCHOOL ASSISTANCE UNVERIFIED", sourceAnchor := marker,
    editionAnchor := hex packet,
    rightsAnchor := "Owner-local authored assistance. The explicit joined school binding is integrity-only development context, not authenticated remote identity.",
    nodes := #[node] }
  (Courses.Package.encode course).mapError (·.render)

private def actionBytes (input : AssistInput) (text : String) (version : Nat) : Except String ByteArray := do
  if text.isEmpty || text.toUTF8.size > 196 then throw "assistance text must contain 1..196 ASCII bytes"
  let ask := input.ask
  let body := "UNVERIFIED ASSISTANCE: " ++ text
  return wordBytes #[version,ask.session,ask.consent,ask.revision,ask.object,ask.sequence,
    ask.cutoff,ask.now,ask.deadline,1,3,1,0,body.toUTF8.size,0,input.policy,0,
    ask.source,ask.edition,ask.task_id,1,0,0,0]

/-- An explicit owner-local invitation to the exact current guest ASK. Its
full authority digest plus durable binding record resolves actor/enrollment in
the school log. The guest checks this immutable context only after JOIN intent.
It is not a remote authentication or a private-key credential. -/
def invitation (binding : SessionBinding) (ask : GuestAsk) : Except String ByteArray := do
  let input : AssistInput := {
    school := binding.school, actor := binding.actor, session := binding.session
    course := binding.course, revision := binding.revision, policy := binding.policy
    generation := binding.generation, now := 0, ask := ask }
  admit binding input
  let context ← schoolWords binding ask
  let packet := wordBytes #[0x314e494f4a484353,1] ++ context ++ wordBytes #[ask.session,ask.source,ask.edition]
  let node : Courses.Package.Node := {
    kind:=.explanation,title:="Join this school session",
    body:=s!"OWNER-LOCAL SCHOOL SESSION: {binding.school}; learner {binding.actor}; course {binding.course}, edition {binding.revision}, policy {binding.policy}. Local development integrity only.",
    sourceAnchor:=s!"authority={binding.authority};binding={binding.bindingRecord};generation={binding.generation}"}
  let course : Courses.Package.Course := {
    identity:=60000,edition:=ask.sequence.toUInt64,
    title:="SCHOOL SESSION JOIN",sourceAnchor:="lemma-school-session/1",editionAnchor:=hex packet,
    rightsAnchor:="Owner-local enrollment receipt; no learner records, model secrets, or production credentials.",nodes:=#[node]}
  (Courses.Package.encode course).mapError (·.render)

/-- No model or assessment answers enter this builder. Text is authored public
context selected by school policy. The action declares no mathematical claim;
the guest independently checks the exact visible unverified annotation. -/
def package (input : AssistInput) (text : String) : Except String ByteArray := do
  encoded input (← actionBytes input text 2) text "lemma-tutor-assistance/2"

def handleLegacyAssist (binding : SessionBinding) (input : AssistInput) (text : String) : Except String ByteArray := do
  admit binding input
  package input text

def handleAssist (binding : SessionBinding) (input : AssistInput) (text : String) : Except String ByteArray := do
  admit binding input
  let packet := (← actionBytes input text 3) ++ (← schoolWords binding input.ask)
  encoded input packet text "lemma-school-assistance/3"

end Lemma.School.Client
