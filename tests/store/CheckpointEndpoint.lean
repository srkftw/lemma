import Lemma.Services.Store.Server
import Lemma.Services.Store.Client
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Host-only literal endpoint/flush-boundary fixture. The interpreter supplies
checked private memory and records actual syscall requests; it neither completes
disk work implicitly nor implements recovery. Target execution remains separate. -/
namespace CheckpointEndpointFixture
open Lemma.Core0.Memory
open Lemma.Services.Store
open Lemma.User

structure Reply where
  handle : UInt64
  bytes : UInt64
  app : UInt64
  words : Array UInt64
  deriving BEq, Repr, Inhabited

structure VM where
  bytes : Std.HashMap UInt64 UInt8 := {}
  replies : Array Reply := #[]
  calls : Array (UInt64 × UInt64 × UInt64 × UInt64 × UInt64 × UInt64) := #[]
  replyStatus : UInt8 := 0
  completion : UInt8 := 168
  receivedBytes : UInt64 := 0
  rejectedRead : Option UInt64 := none

def read (vm : VM) (address : UInt64) (width : Nat := 8) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:width] do
    value := value ||| ((vm.bytes[address+i.toUInt64]?.getD 0).toUInt64 <<< (8*i).toUInt64)
  return value

def write (vm : VM) (address value : UInt64) (width : Nat := 8) : VM := Id.run do
  let mut result := vm
  for i in [:width] do
    result := {result with bytes := result.bytes.insert (address+i.toUInt64) ((value >>> (8*i).toUInt64).toUInt8)}
  return result

def initial : VM := Id.run do
  let mut vm : VM := {}
  for (offset,value) in #[(0,16),(8,17),(24,1)] do vm := write vm (Server.state+offset) value
  for (offset,value) in #[(24,Server.buffer),(40,7),(48,524288),(56,1),(64,0),
      (72,8),(80,262140),(104,Server.index0)] do
    vm := write vm (Server.context+offset) value
  return vm

def packet (vm : VM) (op ns object ticket offset count : UInt64)
    (version : UInt64 := 2) : VM := Id.run do
  let mut vm := vm
  for (i,value) in #[0x31525453414d454c,version,op,ns,object,ticket,offset,count].zipIdx do
    vm := write vm (Server.incoming+64+value.toUInt64*8) i
  return vm

