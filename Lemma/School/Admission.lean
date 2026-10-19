import Lemma.School.Model
import Lemma.School.Digest

/-! Restricted local learner transport. A 256-bit OS-random bearer secret is
exchanged out of band; only its SHA256 is stored. This is a local admission
binding, not internet TLS, device private-key storage, or production identity. -/
namespace Lemma.School.Admission
open Lean

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

def handles (op : String) : Bool := #["admission-issue","admission-revoke"].contains op

def execute (state : State) (actor : String) (request : Json) (now : Nat) : Except String (State × Json) := do
  state.authorize actor "admin" "school"
  let digest ← str request "tokenHash"
  require (Digest.valid digest) "admission requires exact lowercase SHA256 token identity"
  let op ← str request "op"
  if op == "admission-revoke" then
    let row ← (state.latest "admission" digest).toExcept "admission absent"
    let fields ← row.data.getObj?
    let next ← state.add "admission" digest actor now (Json.obj (fields.insert "revoked" (toJson true)))
    return (next,object [("revoked",toJson true)])
  require ((state.latest "admission" digest).isNone) "credential identity already used; generate a new secret"
  let learner ← str request "learner"
  require (validId learner && learner != state.operator) "learner admission cannot confer operator identity"
  let lifetime := optionalNat request "lifetimeMs" 86400000
  require (lifetime > 0 && lifetime <= 2592000000) "admission lifetime must be 1..2592000000 milliseconds"
  let next ← state.add "admission" digest actor now (object [("learner",toJson learner),
    ("deployment",toJson state.deployment),("clockEpochSequence",toJson state.clockEpochSequence),("expires",toJson (now+lifetime)),("revoked",toJson false),
    ("scope",toJson "learner-local/1; no host paths or administrative commands")])
  return (next,object [("learner",toJson learner),("expires",toJson (now+lifetime)),("tokenHash",toJson digest)])

/-- Resolve the principal before the normal school authorization boundary.
Neither an actor field nor an inner school field is caller authority. -/
def resolve (state : State) (request : Json) (now : Nat) : Except String Json := do
  let secret ← str request "token"
  require (Digest.valid secret) "learner token must be 32 lowercase hex-encoded random bytes"
  let row ← (state.latest "admission" (Digest.sha256String secret)).toExcept "learner admission rejected"
  require (!flag row.data "revoked" && optionalNat row.data "expires" > now &&
    optionalStr row.data "deployment" == state.deployment &&
    optionalNat row.data "clockEpochSequence" == state.clockEpochSequence) "learner admission revoked, expired or foreign"
  let command ← field request "command"
  let op ← str command "op"
  require (#["course-catalogue","client-course","join","assist","cancel-session","delivery","attempt",
    "guest-submit","delivery-observe","progress","reviews","review-open","review-state","feedback","feedback-read","learner-choices",
    "goal-set","interpretation-challenge","suggestion-override","work-upload",
    "publish","enroll","enrollment-revoke","review-queue","review-work","review-artifact","review-render","human-assess",
    "recommendation-input","models","model-select","model-rollback","admission-issue","admission-revoke"].contains op)
    "operation is outside bounded learner admission"
  require (!(field command "path").isOk) "host paths are outside admitted transport; use inline definitions or bounded uploads"
  if op == "publish" then require ((field command "definition").isOk) "admitted publication requires an inline definition"
  let fields ← command.getObj?
  let actor ← str row.data "learner"
  return Json.obj (fields.insert "school" (toJson state.school) |>.insert "actor" (toJson actor) |>.insert "admittedLearner" (toJson true))

def uploadBytes (request : Json) : Except String ByteArray := do
  let encoded ← str request "hex"
  require (!encoded.isEmpty && encoded.utf8ByteSize <= 524288 && encoded.utf8ByteSize % 2 == 0)
    "learner upload must contain 1..262144 bytes"
  let digit (b : UInt8) : Except String UInt8 :=
    if 48 <= b && b <= 57 then .ok (b-48) else
    if 97 <= b && b <= 102 then .ok (b-87) else .error "upload must use lowercase hex"
  let raw := encoded.toUTF8
  let mut bytes := ByteArray.empty
  for index in [:raw.size/2] do
    bytes := bytes.push ((← digit raw[index*2]!) <<< 4 ||| (← digit raw[index*2+1]!))
  return bytes

end Lemma.School.Admission
