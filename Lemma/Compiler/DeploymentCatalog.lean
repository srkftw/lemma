import Lean
import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Host-only deployment selection. This module is never imported by target
roots. It names separately elaborated user images; it supplies no target
loading, scheduling or authority policy. -/
namespace Lemma.Compiler.DeploymentCatalog

open Lean
open Lemma.Platform.RiscV.ExecutionPrimitives (UserStartupCase)

/-- These exact deployment names select diagnostic startup authority. They
are never an independent case, module, or instruction-list input. -/
def singletonInstructionCase? (configuration : String) : Option UserStartupCase :=
  if configuration == "user-halfword-ecall-development" then some .halfwordEcall
  else if configuration == "user-return-supervisor-development" then some .returnSupervisor
  else if configuration == "user-return-machine-development" then some .returnMachine else none

def serviceInstructionCase? (configuration : String) : Option UserStartupCase :=
  if configuration == "service-halfword-ecall-development" then some .halfwordEcall
  else if configuration == "service-return-supervisor-development" then some .returnSupervisor
  else if configuration == "service-return-machine-development" then some .returnMachine else none

def isServiceConfiguration (configuration : String) : Bool :=
  configuration == "service-normal" || configuration == "service-development" ||
    configuration == "silicon-service-development" ||
    (serviceInstructionCase? configuration).isSome

def isServiceDevelopmentConfiguration (configuration : String) : Bool :=
  configuration == "service-development" || configuration == "silicon-service-development" || (serviceInstructionCase? configuration).isSome

inductive ManagedBootRole where
  | capabilities | peer | busy | tamper
  | ipcServer | ipcClientA | ipcClientB | backgroundNoGrants | ipcFaultClient
  | bufferServer | bufferCLI | bufferPeer | bufferFaultClient
  | storeServer | notebook | notebookIsolation | arithmeticServer
  deriving BEq, Repr

def ManagedBootRole.stableId : ManagedBootRole → String
  | .capabilities => "capabilities"
  | .peer => "peer"
  | .busy => "busy"
  | .tamper => "tamper"
  | .ipcServer => "ipc-server"
  | .ipcClientA => "ipc-client-a"
  | .ipcClientB => "ipc-client-b"
  | .backgroundNoGrants => "background-no-grants"
  | .ipcFaultClient => "ipc-fault-client"
  | .bufferServer => "buffer-server"
  | .bufferCLI => "buffer-cli"
  | .bufferPeer => "buffer-peer"
  | .bufferFaultClient => "buffer-fault-client"
  | .storeServer => "store-server"
  | .notebook => "notebook"
  | .notebookIsolation => "notebook-isolation-client"
  | .arithmeticServer => "arithmetic-server"

def arithmeticDevelopmentMode? (configuration : String) : Option UInt64 :=
  if configuration == "lemmasim-silicon-power-arithmetic-oom-development" || configuration == "lemmasim-silicon-sums-arithmetic-oom-development" || configuration == "lemmasim-silicon-bytes-arithmetic-oom-development" || configuration == "lemmasim-silicon-array-arithmetic-oom-development" then some 1 else
  if configuration == "lemmasim-silicon-power-arithmetic-fault-development" then some 2 else
  if configuration == "lemmasim-silicon-power-arithmetic-stall-development" then some 3 else none

def isArithmeticDevelopmentConfiguration (configuration : String) : Bool :=
  (arithmeticDevelopmentMode? configuration).isSome

/-- Software deployment successor on the unchanged canonical silicon binding. -/
def isManagedNotebookConfiguration (configuration : String) : Bool :=
  configuration == "lemmasim-silicon-managed-notebook" ||
    configuration == "lemmasim-silicon-managed-initialize"

/-- USB6 transport with the original isolated arithmetic User-v0.2 image. -/
def isUSBNotebookConfiguration (configuration : String) : Bool :=
  configuration == "lemmasim-silicon-usb-notebook" ||
    configuration == "lemmasim-silicon-usb-initialize" ||
    configuration == "lemmasim-silicon-usb-bulk-notebook" ||
    configuration == "lemmasim-silicon-usb-bulk-initialize"

/-- Product7 uses immutable ROM/NV boot; this does not format user media. -/
def isProductNotebookConfiguration (configuration : String) : Bool :=
  configuration == "lemmasim-silicon-product-notebook" ||
    configuration == "lemmasim-silicon-product-bulk-notebook"

/-- Bounded full-width arrays have their own isolated User5 software authority. -/
def isArrayNotebookConfiguration (configuration : String) : Bool :=
  configuration == "lemmasim-silicon-array-bulk-notebook" ||
    configuration == "lemmasim-silicon-array-bulk-initialize" ||
    configuration == "lemmasim-silicon-array-arithmetic-oom-development"

