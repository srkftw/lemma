import Lemma.School.Model
import Lemma.School.Client
import Lemma.School.Digest

/-! Bounded observations of an immutable authored assistance decision.
A bearer client reports byte admission, exact guest console records and raw
controller snapshots. None is an attestation of presentation, understanding,
learning or mathematical correctness. No observation changes a decision. -/
namespace Lemma.School.Delivery
open Lean

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

private def keys (value : Json) (allowed : Array String) : Except String Unit := do
  for (key,_) in (← value.getObj?).toList do
    require (allowed.contains key) s!"unknown delivery observation field:{key}"

private def number (value : Json) (key : String) : Except String Nat := do
  let result ← nat value key
  require (result ≤ 0xffffffffffffffff) s!"delivery observation integer exceeds64bits:{key}"
  return result

private def digest (value : Json) (key : String) : Except String String := do
  let result ← str value key
  require (Digest.valid result) s!"delivery observation requires lowercase SHA256:{key}"
  return result

private def rawRecord (observation : Json) : Except String (Array Nat) := do
  let record : Array Nat ← field observation "record" >>= fromJson?
  require (record.size == 5 && record.all (· ≤ 0xffffffffffffffff)) "delivery observation requires five full64-bit console words"
  return record

private def normalize (kind : String) (observation : Json) (ask : Client.GuestAsk) : Except String Json := do
  if kind == "transport" then
    keys observation #["admittedBytes","wireBytes","packetSHA256"]
    let admitted ← number observation "admittedBytes"
    let wire ← number observation "wireBytes"
    require (wire > 0 && wire ≤ 65536 && admitted ≤ wire) "delivery byte admission outside declared wire span"
    return object [("admittedBytes",toJson admitted),("wireBytes",toJson wire),
      ("packetSHA256",toJson (← digest observation "packetSHA256"))]
  else if kind == "guest-raster" || kind == "guest-rejected" then
    keys observation #["record","uartSHA256"]
    let record ← rawRecord observation
    if kind == "guest-raster" then
      require (record == #[0x725,ask.sequence,1,0,0]) "delivery raster record differs from original ASK sequence/725 semantics"
    else
      require (record[0]! == 0x724 && record[1]! > 0 && record[2]! == ask.revision &&
        record[3]! == ask.object && record[4]! == 0) "delivery rejection record differs from original ASK context/724 semantics"
    return object [("record",toJson record),("uartSHA256",toJson (← digest observation "uartSHA256"))]
  else if kind == "controller-snapshot" then
    keys observation #["cycle","completed","accepted","busy","targetSHA256","visibleSHA256","hashEncoding"]
    let cycle ← number observation "cycle"
    let completed ← number observation "completed"
    let busy ← number observation "busy"
    require (busy ≤ 1) "delivery controller busy is not a bit"
    let mut fields := [("cycle",toJson cycle),("completed",toJson completed),("busy",toJson busy)]
    if (field observation "accepted").isOk then
      let accepted ← number observation "accepted"
      require (completed ≤ accepted) "delivery controller completed exceeds accepted sequence"
      fields := fields ++ [("accepted",toJson accepted)]
    let hashed := (field observation "targetSHA256").isOk || (field observation "visibleSHA256").isOk
    if hashed then
      let encoding ← str observation "hashEncoding"
      require (#["gray4","gray8","controller-bytes"].contains encoding) "delivery controller hash encoding unsupported"
      fields := fields ++ [("hashEncoding",toJson encoding)]
      for key in #["targetSHA256","visibleSHA256"] do
        if (field observation key).isOk then fields := fields ++ [(key,toJson (← digest observation key))]
    else require (!(field observation "hashEncoding").isOk) "delivery hash encoding has no observed hash"
    return object fields
  else if kind == "cancelled" then
    keys observation #["reason"]
    let reason ← str observation "reason"
    require (#["user-cancel","disconnect","permission-revoked","navigation","expired","machine-restart","transfer-failed"].contains reason)
      "unsupported delivery cancellation reason"
    return object [("reason",toJson reason)]
  else throw "unsupported delivery observation kind"

def scope (kind : String) : String :=
  if kind == "transport" then "reported UART byte admission; partial/full transport is not guest acceptance or presentation"
  else if kind == "guest-raster" then "reported exact guest725 raster acceptance; panel completion and all-body visibility remain separate"
  else if kind == "guest-rejected" then "reported exact guest724 rejection in original revision/object context; no presentation inferred"
  else if kind == "controller-snapshot" then "raw controller snapshot reported by live observer; completed sequence/hashes do not establish that the whole authored body was displayed"
  else "reported cancellation; prior partial transport/raster/controller observations remain immutable"

/-- Content idempotency is derived in Lean from normalized typed observations,
original decision/context and a live execution observer identity. Exact lost-ACK
retries return the original commit even after session cancellation/restart.
Credential revocation still happens before this function. No active authority
is extended by recording a historical observation. -/
def execute (state : State) (actor : String) (request : Json) (now : Nat) : Except String (State × Json) := do
  let decision ← str request "decision"
  let row ← (state.latest "decision" decision).toExcept "delivery decision absent"
  require (row.actor == actor) "delivery observation principal differs from decision"
  let input : Client.AssistInput ← field row.data "input" >>= fromJson?
  require (input.school == state.school && input.actor == actor) "delivery original decision scope differs"
  let sequence ← number request "sequence"
  require (sequence == input.ask.sequence) "delivery observation sequence differs from immutable decision"
  let observer ← str request "observer"
  require (validId observer) "delivery observer requires a fresh live execution identity"
  let kind ← str request "kind"
  let observation ← normalize kind (← field request "observation") input.ask
  let data := object [("schema",toJson "lemma-school-delivery-observation/1"),
    ("decision",toJson decision),("decisionSequence",toJson row.sequence),
    ("artifact",toJson (optionalStr row.data "artifact")),("session",toJson input.session),
    ("course",toJson input.course),("edition",toJson input.revision),("policy",toJson input.policy),
    ("decisionGeneration",toJson input.generation),("ask",toJson input.ask),
    ("observer",toJson observer),("kind",toJson kind),("observation",observation),("scope",toJson (scope kind))]
  let identity := Digest.sha256String data.compress
  let response (commit : Nat) (reused : Bool) := object [("observation",toJson identity),
    ("commitSequence",toJson commit),("kind",toJson kind),("sequence",toJson sequence),
    ("reused",toJson reused),("scope",toJson (scope kind))]
  if let some prior := state.latest "delivery-observation" identity then
    require (prior.actor == actor && prior.data == data) "delivery content identity conflict"
    return (state,response prior.sequence true)
  let next ← state.add "delivery-observation" identity actor now data
  return (next,response next.records.size false)

end Lemma.School.Delivery