partial def run (vm : IO.Ref VM) : Action → IO (UInt8 × UInt64)
  | .done s value => pure (s,value)
  | .bind first next => do
      let (s,value) ← run vm first
      run vm (next s value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next => do
      if count.toNat > budget then run vm (next 9 initial) else
      let mut result := initial
      let mut status : UInt8 := 0
      for i in [:count.toNat] do
        if status = 0 then
          let (s,value) ← run vm (step i.toUInt32 count result c0 c1 c2 c3)
          status := s
          result := value
      run vm (next status result)
  | .platform op a b c d e f next => do
      match op with
      | .virtualRead8 | .virtualRead64 =>
        let state ← vm.get
        if state.rejectedRead = some a then run vm (next 13 0) else
        run vm (next 0 (read state a (if op = .virtualRead8 then 1 else 8)))
      | .virtualWrite8 | .virtualWrite64 =>
        vm.modify fun state => write state a b (if op = .virtualWrite8 then 1 else 8)
        run vm (next 0 0)
      | .syscall =>
        vm.modify fun state => {state with calls := state.calls.push (a,b,c,d,e,f)}
        let state ← vm.get
        if a = 24 then
          let words := (List.range 8).toArray.map fun i => read state (c+i.toUInt64*8)
          vm.modify fun state => {state with replies := state.replies.push {handle:=b,bytes:=d,app:=e,words}}
          run vm (next state.replyStatus 0)
        else if a = 21 then
          if d ≠ 256 || e ≠ 0 || f ≠ 0 then throw <| IO.userError "active service attempted blocking receive"
          run vm (next 12 0)
        else if a = 66 then run vm (next state.completion 0)
        else if a = 4 then
          if b ≠ 10000 then throw <| IO.userError "unexpected block completion sleep"
          run vm (next 0 0)
        else if a = 67 || a = 23 then run vm (next 0 state.receivedBytes)
        else throw <| IO.userError s!"unexpected syscall{a}"
      | _ => throw <| IO.userError "unexpected checkpoint fixture effect"
  | _ => throw <| IO.userError "unexpected checkpoint Action"

def execute (initial : VM) (action : Action) : IO VM := do
  let vm ← IO.mkRef initial
  if (← run vm action).1 ≠ 0 then throw <| IO.userError "service Action failed"
  vm.get

def replyIs (vm : VM) (op ns sequence detail app : UInt64) : IO Unit := do
  let some reply := vm.replies.back? | throw <| IO.userError "missing actual IPC reply"
  if reply.handle ≠ 16 || reply.bytes ≠ 64 || reply.app ≠ app ||
      reply.words ≠ #[0x31525453414d454c,(if op=12 || op=13 then 2 else 1),op,ns,0,sequence,detail,0] then
    throw <| IO.userError s!"literal endpoint reply mismatch:{reprStr reply}"

def privateFields (vm : VM) : Array UInt64 :=
  ((List.range 24).toArray.map fun i => read vm (Server.state+i.toUInt64*8)) ++
  ((List.range 64).toArray.map fun i => read vm (Server.context+i.toUInt64*8))

def endpoint : IO Unit := do
  let owner : UInt64 := 0x100000002
  let accepted ← execute (packet initial 12 1 0 9 0 0) (Server.application owner 16 64)
  replyIs accepted 12 1 7 1 0
  if read accepted (Server.state+128) ≠ 1 || read accepted (Server.state+40) ≠ 0 ||
      read accepted (Server.state+48) ≠ 0 || read accepted (Server.context+0) ≠ 2 ||
      read accepted (Server.context+8) ≠ 37 || read accepted (Server.context+56) ≠ 1 then
    throw <| IO.userError "begin did not retain independent Pending ownership/old root"
  for op in #[12,13] do
    let observed ← execute (packet accepted op 1 0 9 0 0) (Server.application owner 16 64)
    replyIs observed op 1 7 1 0
    if privateFields observed ≠ privateFields accepted then throw <| IO.userError "retry/status restarted active checkpoint"
  for (sender,ns,ticket,op,app) in #[(owner,1,10,12,231),(owner,1,10,13,232),
      (0x200000002,1,9,13,232),(owner,2,9,13,232)] do
    let observed ← execute (packet accepted op ns 0 ticket 0 0) (Server.application sender 16 64)
    replyIs observed op ns 7 0 app
    if privateFields observed ≠ privateFields accepted then throw <| IO.userError "foreign/busy request mutated checkpoint"
  for (op,ns,obj,ticket,offset,count,version,bytes,app) in #[(12,1,0,9,0,0,1,64,222),
      (7,1,0,0,0,0,2,64,222),(12,3,0,9,0,0,2,64,220),(12,1,1,9,0,0,2,64,220),
      (12,1,0,0,0,0,2,64,220),(13,1,0,9,1,0,2,64,220),(13,1,0,9,0,1,2,64,220),
      (13,1,0,9,0,0,2,65,220)] do
    let observed ← execute (packet accepted op ns obj ticket offset count version) (Server.application owner 16 bytes)
    let some reply := observed.replies.back? | throw <| IO.userError "missing rejection"
    if reply.app ≠ app || privateFields observed ≠ privateFields accepted then
      throw <| IO.userError "version/malformed input started work or changed receipt"
  let otherIO ← execute (packet accepted 5 1 1 0 0 128 1) (Server.application owner 16 64)
  if otherIO.replies.back!.app ≠ 231 || privateFields otherIO ≠ privateFields accepted then
    throw <| IO.userError "ordinary I/O raced the checkpoint/outgoing buffer"
  let expired ← execute {accepted with replyStatus := 96} (Server.checkpointStatus owner 16 13 1 9)
  if privateFields expired ≠ privateFields accepted then throw <| IO.userError "client death changed active ownership"
  let stepped ← execute (write accepted (Server.state+32) 1) Server.step
  if stepped.calls.back? ≠ some (21,17,Server.incoming,256,0,0) ||
      read stepped (Server.state+128) ≠ 1 || read stepped (Server.state+32) ≠ 1 then
    throw <| IO.userError "async pump blocked on IPC or released pending block work"
  let mounting := write (write initial (Server.state+24) 0) (Server.context+0) 1
  let status ← execute (packet mounting 8 1 0 0 0 0 1) (Server.application owner 16 64)
  replyIs status 8 1 7 0 0
  if privateFields status ≠ privateFields mounting then throw <| IO.userError "mount status fabricated readiness"
  let mounting ← execute (write mounting (Server.state+32) 1) Server.step
  if mounting.calls.back? ≠ some (21,17,Server.incoming,256,0,0) then
    throw <| IO.userError "mount pump used a blocking document receive"
  let legacy ← execute (packet initial 7 1 0 0 0 0 1) (Server.application owner 16 64)
  if !legacy.replies.isEmpty || read legacy (Server.state+40) ≠ 16 ||
      read legacy (Server.state+128) ≠ 0 then throw <| IO.userError "legacy checkpoint no longer waits for flush"
  IO.println "STORE_CHECKPOINT_ENDPOINT:PASS begin/status, same-ticket retry, owner/ns/ticket/version/busy, death, nonblocking mount/pump and unchanged v1 deferred checkpoint"