/-- Bounded ordinary ByteArray source execution is admitted only in its isolated User4 image. -/
def isBytesNotebookConfiguration (configuration : String) : Bool :=
  configuration == "lemmasim-silicon-bytes-bulk-notebook" ||
    configuration == "lemmasim-silicon-bytes-bulk-initialize" ||
    configuration == "lemmasim-silicon-bytes-arithmetic-oom-development"

/-- The bounded owned-page Surface ABI is a separate software selection. -/
def isBulkNotebookConfiguration (configuration : String) : Bool :=
  isArrayNotebookConfiguration configuration || isBytesNotebookConfiguration configuration ||
  configuration == "lemmasim-silicon-bulk-notebook" ||
    configuration == "lemmasim-silicon-bulk-initialize" ||
    configuration == "lemmasim-silicon-usb-bulk-notebook" ||
    configuration == "lemmasim-silicon-usb-bulk-initialize" ||
    configuration == "lemmasim-silicon-product-bulk-notebook"

/-- Additive managed sums software; hardware remains silicon0.3. -/
def isSumsNotebookConfiguration (configuration : String) : Bool :=
  (isBulkNotebookConfiguration configuration && !isBytesNotebookConfiguration configuration && !isArrayNotebookConfiguration configuration) ||
  configuration == "lemmasim-silicon-sums-notebook" ||
    configuration == "lemmasim-silicon-sums-initialize" ||
    configuration == "lemmasim-silicon-sums-arithmetic-oom-development"

def softwareDeploymentFields (configuration : String) : List (String × Json) :=
  if isArrayNotebookConfiguration configuration then
  [("software_deployment", Json.mkObj [
    ("contract_version", .str "lemma-managed-array-bulk-deployment-v1"),
    ("silicon_profile", .str "lemma-silicon-dev/0.3.0"),
    ("user_profiles", Json.mkObj [("store", .str "core0-user-v0.1"),
      ("notebook", .str "core0-user-v0.2"), ("arithmetic", .str "core0-user-v0.5")])])]
  else if isBytesNotebookConfiguration configuration then
  [("software_deployment", Json.mkObj [
    ("contract_version", .str "lemma-managed-bytes-bulk-deployment-v1"),
    ("silicon_profile", .str "lemma-silicon-dev/0.3.0"),
    ("user_profiles", Json.mkObj [("store", .str "core0-user-v0.1"),
      ("notebook", .str "core0-user-v0.2"), ("arithmetic", .str "core0-user-v0.4")])])]
  else   if isSumsNotebookConfiguration configuration then
  [("software_deployment", Json.mkObj [
    ("contract_version", .str (if configuration == "lemmasim-silicon-product-bulk-notebook" then "lemma-managed-sums-bulk-product-deployment-v1" else if isUSBNotebookConfiguration configuration then "lemma-managed-sums-bulk-usb-deployment-v1" else if isBulkNotebookConfiguration configuration then "lemma-managed-sums-bulk-deployment-v1" else "lemma-managed-sums-deployment-v1")),
    ("silicon_profile", .str (if isProductNotebookConfiguration configuration then "lemma-silicon-dev/0.7.0" else if isUSBNotebookConfiguration configuration then "lemma-silicon-dev/0.6.0" else "lemma-silicon-dev/0.3.0")),
    ("user_profiles", Json.mkObj [("store", .str "core0-user-v0.1"),
      ("notebook", .str "core0-user-v0.2"), ("arithmetic", .str "core0-user-v0.3")])])]
  else if !isManagedNotebookConfiguration configuration then [] else
  [("software_deployment", Json.mkObj [
    ("contract_version", .str "lemma-managed-notebook-deployment-v1"),
    ("silicon_profile", .str "lemma-silicon-dev/0.3.0"),
    ("user_profiles", Json.mkObj [("store", .str "core0-user-v0.1"),
      ("notebook", .str "core0-user-v0.2"), ("arithmetic", .str "core0-user-v0.2")])])]

def capabilityManagedPolicy : String := "lemma-capabilities-v1"
def ipcManagedPolicy : String := "lemma-ipc-v1"
def bufferManagedPolicy : String := "lemma-buffer-service-v1"

