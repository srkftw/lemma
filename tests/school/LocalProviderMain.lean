import Lemma.School.LocalProvider
open Lean Lemma.School

/-! Pure synthetic launch fixture. No VM or inferred numerical result is supplied
by this fixture; actual job/load scenarios independently execute real QEMU. -/
private def request (op : String) (fields : List (String × Json)) : Json := object <|
  [("op",toJson op),("school",toJson "school-a"),("actor",toJson "owner")] ++ fields

private def update (state : State) (op : String) (fields : List (String × Json)) : Except String State := do
  return (← LocalProvider.apply state "owner" state.clock (request op fields)).1

private def health (status : String) (image : String) : List (String × Json) :=
  [("worker",toJson "w1"),("generation",toJson (1:Nat)),("configVersion",toJson (1:Nat)),
   ("status",toJson status),("reason",toJson "deliberately synthetic launch report"),("artifacts",toJson #[image])]

def main : IO Unit := do
  let image := Digest.sha256String "synthetic component launch image"
  let initial : State := { school := "school-a", deployment := "synthetic", operator := "owner" }
  let nodeFields := [("node",toJson "local"),("version",toJson (1:Nat)),("provider",toJson "local"),
    ("profile",toJson "core0-v0.5"),("capabilities",toJson #["school-linear-worker/1"]),
    ("maxWorkers",toJson (4:Nat)),("memoryBytes",toJson (536870912:Nat)),("storageBytes",toJson (268435456:Nat))]
  let state ← IO.ofExcept (update initial "node-config" nodeFields)
  let workerFields := [("worker",toJson "w1"),("version",toJson (1:Nat)),("node",toJson "local"),
    ("controller",toJson "owner"),("profile",toJson "core0-v0.5"),("imageSha256",toJson image),
    ("capabilities",toJson #["school-linear-worker/1"]),("cpuSlots",toJson (1:Nat)),
    ("memoryBytes",toJson (134217728:Nat)),("inputBytes",toJson (88:Nat)),
    ("outputBytes",toJson (48:Nat)),("scratchBytes",toJson (16384:Nat))]
  let state ← IO.ofExcept (update state "worker-config" workerFields)
  let state ← IO.ofExcept (update state "worker-health" (health "ready" image))
  let job : Record := {
    sequence := 4,kind := "job",key := "j1",actor := "owner",time := 0,
    data := object [("status",toJson "queued"),("input",object [("kind",toJson "school-linear-worker/1"),
      ("imageSha256",toJson image)])],artifacts := #[image]}
  let reservation ← IO.ofExcept (LocalProvider.admitLease state "owner" 0 "w1" job 20)
  let leased := {job with data := object [("status",toJson "leased"),("input",← IO.ofExcept (field job.data "input")),
    ("worker",toJson "w1"),("generation",toJson (1:Nat)),("expires",toJson (1000:Nat)),("provider",reservation)]}
  let state ← IO.ofExcept (state.add "job" "j1" "owner" 0 leased.data leased.artifacts)
  let drained ← IO.ofExcept (update state "worker-drain" [("worker",toJson "w1"),("draining",toJson true)])
  let nodeDrained ← IO.ofExcept (update state "node-drain" [("node",toJson "local"),("draining",toJson true)])
  let offline ← IO.ofExcept (update state "worker-health" (health "offline" image))
  let refreshed ← IO.ofExcept (update offline "worker-health" (health "ready" image))
  let repeated ← IO.ofExcept (update state "worker-health" (health "ready" image))
  let changedWorker ← IO.ofExcept (update state "worker-config" (workerFields.map fun (name,value) =>
    if name == "version" then (name,toJson (2:Nat)) else (name,value)))
  let changedNode ← IO.ofExcept (update state "node-config" (nodeFields.map fun (name,value) =>
    if name == "version" then (name,toJson (2:Nat)) else (name,value)))
  let checks := [
    ("initial-report-permits-assigned-completion",toJson (LocalProvider.completionAllowed state leased).isOk),
    ("worker-drain-preserves-completion",toJson (LocalProvider.completionAllowed drained leased).isOk),
    ("node-drain-preserves-completion",toJson (LocalProvider.completionAllowed nodeDrained leased).isOk),
    ("offline-revokes-completion",toJson !(LocalProvider.completionAllowed offline leased).isOk),
    ("offline-ready-never-resurrects-old-lease",toJson !(LocalProvider.completionAllowed refreshed leased).isOk),
    ("identical-report-retry-keeps-epoch",toJson (repeated.records.size == state.records.size &&
      (LocalProvider.completionAllowed repeated leased).isOk)),
    ("worker-reconfiguration-supersedes-lease",toJson !(LocalProvider.completionAllowed changedWorker leased).isOk),
    ("node-budget-version-preserves-assigned-completion",toJson (LocalProvider.completionAllowed changedNode leased).isOk),
    ("restart-requires-current-generation-report",toJson !(LocalProvider.completionAllowed {state with generation := 2} leased).isOk),
    ("original-prefix-retained",toJson ((refreshed.records.extract 0 state.records.size).map toJson == state.records.map toJson))]
  IO.println (Json.mkObj checks).compress
