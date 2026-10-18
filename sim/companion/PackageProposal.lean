import Lean
import Lemma.Courses.Package

/-! Hosted Lean data publisher for untrusted model assistance. This is package
construction, never a target compiler or mathematical authority. Guest CRC,
shape, copied action admission and current source/revision checks remain required.
The sole existing installer owns UART and publishes through ordinary Store. -/
open Lean
namespace LemmaSim.Companion.PackageProposal
private def field (j : Json) (key : String) : Except String Json := j.getObjVal? key
private def string (j : Json) (key : String) : Except String String := do (← field j key).getStr?
private def number (j : Json) (key : String) : Except String Nat := do (← field j key).getNat?
private def decodeHex (text : String) : Except String ByteArray := do
  let bytes := text.toUTF8
  if bytes.size != 384 then throw "action packet must contain384hex bytes"
  let digit (b : UInt8) : Except String UInt8 :=
    if b >= 48 && b <= 57 then .ok (b-48) else if b >= 97 && b <= 102 then .ok (b-87) else .error "invalid action hex"
  let mut out := ByteArray.empty
  for i in [:192] do out := out.push ((← digit bytes[2*i]!) <<< 4 ||| (← digit bytes[2*i+1]!))
  return out
private def word (b : ByteArray) (offset : Nat) : UInt64 := Id.run do
  let mut result : UInt64 := 0
  for i in [:8] do result := result ||| (b[offset+i]!.toUInt64 <<< (i*8).toUInt64)
  return result

def publish (proposal : Json) (output : System.FilePath) : IO Unit := do
  if ← output.pathExists then throw <| IO.userError "unused package output required"
  let schema ← IO.ofExcept <| string proposal "schema"
  if schema != "lemma-tutor-proposal/2" then throw <| IO.userError "untrusted proposal schema"
  let hex ← IO.ofExcept <| string proposal "packet_hex"
  let packet ← IO.ofExcept <| decodeHex hex
  let text ← IO.ofExcept <| string proposal "text"
  let action ← IO.ofExcept <| string proposal "action"
  let modelText ← IO.ofExcept <| string proposal "model_text"
  let claims ← IO.ofExcept <| (← IO.ofExcept <| field proposal "claims_requiring_check").getArr?
  let claimKind := word packet 96
  if claimKind > 1 || (claimKind == 0) != claims.isEmpty then throw <| IO.userError "unsupported or inconsistent mathematical claim declaration"
  let annotation := if claims.isEmpty then "UNVERIFIED ASSISTANCE: " else "UNVERIFIED ASSISTANCE - CHECKING PENDING: "
  if modelText.toUTF8.size > 196 || text != annotation ++ modelText || text.toUTF8.size > 256 then
    throw <| IO.userError "visible unverified/pending annotation and unmodified bounded model text required"
  if text.isEmpty || text.toUTF8.size > 512 then throw <| IO.userError "silence needs no package; text max512"
  if word packet 0 != 2 || word packet 104 != text.toUTF8.size.toUInt64 then throw <| IO.userError "packet/text binding mismatch"
  let sequence := word packet 40
  if sequence = 0 || sequence > 0xffffffff then throw <| IO.userError "package edition sequence exhausted"
  let context ← IO.ofExcept <| field proposal "context"
  for (name,offset) in #[("source",136),("edition",144),("task_id",152),("revision",24),("object",32),("sequence",40)] do
    let actual ← IO.ofExcept <| number context name
    if actual.toUInt64 != word packet offset then throw <| IO.userError "context/action mismatch"
  let anchor := s!"source={word packet 136};edition={word packet 144};task={word packet 152};revision={word packet 24};object={word packet 32};cutoff={word packet 48}"
  let node : Lemma.Courses.Package.Node := { kind := .explanation, title := action, body := text, sourceAnchor := anchor, review := "Generated assistance is not an independent student solution or Verified evidence." }
  let course : Lemma.Courses.Package.Course := {
    identity := 60001, edition := sequence, title := "TUTOR ASSISTANCE UNVERIFIED",
    sourceAnchor := "lemma-tutor-assistance/2", editionAnchor := hex,
    rightsAnchor := "Owner-local model-generated assistance; see inference model/license receipt. No mathematical authority.",
    nodes := #[node] }
  let bytes ← IO.ofExcept <| (Lemma.Courses.Package.encode course).mapError (·.render)
  IO.FS.writeBinFile output bytes
  IO.println <| Json.compress <| Json.mkObj [("schema",.str "lemma-tutor-package/1"),("bytes",toJson bytes.size),
    ("identity",toJson (60001 : Nat)),("edition",toJson sequence.toNat),("action",.str action),
    ("source_anchor",.str anchor),("transport",.str "OWNER_LOCAL_INTEGRITY_ONLY"),
    ("authority",.str "UNTRUSTED_ASSISTANCE"),("delivery",.str "NOT_YET_INSTALLED_OR_DISPLAYED")]
end LemmaSim.Companion.PackageProposal

def main (args : List String) : IO Unit := do
  match args with
  | ["--proposal",input,"--output",output] =>
    let j ← IO.ofExcept <| Json.parse (← IO.FS.readFile input)
    LemmaSim.Companion.PackageProposal.publish j output
  | _ => throw <| IO.userError "usage: lake env lean --run sim/companion/PackageProposal.lean --proposal PROPOSAL.json --output UNUSED.lcp"