def managedPolicyFor (configuration : String) : Option String :=
  if configuration == "lemmasim-silicon-power-notebook" || configuration == "lemmasim-silicon-power-initialize" ||
      isArithmeticDevelopmentConfiguration configuration || isManagedNotebookConfiguration configuration || isSumsNotebookConfiguration configuration || isBytesNotebookConfiguration configuration || isArrayNotebookConfiguration configuration || isUSBNotebookConfiguration configuration || isProductNotebookConfiguration configuration then some "lemma-notebook-arithmetic-v1" else
  if configuration == "lemmasim-notebook" || configuration == "lemmasim-initialize" ||
      configuration == "lemmasim-silicon-full-notebook" || configuration == "lemmasim-silicon-notebook" || configuration == "lemmasim-silicon-full-initialize" || configuration == "lemmasim-silicon-initialize" ||
      configuration == "lemmasim-isolation-development" then some "lemma-notebook-v1"
  else if configuration == "capabilities-development" then some capabilityManagedPolicy
  else if configuration == "ipc-development" then some ipcManagedPolicy
  else if isServiceConfiguration configuration then
    some bufferManagedPolicy else none

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


/-- Gate I selects five independently linked images. The two client roots
share only their exact production-library/IPCClients source module closure. -/
def ipcImages : Array UserImageSpec := #[
  { key := "server", id := 1, moduleName := `Lemma.User.Development.IPCServer,
    root := `Lemma.User.Development.IPCServer.main, bootRole? := some .ipcServer },
  { key := "clienta", id := 2, moduleName := `Lemma.User.Development.IPCClients,
    root := `Lemma.User.Development.IPCClients.clientA, bootRole? := some .ipcClientA },
  { key := "clientb", id := 3, moduleName := `Lemma.User.Development.IPCClients,
    root := `Lemma.User.Development.IPCClients.clientB, bootRole? := some .ipcClientB },
  { taskImages[2]! with id := 4, bootRole? := some .backgroundNoGrants },
  { key := "fault", id := 5, moduleName := `Lemma.User.Development.IPCFault,
    root := `Lemma.User.Development.IPCFault.main, bootRole? := some .ipcFaultClient }]

/-- The normal service deployment consists of production executables. The
fault client is selected only by the separate development registry. -/
def serviceImages : Array UserImageSpec := #[
  { key := "server", id := 1, moduleName := `Lemma.Services.Buffer.Server,
    root := `Lemma.Services.Buffer.Server.main, bootRole? := some .bufferServer },
  { key := "cli", id := 2, moduleName := `Lemma.Applications.BufferCLI,
    root := `Lemma.Applications.BufferCLI.main, bootRole? := some .bufferCLI },
  { key := "peer", id := 3, moduleName := `Lemma.Applications.BufferPeer,
    root := `Lemma.Applications.BufferPeer.main, bootRole? := some .bufferPeer },
  { key := "busy", id := 4, moduleName := `Lemma.Applications.CPUBound,
    root := `Lemma.Applications.CPUBound.main, bootRole? := some .backgroundNoGrants }]

def serviceDevelopmentImages : Array UserImageSpec := serviceImages.push {
  key := "fault", id := 5, moduleName := `Lemma.User.Development.BufferFault,
  root := `Lemma.User.Development.BufferFault.main, bootRole? := some .bufferFaultClient }

def serviceInstructionImages (userCase : UserStartupCase) : Array UserImageSpec := serviceImages.push {
  key := "fault", id := 5, moduleName := `Lemma.User.Entry,
  root := `Lemma.User.Entry.main, startupCase := userCase, bootRole? := some .bufferFaultClient }

def notebookImages : Array UserImageSpec := #[
  { key := "store", id := 1, moduleName := `Lemma.Services.Store.Server,
    root := `Lemma.Services.Store.Server.main, bootRole? := some .storeServer },
  { key := "notebook", id := 2, moduleName := `Lemma.Applications.Notebook,
    root := `Lemma.Applications.Notebook.main, bootRole? := some .notebook }]

def arithmeticNotebookImages : Array UserImageSpec := notebookImages.push {
  key := "arithmetic", id := 3, moduleName := `Lemma.Services.Arithmetic.Server,
  root := `Lemma.Services.Arithmetic.Server.main, bootRole? := some .arithmeticServer }

def sumsNotebookImages : Array UserImageSpec := #[
  notebookImages[0]!,
  {key := "notebook", id := 2, moduleName := `Lemma.Applications.Notebook,
    root := `Lemma.Applications.Notebook.mainSums, bootRole? := some .notebook},
  {key := "arithmetic", id := 3, moduleName := `Lemma.Services.Arithmetic.ServerV3,
    root := `Lemma.Services.Arithmetic.ServerV3.main, bootRole? := some .arithmeticServer}]

