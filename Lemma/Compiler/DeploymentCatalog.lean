import Lean
import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Host-only deployment selection. This module is never imported by target
roots. It names separately elaborated user images; it supplies no target
loading, scheduling or authority policy. -/
namespace Lemma.Compiler.DeploymentCatalog

open Lean
open Lemma.Platform.RiscV.ExecutionPrimitives (UserStartupCase)

structure UserImageSpec where
  key : String
  id : Nat
  moduleName : Name
  root : Name
  startupCase : UserStartupCase := .none
  deriving BEq, Repr

instance : Inhabited UserImageSpec := ⟨{
  key := "", id := 0, moduleName := .anonymous, root := .anonymous }⟩

def UserImageSpec.symbolPrefix (image : UserImageSpec) : String :=
  "lemma_user_" ++ image.key ++ "_"

def UserImageSpec.directory (image : UserImageSpec) : String :=
  "users/" ++ image.key

def taskImages : Array UserImageSpec := #[
  { key := "compute", id := 1, moduleName := `Lemma.User.Development.Tasks.Compute,
    root := `Lemma.User.Development.Tasks.Compute.main },
  { key := "sleeper", id := 2, moduleName := `Lemma.User.Development.Tasks.Sleeper,
    root := `Lemma.User.Development.Tasks.Sleeper.main },
  { key := "busy", id := 3, moduleName := `Lemma.User.Development.Tasks.Busy,
    root := `Lemma.User.Development.Tasks.Busy.main }]

/-- The one adversarial image belongs only to the fault-containment deployment.
Ordinary peers retain the exact sources, IDs and startup authority of Gate F. -/
def taskFaultImages : Array UserImageSpec := taskImages.push {
  key := "fault", id := 4, moduleName := `Lemma.User.Development.Tasks.Fault,
  root := `Lemma.User.Development.Tasks.Fault.main, startupCase := .supervisorCsr }

def isMultiImageConfiguration (configuration : String) : Bool :=
  configuration == "tasks-development" || configuration == "tasks-fault-development"

/-- Closed selection, rather than a file/CLI-supplied module or root. -/
def imagesFor (configuration : String) : Except String (Array UserImageSpec) :=
  if configuration == "tasks-development" then .ok taskImages
  else if configuration == "tasks-fault-development" then .ok taskFaultImages
  else .error "configuration has no admitted multiimage deployment"

def imageFor (configuration key : String) : Except String UserImageSpec := do
  let images ← imagesFor configuration
  let some image := images.find? (fun image => image.key == key)
    | throw "unknown closed user image key"
  pure image

/-- Used at each exporter boundary, including after reading manifests. -/
def validateImages (configuration : String) (images : Array UserImageSpec) : Except String Unit := do
  let selected ← imagesFor configuration
  unless !images.isEmpty && images.size ≤ 8 && images == selected do
    throw "user image registry differs from the closed selected deployment"

def validateSelection (configuration key : String) (roots : Array Name) : Except String UserImageSpec := do
  let image ← imageFor configuration key
  unless roots == #[image.root] do
    throw "user image root differs from its closed selected source"
  pure image

def imageJson (image : UserImageSpec) : Json := Json.mkObj [
  ("key", .str image.key), ("id", toJson image.id),
  ("module", .str image.moduleName.toString), ("source", .str image.root.toString),
  ("args", .arr #[.str "u64"]), ("symbol_prefix", .str image.symbolPrefix),
  ("startup_case", .str image.startupCase.stableId), ("directory", .str image.directory)]

def catalogJson (configuration : String) : Except String Json := do
  let images ← imagesFor configuration
  validateImages configuration images
  pure <| Json.mkObj [
    ("schema_version", 1), ("contract_version", .str "lemma-user-image-catalog-v1"),
    ("configuration", .str configuration), ("stage", .str "supervisor"),
    ("image_count", toJson images.size), ("images", .arr (images.map imageJson))]

end Lemma.Compiler.DeploymentCatalog
