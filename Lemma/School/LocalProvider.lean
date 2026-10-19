import Lemma.School.Model
import Lemma.School.Digest

/-! A bounded, single-machine provider registry and admission policy. Registered
resources are owner declarations, not remote attestation or OS cgroup limits.
Ready means the controller reports ready to launch; actual VM READY and execution
bytes remain independent worker evidence. Runtime identities stay out of reusable
school packages. All decisions are pure; Authority verifies local artifact bytes. -/
namespace Lemma.School.LocalProvider
open Lean

structure Node where
  schema : String := "lemma-local-node/1"
  node : String
  version : Nat
  provider : String
  profile : String
  capabilities : Array String
  maxWorkers : Nat
  memoryBytes : Nat
  storageBytes : Nat
  deriving ToJson, FromJson

structure Worker where
  schema : String := "lemma-local-worker/1"
  worker : String
  version : Nat
  node : String
  controller : String
  profile : String
  imageSha256 : String
  capabilities : Array String
  cpuSlots : Nat
  memoryBytes : Nat
  inputBytes : Nat
  outputBytes : Nat
  scratchBytes : Nat
  deriving ToJson, FromJson

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

private def fields (request : Json) (extra : Array String) : Except String Unit := do
  let allowed := #["op","school","actor","now"] ++ extra
  for (name,_) in (← request.getObj?).toList do
    require (allowed.contains name) s!"unsupported local provider field {name}"

private def node (state : State) : Except String (Record × Node) := do
  let row ← (state.latest "provider-node" "local").toExcept "local provider node is not configured"
  return (row,← fromJson? row.data)

private def worker (state : State) (id : String) : Except String (Record × Worker) := do
  let row ← (state.latest "provider-worker" id).toExcept "local provider worker is not configured"
  return (row,← fromJson? row.data)

private def controller (state : State) (actor : String) (config : Worker) : Except String Unit := do
  require (actor == state.operator || actor == config.controller) "local worker controller denied"

