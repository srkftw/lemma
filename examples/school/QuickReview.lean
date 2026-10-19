import Lemma.School.Authoring

/-! A real developer policy extension through the maintained semantic API.
The input is the same teacher-authored Unit JSON; no second curriculum exists.
This short delay is for a controlled software review scenario, not retention. -/
open Lean Lemma.School

def quickReview (unit : Authoring.Unit) (edition : UInt64) : Except String Authoring.Unit := do
  if edition <= unit.course.edition then throw "extension must publish a new immutable edition"
  let changed := { unit with
    course := {unit.course with edition}
    review := {unit.review with delaySeconds := 60} }
  Authoring.validate changed
  return changed

def main (args : List String) : IO UInt32 := do
  match args with
  | [input,output,edition] =>
    let metadata ← (System.FilePath.mk input).metadata
    if metadata.type != .file || metadata.byteSize > 1048576 then
      throw (IO.userError "unit must be a regular file of at most 1MiB")
    if ← (System.FilePath.mk output).pathExists then throw (IO.userError "output already exists")
    let original ← IO.ofExcept (Json.parse (← IO.FS.readFile input) >>= Authoring.decode)
    let version ← match edition.toNat? with
      | some value => pure value
      | none => throw (IO.userError "edition must be an integer")
    if version > 0xffffffff then throw (IO.userError "edition outside existing package profile")
    let changed ← IO.ofExcept (quickReview original version.toUInt64)
    let bytes ← IO.ofExcept (Authoring.compile changed)
    IO.FS.writeFile output ((toJson changed).compress ++ "\n")
    IO.println (Json.mkObj [("edition",toJson version),("reviewDelaySeconds",toJson changed.review.delaySeconds),
      ("packageDigest",toJson (Digest.sha256Bytes bytes)),("definition",toJson output)]).compress
    return 0
  | _ => throw (IO.userError "usage: QuickReview.lean INPUT_UNIT NEW_UNIT_JSON NEW_EDITION")
