import Lemma.Courses.PackagePublish

/-! Host CLI is separate from the reusable publisher library, so ordinary
authoring modules can define their own main without importing a competing main. -/
def main (arguments : List String) : IO Unit := do
  match arguments with
    | ["--output-dir", path] => Lemma.Courses.PackagePublish.publish (System.FilePath.mk path)
    | _ => throw <| IO.userError "usage: lake env lean --run Lemma/Courses/PackagePublishMain.lean --output-dir NEW_DIRECTORY"
