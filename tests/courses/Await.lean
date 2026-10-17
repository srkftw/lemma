import Lemma.Courses.PackageAwaitClient
import Lemma.Services.Store.ServerAwait

/-! Independent literal copied-IPC/owned RAM fixture. Real imported Actions
execute, but the supplied clock/packet outcomes are a host test model, not a
machine boot, guest journal mount, controller result or trusted evidence. -/
namespace CourseAwaitTests
open Lemma.Core0.Memory
open Lemma.Services.Store
open Lemma.Courses
open Lemma.User

def base : UInt64 := 0x20000
def clientOut : UInt64 := 0x2a000
def clientIn : UInt64 := 0x2b000

structure Reply where
  handle : UInt64
  status : UInt64
  words : Array UInt64
  accepted : Bool
  deriving BEq, Inhabited

structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 196608 0)
  now : UInt64 := 1000
  replies : Array Reply := #[]
  rejectedReply : UInt64 := 0
  calls : Array UInt64 := #[]
  clientPending : Bool := false
  pollBlocked : Bool := false
  canceled : Bool := false
  cancelStatus : UInt8 := 0
  response : Array UInt64 := #[0x31504349414d454c,3,8217,1000,0,64,0,0,
    0x31525453414d454c,2,16,1,0,2,1,1]

