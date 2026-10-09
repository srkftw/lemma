import Lean
import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Host-only deployment selection. This module is never imported by target
roots. It names separately elaborated user images; it supplies no target
loading, scheduling or authority policy. -/
namespace Lemma.Compiler.DeploymentCatalog

open Lean
open Lemma.Platform.RiscV.ExecutionPrimitives (UserStartupCase)

inductive ManagedBootRole where
  | capabilities | peer | busy | tamper
  deriving BEq, Repr

def ManagedBootRole.stableId : ManagedBootRole → String
  | .capabilities => "capabilities"
  | .peer => "peer"
  | .busy => "busy"
  | .tamper => "tamper"

def capabilityManagedPolicy : String := "lemma-capabilities-v1"

def managedPolicyFor (configuration : String) : Option String :=
  if configuration == "capabilities-development" then some capabilityManagedPolicy else none

structure UserImageSpec where
  key : String
  id : Nat
  moduleName : Name
  root : Name
  startupCase : UserStartupCase := .none
  bootRole? : Option ManagedBootRole := none
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

def capabilityImages : Array UserImageSpec := #[
  { key := "capabilities", id := 1, moduleName := `Lemma.User.Development.Capabilities,
    root := `Lemma.User.Development.Capabilities.main, bootRole? := some .capabilities },
  { key := "peer", id := 2, moduleName := `Lemma.User.Development.CapabilitiesPeer,
    root := `Lemma.User.Development.CapabilitiesPeer.main, bootRole? := some .peer },
  { taskImages[2]! with bootRole? := some .busy },
  { key := "tamper", id := 4, moduleName := `Lemma.User.Development.CapabilitiesTamper,
    root := `Lemma.User.Development.CapabilitiesTamper.main, bootRole? := some .tamper }]

def isMultiImageConfiguration (configuration : String) : Bool :=
  configuration == "tasks-development" || configuration == "tasks-fault-development" ||
    configuration == "capabilities-development"

/-- Closed selection, rather than a file/CLI-supplied module or root. -/
def imagesFor (configuration : String) : Except String (Array UserImageSpec) :=
  if configuration == "tasks-development" then .ok taskImages
  else if configuration == "tasks-fault-development" then .ok taskFaultImages
  else if configuration == "capabilities-development" then .ok capabilityImages
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

def imageJson (image : UserImageSpec) : Json := Json.mkObj ([
  ("key", .str image.key), ("id", toJson image.id),
  ("module", .str image.moduleName.toString), ("source", .str image.root.toString),
  ("args", .arr #[.str "u64"]), ("symbol_prefix", .str image.symbolPrefix),
  ("startup_case", .str image.startupCase.stableId), ("directory", .str image.directory)] ++
  (image.bootRole?.map (fun role => [("boot_role", Json.str role.stableId)]) |>.getD []))

def catalogJson (configuration : String) : Except String Json := do
  let images ← imagesFor configuration
  validateImages configuration images
  pure <| Json.mkObj ([
    ("schema_version", 1), ("contract_version", .str "lemma-user-image-catalog-v1"),
    ("configuration", .str configuration), ("stage", .str "supervisor"),
    ("image_count", toJson images.size), ("images", .arr (images.map imageJson))] ++
    ((managedPolicyFor configuration).map (fun policy => [("managed_policy", Json.str policy)]) |>.getD []))

end Lemma.Compiler.DeploymentCatalog
