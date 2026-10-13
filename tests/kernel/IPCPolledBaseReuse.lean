import Lemma.Kernel.Task
import Lemma.Compiler.CFGLower
open Lean Elab Command
run_cmd do
  for (suffix, aliasName, arity) in [
      ("IPCStorage.equalWord", "storageEqualWord", 2),
      ("IPC.word", "ipcWord", 2), ("IPC.pollWaiting", "ipcPollWaiting", 3),
      ("Task.lookupRecord", "taskLookupRecord", 1),
      ("Task.completeBlocked", "taskCompleteBlocked", 5)] do
    let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith suffix
    unless candidates.length = 1 do throwError "expected one imported private declaration: {suffix}"
    let n := mkIdent candidates.head!.1
    let alias := mkIdent <| Name.mkSimple aliasName
    if arity = 1 then
      elabCommand (← `(def $alias (a : UInt64) : Lemma.Core0.Memory.Action := $n a))
    else if arity = 2 then
      elabCommand (← `(def $alias (a b : UInt64) : Lemma.Core0.Memory.Action := $n a b))
    else if arity = 3 then
      elabCommand (← `(def $alias (a b c : UInt64) : Lemma.Core0.Memory.Action := $n a b c))
    else
      elabCommand (← `(def $alias (a b c d e : UInt64) : Lemma.Core0.Memory.Action := $n a b c d e))