private def append (state : State) (kind id actor : String) (now : Nat)
    (data : Json) (artifacts : Array String := #[]) : Except String (State × Record) := do
  if let some old := state.latest kind id then
    if old.data == data && old.artifacts == artifacts then return (state,old)
  let next ← state.add kind id actor now data artifacts
  return (next,next.records.back!)

private def configure (state : State) (kind id actor : String) (now version : Nat)
    (data : Json) (artifacts : Array String := #[]) : Except String (State × Record) := do
  require (version > 0 && version ≤ 0x7ffffffffffffffe) "invalid local provider configuration version"
  if let some old := state.latest kind id then
    if old.data == data && old.artifacts == artifacts then return (state,old)
    require (version > optionalNat old.data "version") "local provider configuration version must advance"
  append state kind id actor now data artifacts

private def decodeNode (state : State) (request : Json) : Except String Node := do
  fields request #["node","version","provider","profile","capabilities","maxWorkers","memoryBytes","storageBytes"]
  let config : Node := {
    node := ← str request "node", version := ← nat request "version",
    provider := ← str request "provider", profile := ← str request "profile",
    capabilities := ← (field request "capabilities" >>= fromJson?), maxWorkers := ← nat request "maxWorkers",
    memoryBytes := ← nat request "memoryBytes", storageBytes := ← nat request "storageBytes" }
  require (config.node == "local" && config.provider == "local") "unsupported local provider/node"
  require (config.profile == "core0-v0.5" && config.capabilities == #["school-linear-worker/1"])
    "unsupported local node profile or capability"
  require (config.maxWorkers > 0 && config.maxWorkers ≤ state.budgets.maxLeased)
    "local node slots exceed school lease budget"
  require (config.memoryBytes ≥ 134217728 && config.memoryBytes ≤ 2147483648 &&
    config.storageBytes > 0 && config.storageBytes ≤ 1073741824) "local node memory/storage budget outside profile"
  return config

private def decodeWorker (state : State) (request : Json) : Except String Worker := do
  fields request #["worker","version","node","controller","profile","imageSha256","capabilities",
    "cpuSlots","memoryBytes","inputBytes","outputBytes","scratchBytes"]
  let config : Worker := {
    worker := ← str request "worker",version := ← nat request "version",
    node := ← str request "node",controller := ← str request "controller",profile := ← str request "profile",
    imageSha256 := ← str request "imageSha256",capabilities := ← (field request "capabilities" >>= fromJson?),
    cpuSlots := ← nat request "cpuSlots",memoryBytes := ← nat request "memoryBytes",
    inputBytes := ← nat request "inputBytes",outputBytes := ← nat request "outputBytes",
    scratchBytes := ← nat request "scratchBytes"}
  let (_,host) ← node state
  require (validId config.worker && validId config.controller && config.node == host.node)
    "invalid local worker identity/controller/node"
  require (config.profile == host.profile && config.capabilities == #["school-linear-worker/1"] &&
    Digest.valid config.imageSha256) "unsupported local worker profile/capability/image"
  require (config.cpuSlots == 1 && config.memoryBytes == 134217728 && config.inputBytes == 88 &&
    config.outputBytes == 48 && config.scratchBytes == 16384) "unsupported local worker resource profile"
  require ((state.latest "provider-worker" config.worker).isSome || (state.allLatest "provider-worker").size < 64)
    "local worker registry capacity reached"
  return config

private def draining (state : State) (kind id : String) : Bool :=
  (state.latest kind id).any (fun row => flag row.data "draining")

/-- Append-only operator configuration and controller reports. Ready reports
bind an explicit current config and execution generation. Artifact availability
is verified by the effectful caller before committing the returned record. -/
def apply (state : State) (actor : String) (now : Nat) (request : Json) : Except String (State × Record) := do
  require ((← state.checkSchool request) == actor) "local provider actor differs from request"
  match ← str request "op" with
  | "node-config" =>
    state.authorize actor "admin" "school"
    let config ← decodeNode state request
    configure state "provider-node" config.node actor now config.version (toJson config)
  | "worker-config" =>
    state.authorize actor "admin" "school"
    let config ← decodeWorker state request
    configure state "provider-worker" config.worker actor now config.version (toJson config) #[config.imageSha256]
  | "worker-health" =>
    fields request #["worker","configVersion","generation","status","reason","artifacts"]
    let id ← str request "worker"
    let (_,config) ← worker state id
    controller state actor config
    let version ← nat request "configVersion"
    let generation ← nat request "generation"
    let status ← str request "status"
    let reason ← str request "reason"
    let artifacts : Array String ← field request "artifacts" >>= fromJson?
    require (version == config.version && generation == state.generation) "local health configuration/generation is stale"
    require (#["unknown","ready","offline"].contains status) "unsupported local worker health"
    require (!reason.trimAscii.toString.isEmpty && reason.utf8ByteSize ≤ 512 && artifacts.size ≤ 32 &&
      artifacts.all Digest.valid) "invalid local worker health reason/artifact closure"
    if status == "ready" then
      require (artifacts.contains config.imageSha256) "ready-to-launch report must reference the configured image"
    append state "provider-health" id actor now (object [("schema",toJson "lemma-local-health/1"),
      ("worker",toJson id),("configVersion",toJson version),("generation",toJson generation),
      ("status",toJson status),("reason",toJson reason),
      ("scope",toJson "authorized controller report; ready-to-launch, not independently observed VM readiness")]) artifacts
  | "node-drain" =>
    state.authorize actor "admin" "school"
    fields request #["node","draining"]
    let id ← str request "node"
    let (_,config) ← node state
    require (id == config.node) "local node differs"
    let value ← field request "draining" >>= Json.getBool?
    append state "provider-node-drain" id actor now (object [("node",toJson id),("draining",toJson value)])
  | "worker-drain" =>
    fields request #["worker","draining"]
    let id ← str request "worker"
    let (_,config) ← worker state id
    controller state actor config
    let value ← field request "draining" >>= Json.getBool?
    append state "provider-worker-drain" id actor now (object [("worker",toJson id),("draining",toJson value)])
  | _ => throw "unsupported local provider operation"

def numerical (row : Record) : Bool :=
  match field row.data "input" with
  | .ok input => optionalStr input "kind" == "school-linear-worker/1"
  | .error _ => false

private def active (state : State) (now : Nat) : Array Record :=
  (state.allLatest "job").filter (fun row => numerical row && optionalStr row.data "status" == "leased" &&
    optionalNat row.data "generation" == state.generation && optionalNat row.data "expires" > now)

private def reportedReady (state : State) (config : Worker) : Except String Record := do
  let health ← (state.latest "provider-health" config.worker).toExcept "local worker has no readiness report"
  require (optionalStr health.data "status" == "ready") "local worker is not reported ready to launch"
  require (optionalNat health.data "configVersion" == config.version &&
    optionalNat health.data "generation" == state.generation) "local worker readiness configuration/generation is stale"
  return health

/-- `artifactBytes` is the effectful caller's sum of verified unique job CAS
bytes. Storage budgets reserve each concurrent lease's entire closure, including
shared bytes conservatively; they are not a filesystem free-space guarantee. -/
def admitLease (state : State) (actor : String) (now : Nat) (id : String)
    (job : Record) (artifactBytes : Nat) : Except String Json := do
  if !numerical job then return Json.null
  let (nodeRow,host) ← node state
  let (workerRow,config) ← worker state id
  controller state actor config
  require (config.node == host.node && config.profile == host.profile) "local worker node/profile differs"
  let input ← field job.data "input"
  require (optionalStr input "imageSha256" == config.imageSha256 && job.artifacts.contains config.imageSha256)
    "local worker image differs from declared job artifact"
  require (!draining state "provider-node-drain" host.node && !draining state "provider-worker-drain" id)
    "local node or worker is draining"
  let health ← reportedReady state config
  let jobs := active state now
  require (!(jobs.any (fun row => optionalStr row.data "worker" == id))) "local worker already owns an active lease"
  require (jobs.size < host.maxWorkers) "local node worker slots exhausted"
  let reservations := jobs.map (fun row => (field row.data "provider").toOption.getD Json.null)
  let memory := reservations.foldl (fun total value => total + optionalNat value "memoryBytes" 134217728) 0
  let storage := reservations.foldl (fun total value => total + optionalNat value "storageBytes") 0
  require (memory + config.memoryBytes ≤ host.memoryBytes) "local node memory reservation exhausted"
  require (storage + artifactBytes ≤ host.storageBytes) "local node artifact storage reservation exhausted"
  return object [("schema",toJson "lemma-local-lease/1"),("node",toJson host.node),
    ("nodeVersion",toJson host.version),("nodeSequence",toJson nodeRow.sequence),
    ("workerVersion",toJson config.version),("workerSequence",toJson workerRow.sequence),
    ("healthSequence",toJson health.sequence),("profile",toJson config.profile),
    ("cpuSlots",toJson config.cpuSlots),("memoryBytes",toJson config.memoryBytes),
    ("storageBytes",toJson artifactBytes),("inputBytes",toJson config.inputBytes),
    ("outputBytes",toJson config.outputBytes),("scratchBytes",toJson config.scratchBytes),
    ("scope",toJson "declared local launch resources; CAS bytes verified; no cgroup or physical-ready attestation")]

/-- A drain permits work already assigned to finish. A new health report,
worker reconfiguration or restart supersedes its exact launch authority; an
offline→ready transition cannot resurrect an old assignment. Identical report
retries retain their original sequence. Node budget changes govern new leases;
existing reservations retain the node version under which they were admitted.
Reconciliation requeues superseded work; ordinary lease fencing rejects its old
response. -/
def completionAllowed (state : State) (job : Record) : Except String Unit := do
  if !numerical job then return
  let (_,config) ← worker state (optionalStr job.data "worker")
  let health ← reportedReady state config
  let reservation ← field job.data "provider"
  require (optionalNat reservation "workerVersion" == config.version) "local worker configuration superseded lease"
  require (optionalNat reservation "healthSequence" == health.sequence) "local worker health report superseded lease"

def unavailable (state : State) (job : Record) : Bool :=
  numerical job && !(completionAllowed state job).isOk

def describe (state : State) : Json := object [
  ("schema",toJson "lemma-local-provider/1"),("provider",toJson "local"),
  ("nodes",toJson (state.allLatest "provider-node")),("workers",toJson (state.allLatest "provider-worker")),
  ("health",toJson (state.allLatest "provider-health")),
  ("nodeDrains",toJson (state.allLatest "provider-node-drain")),
  ("workerDrains",toJson (state.allLatest "provider-worker-drain")),
  ("generation",toJson state.generation),
  ("scope",toJson "one local declared provider; explicit current-generation ready-to-launch reports; no VM attestation, cgroups, remote placement or failover")]

end Lemma.School.LocalProvider
