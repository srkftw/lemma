import Lemma.Compiler.KernelExport

/-! Genuine elaboration and closed deployment rejection checks. No fixture is
admitted into a deployment or used as target evidence. -/
namespace Lemma.Compiler.Test.DeploymentCatalog

open Lean Elab Command
open Lemma.Core0
open Lemma.Compiler
open Lemma.Compiler.DeploymentCatalog

def ordinary (argument : UInt64) : Memory.Action := .done 0 argument

run_cmd do
  let env ← getEnv
  match checkAndLowerActionSuiteForProfile env .user_v0_1 #[``ordinary] with
  | .error diagnostic => throwError diagnostic.render
  | .ok _ => pure ()
  for key in #["compute", "sleeper", "busy"] do
    let image ← match imageFor "tasks-development" key with
      | .ok image => pure image
      | .error error => throwError error
    match validateSelection "tasks-development" key #[image.root] with
    | .ok _ => pure ()
    | .error error => throwError error
    match validateSelection "tasks-development" key #[``ordinary] with
    | .ok _ => throwError "an accepted source was mistaken for a selected deployment root"
    | .error _ => pure ()
    match validateSelection "tasks-development" key #[image.root, image.root] with
    | .ok _ => throwError "duplicate image roots were admitted"
    | .error _ => pure ()
    unless image.symbolPrefix == "lemma_user_" ++ key ++ "_" && image.directory == "users/" ++ key do
      throwError "closed symbol/path derivation changed"
  for configuration in #["normal", "frames-development", "user-syscall-development", "unknown"] do
    match imagesFor configuration with
    | .ok _ => throwError "a singleton/unknown configuration acquired multiimage authority"
    | .error _ => pure ()
  for key in #["unknown", "../compute", "compute/", "Compute"] do
    match imageFor "tasks-development" key with
    | .ok _ => throwError "an unselected/path-like key was admitted"
    | .error _ => pure ()
  let first := taskImages[0]!
  for images in #[#[], #[first], #[first, first, taskImages[2]!],
      taskImages.set! 1 { taskImages[1]! with id := 1 },
      taskImages.set! 0 { first with moduleName := `Lemma.User.Development.Tasks.Busy },
      taskImages.set! 0 { first with root := ``ordinary }, taskImages.reverse] do
    match validateImages "tasks-development" images with
    | .ok _ => throwError "a forged/incomplete/reordered deployment catalog was admitted"
    | .error _ => pure ()
  match validateImages "tasks-development" taskImages with
  | .ok _ => pure ()
  | .error error => throwError error
  unless taskFaultImages.extract 0 3 == taskImages &&
      taskImages.all (fun image => image.startupCase == .none) do
    throwError "fault deployment changed the ordinary Gate F peers or startup authority"
  let fault ← match imageFor "tasks-fault-development" "fault" with
    | .ok image => pure image
    | .error error => throwError error
  unless fault.id == 4 && fault.moduleName == `Lemma.User.Development.Tasks.Fault &&
      fault.root == `Lemma.User.Development.Tasks.Fault.main && fault.startupCase == .supervisorCsr do
    throwError "fault startup authority escaped its exact fourth-image source"
  match imageFor "tasks-development" "fault" with
  | .ok _ => throwError "ordinary Gate F acquired the fault image"
  | .error _ => pure ()
  match validateImages "tasks-fault-development" taskFaultImages with
  | .ok _ => pure ()
  | .error error => throwError error
  for images in #[taskImages, taskFaultImages.reverse,
      taskFaultImages.set! 0 { taskFaultImages[0]! with startupCase := .supervisorCsr },
      taskFaultImages.set! 3 { fault with startupCase := .none },
      taskFaultImages.set! 3 { fault with moduleName := `Lemma.User.Development.Tasks.Compute },
      taskFaultImages.set! 3 { fault with root := ``ordinary }] do
    match validateImages "tasks-fault-development" images with
    | .ok _ => throwError "a forged fault startup authority/module/root/order was admitted"
    | .error _ => pure ()
  match validateSelection "tasks-fault-development" "compute" #[fault.root] with
  | .ok _ => throwError "fault source crossed the ordinary compute image selection"
  | .error _ => pure ()
  unless managedPolicyFor "capabilities-development" == some "lemma-capabilities-v1" &&
      managedPolicyFor "tasks-development" == none && managedPolicyFor "tasks-fault-development" == none &&
      capabilityImages.size == 4 && capabilityImages.all (fun image => image.startupCase == .none && image.bootRole?.isSome) do
    throwError "managed policy/boot roles escaped the exact H deployment"
  let managedFirst := capabilityImages[0]!
  for key in #["capabilities", "peer", "busy", "tamper"] do
    let image ← match imageFor "capabilities-development" key with
      | .ok image => pure image
      | .error error => throwError error
    unless image.bootRole?.map ManagedBootRole.stableId == some key do
      throwError "managed boot role differs from its source-selected image"
    match validateSelection "capabilities-development" key #[image.root] with
    | .ok _ => pure ()
    | .error error => throwError error
  for images in #[taskFaultImages, capabilityImages.reverse,
      capabilityImages.set! 0 { managedFirst with bootRole? := none },
      capabilityImages.set! 0 { managedFirst with bootRole? := some .peer },
      capabilityImages.set! 0 { managedFirst with startupCase := .supervisorCsr },
      capabilityImages.set! 0 { managedFirst with root := ``ordinary },
      capabilityImages.set! 0 { managedFirst with moduleName := `Lemma.User.Development.CapabilitiesPeer }] do
    match validateImages "capabilities-development" images with
    | .ok _ => throwError "a forged H managed role/startup/module/root/order was admitted"
    | .error _ => pure ()
  for configuration in #["tasks-development", "tasks-fault-development"] do
    match imageFor configuration "capabilities" with
    | .ok _ => throwError "H managed source escaped to an earlier deployment"
    | .error _ => pure ()
  unless managedPolicyFor "ipc-development" == some "lemma-ipc-v1" && ipcImages.size == 5 &&
      ipcImages.all (fun image => image.startupCase == .none && image.bootRole?.isSome) do
    throwError "IPC policy/roles differ from their exact deployment"
  let clientA := ipcImages[1]!
  let clientB := ipcImages[2]!
  unless clientA.moduleName == clientB.moduleName && clientA.root != clientB.root &&
      clientA.key == "clienta" && clientB.key == "clientb" &&
      clientA.symbolPrefix == "lemma_user_clienta_" && clientB.symbolPrefix == "lemma_user_clientb_" do
    throwError "shared client source module collapsed separate roots/symbol namespaces"
  for key in #["server", "clienta", "clientb", "busy", "fault"] do
    let image ← match imageFor "ipc-development" key with
      | .ok image => pure image
      | .error error => throwError error
    match validateSelection "ipc-development" key #[image.root] with
    | .ok _ => pure ()
    | .error error => throwError error
  for images in #[capabilityImages, ipcImages.reverse,
      ipcImages.set! 1 { clientA with root := clientB.root },
      ipcImages.set! 1 { clientA with bootRole? := clientB.bootRole? },
      ipcImages.set! 1 { clientA with startupCase := .supervisorCsr },
      ipcImages.set! 4 { ipcImages[4]! with moduleName := `Lemma.User.Development.Tasks.Fault }] do
    match validateImages "ipc-development" images with
    | .ok _ => throwError "forged IPC root/role/startup/module/order admitted"
    | .error _ => pure ()
  for configuration in #["tasks-development", "tasks-fault-development", "capabilities-development"] do
    match imageFor configuration "clienta" with
    | .ok _ => throwError "IPC client escaped to an earlier deployment"
    | .error _ => pure ()
  match validateSelection "ipc-development" "clienta" #[clientB.root] with
  | .ok _ => throwError "client B root crossed separately linked client A selection"
  | .error _ => pure ()
  for (suffix, userCase) in #[("halfword-ecall", Lemma.Platform.RiscV.ExecutionPrimitives.UserStartupCase.halfwordEcall),
      ("return-supervisor", .returnSupervisor), ("return-machine", .returnMachine)] do
    let singleton := "user-" ++ suffix ++ "-development"
    let managed := "service-" ++ suffix ++ "-development"
    unless singletonInstructionCase? singleton == some userCase &&
        serviceInstructionCase? managed == some userCase &&
        singletonInstructionCase? managed == none && serviceInstructionCase? singleton == none do
      throwError "instruction startup authority crossed its exact deployment kind"
    let images ← match imagesFor managed with
      | .ok images => pure images
      | .error error => throwError error
    unless images.extract 0 4 == serviceImages && images.size == 5 do
      throwError "instruction quarantine changed ordinary service images"
    let probe := images[4]!
    unless probe.moduleName == `Lemma.User.Entry && probe.root == `Lemma.User.Entry.main &&
        probe.startupCase == userCase && probe.id == 5 && probe.key == "fault" do
      throwError "instruction probe lacks its exact genuine Entry precondition"
    for forged in #[images.set! 0 { images[0]! with startupCase := userCase },
        images.set! 4 { probe with startupCase := .none },
        images.set! 4 { probe with root := `Lemma.User.Development.BufferFault.main }] do
      match validateImages managed forged with
      | .ok _ => throwError "instruction authority escaped its selected fifth image"
      | .error _ => pure ()
    match imagesFor singleton with
    | .ok _ => throwError "singleton instruction startup acquired managed images"
    | .error _ => pure ()
  for unknown in #["service-halfword-ecall", "service-normal-return-machine-development", "user-unknown-development"] do
    unless singletonInstructionCase? unknown == none && serviceInstructionCase? unknown == none do
      throwError "unknown instruction configuration admitted"
  unless notebookIsolationImages.extract 0 2 == notebookImages && notebookIsolationImages.size == 3 do
    throwError "isolation deployment changed the production store/notebook images"
  let isolated ← match imageFor "lemmasim-isolation-development" "isolation" with
    | .ok image => pure image
    | .error error => throwError error
  unless isolated.id == 3 && isolated.moduleName == `Lemma.User.Development.NotebookIsolation &&
      isolated.root == `Lemma.User.Development.NotebookIsolation.main && isolated.startupCase == .none &&
      isolated.bootRole?.map ManagedBootRole.stableId == some "notebook-isolation-client" do
    throwError "isolation fixture escaped its ordinary User source/role"
  for configuration in #["lemmasim-notebook", "lemmasim-initialize", "service-normal"] do
    match imageFor configuration "isolation" with
    | .ok _ => throwError "isolation fixture entered a production deployment"
    | .error _ => pure ()
  for forged in #[notebookImages, notebookIsolationImages.reverse,
      notebookIsolationImages.set! 0 isolated,
      notebookIsolationImages.set! 2 { isolated with startupCase := .supervisorCsr },
      notebookIsolationImages.set! 2 { isolated with root := `Lemma.Applications.Notebook.main }] do
    match validateImages "lemmasim-isolation-development" forged with
    | .ok _ => throwError "forged isolation startup/source/catalog admitted"
    | .error _ => pure ()
  for configuration in #["lemmasim-silicon-school24-notebook", "lemmasim-silicon-school24-initialize",
      "lemmasim-silicon-integrated-school24-notebook", "lemmasim-silicon-integrated-pcm-school24-notebook"] do
    let images ← match imagesFor configuration with
      | .ok images => pure images
      | .error error => throwError error
    unless images == school24NotebookImages && images.size == 4 &&
        images[0]! == schoolNotebookImages[0]! && images[3]! == schoolNotebookImages[3]! &&
        images[1]!.id == 2 && images[2]!.id == 3 &&
        images[1]!.root == `Lemma.Applications.Notebook.mainMultimodalSchool24 &&
        images[2]!.root == `Lemma.Services.Arithmetic.ServerV9.main &&
        images[1]!.bootRole? == some .notebook && images[2]!.bootRole? == some .arithmeticServer do
      throwError "School24 changed unrelated images, identifiers or boot authority"
    match validateImages configuration schoolNotebookImages with
    | .ok _ => throwError "School23 roots entered School24"
    | .error _ => pure ()
    for key in #["notebook", "arithmetic"] do
      let image ← match imageFor configuration key with
        | .ok image => pure image
        | .error error => throwError error
      match validateSelection configuration key #[image.root] with
      | .ok _ => pure ()
      | .error error => throwError error
      match validateSelection configuration key #[schoolNotebookImages[if key == "notebook" then 1 else 2]!.root] with
      | .ok _ => throwError "another version acquired an exact School24 role"
      | .error _ => pure ()
  for configuration in #["lemmasim-silicon-school-notebook", "lemmasim-silicon-school-initialize",
      "lemmasim-silicon-integrated-school-notebook", "lemmasim-silicon-integrated-pcm-school-notebook"] do
    match validateImages configuration school24NotebookImages with
    | .ok _ => throwError "School24 roots entered historical School23"
    | .error _ => pure ()
  for configuration in #["lemmasim-silicon-school25-notebook", "lemmasim-silicon-school24-arithmetic",
      "lemmasim-silicon-school24-notebook/../initialize"] do
    match imagesFor configuration with
    | .ok _ => throwError "unknown School deployment acquired root authority"
    | .error _ => pure ()
  logInfo "PASS: genuine source selection, closed registries, School23/24 separation and per-image startup/managed authority fail closed"

end Lemma.Compiler.Test.DeploymentCatalog
