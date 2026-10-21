import Lean

/-! Versioned hosted school control records. These are application data, not
an expansion of any Core0 language profile or an authentication mechanism. -/
def Option.toExcept {α : Type} (value : Option α) (message : String) : Except String α :=
  match value with | some a => .ok a | none => .error message

namespace Lemma.School
open Lean

structure Budgets where
  maxEvents : Nat := 10000
  maxArtifactBytes : Nat := 8388608
  maxQueued : Nat := 32
  interactiveReserve : Nat := 4
  maxLeased : Nat := 4
  maxRetries : Nat := 3
  maxLeaseMs : Nat := 60000
  deriving Inhabited, FromJson, ToJson

/-- Append-only authoritative transaction. `artifacts` is the required immutable
closure; indexes may be rebuilt from this ordered history. -/
structure Record where
  sequence : Nat
  kind : String
  key : String
  actor : String
  time : Nat
  data : Json
  artifacts : Array String := #[]
  deriving Inhabited, FromJson, ToJson

structure State where
  schema : String := "lemma-school-state/2"
  school : String
  deployment : String
  operator : String
  generation : Nat := 1
  clock : Nat := 0
  clockModel : String := "monotonic-ms"
  /-- Logical scheduling time is anchored to one identified host boot. Old
  records keep their original times; unknown elapsed time across boots freezes. -/
  clockEpoch : String := ""
  clockEpochSequence : Nat := 0
  clockAnchor : Nat := 0
  clockBase : Nat := 0
  budgets : Budgets := {}
  records : Array Record := #[]
  deriving Inhabited, FromJson, ToJson

def State.latest (state : State) (kind key : String) : Option Record :=
  state.records.toList.reverse.find? (fun r => r.kind == kind && r.key == key)

def State.allLatest (state : State) (kind : String) : Array Record := Id.run do
  let mut keys : Array String := #[]
  let mut rows : Array Record := #[]
  for r in state.records.toList.reverse do
    if r.kind == kind && !keys.contains r.key then
      keys := keys.push r.key
      rows := rows.push r
  return rows.reverse

def State.references (state : State) : Array String :=
  state.records.foldl (fun refs row => row.artifacts.foldl
    (fun refs digest => if refs.contains digest then refs else refs.push digest) refs) #[]

def validId (value : String) : Bool :=
  !value.isEmpty && value.utf8ByteSize <= 128 &&
    value.toList.all (fun c => c.isAlphanum || c == '-' || c == '_' || c == '.')

def field (json : Json) (name : String) : Except String Json :=
  json.getObjVal? name
def str (json : Json) (name : String) : Except String String := do
  (← field json name).getStr?
def nat (json : Json) (name : String) : Except String Nat := do
  (← field json name).getNat?
def optionalNat (json : Json) (name : String) (fallback : Nat := 0) : Nat :=
  (nat json name).toOption.getD fallback
def optionalStr (json : Json) (name : String) (fallback : String := "") : String :=
  (str json name).toOption.getD fallback
def flag (json : Json) (name : String) : Bool :=
  ((field json name >>= Json.getBool?).toOption).getD false
def object (fields : List (String × Json)) : Json := Json.mkObj fields

/-- Lease deadlines belong to the current boot's monotonic domain. Logical
scheduling time remains the independent review/history clock. -/
def State.bootTime (state : State) (logicalTime : Nat) : Nat :=
  if state.clockModel == "controlled-ms" then logicalTime
  else state.clockAnchor + (logicalTime - state.clockBase)

def State.liveLease (state : State) (data : Json) (now : Nat) : Bool :=
  optionalNat data "generation" == state.generation &&
  if (field data "leaseBootExpires").isOk then
    optionalStr data "leaseClockEpoch" == state.clockEpoch &&
      optionalNat data "leaseBootExpires" > state.bootTime now
  else
    -- Historical controlled-clock fixtures remain readable. Migrating an old
    -- operational state binds a nonempty epoch and fences all its old leases.
    state.clockEpoch.isEmpty && optionalNat data "expires" > now

def State.add (state : State) (kind key actor : String) (time : Nat)
    (data : Json) (artifacts : Array String := #[]) : Except String State := do
  if state.records.size >= state.budgets.maxEvents then throw "record quota reached; export before extending capacity"
  if !validId actor || key.isEmpty || key.utf8ByteSize > 256 then throw "invalid actor or record key"
  if time < state.clock then throw "authority clock rollback rejected"
  return { state with clock := time, records := state.records.push {
    sequence := state.records.size + 1, kind, key, actor, time, data, artifacts } }

def State.authorize (state : State) (actor action resource : String) : Except String Unit := do
  if !validId actor then throw "invalid actor"
  if actor == state.operator then return
  let grants := state.allLatest "grant"
  unless grants.any (fun row => optionalStr row.data "subject" == actor &&
      optionalStr row.data "action" == action && optionalStr row.data "resource" == resource &&
      !flag row.data "revoked") do
    throw s!"grant denied: {actor}/{action}/{resource}"

def State.checkSchool (state : State) (request : Json) : Except String String := do
  if (← str request "school") != state.school then throw "cross-school request rejected at authority admission"
  let actor ← str request "actor"
  if !validId actor then throw "invalid actor"
  return actor

end Lemma.School
