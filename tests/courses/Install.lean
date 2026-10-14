import Lemma.Courses.PackageStore
import Lemma.Courses.PackageReference

/-! Opaque copied-IPC outcomes exercise the actual guest install Action.
This RAM/transport fixture does not implement journal recovery or claim a
physical barrier. Real Store durability remains a separate machine scenario. -/
namespace CourseInstallTests
open Lemma.Core0.Memory
open Lemma.Courses
open Lemma.Services.Store
open Lemma.User

def base : UInt64 := 0x40000
def target : UInt64 := 0x50000

structure Model where
  memory : ByteArray
  package : ByteArray
  requests : Array (UInt64 × UInt64 × UInt64) := #[]
  uploaded : UInt64 := 0
  pending : Bool := false
  request : UInt64 := 0
  operation : UInt64 := 0
  offset : UInt64 := 0
  count : UInt64 := 0
  faultOperation : UInt64 := 0
  fault : UInt64 := 0

private def read (model : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || model.memory.size.toUInt64 < width || model.memory.size.toUInt64 - width < address - base then
    throw "Store loader touched outside its owned fixture arena"
  return (List.range width.toNat).foldl (fun value i =>
    value ||| (model.memory[(address-base).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0

private def write (model : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read model address width
  let memory := (List.range width.toNat).foldl
    (fun bytes i => bytes.set! ((address-base).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) model.memory
  return {model with memory}

private def set (model : Model) (address value : UInt64) : IO Model := IO.ofExcept (write model address 8 value)

private def syscall (state : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let model ← state.get
  if number = IPCABI.callBegin then
    if model.pending || a != 16 || b != base+512 || e != 300000000 then
      throw <| IO.userError "installer changed copied IPC authority/deadline"
    let header ← IO.ofExcept <| read model b 8
    let version ← IO.ofExcept <| read model (b+8) 8
    let operation ← IO.ofExcept <| read model (b+16) 8
    let ns ← IO.ofExcept <| read model (b+24) 8
    let object ← IO.ofExcept <| read model (b+32) 8
    let transaction ← IO.ofExcept <| read model (b+40) 8
    let offset ← IO.ofExcept <| read model (b+48) 8
    let count ← IO.ofExcept <| read model (b+56) 8
    if header != 0x31525453414d454c || version != 1 || ns != 1 ||
        object != 0x4350000100000001 || transaction != 7 then
      throw <| IO.userError "installer changed exact object/edition/namespace/transaction"
    let expectedRequest := if operation == 4 then 1257 else if operation == 9 then 1258 else
      if operation == 2 then 1000 else 1001+offset/128
    if d != expectedRequest || c != (if operation == 3 then 64+count else 64) then
      throw <| IO.userError "installer changed stable operation identity/frame"
    if operation == 2 then
      if !model.requests.isEmpty || offset != 0 || count != model.package.size.toUInt64 then
        throw <| IO.userError "Begin did not precede the declared upload"
    else if operation == 3 then
      let expectedCount := min 128 (model.package.size.toUInt64-offset)
      if offset != model.uploaded || count != expectedCount then
        throw <| IO.userError "chunk order/backpressure/limit changed"
      for i in [:count.toNat] do
        let copied ← IO.ofExcept <| read model (b+64+i.toUInt64) 1
        if copied != model.package[offset.toNat+i]!.toUInt64 then
          throw <| IO.userError "actual copied-IPC payload differs from caller package"
    else if operation == 4 then
      if model.uploaded != model.package.size.toUInt64 || offset != 0 || count != 0 then
        throw <| IO.userError "Commit occurred before all owned bytes"
    else if operation == 9 then
      if model.requests.any (fun row => row.2.1 == 4) || offset != 0 || count != 0 then
        throw <| IO.userError "Abort followed uncertain Commit or changed frame"
    else throw <| IO.userError "installer acquired another protocol operation"
    state.set {model with requests := model.requests.push (d,operation,count), pending := true, request := d, operation, offset, count}
    if operation == model.faultOperation && model.fault == 1 then
      state.modify fun next => {next with pending := false}
      return (93,0)
    return (0,42)
  else if number = IPCABI.callWait then
    if !model.pending || a != 42 || b != base+768 || c != 256 || d != 0 || e != 0 then
      throw <| IO.userError "installer changed actual wait framing"
    let fault := model.operation == model.faultOperation
    let app : UInt64 := if fault && model.fault == 2 then
      if model.operation == 2 then 223 else 230 else 0
    let detail : UInt64 := if model.operation == 3 then model.offset+model.count else
      if model.operation == 4 then 1 else 0
    let detail := if fault && model.fault == 3 then detail+1 else
      if fault && model.fault == 4 then 0 else detail
    let sequence : UInt64 := if model.operation == 4 then
      if fault && model.fault == 5 then 0 else 37 else 0
    let mut response := model
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,model.request),(32,0),
        (40,64),(48,app),(56,0),(64,0x31525453414d454c),(72,1),(80,model.operation),(88,1),
        (96,0x4350000100000001),(104,sequence),(112,detail),(120,0)] do
      response ← set response (b+offset) value
    state.set {response with pending := false, uploaded := if app == 0 && model.operation == 3 then model.uploaded+model.count else model.uploaded}
    return (0,128)
  else throw <| IO.userError "installer acquired undeclared syscall"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if count.toNat > budget then throw <| IO.userError "Store loader exceeded its declared fold"
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
          let value ← IO.ofExcept <| read (← state.get) a width
          run state (next 0 value)
        | .virtualWrite8 | .virtualWrite64 =>
          let width := if operation == .virtualWrite8 then 1 else 8
          state.set (← IO.ofExcept <| write (← state.get) a width b)
          run state (next 0 0)
        | .syscall =>
          let (s,value) ← syscall state a b c d e f
          run state (next s value)
        | _ => throw <| IO.userError "Store loader acquired an undeclared platform operation"
  | _ => throw <| IO.userError "Store loader acquired an undeclared Action"

private def initial (image : ByteArray) : IO Model := do
  let mut model : Model := {memory := ByteArray.mk (Array.replicate 73728 0xa5), package := image}
  for (offset,value) in #[(0,16),(8,base+512),(16,base+768),(24,1),(32,1),(40,1),
      (48,target),(56,8192),(64,1000),(72,0)] do
    model ← set model (base+offset) value
  return model

def check : IO Unit := do
  let image ← match Package.encode PackageReference.arithmetic with
    | .ok image => pure image | .error error => throw <| IO.userError error.render
  let mut before ← initial image
  for i in [:image.size] do before ← IO.ofExcept <| write before (target+i.toUInt64) 1 image[i]!.toUInt64
  let state ← IO.mkRef before
  let actual ← run state (PackageStore.install base image.size.toUInt64 7)
  let after ← state.get
  if actual != (0,37) || after.requests.size != (image.size+127)/128+2 || after.pending ||
      after.uploaded != image.size.toUInt64 || after.memory.extract 65536 73728 != before.memory.extract 65536 73728 then
    throw <| IO.userError "actual installer did not retain source/use ordered complete publication"
  for (operation,fault,status,last) in #[(2,1,93,2),(2,2,223,2),(3,1,93,9),(3,2,230,9),
      (3,3,240,9),(4,1,93,4),(4,2,230,4),(4,4,240,4),(4,5,240,4)] do
    let failed ← IO.mkRef {before with faultOperation := operation, fault}
    let result ← run failed (PackageStore.install base image.size.toUInt64 7)
    let observed ← failed.get
    if result != (status,0) || observed.pending || observed.requests.back!.2.1 != last ||
        (last == 9 && observed.requests.size != 3) ||
        (operation == 4 && observed.requests.any (fun row => row.2.1 == 9)) then
      throw <| IO.userError s!"failure invented Installed/retried uncertain Commit/lost error: {operation}/{fault} {result}"
  for (offset,value,status) in #[(32,0,240),(40,2,240),(56,127,242),(64,0,240),(72,1,240),
      (48,base+512,240),(8,base+16,240)] do
    let invalid ← IO.mkRef (← set before (base+offset) value)
    let result ← run invalid (PackageStore.install base image.size.toUInt64 7)
    if result != (status,0) || !(← invalid.get).requests.isEmpty then
      throw <| IO.userError "invalid install context consumed Store I/O"
  let corrupt := {before with memory := before.memory.set! (65536+image.size-1) 0}
  let invalid ← IO.mkRef corrupt
  let result ← run invalid (PackageStore.install base image.size.toUInt64 7)
  if result != (243,0) || !(← invalid.get).requests.isEmpty then
    throw <| IO.userError "integrity failure consumed Store I/O"
  IO.println s!"COURSE_INSTALL_ACTIONS:PASS {after.requests.size} genuine ordered Begin/chunks/Commit calls,{image.size} exact copied bytes,9 independent failed outcomes,7 admission guards,CRC rejection; component only"

end CourseInstallTests

def main : IO Unit := CourseInstallTests.check
