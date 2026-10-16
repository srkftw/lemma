import Lemma.Compiler.KernelExport
import Lemma.Platform.LemmaSim.NotebookKernel

open Lean Elab Command Lemma.Core0 Lemma.Compiler.DeploymentCatalog

run_cmd do
  for (suffix, alias) in [("KernelExport.roleProfile", `productReaderProfile),
                         ("KernelExport.rootIdentities", `productReaderRoots)] do
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
  let configuration := "lemmasim-silicon-product-course-reader-bulk-notebook"
  let selected ← IO.ofExcept (imagesFor configuration)
  unless selected.size == 4 && selected.map (·.key) == #["store", "notebook", "arithmetic", "course"] &&
      selected.map (·.id) == #[1, 2, 3, 4] do
    throw <| IO.userError "Product course deployment lost a separately linked role"
  unless selected[1]!.root == `Lemma.Applications.Notebook.mainPackageNumberPadBookmark &&
      selected[2]!.root == `Lemma.Services.Arithmetic.ServerV7.main do
    throw <| IO.userError "Product course deployment changed Reader18/Closure7 software"
  unless productReaderRoots configuration "kernel" ==
      #["Lemma.Platform.LemmaSim.NotebookKernel.siliconProductCourseReaderBoot",
        "Lemma.Platform.LemmaSim.NotebookKernel.dispatchProductExecutedBulk"] do
    throw <| IO.userError "Product course selected the historical three-role constructor"
  unless (← IO.ofExcept (productReaderProfile "kernel" configuration none)) == .kernel_v0_7 do
    throw <| IO.userError "Product course lost supervised product/NV authority"
  for image in selected do
    let expected := if image.key == "notebook" then Profile.user_v0_2 else
      if image.key == "arithmetic" then Profile.user_v0_7 else Profile.user_v0_1
    unless (← IO.ofExcept (productReaderProfile "user" configuration (some image))) == expected do
      throw <| IO.userError "Product course acquired the wrong User language/privilege profile"
    unless Lemma.Compiler.KernelExport.llvmModuleSourceName configuration "user" (some image) ==
        "Lemma lemma-silicon-dev/0.10.0 user " ++ image.root.toString do
      throw <| IO.userError "Product course is mislabeled as canonical preload hardware"
  let catalog ← IO.ofExcept (catalogJson configuration)
  let software ← IO.ofExcept (catalog.getObjValAs? Json "software_deployment")
  unless (← IO.ofExcept (software.getObjValAs? String "contract_version")) ==
      "lemma-package-reader-product10-deployment-v1" &&
      (← IO.ofExcept (software.getObjValAs? String "kernel_lowering")) ==
        "lemma-product-course-checked-physical-inline/1" &&
      (← IO.ofExcept (software.getObjValAs? String "silicon_profile")) == "lemma-silicon-dev/0.10.0" do
    throw <| IO.userError "Product course lacks its exact additive software/hardware contract"
  for name in #[configuration ++ "-initialize", "lemmasim-silicon-product-course-reader-bulk-initialize",
      "lemmasim-silicon-product-course-reader-arbitrary"] do
    match imagesFor name with
    | .error _ => pure ()
    | .ok _ => throw <| IO.userError "ordinary product course boot acquired formatting/arbitrary selection"
  unless (← IO.ofExcept (imagesFor "lemmasim-silicon-product-executed-bulk-notebook")).size == 3 &&
      (← IO.ofExcept (imagesFor "lemmasim-silicon-package-reader-bulk-notebook")) == packageReaderNotebookImages do
    throw <| IO.userError "Product course changed a historical deployment"
  match validateSelection configuration "notebook" #[`Lemma.Applications.Notebook.mainPackageNumberPadBrowse] with
  | .error _ => pure ()
  | .ok _ => throw <| IO.userError "Product course admits a substituted notebook root"
  IO.println "PRODUCT_COURSE_READER_DEPLOYMENT:PASS exact four genuine roots/profiles/Product10; no formatting; historical selections preserved"
