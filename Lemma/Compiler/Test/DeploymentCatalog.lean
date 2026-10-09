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
  logInfo "PASS: genuine source selection, exact closed F/G registries and per-image startup authority fail closed"

end Lemma.Compiler.Test.DeploymentCatalog
