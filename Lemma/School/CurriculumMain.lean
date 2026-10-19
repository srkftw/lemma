import Lemma.School.Catalogue
import Lemma.School.FixtureUnit

open Lean Lemma.School

private def unwrap {α : Type} (result : Except String α) : IO α :=
  match result with
  | .ok value => pure value
  | .error error => throw (IO.userError error)

private def readUnit (path : System.FilePath) : IO Authoring.Unit := do
  let metadata ← path.metadata
  if metadata.type != .file || metadata.byteSize > 1048576 then
    throw (IO.userError "unit JSON exceeds 1MiB or is not a regular file")
  let bytes ← IO.FS.withFile path .read (fun handle => handle.read 1048577)
  if bytes.size > 1048576 then throw (IO.userError "unit JSON grew beyond 1MiB")
  let raw ← match String.fromUTF8? bytes with
    | some text => pure text
    | none => throw (IO.userError "invalid unit JSON UTF-8")
  unwrap (Json.parse raw >>= Authoring.decode)

private def emit (value : Json) : IO UInt32 := do
  IO.println value.pretty
  return 0

def main (arguments : List String) : IO UInt32 := do
  match arguments with
  | "catalogue" :: tail => Catalogue.cli tail
  | ["fixture"] => emit (toJson FixtureUnit.unit)
  | ["fixture-checks"] => emit (toJson FixtureUnit.checkerExamples)
  | ["preview",path] => emit (← unwrap (Authoring.preview (← readUnit path)))
  | ["compile",path,output] =>
    if ← (System.FilePath.mk output).pathExists then throw (IO.userError "refusing existing package artifact")
    let unit ← readUnit path
    let bytes ← unwrap (Authoring.compile unit)
    IO.FS.writeBinFile output bytes
    emit (Json.mkObj [("bytes",toJson bytes.size),("sha256",toJson (Digest.sha256Bytes bytes))])
  | ["tutor-context",path,activity] => emit (← unwrap (Authoring.tutorContext (← readUnit path) activity))
  | ["resolve-sources",path] =>
    let unit ← readUnit path
    let _ ← unwrap (Authoring.validate unit)
    let mut paths : Array String := #[]
    for source in unit.sources.sources do paths := paths.push (← SourceRegistry.resolve source).toString
    emit (toJson paths)
  | ["sha256",path] => emit (toJson (← Digest.sha256File path))
  | _ => throw (IO.userError "curriculum: catalogue ... | fixture | fixture-checks | preview UNIT_JSON | compile UNIT_JSON NEW_LCP | tutor-context UNIT_JSON ACTIVITY | resolve-sources UNIT_JSON | sha256 FILE")
