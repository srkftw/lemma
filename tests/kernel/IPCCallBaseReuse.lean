import Lemma.Kernel.IPC
import Lemma.Compiler.CFGLower
open Lean Elab Command
run_cmd do
  for (suffix, aliasName, arity) in [
      ("IPC.payload","originalPayload",3), ("IPC.idle","originalIdle",1),
      ("IPC.queueRoom","originalQueueroom",1), ("IPC.stage","originalStage",7)] do
    let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith suffix
    unless candidates.length = 1 do throwError "expected exact genuine maintained private callback {suffix}"
    let n := mkIdent candidates.head!.1
    let alias := mkIdent <| Name.mkSimple aliasName
    if arity = 1 then
      elabCommand (← `(def $alias (a : UInt64) : Lemma.Core0.Memory.Action := $n a))
    else if arity = 3 then
      elabCommand (← `(def $alias (a b c : UInt64) : Lemma.Core0.Memory.Action := $n a b c))
    else
      elabCommand (← `(def $alias (a b c d e f g : UInt64) : Lemma.Core0.Memory.Action := $n a b c d e f g))

namespace CallBorrowBefore
open Lemma.Core0.Memory Lemma.Kernel Lemma.Kernel.IPC Lemma.User
def callBeginWithLimit (maximum descriptor handle pointer length request ticks : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s key =>
  if failed s = true then .done s 0 else
  .bind (originalPayload descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (originalIdle descriptor) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (originalQueueroom key) fun s queue =>
  if failed s = true then .done s 0 else
  .bind Objects.replyAvailable fun s available =>
  if failed s = true then .done s 0 else
  if available = 0 then .done CapabilityABI.objectFull 0 else
  .bind (deadlineWithLimit ticks maximum) fun s expires =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.prepare descriptor IPCStorage.callOperation key 0 0 expires) fun s transaction =>
  if failed s = true then .done s 0 else
  .bind (originalStage descriptor transaction pointer length IPCABI.callKind request 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.createReply descriptor key transaction expires) fun s reply =>
  if failed s = true then fatal else
  .bind (IPCStorage.setReply descriptor transaction reply) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.queueEnqueue queue key descriptor reply) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.markReplyQueued reply) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.commitWait descriptor transaction) fun s _ =>
  if failed s = true then fatal else .done 0 transaction

end CallBorrowBefore
namespace CallBorrowFaults
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.Kernel Lemma.User
structure Request where
  op : Lemma.Core0.Execution.Op
  address : UInt64
  value : UInt64
  status : UInt8
  deriving BEq
instance : Inhabited Request := ⟨⟨.physicalRead64,0,0,0⟩⟩
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  requests : Array Request := #[]
  now : UInt64 := 1000
  operations : Nat := 0
  callbacks : Nat := 0
  failRead : Option UInt64 := none
  failWrite : Option UInt64 := none
  failure : UInt8 := 7
  firmwareFailure : UInt8 := 0

def require (ok : Bool) (m : String) : IO Unit := if ok then pure () else throw <| IO.userError m
def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  {s with words := if v = 0 then s.words.erase a else s.words.insert a v}
def byte (s : State) (a : UInt64) : UInt64 :=
  (word s (a - a % 8) >>> (a % 8 * 8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a % 8 * 8
  put s (a - a % 8) ((word s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))
def reset (s : State) : State :=
  {s with
    requests := #[]
    operations := 0
    callbacks := 0
    failRead := none
    failWrite := none
    failure := 7
    firmwareFailure := 0}
partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next => let (s,v) ← execute ref first; execute ref (next s v)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if budget < count.toNat then execute ref (next 9 initial) else
    let mut result := (0,initial)
    for i in [:count.toNat] do
      if result.1 = 0 then
        ref.modify fun s => {s with callbacks := s.callbacks+1}
        result ← execute ref (step i.toUInt32 count result.2 c0 c1 c2 c3)
    execute ref (next result.1 result.2)
  | .platform op a b _ _ _ _ next =>
    let s ← ref.get
    require (s.operations < 10000000) "model resource ceiling"
    ref.set {s with operations := s.operations+1}
    if op = .installSatp then execute ref (next 0 0) else
    if op = .firmwareCall then
      require (a = 2 && b = 0) "undeclared firmware call"
      ref.modify fun s => {s with requests := s.requests.push ⟨op,a,s.now,s.firmwareFailure⟩}
      execute ref (next s.firmwareFailure (if s.firmwareFailure = 0 then s.now else 0))
    else
      require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000)) "finite RAM range"
      let isRead := op = .physicalRead64 || op = .physicalRead8
      let status : UInt8 := if (if isRead then s.failRead == some a else s.failWrite == some a) then s.failure else 0
      let value := if op = .physicalRead64 then word s a else if op = .physicalRead8 then byte s a else b
      ref.modify fun s => {s with requests := s.requests.push ⟨op,a,(if isRead && status != 0 then 0 else value),status⟩}
      match op with
      | .physicalRead64 => require (a % 8 = 0) "alignedread"; execute ref (next status (if status = 0 then value else 0))
      | .physicalWrite64 =>
        require (a % 8 = 0) "alignedwrite"
        if status = 0 then ref.modify fun s => put s a b
        execute ref (next status 0)
      | .physicalRead8 => execute ref (next status (if status = 0 then value else 0))
      | .physicalWrite8 =>
        if status = 0 then ref.modify fun s => putByte s a b
        execute ref (next status 0)
      | _ => throw <| IO.userError "unadmitted model operation"
  | _ => throw <| IO.userError "unadmitted model Action"

def success (ref : IO.Ref State) (a : Action) : IO UInt64 := do
  let (s,v) ← execute ref a
  require (s = 0) s!"setup status{s}"
  pure v

def compare (snapshot : State) (descriptor handle pointer length : UInt64) (baseTrace : Array Request) : IO (Nat × Nat) := do
  let old ← IO.mkRef snapshot
  let fresh ← IO.mkRef snapshot
  let before ← execute old (CallBorrowBefore.callBeginWithLimit IPCABI.lemmaSimMaximumTicks descriptor handle pointer length 77 1000000)
  let after ← execute fresh (IPC.callBeginWithLimit IPCABI.lemmaSimMaximumTicks descriptor handle pointer length 77 1000000)
  let a ← old.get
  let b ← fresh.get
  require (before == after && a.words == b.words) s!"actual result/RAM differ {before} vs {after}"
  -- Only identical, successful duplicate whole-base read subsequences may go.
  -- Every remaining request, status, returned byte and write is exact.
  let mut i := 0
  let mut j := 0
  while i < a.requests.size do
    let block := a.requests.extract i (i+baseTrace.size)
    let second := b.requests.extract j (j+baseTrace.size)
    if block == baseTrace && block != second then i := i+baseTrace.size else
      require (j < b.requests.size && a.requests[i]! == b.requests[j]!) "request differs beyond duplicate immutable base reads"
      i := i+1
      j := j+1
  require (j == b.requests.size) "new request suffix"
  return (a.requests.size,b.requests.size)

def check (expanded : Bool) : IO Unit := do
  let ref ← IO.mkRef ({} : State)
  discard <| success ref (Frames.configure (if expanded then 8192 else 512) (if expanded then 8192 else 32) 4)
  discard <| success ref Frames.init
  discard <| success ref Objects.init
  let server ← success ref (AddressSpace.create 2)
  let caller ← success ref (AddressSpace.create 3)
  discard <| success ref (Capability.attach server)
  discard <| success ref (Capability.attach caller)
  let endpoint ← success ref (Objects.createEndpoint server)
  let handle ← success ref (Capability.grantBoot caller endpoint CapabilityABI.endpointCall)
  discard <| success ref (Capability.activate server)
  discard <| success ref (Capability.activate caller)
  let page ← success ref (Frames.allocate 3 4)
  discard <| success ref (AddressSpace.mapUser caller 0x40000 page 3)
  let physical ← success ref (Frames.resolvePurpose 3 page 4)
  for i in [:24] do ref.modify fun s => put s (physical+i.toUInt64*8) (0x0102030405060708+i.toUInt64)
  let before := reset (← ref.get)
  let baseRef ← IO.mkRef before
  discard <| success baseRef (AddressSpace.base caller)
  let baseTrace := (← baseRef.get).requests
  let counts ← compare before caller handle 0x40000 192 baseTrace
  require (counts.2+6*baseTrace.size == counts.1) "expected exactly six removed whole-descriptor checks"
  for length in #[0,64,128,189,192,193] do discard <| compare before caller handle 0x40000 length baseTrace
  for offered in #[handle+16,0] do discard <| compare before caller offered 0x40000 192 baseTrace
  for pointer in #[0x40001,0x40fff,0x50000,0xffffffffffffffff] do discard <| compare before caller handle pointer 192 baseTrace
  let first ← IO.mkRef before
  discard <| execute first (CallBorrowBefore.callBeginWithLimit IPCABI.lemmaSimMaximumTicks caller handle 0x40000 192 77 1000000)
  let unique := (← first.get).requests.foldl (fun acc row => if acc.contains row.address then acc else acc.push row.address) (#[] : Array UInt64)
  for address in unique do
    discard <| compare {before with failRead := some address} caller handle 0x40000 192 baseTrace
    discard <| compare {before with failWrite := some address} caller handle 0x40000 192 baseTrace
  IO.println s!"IPC_CALL_BORROW_ACTIONS:PASS pool{if expanded then 8192 else 512} requests{counts.1}->{counts.2}, six complete duplicate base checks removed; exact result/RAM/remaining requests, payload/authority/range guards and {unique.size*2} access-fault cases"
end CallBorrowFaults

def main : IO Unit := do
  CallBorrowFaults.check false
  CallBorrowFaults.check true
