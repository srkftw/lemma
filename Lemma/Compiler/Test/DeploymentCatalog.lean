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
  logInfo "PASS: genuine source selection, exact closed F/G/H/I registries and per-image startup/managed authority fail closed"

end Lemma.Compiler.Test.DeploymentCatalog