def flushBoundary : IO Unit := do
  let owner : UInt64 := 0x100000002
  let mut pending := initial
  for (offset,value) in #[(128,1),(136,owner),(144,1),(152,9),(160,7),(168,7)] do
    pending := write pending (Server.state+offset) value
  for (offset,value) in #[(0,2),(8,39),(256,Server.index1),(272,3),(280,262148),
      (288,2),(296,1)] do pending := write pending (Server.context+offset) value
  let vm ← IO.mkRef pending
  if (← run vm (Engine.complete Server.context 0)).1 ≠ 0 then throw <| IO.userError "root write completion failed"
  if (← run vm Server.settleCheckpoint).1 ≠ 0 then throw <| IO.userError "pending boundary failed"
  let before ← vm.get
  if read before (Server.context+0) ≠ 3 || read before (Server.context+8) ≠ 40 ||
      read before (Server.state+128) ≠ 1 || read before (Server.context+56) ≠ 1 then
    throw <| IO.userError "ordinary root write completion published success before flush"
  if (← run vm (Engine.complete Server.context 0)).1 ≠ 0 ||
      (← run vm Server.settleCheckpoint).1 ≠ 0 then throw <| IO.userError "actual root flush did not settle"
  let complete ← vm.get
  if read complete (Server.state+128) ≠ 2 || read complete (Server.context+56) ≠ 2 ||
      read complete (Server.context+104) ≠ Server.index1 || read complete (Server.context+40) ≠ 7 then
    throw <| IO.userError "durable completion did not switch root/retain document sequence"
  let complete ← execute complete (Server.checkpointStatus owner 16 13 1 9)
  replyIs complete 13 1 7 0 0
  let latched ← execute (write complete (Server.context+32) 227) Server.settleCheckpoint
  if privateFields latched ≠ privateFields (write complete (Server.context+32) 227) then
    throw <| IO.userError "terminal receipt was overwritten by a later engine result"
  for phase in #[37,38,39,40] do
    let vm ← IO.mkRef (write (write pending (Server.context+8) phase) (Server.context+0) (if phase=38 || phase=40 then 3 else 2))
    if (← run vm (Engine.complete Server.context 173)).1 ≠ 227 ||
        (← run vm Server.settleCheckpoint).1 ≠ 0 then throw <| IO.userError "real completion error was swallowed"
    let observed ← execute (← vm.get) (Server.checkpointStatus owner 16 13 1 9)
    replyIs observed 13 1 7 0 227
    if read observed (Server.state+128) ≠ 3 || read observed (Server.context+56) ≠ 1 then
      throw <| IO.userError "failed checkpoint became Saved or changed old root"
  let stale := write pending (Server.context+0) 0
  let vm ← IO.mkRef (write stale (Server.context+40) 8)
  if (← run vm Server.settleCheckpoint).1 ≠ 95 || read (← vm.get) (Server.state+128) ≠ 1 then
    throw <| IO.userError "receipt accepted an unrelated document sequence"
  let replacement ← execute (packet complete 12 2 0 10 0 0) (Server.application owner 16 64)
  replyIs replacement 12 2 7 1 0
  let stale ← execute (packet replacement 13 1 0 9 0 0) (Server.application owner 16 64)
  replyIs stale 13 1 7 0 232
  IO.println "STORE_CHECKPOINT_FLUSH:PASS literal root-write/final-flush boundary, four actual completion errors, stable receipt, stale sequence/ticket and completed replacement"

