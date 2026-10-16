import Lemma.Compiler.KernelExport
import Lemma.Platform.LemmaSim.NotebookKernel

open Lean Elab Command Lemma.Core0 Lemma.Compiler.DeploymentCatalog

run_cmd do
  for (suffix, alias) in [("KernelExport.roleProfile", `recoveryEntry2Profile),
                         ("KernelExport.rootIdentities", `recoveryEntry2Roots)] do
    let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith suffix
    unless candidates.length = 1 do throwError "one actual closed exporter selector required"
    let selector := mkIdent candidates.head!.1
    let alias := mkIdent alias
    if suffix.endsWith "roleProfile" then
      elabCommand (← `(def $alias (role configuration : String) (image : Option UserImageSpec) : Except String Profile :=
        $selector role configuration image))
    else
      elabCommand (← `(def $alias (configuration role : String) : Array String :=
        $selector configuration role))

#eval show IO Unit from do
  let configuration := "lemmasim-silicon-usb-clocked-package-entry2-bulk-notebook"
  let selected ← IO.ofExcept (imagesFor configuration)
  unless selected.size == 4 && selected.map (·.key) == #["store", "notebook", "arithmetic", "course"] &&
      selected.map (·.id) == #[1, 2, 3, 4] do
    throw <| IO.userError "Recovery Entry2 deployment lost a separately linked role"
  unless selected[1]!.root == `Lemma.Applications.Notebook.mainRecoverablePackageNumberPad &&
      selected[2]!.root == `Lemma.Services.Arithmetic.ServerV7.main do
    throw <| IO.userError "Recovery Entry2 deployment changed Reader18/Closure7 software"
  unless recoveryEntry2Roots configuration "kernel" ==
      #["Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBPackageRecoveryEntry2Boot",
        "Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBPackageRecoveryBulk"] do
    throw <| IO.userError "Recovery Entry2 selected the historical three-role constructor"
  unless (← IO.ofExcept (recoveryEntry2Profile "kernel" configuration none)) == .kernel_v0_6 do
    throw <| IO.userError "Recovery Entry2 lost Kernel6 recovery authority"
  for image in selected do
    let expected := if image.key == "notebook" || image.key == "store" then Profile.user_v0_2 else
      if image.key == "arithmetic" then Profile.user_v0_7 else Profile.user_v0_1
    unless (← IO.ofExcept (recoveryEntry2Profile "user" configuration (some image))) == expected do
      throw <| IO.userError "Recovery Entry2 acquired the wrong User language/privilege profile"
    unless Lemma.Compiler.KernelExport.llvmModuleSourceName configuration "user" (some image) ==
        "Lemma lemma-silicon-dev/0.13.0 user " ++ image.root.toString do
      throw <| IO.userError "Recovery Entry2 is mislabeled as canonical preload hardware"
  let catalog ← IO.ofExcept (catalogJson configuration)
  let software ← IO.ofExcept (catalog.getObjValAs? Json "software_deployment")
  unless (← IO.ofExcept (software.getObjValAs? String "contract_version")) ==
      "lemma-package-clocked-recovery4-entry2-deployment-v1" &&
      (← IO.ofExcept (software.getObjValAs? String "silicon_profile")) == "lemma-silicon-dev/0.13.0" do
    throw <| IO.userError "Recovery Entry2 lacks its exact additive software/hardware contract"
  let initialized := "lemmasim-silicon-usb-clocked-package-entry2-bulk-initialize"
  unless (← IO.ofExcept (imagesFor initialized)) == selected &&
      recoveryEntry2Roots initialized "kernel" ==
        #["Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBPackageRecoveryEntry2InitializeMedium",
          "Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBPackageRecoveryBulk"] do
    throw <| IO.userError "explicit new-medium entry selector differs"
  unless recoveryEntry2Roots "lemmasim-silicon-usb-clocked-package-retry-bulk-notebook" "kernel" ==
      #["Lemma.Platform.LemmaSim.NotebookKernel.siliconUSBPackageRecoveryBoot",
        "Lemma.Platform.LemmaSim.NotebookKernel.dispatchUSBPackageRecoveryBulk"] do
    throw <| IO.userError "Entry2 changed historical companion boot selection"
  unless (← IO.ofExcept (software.getObjValAs? String "entry_contract")) == "lemma-scheduler-entry-borrow-v2" do
    throw <| IO.userError "Entry2 exact lifetime contract missing"
  match validateSelection configuration "notebook" #[`Lemma.Applications.Notebook.mainPackageNumberPadBrowse] with
  | .error _ => pure ()
  | .ok _ => throw <| IO.userError "Recovery Entry2 admits a substituted notebook root"
  IO.println "RECOVERY_ENTRY2_DEPLOYMENT:PASS exact four genuine roots/profiles/Clocked13; separate initialization; historical selections preserved"
