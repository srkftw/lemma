import Lemma.Compiler.DeploymentCatalog

open Lemma.Compiler.DeploymentCatalog

private def check : IO Unit := do
  let normal := "lemmasim-silicon-package-reader-bulk-notebook"
  let initializer :=  "lemmasim-silicon-package-reader-bulk-initialize"
  for configuration in #[normal, initializer] do
    let images ← IO.ofExcept (imagesFor configuration)
    unless images == packageReaderNotebookImages && images.size == 4 do
      throw <| IO.userError "Reader18 lost its closed four-role deployment"
    let notebook ← IO.ofExcept (imageFor configuration "notebook")
    unless notebook.root == `Lemma.Applications.Notebook.mainPackageNumberPadBookmark do
      throw <| IO.userError "Reader18 selected a historical or foreign notebook"
    match validateSelection configuration "notebook" #[`Lemma.Applications.Notebook.mainPackageNumberPadBrowse] with
    | .error _ => pure ()
    | .ok _ => throw <| IO.userError "Reader18 accepts a substituted entry root"
  for configuration in #["lemmasim-silicon-package-closure-entry2-bulk-notebook",
      "lemmasim-silicon-package-closure-entry2-bulk-initialize"] do
    unless (← IO.ofExcept (imagesFor configuration)) == packageNumberPadBrowseNotebookImages do
      throw <| IO.userError "Reader18 changed the history17 deployment"
  match imagesFor "lemmasim-silicon-package-reader-arbitrary" with
  | .error _ => pure ()
  | .ok _ => throw <| IO.userError "Reader18 configuration is not closed"
  IO.println "PASS closed Reader18 and preserved history17 deployment selection"

#eval check
