import Lean
import Lemma.Courses.PackageReference

/-! Hosted authoring command. Its Lean/IO runtime is never linked into a guest.
It writes an immutable file artifact only; it does not inspect or edit a journal,
run a checker, install a package in guest media or authorize trusted evidence. -/
namespace Lemma.Courses.PackagePublish
open Lean

private def word (bytes : ByteArray) (offset : Nat) : UInt64 :=
  (List.range 8).foldl (fun value i => value ||| (bytes[offset+i]!.toUInt64 <<< (i.toUInt64 * 8))) 0

def publishCourse (directory : System.FilePath) (course : Package.Course) (declaration : String) : IO Unit := do
  if ← directory.pathExists then throw <| IO.userError "course publisher refuses a retained output directory"
  let image ← match Package.encode course with
    | .ok bytes => pure bytes
    | .error error => throw <| IO.userError error.render
  let manifest := Json.mkObj [
    ("schema_version", toJson (1 : Nat)),
    ("format", .str "lemma-course-package/1"),
    ("source_declaration", .str declaration),
    ("file", .str "arithmetic.lcp"),
    ("identity", .str (toString course.identity)),
    ("edition", .str (toString course.edition)),
    ("title", .str course.title),
    ("source_anchor", .str course.sourceAnchor),
    ("edition_anchor", .str course.editionAnchor),
    ("rights_anchor", .str course.rightsAnchor),
    ("bytes", toJson image.size),
    ("nodes", toJson course.nodes.size),
    ("crc32", .str (toString (word image 80))),
    ("integrity_scope", .str "CRC32/ISO-HDLC corruption detection; authentication unavailable"),
    ("checker_scope", .str "pinned original goals 1/2; explicit unsupported goal 3; no new goal semantics"),
    ("guest_installation", .str "not yet wired into the notebook"),
    ("rights", .str "source declaration only; no repository licensing or redistribution change")]
  IO.FS.createDirAll directory
  IO.FS.writeBinFile (directory / "arithmetic.lcp") image
  IO.FS.writeFile (directory / "package.json") (manifest.pretty ++ "\n")
  IO.println s!"COURSE_PACKAGE_PUBLISH:PASS {image.size} bytes,{course.nodes.size} original typed nodes"

/-- The bundled reference command is only one user of the reusable publisher.
An author's ordinary Lean main may pass its own typed declaration and source
identity without changing or rebuilding target software. -/
def publish (directory : System.FilePath) : IO Unit :=
  publishCourse directory PackageReference.arithmetic "Lemma.Courses.PackageReference.arithmetic"

end Lemma.Courses.PackagePublish
