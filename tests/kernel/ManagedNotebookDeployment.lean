import Lemma.Compiler.KernelExport
open Lean Elab Command Lemma.Core0 Lemma.Compiler.DeploymentCatalog
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith "KernelExport.roleProfile"
  unless candidates.length = 1 do throwError "expected exact exporter profile selector"
  let n := mkIdent candidates.head!.1
  let alias := mkIdent `actualDeploymentProfile
  elabCommand (← `(def $alias (role configuration : String) (image : Option UserImageSpec) : Except String Profile :=
    $n role configuration image))
#eval do
  for configuration in ["lemmasim-silicon-managed-notebook", "lemmasim-silicon-managed-initialize"] do
    let selected ← IO.ofExcept (imagesFor configuration)
    let legacy ← IO.ofExcept (imagesFor "lemmasim-silicon-power-notebook")
    unless selected == legacy do throw <| IO.userError "software successor changed the selected images"
    let catalog ← IO.ofExcept (catalogJson configuration)
    let software ← IO.ofExcept (catalog.getObjValAs? Json "software_deployment")
    let expected := (softwareDeploymentFields configuration).head!.2
    unless software == expected do throw <| IO.userError "software deployment catalog omitted its exact version"
    let kernel ← IO.ofExcept (actualDeploymentProfile "kernel" configuration none)
    unless kernel == Profile.kernel_v0_4 do throw <| IO.userError "software successor changed kernel privilege profile"
    for image in selected do
      let profile ← IO.ofExcept (actualDeploymentProfile "user" configuration (some image))
      unless profile == (if image.key == "store" then Profile.user_v0_1 else Profile.user_v0_2) do
        throw <| IO.userError "new image has wrong explicit profile"
      unless Lemma.Compiler.KernelExport.llvmModuleSourceName configuration "user" (some image) ==
          "Lemma lemma-silicon-dev/0.3.0 user " ++ image.root.toString do
        throw <| IO.userError "software successor changed hardware source identity"
  for configuration in ["lemmasim-silicon-power-notebook", "lemmasim-silicon-power-initialize"] do
    let notebook ← IO.ofExcept (imageFor configuration "notebook")
    let profile ← IO.ofExcept (actualDeploymentProfile "user" configuration (some notebook))
    unless profile == Profile.user_v0_1 && (softwareDeploymentFields configuration).isEmpty do
      throw <| IO.userError "historical Notebook profile/catalog changed"
  IO.println "MANAGED_NOTEBOOK_DEPLOYMENT:PASS genuine exporter profile selector and exact catalog; legacy remains User-v0.1"