private def read (model : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || model.memory.size.toUInt64 < width || model.memory.size.toUInt64 - width < address - base then
    throw "await fixture touched outside its private RAM"
  return (List.range width.toNat).foldl (fun value i =>
    value ||| (model.memory[(address-base).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0

private def write (model : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read model address width
  let memory := (List.range width.toNat).foldl
    (fun bytes i => bytes.set! ((address-base).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) model.memory
  return {model with memory}

private def set (model : Model) (address value : UInt64) : IO Model := IO.ofExcept (write model address 8 value)
private def field (state : IO.Ref Model) (address : UInt64) : IO UInt64 := do
  IO.ofExcept (read (← state.get) address 8)

private def syscall (state : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let model ← state.get
  if number = 5 then
    if a ||| b ||| c ||| d ||| e != 0 then throw <| IO.userError "unexpected clock arguments"
    state.modify fun m => {m with calls := m.calls.push number}
    return (0,model.now)
  else if number = 24 then
    if b != 0x20500 || c != 64 || e != 0 then throw <| IO.userError "await response changed its owned copied framing"
    let words ← (List.range 8).toArray.mapM fun i => IO.ofExcept <| read model (b+i.toUInt64*8) 8
    state.set {model with replies := model.replies.push {handle := a,status := d,words := words,accepted := a != model.rejectedReply}, calls := model.calls.push number}
    return (if a == model.rejectedReply then CapabilityABI.invalidHandle else 0,0)
  else if number = 22 then
    if model.clientPending || a != 16 || b != clientOut || c != 64 || d != 1000 || e != 300000000 then
      throw <| IO.userError "await client changed transaction/framing/deadline"
    let actual ← (List.range 8).toArray.mapM fun i => IO.ofExcept <| read model (b+i.toUInt64*8) 8
    if actual != #[0x31525453414d454c,2,16,1,0,0,0,0] then throw <| IO.userError "await client changed literal v2 request"
    state.set {model with clientPending := true, calls := model.calls.push number}
    return (0,42)
  else if number = 23 || number = 67 then
    if !model.clientPending || a != 42 || b != clientIn || c != 256 || d ||| e != 0 then
      throw <| IO.userError "await client changed actual transaction completion"
    if model.pollBlocked then
      if number != 67 then throw <| IO.userError "fixture only blocks a nonblocking poll"
      state.set {model with calls := model.calls.push number}
      return (12,0)
    if model.canceled then
      state.set {model with clientPending := false,calls := model.calls.push number}
      return (94,0)
    let mut model := model
    for i in [:16] do model ← set model (b+i.toUInt64*8) model.response[i]!
    state.set {model with clientPending := false,calls := model.calls.push number}
    return (0,128)
  else if number = 25 then
    if !model.clientPending || a != 42 || b ||| c ||| d ||| e != 0 then
      throw <| IO.userError "await client canceled a different transaction"
    state.set {model with canceled := model.cancelStatus == 0,calls := model.calls.push number}
    return (model.cancelStatus,0)
  else throw <| IO.userError s!"await Action acquired an undeclared syscall {number}"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
    let (s,value) ← run state first
    run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if count.toNat > budget then throw <| IO.userError "await exceeded its declared fold"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status == 0 then
        let (s,result) ← run state (step i.toUInt32 count value a b c d)
        status := s
        value := result
    run state (next status value)
  | .platform operation a b c d e f next => do
    match operation with
      | .virtualRead8 | .virtualRead64 =>
        let width := if operation == .virtualRead8 then 1 else 8
        run state (next 0 (← IO.ofExcept <| read (← state.get) a width))
      | .virtualWrite8 | .virtualWrite64 =>
        let width := if operation == .virtualWrite8 then 1 else 8
        state.set (← IO.ofExcept <| write (← state.get) a width b)
        run state (next 0 0)
      | .syscall =>
        let (s,value) ← syscall state a b c d e f
        run state (next s value)
      | _ => throw <| IO.userError "await acquired an undeclared platform operation"
  | _ => throw <| IO.userError "await fixture acquired an undeclared Action"

private def initial (mode active initialization : UInt64) : IO Model := do
  let mut model : Model := {}
  for (address,value) in #[(0x20810,8217),(0x20818,mode),(0x20870,initialization),
    (0x40000,active),(0x40028,2),(0x40038,1),(0x40150,0)] do model ← set model address value
  return model

private def request (state : IO.Ref Model) (initialization : UInt64) : IO Unit := do
  let mut model ← state.get
  for (value,index) in #[0x31525453414d454c,2,16,1,0,initialization,0,0].toList.zipIdx do
    model ← set model (0x20340+index.toUInt64*8) value
  state.set model

private def apply (state : IO.Ref Model) (sender reply initialization : UInt64) : IO Unit := do
  request state initialization
  if (← run state (ServerAwait.awaitApplication sender reply 64)) != (0,0) then
    throw <| IO.userError "valid await request failed"

private def expectReply (model : Model) (handle status mode generation : UInt64) : IO Unit := do
  let expected : Reply := {handle := handle,status := status,accepted := true, words := #[0x31525453414d454c,2,16,1,0,(if status == 231 || status == 220 then 0 else 2),mode,generation]}
  if model.replies.back? != some expected then throw <| IO.userError "independent exact final reply differs"

def check : IO Unit := do
  let state ← IO.mkRef (← initial 0 1 0)
  apply state 8357 16 0
  if !(← state.get).replies.isEmpty || (← field state 0x209f0) != 1 ||
      (← field state 0x20a00) != 16 || (← field state 0x20a08) != 8357 ||
      (← field state 0x20a28) != 8217 then throw <| IO.userError "admission ACKed Ready or lost owner-bound row"
  for _ in [:12] do
    if (← run state ServerAwait.settleWaiters) != (0,0) then throw <| IO.userError "pending mount failed"
  if !(← state.get).replies.isEmpty || (← state.get).calls != #[5] then
    throw <| IO.userError "pending mount polled, slept or manufactured Ready"
  state.set (← set (← state.get) 0x20818 1)
  if (← run state ServerAwait.settleWaiters) != (0,0) || !(← state.get).replies.isEmpty then
    throw <| IO.userError "active engine created mounted Ready"
  state.set (← set (← state.get) 0x40000 0)
  if (← run state ServerAwait.settleWaiters) != (0,0) then throw <| IO.userError "completed real engine was not published"
  expectReply (← state.get) 16 0 1 1
  if (← field state 0x209f0) != 0 || (← field state 0x20a00) != 0 then
    throw <| IO.userError "completed waiter was retained or repeated"
  let before := (← state.get).replies.size
  let _ ← run state ServerAwait.settleWaiters
  if (← state.get).replies.size != before then throw <| IO.userError "duplicate Ready reply"

  for (mode,initialization,status,generation) in #[(2,0,221,0),(3,0,223,1)] do
    let state ← IO.mkRef (← initial mode 0 0)
    apply state 8357 16 initialization
    expectReply (← state.get) 16 status mode generation
  let state ← IO.mkRef (← initial 2 0 1)
  apply state 8357 16 1
  let _ ← run state ServerAwait.settleWaiters
  if !(← state.get).replies.isEmpty then throw <| IO.userError "initializer created formatting authority/Ready"
  let blocked ← IO.mkRef (← initial 2 0 0)
  apply blocked 8357 16 1
  expectReply (← blocked.get) 16 220 0 0
  for (address,value) in #[(0x40150,1),(0x40038,0)] do
    let state ← IO.mkRef (← initial 0 1 0)
    apply state 8357 16 0
    let mut m ← state.get
    m ← set m 0x20818 1
    m ← set m 0x40000 0
    m ← set m address value
    state.set m
    if (← run state ServerAwait.settleWaiters).1 != 95 || !(← state.get).replies.isEmpty then
      throw <| IO.userError "unvalidated/read-only root created Ready"

  let full ← IO.mkRef (← initial 0 1 0)
  for i in [:4] do apply full (8357+i.toUInt64) (16+i.toUInt64) 0
  if (← field full 0x209f0) != 15 || !(← full.get).replies.isEmpty then throw <| IO.userError "bounded waiter queue lost a request"
  apply full 9999 20 0
  expectReply (← full.get) 20 231 0 0
  full.modify fun m => {m with now := 300001001,rejectedReply := 16}
  apply full 9999 21 0
  if (← field full 0x20a00) != 21 || (← full.get).replies.size != 2 || (← full.get).replies[1]!.accepted then
    throw <| IO.userError "expired/canceled waiter blocked bounded reuse or created accepted Ready"
  let owner ← IO.mkRef (← initial 0 1 0)
  apply owner 8357 16 0
  let mut m ← owner.get
  m ← set m 0x20818 1
  m ← set m 0x40000 0
  m ← set m 0x20a28 8218
  owner.set m
  if (← run owner ServerAwait.settleWaiters).1 != 95 || !(← owner.get).replies.isEmpty then
    throw <| IO.userError "stale service lifetime created Ready"

  let client ← IO.mkRef ({} : Model)
  if (← run client (PackageAwaitClient.beginCall 16 clientOut clientIn 1 0 1000)) != (0,42) then
    throw <| IO.userError "client did not issue the exact owned pending request"
  client.modify fun m => {m with pollBlocked := true}
  if (← run client (PackageAwaitClient.pollCall 42 clientIn 1000 1)) != (12,0) || !(← client.get).clientPending then
    throw <| IO.userError "client consumed wouldBlock"
  client.modify fun m => {m with pollBlocked := false}
  if (← run client (PackageAwaitClient.pollCall 42 clientIn 1000 1)) != (0,1) || (← client.get).clientPending then
    throw <| IO.userError "client did not validate mounted publication"
  for (index,value) in #[(3,1001),(2,0),(4,16),(5,63),(9,3),(10,15),(11,2),(12,1),(14,0),(15,0),(15,0x8000000000000000)] do
    let state ← IO.mkRef ({response := ({} : Model).response.set! index value} : Model)
    let _ ← run state (PackageAwaitClient.beginCall 16 clientOut clientIn 1 0 1000)
    if (← run state (PackageAwaitClient.waitCall 42 clientIn 1000 1)) != (101,0) then
      throw <| IO.userError "wrong envelope/version/namespace/root generated Ready"
  for status in #[(0 : UInt8),100] do
    let state ← IO.mkRef ({cancelStatus := status} : Model)
    let _ ← run state (PackageAwaitClient.beginCall 16 clientOut clientIn 1 0 1000)
    let canceled ← run state (PackageAwaitClient.cancel 42 clientIn)
    if canceled.1 != 0 || (← state.get).clientPending || (← state.get).calls != #[22,25,67] then
      throw <| IO.userError "cancel repeated, left a handle or published Ready"
  IO.println "COURSE_MOUNT_AWAIT_ACTIONS:PASS pending is not Ready; actual idle/writable/root publication; four bounded owner-bound waiters; initializer/error/lifetime/deadline/revocation; exact client/poll/cancel +11 framing negatives; no CPU/format/durable acknowledgement"

end CourseAwaitTests

def main : IO Unit := CourseAwaitTests.check