namespace PollBorrowStorage
open Lemma.Core0.Memory
open Lemma.Kernel.IPCStorage
def pendingAt (descriptor base : UInt64) : Action :=
  let address := base + metadataOffset
  .bind (storageEqualWord address magic) fun s _ =>
  if failed s = true then fatal else
  .bind (storageEqualWord (address + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (storageEqualWord (address + 16) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state ≤ stateReady then
  .bind (get (address + nextTransactionOffset)) fun s next =>
  if failed s = true then fatal else
  if 0 < next then if next ≤ maxTransaction + 1 then
  .bind (get (address + transactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  if state = stateIdle then
    if transaction = 0 then .done 0 address else fatal
  else
  if 0 < transaction then if transaction ≤ maxTransaction then
  .bind (get (address + operationOffset)) fun s operation =>
  if failed s = true then fatal else
  if 0 < operation then if operation ≤ callOperation then
  .bind (get (address + endpointOffset)) fun s endpoint =>
  if failed s = true then fatal else
  if 0 < endpoint then
    if state = stateReserved then
      if transaction = next then .done 0 address else fatal
    else if transaction + 1 = next then .done 0 address else fatal
  else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal
  else fatal

def pending (descriptor : UInt64) : Action :=
  .bind (Lemma.Kernel.Memory.AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done 80 0 else pendingAt descriptor base
end PollBorrowStorage
namespace PollBorrowIPC
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.IPC
open Lemma.User
def pollAt (descriptor base : UInt64) : Action :=
  .bind (PollBorrowStorage.pendingAt descriptor base) fun s metadata =>
  if failed s = true then fatal else
  .bind (ipcWord metadata IPCStorage.stateOffset) fun s state =>
  if failed s = true then fatal else
  if state = IPCStorage.stateIdle then .done IPCABI.wouldBlock 0 else
  .bind (ipcWord metadata IPCStorage.transactionOffset) fun s transaction =>
  if failed s = true then fatal else
  if state = IPCStorage.stateReady then .done 0 metadata else
  if state = IPCStorage.stateWaiting then ipcPollWaiting descriptor transaction metadata else fatal

def poll (descriptor : UInt64) : Action :=
  .bind (Lemma.Kernel.Memory.AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else pollAt descriptor base
end PollBorrowIPC
namespace PollBorrowTask
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.Kernel.Task

end PollBorrowTask
open Lean Elab Command
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith "Task.pollIPCStep"
  unless candidates.length = 1 do throwError "expected one genuine maintained private callback"
  let n := mkIdent candidates.head!.1
  let alias := mkIdent `PollBorrowTask.after
  elabCommand (← `(def $alias (i nCount : UInt32) (acc address now c2 c3 : UInt64) : Lemma.Core0.Memory.Action :=
    $n i nCount acc address now c2 c3))
namespace PollBorrowTask
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.Kernel.Task
def observedBefore (i _ : UInt32) (acc address now _ _ : UInt64) : Action :=
  let record := address + i.toUInt64 * stride
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if dying < state then fatal else
  if (if runnable ≤ state then if state < dying then true else false else false) = true then
    .bind (Access.read64 (record + managedOffset)) fun s managed =>
    if failed s = true then fatal else
    if managed = 0 then .done 0 acc else
    if managed = 1 then
      .bind (Access.read64 record) fun s descriptor =>
      if failed s = true then fatal else
      .bind (lookup descriptor) fun s checked =>
      if failed s = true then fatal else
      if checked = record then
      .bind (Access.read64 (record + waitEpochOffset)) fun s epoch =>
      if failed s = true then fatal else
      .bind (Access.read64 (record + waitTransactionOffset)) fun s transaction =>
      if failed s = true then fatal else
      .bind (IPC.poll descriptor) fun status _ =>
      if status = Lemma.User.IPCABI.wouldBlock then .done 0 acc else
      if status = 0 then
        if state = blocked then
          if transaction = 0 then fatal else
          .bind (taskCompleteBlocked record descriptor epoch transaction now) fun s woke =>
          if failed s = true then fatal else .done 0 (acc + woke)
        else .done 0 acc
      else fatal
      else fatal
    else fatal
  else .done 0 acc

end PollBorrowTask

namespace PollBorrowFaults
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Kernel
structure Request where
  op : Lemma.Core0.Execution.Op
  address : UInt64
  value : UInt64
  status : UInt8
  deriving BEq
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

def compare (s : State) (table descriptor : UInt64) (baseTrace : Array Request) : IO (Nat × Nat × Nat) := do
  let old ← IO.mkRef s
  let fresh ← IO.mkRef s
  let before ← execute old (PollBorrowTask.observedBefore 0 8 5 table 1000 0 0)
  let after ← execute fresh (PollBorrowTask.after 0 8 5 table 1000 0 0)
  let a ← old.get
  let b ← fresh.get
  require (before = after) s!"result mismatch {before} vs {after}"
  require (a.words == b.words) "authoritative RAM or failed-write prefix differs"
  for (first,second) in #[(IPCStorage.pending descriptor,PollBorrowStorage.pending descriptor),
      (IPC.poll descriptor,PollBorrowIPC.poll descriptor)] do
    let firstRef ← IO.mkRef s
    let secondRef ← IO.mkRef s
    let firstResult ← execute firstRef first
    let secondResult ← execute secondRef second
    let firstState ← firstRef.get
    let secondState ← secondRef.get
    require (firstResult == secondResult && firstState.words == secondState.words &&
      firstState.requests == secondState.requests) "public wrapper changed exact result/RAM/read-write order"
  let boundary := table + Task.waitTransactionOffset
  let cut := a.requests.toList.findIdx? fun r => r.op = .physicalRead64 && r.address = boundary && r.status = 0
  let projected := match cut with
    | none => a.requests
    | some n =>
      let leading := a.requests.extract 0 (n+1)
      let candidate := a.requests.extract (n+1) (n+1+baseTrace.size)
      if candidate == baseTrace then leading ++ a.requests.extract (n+1+baseTrace.size) a.requests.size else a.requests
  require (projected == b.requests) "live request order/status/value differs beyond exact duplicate base reads"
  return (a.requests.size,b.requests.size,b.requests.filter (fun r => r.op = .physicalWrite64 || r.op = .physicalWrite8) |>.size)

def check (expanded : Bool) : IO Unit := do
  let ref ← IO.mkRef ({} : State)
  discard <| success ref (Frames.configure (if expanded then 8192 else 512) (if expanded then 8192 else 32) 4)
  discard <| success ref Frames.init
  let descriptor ← success ref (AddressSpace.create 2)
  let address ← success ref (AddressSpace.base descriptor)
  discard <| success ref (IPCStorage.initialize descriptor)
  let stack ← success ref (Frames.allocateContiguous4 2 1)
  let handles := #[(word (← ref.get) stack),word (← ref.get) (stack+8),word (← ref.get) (stack+16),word (← ref.get) (stack+24)]
  let physical ← success ref (Frames.resolvePurpose 2 handles[0]! 1)
  for (offset,value) in #[((2400 : UInt64),handles[0]!),(2480,handles[1]!),(2488,handles[2]!),
      (2496,handles[3]!),(2504,4),(2512,physical),(2408,physical+16368)] do
    ref.modify fun s => put s (address+offset) value
  ref.modify fun s => put (put s physical Loader.stackCanary) (physical+16376) Loader.stackCanary
  discard <| success ref Task.init
  let table ← success ref Task.table
  let saved := address+2048
  ref.modify fun s => put (put (put s saved 0) (saved+264) 0x200000020)
    (saved+272) (word s (address+72))
  ref.modify fun s => put s (saved+280) (physical+16368)
  let metadata := address+IPCStorage.metadataOffset
  ref.modify fun s => put (put (put (put s table descriptor) (table+Task.stateOffset) Task.runnable)
    (table+Task.managedOffset) 1) (table+Task.waitEpochOffset) 7
  let initial := reset (← ref.get)
  let baseRef ← IO.mkRef initial
  discard <| success baseRef (AddressSpace.base descriptor)
  let baseTrace := (← baseRef.get).requests
  let states := #[(Task.runnable,IPCStorage.stateIdle),(Task.runnable,IPCStorage.stateReady),
    (Task.runnable,IPCStorage.stateWaiting),(Task.blocked,IPCStorage.stateReady)]
  let mut cases := 0
  for (taskState,ipcState) in states do
    let state := reset <| put (put (put (put (put (put (put initial (table+Task.stateOffset) taskState)
      (table+Task.waitTransactionOffset) (if ipcState = 0 then 0 else 1))
      (metadata+IPCStorage.stateOffset) ipcState)
      (metadata+IPCStorage.operationOffset) 3)
      (metadata+IPCStorage.transactionOffset) (if ipcState = 0 then 0 else 1))
      (metadata+IPCStorage.nextTransactionOffset) (if ipcState = 0 then 1 else 2))
      (metadata+IPCStorage.endpointOffset) 7
    let state := put (put state (metadata+IPCStorage.deadlineOffset) 2000) (metadata+IPCStorage.resultStatusOffset) 93
    let (oldReads,newReads,writes) ← compare state table descriptor baseTrace
    IO.println s!"IPC_BORROW_WORK expanded={expanded} task{taskState} ipc{ipcState} reads{oldReads}→{newReads} writes{writes}"
    let traceRef ← IO.mkRef state
    discard <| execute traceRef (PollBorrowTask.observedBefore 0 8 5 table 1000 0 0)
    let trace := (← traceRef.get).requests
    let locations := (trace.toList.filter fun r => r.op = .physicalRead64 || r.op = .physicalRead8).map (·.address) |>.eraseDups
    for location in locations do
      for failure in #[(0 : UInt8),1,7,255] do
        discard <| compare {state with failRead := some location,failure := failure} table descriptor baseTrace
        cases := cases+1
    for location in (trace.toList.filter fun r => r.op = .physicalWrite64 || r.op = .physicalWrite8).map (·.address) |>.eraseDups do
      for failure in #[(0 : UInt8),1,7,255] do
        discard <| compare {state with failWrite := some location,failure := failure} table descriptor baseTrace
        cases := cases+1
    if ipcState = IPCStorage.stateWaiting then
      for failure in #[(0 : UInt8),1,7,255] do
        discard <| compare {state with firmwareFailure := failure} table descriptor baseTrace
        cases := cases+1
    for (offset,value) in #[(0,0),(8,2),(16,descriptor+1),(24,4),(48,0),(48,IPCStorage.maxTransaction+2),
        (40,0),(40,IPCStorage.maxTransaction+1),(32,0),(32,4),(56,0)] do
      discard <| compare (put state (metadata+offset) value) table descriptor baseTrace
    for (offset,value) in #[(Task.stateOffset,7),(Task.managedOffset,2),(Task.waitTransactionOffset,0)] do
      discard <| compare (put state (table+offset) value) table descriptor baseTrace
  -- Full directory authority is still validated once before borrowing. Mutating
  -- any later bank or introducing any of all28 bank duplicates remains fatal.
  if expanded then
    for i in [:8] do
      let slot := address+1424+i.toUInt64*16
      let handle := word initial slot
      let record := Frames.records+(handle%8192)*32
      for (a,v) in #[(slot,0),(slot+8,0),(record,3),(record+8,99),(record+24,2),(record+16,1)] do
        discard <| compare (put initial a v) table descriptor baseTrace
    for i in [:8] do
      for j in [i+1:8] do
        let slot := address+1424+i.toUInt64*16
        let other := address+1424+j.toUInt64*16
        let bad := put (put initial other (word initial slot)) (other+8) (word initial (slot+8))
        discard <| compare bad table descriptor baseTrace
  IO.println s!"IPC_BORROW_FAULTS:PASS expanded={expanded} cases{cases} status0/1/7/255 each live read/write/time failure exact-result/RAM/request projection and full directory malformed rejection"
end PollBorrowFaults
run_cmd do
  liftIO <| PollBorrowFaults.check false
  liftIO <| PollBorrowFaults.check true
