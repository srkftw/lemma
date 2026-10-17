import Lemma.Compiler.DeploymentCatalog

open Lemma.Compiler.DeploymentCatalog

private def check : IO Unit := do
  let normal := "lemmasim-silicon-package-chooser-bulk-notebook"
  let initializer :=  "lemmasim-silicon-package-chooser-bulk-initialize"
  for configuration in #[normal, initializer] do
    let images ← IO.ofExcept (imagesFor configuration)
    unless images == packageChooserNotebookImages && images.size == 4 do
      throw <| IO.userError "Reader20 lost its closed four-role deployment"
    let notebook ← IO.ofExcept (imageFor configuration "notebook")
    unless notebook.root == `Lemma.Applications.Notebook.mainPackageReaderChooser do
      throw <| IO.userError "Reader20 selected a historical or foreign notebook"
    match validateSelection configuration "notebook" #[`Lemma.Applications.Notebook.mainPackageNumberPadBrowse] with
    | .error _ => pure ()
    | .ok _ => throw <| IO.userError "Reader20 accepts a substituted entry root"
  unless (← IO.ofExcept (imagesFor "lemmasim-silicon-package-reader-bulk-notebook")) == packageReaderNotebookImages do
    throw <| IO.userError "Reader20 changed historical Reader18"
  for configuration in #["lemmasim-silicon-package-closure-entry2-bulk-notebook",
      "lemmasim-silicon-package-closure-entry2-bulk-initialize"] do
    unless (← IO.ofExcept (imagesFor configuration)) == packageNumberPadBrowseNotebookImages do
      throw <| IO.userError "Reader20 changed the history17 deployment"
  match imagesFor "lemmasim-silicon-package-reader-arbitrary" with
  | .error _ => pure ()
  | .ok _ => throw <| IO.userError "Reader20 configuration is not closed"
  IO.println "PASS closed Reader20 chooser and preserved Reader18/history17 deployment selection"

#eval check
