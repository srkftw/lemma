import Lemma.Compiler.KernelExport
import Lemma.Platform.LemmaSim.NotebookKernel

open Lean Elab Command Lemma.Core0 Lemma.Compiler.DeploymentCatalog

/-! Invoke actual closed host exporter selectors; this creates no target AST
or program and grants no guest execution/durability qualification. -/
run_cmd do
  for (suffix, alias) in [("KernelExport.roleProfile", `companionReaderProfile),
                         ("KernelExport.rootIdentities", `companionReaderRoots)] do
    let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith suffix
    unless candidates.length = 1 do throwError "one actual closed exporter selector required"
    let selector := mkIdent candidates.head!.1
    if suffix.endsWith "roleProfile" then
      elabCommand (← `(def $(mkIdent alias) (role configuration : String) (image : Option UserImageSpec) : Except String Profile :=
        $selector role configuration image))
    else
      elabCommand (← `(def $(mkIdent alias) (configuration role : String) : Array String :=
        $selector configuration role))

#eval show IO Unit from do
  let normal := "lemmasim-silicon-usb-clocked-reader-entry2-bulk-notebook"
  let initializer := "lemmasim-silicon-usb-clocked-reader-entry2-bulk-initialize"
  for cfg in #[normal, initializer] do
    let images ← IO.ofExcept (imagesFor cfg)
    unless images == packageRecoveryReaderNotebookImages && images.size == 4 &&
        images.map (·.key) == #["store","notebook","arithmetic","course"] &&
        images[1]!.root == `Lemma.Applications.Notebook.mainRecoverablePackageReader do
      throw <| IO.userError "Reader19 lost exact four-service composition"
    for (key, profile) in #[("store",Profile.user_v0_2),("notebook",Profile.user_v0_2),
        ("arithmetic",Profile.user_v0_7),("course",Profile.user_v0_1)] do
      let image ← IO.ofExcept (imageFor cfg key)
      unless (← IO.ofExcept (companionReaderProfile "user" cfg (some image))) == profile do
        throw <| IO.userError "Reader19 actual privilege profile changed"
    unless (← IO.ofExcept (companionReaderProfile "kernel" cfg none)) == Profile.kernel_v0_6 do
      throw <| IO.userError "Reader19 did not retain Kernel6"
    let metadata := Json.mkObj (softwareDeploymentFields cfg)
    let software ← IO.ofExcept (metadata.getObjVal? "software_deployment")
    for (key,value) in #[("contract_version","lemma-package-reader-clocked-recovery5-entry2-deployment-v1"),
        ("silicon_profile","lemma-silicon-dev/0.13.0"),("entry_contract","lemma-scheduler-entry-borrow-v2"),
        ("reader_contract","lemma-course-reader-location/1"),("recovery_contract","lemma-notebook-reader-recovery/5")] do
      unless (← IO.ofExcept (software.getObjValAs? String key)) == value do
        throw <| IO.userError "Reader19 software/hardware tuple changed"
    unless companionReaderRoots cfg "kernel" == #[
        "Lemma.Platform.LemmaSim.NotebookKernel." ++ (if cfg == normal then
          "siliconUSBPackageRecoveryEntry2Boot" else "siliconUSBPackageRecoveryEntry2InitializeMedium"),
        "Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBPackageRecoveryBulk"] do
      throw <| IO.userError "Reader19 selected another kernel or an implicit initializer"
    match validateSelection cfg "notebook" #[`Lemma.Applications.Notebook.mainPackageNumberPadBookmark] with
    | .error _ => pure ()
    | .ok _ => throw <| IO.userError "Reader19 accepted a nonrecoverable reader substitution"
  unless (← IO.ofExcept (imagesFor "lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook")) ==
      packageRecoveryNumberPadNotebookImages &&
      (← IO.ofExcept (imagesFor "lemmasim-silicon-package-reader-bulk-notebook")) == packageReaderNotebookImages do
    throw <| IO.userError "Reader19 changed historical Recovery16 or Reader18"
  match imagesFor "lemmasim-silicon-usb-clocked-reader-entry2-arbitrary" with
  | .error _ => pure ()
  | .ok _ => throw <| IO.userError "Reader19 configuration family is open"
  IO.println "COMPANION_READER19_DEPLOYMENT:PASS exact four roots/profiles/Reader1/Recovery5/EntryV2/Clocked13; historical selectors preserved"