def bulkNotebookImages : Array UserImageSpec := #[
  notebookImages[0]!,
  {key := "notebook", id := 2, moduleName := `Lemma.Applications.Notebook,
    root := `Lemma.Applications.Notebook.mainSumsBulk, bootRole? := some .notebook},
  sumsNotebookImages[2]!]

def bytesNotebookImages : Array UserImageSpec := #[
  notebookImages[0]!,
  {key := "notebook", id := 2, moduleName := `Lemma.Applications.Notebook,
    root := `Lemma.Applications.Notebook.mainBytesBulk, bootRole? := some .notebook},
  {key := "arithmetic", id := 3, moduleName := `Lemma.Services.Arithmetic.ServerV4,
    root := `Lemma.Services.Arithmetic.ServerV4.main, bootRole? := some .arithmeticServer}]

def arrayNotebookImages : Array UserImageSpec := #[
  notebookImages[0]!,
  {key := "notebook", id := 2, moduleName := `Lemma.Applications.Notebook,
    root := `Lemma.Applications.Notebook.mainArrayBulk, bootRole? := some .notebook},
  {key := "arithmetic", id := 3, moduleName := `Lemma.Services.Arithmetic.ServerV5,
    root := `Lemma.Services.Arithmetic.ServerV5.main, bootRole? := some .arithmeticServer}]

/-- Ordinary store/notebook specifications are byte-for-byte the selected
production peers; only this closed deployment admits the third User fixture. -/
def notebookIsolationImages : Array UserImageSpec := notebookImages.push {
  key := "isolation", id := 3, moduleName := `Lemma.User.Development.NotebookIsolation,
  root := `Lemma.User.Development.NotebookIsolation.main, bootRole? := some .notebookIsolation }

def isMultiImageConfiguration (configuration : String) : Bool :=
  isArithmeticDevelopmentConfiguration configuration || isManagedNotebookConfiguration configuration || isSumsNotebookConfiguration configuration || isBytesNotebookConfiguration configuration || isArrayNotebookConfiguration configuration || isUSBNotebookConfiguration configuration || isProductNotebookConfiguration configuration ||
  configuration == "lemmasim-silicon-power-notebook" || configuration == "lemmasim-silicon-power-initialize" || configuration == "lemmasim-notebook" || configuration == "lemmasim-initialize" ||
      configuration == "lemmasim-silicon-full-notebook" || configuration == "lemmasim-silicon-notebook" || configuration == "lemmasim-silicon-full-initialize" || configuration == "lemmasim-silicon-initialize" ||
  configuration == "lemmasim-isolation-development" || configuration == "tasks-development" || configuration == "tasks-fault-development" ||
    configuration == "capabilities-development" || configuration == "ipc-development" ||
    isServiceConfiguration configuration

/-- Closed selection, rather than a file/CLI-supplied module or root. -/
def imagesFor (configuration : String) : Except String (Array UserImageSpec) :=
  if isArrayNotebookConfiguration configuration then .ok arrayNotebookImages
  else if isBytesNotebookConfiguration configuration then .ok bytesNotebookImages
  else if isBulkNotebookConfiguration configuration then .ok bulkNotebookImages else
  if isSumsNotebookConfiguration configuration then .ok sumsNotebookImages else
  if configuration == "lemmasim-silicon-power-notebook" || configuration == "lemmasim-silicon-power-initialize" ||
      isArithmeticDevelopmentConfiguration configuration || isManagedNotebookConfiguration configuration || isUSBNotebookConfiguration configuration || isProductNotebookConfiguration configuration then .ok arithmeticNotebookImages else
  if configuration == "lemmasim-notebook" || configuration == "lemmasim-initialize" ||
      configuration == "lemmasim-silicon-full-notebook" || configuration == "lemmasim-silicon-notebook" || configuration == "lemmasim-silicon-full-initialize" || configuration == "lemmasim-silicon-initialize" then .ok notebookImages
  else if configuration == "lemmasim-isolation-development" then .ok notebookIsolationImages
  else if configuration == "tasks-development" then .ok taskImages
  else if configuration == "tasks-fault-development" then .ok taskFaultImages
  else if configuration == "capabilities-development" then .ok capabilityImages
  else if configuration == "ipc-development" then .ok ipcImages
  else if configuration == "service-normal" then .ok serviceImages
  else if configuration == "service-development" || configuration == "silicon-service-development" then .ok serviceDevelopmentImages
  else if let some userCase := serviceInstructionCase? configuration then .ok (serviceInstructionImages userCase)
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
    ((managedPolicyFor configuration).map (fun policy => [("managed_policy", Json.str policy)]) |>.getD []) ++
    softwareDeploymentFields configuration)

end Lemma.Compiler.DeploymentCatalog
