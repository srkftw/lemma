import Lemma.Courses.PackagePublish
import Lemma.Courses.PackageTarget

/-! Ordinary authoring example and a new-edition check. It runs on hosted Lean
and reuses the unchanged genuinely compiled target decoder declarations. -/
namespace CourseAuthorExample
open Lemma.Courses
open Lemma.Core0.Memory

def editionTwo : Package.Course := {
  PackageReference.arithmetic with
  edition := 2
  title := "Exact arithmetic: an alternative review edition"
  sourceAnchor := "tests/courses/Author.lean#editionTwo"
  editionAnchor := "original alternative lesson edition 2"
  nodes := PackageReference.arithmetic.nodes.set! 2 {
    PackageReference.arithmetic.nodes[2]! with
    hint := "Choose a common positive denominator, rewrite both fractions, then add the numerators."
    sourceAnchor := "original:alternative-fraction-hint-edition-2"
  }
}

private def read (bytes : ByteArray) (address width : UInt64) : IO UInt64 := do
  if address < 0x40000 || bytes.size.toUInt64 < width || bytes.size.toUInt64-width < address-0x40000 then
    throw <| IO.userError "author decoder read outside exact package bytes"
  return (List.range width.toNat).foldl (fun value i =>
    value ||| (bytes[(address-0x40000).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0

partial def observe (bytes : ByteArray) : Action → IO (UInt8 × UInt64)
  | .done s value => pure (s,value)
  | .bind first next => do
      let (s,value) ← observe bytes first
      observe bytes (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "author decoder budget exceeded"
      let mut status : UInt8 := 0
      let mut value := initial
      for i in [:count.toNat] do
        if status == 0 then
          let (s,result) ← observe bytes (step i.toUInt32 count value a b c d)
          status := s
          value := result
      observe bytes (next status value)
  | .platform operation a _ _ _ _ _ next => do
      let width ← match operation with
        | .virtualRead8 => pure 1 | .virtualRead64 => pure 8
        | _ => throw <| IO.userError "author decoder acquired a write/syscall"
      observe bytes (next 0 (← read bytes a width))
  | _ => throw <| IO.userError "author decoder acquired unsupported Action syntax"

def validatePublished (directory : System.FilePath) : IO Unit := do
  let bytes ← IO.FS.readBinFile (directory / "arithmetic.lcp")
  for (action,result) in #[(PackageTarget.validate 0x40000 bytes.size.toUInt64,(0,8)),
      (PackageTarget.goal 0x40000 bytes.size.toUInt64 2,(0,1)),
      (PackageTarget.character 0x40000 bytes.size.toUInt64 2 5 0,(0,67))] do
    if (← observe bytes action) != result then
      throw <| IO.userError "unchanged target decoder rejected the ordinary author's new edition"
  IO.println "COURSE_AUTHOR_EDITION:PASS changed lesson/hint/source/edition; unchanged target decoder selects pinned goal1 and new hint bytes"

end CourseAuthorExample

def main (arguments : List String) : IO Unit := do
  match arguments with
    | ["--output-dir", path] =>
      do
      Lemma.Courses.PackagePublish.publishCourse path CourseAuthorExample.editionTwo
        "CourseAuthorExample.editionTwo"
      CourseAuthorExample.validatePublished path
    | _ => throw <| IO.userError "usage: lake env lean --run tests/courses/Author.lean --output-dir NEW_DIRECTORY"