def clientPacket (operation version detail app count bytes : UInt64) : VM := Id.run do
  let address := Server.incoming
  let mut vm := {initial with receivedBytes := bytes}
  for (value,i) in #[0x31504349414d454c,3,0x100000001,19,0,64,app,0,
      0x31525453414d454c,version,operation,1,0,7,detail,count].zipIdx do
    vm := write vm (address+i.toUInt64*8) value
  return vm

def client : IO Unit := do
  for operation in #[12,13] do
    for (version,detail,app,count,bytes,expected) in #[(2,0,0,0,128,0),(2,1,0,0,128,0),
        (2,0,227,0,128,227),(2,0,232,0,128,232),(1,0,0,0,128,101),
        (2,2,0,0,128,101),(2,1,227,0,128,101),(2,0,0,1,129,101),(2,0,0,0,129,101)] do
      let vm ← IO.mkRef (clientPacket operation version detail app count bytes)
      let result ← run vm (Client.pollCall 17 Server.incoming operation 1 0 19 0)
      if result.1.toUInt64 ≠ expected || (if expected=101 then result.2≠0 else result.2≠7) then
        throw <| IO.userError "client accepted malformed v2 Pending/completion/failed reply"
  for operation in #[1,7,8,10,11] do
    if Protocol.requestVersion operation ≠ 1 then throw <| IO.userError "v1 operation version changed"
  IO.println "STORE_CHECKPOINT_CLIENT:PASS actual begin/status reply validation, malformed detail/count/version/errors and v1 version retention"

end CheckpointEndpointFixture
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  liftIO CheckpointEndpointFixture.endpoint
  liftIO CheckpointEndpointFixture.flushBoundary
  liftIO CheckpointEndpointFixture.client
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[`Lemma.Services.Store.Server.main, `Lemma.Services.Store.Client.beginCall,
        `Lemma.Services.Store.Client.pollCall] with
    | .ok result => pure result
    | .error diagnostic => throwError diagnostic.render
  let result ← match lowerActionSuiteExecution .user_v0_1 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "checkpoint_endpoint_" } with
    | .ok result => pure result
    | .error diagnostic => throwError diagnostic
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map llvmTy }
  let module : LLVM.Module := {sourceName := "genuine Store endpoint checkpoint v2", declarations, functions := result.functions}
  match LLVM.validateModule module with
  | .ok () => pure ()
  | .error error => throwError error
  if let some output ← liftIO <| IO.getEnv "LEMMA_CHECKPOINT_PROBE_OUT" then
    let path := System.FilePath.mk output
    if ← liftIO path.pathExists then throwError "refusing existing checkpoint probe output"
    liftIO <| IO.FS.createDirAll path
    liftIO <| IO.FS.writeFile (path / "program.ll") module.render
    liftIO <| IO.FS.writeFile (path / "symbols.txt") result.renderSymbolManifest
  logInfo "STORE_CHECKPOINT_COMPILE:PASS genuine service/client elaboration, Core0 checked closure and LLVM lowering; RV64 execution separate"
