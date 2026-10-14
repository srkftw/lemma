import Lemma.Courses.PackageStore

/-! Literal opaque copied-IPC fixture for the real guest loader. The fixture
supplies package bytes and framed transport outcomes only; it does not mount a
journal, install a package, evaluate an answer or create guest proof evidence. -/
namespace CourseStoreTests
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
  pending : Bool := false
  request : UInt64 := 0
  offset : UInt64 := 0
  count : UInt64 := 0
  faultRequest : Option Nat := none
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
    if model.pending || a != 16 || b != base+512 || c != 64 || e != 300000000 then
      throw <| IO.userError "loader changed the admitted copied IPC call framing"
    let header ← IO.ofExcept <| read model b 8
    let version ← IO.ofExcept <| read model (b+8) 8
    let operation ← IO.ofExcept <| read model (b+16) 8
    let ns ← IO.ofExcept <| read model (b+24) 8
    let object ← IO.ofExcept <| read model (b+32) 8
    let transaction ← IO.ofExcept <| read model (b+40) 8
    let offset ← IO.ofExcept <| read model (b+48) 8
    let count ← IO.ofExcept <| read model (b+56) 8
    let expectedOffset := model.requests.size.toUInt64*128
    let expectedCount := if model.package.size.toUInt64 - expectedOffset < 128 then
      model.package.size.toUInt64 - expectedOffset else 128
    if header != 0x31525453414d454c || version != 1 || operation != 5 || ns != 1 ||
        object != 0x4350000100000001 || transaction != 0 || offset != expectedOffset ||
        count != expectedCount || d != 1000+model.requests.size.toUInt64 then
      throw <| IO.userError "loader changed the exact object, ordered offset/count or stable request ID"
    state.set {model with requests := model.requests.push (d,offset,count), pending := true, request := d, offset, count}
    if model.faultRequest == some model.requests.size && model.fault == 1 then
      state.modify fun next => {next with pending := false}
      return (93,0)
    return (0,42)
  else if number = IPCABI.callWait then
    if !model.pending || a != 42 || b != base+768 || c != 256 || d != 0 || e != 0 then
      throw <| IO.userError "loader changed its actual transaction wait"
    let fault := model.faultRequest == some (model.requests.size-1)
    let count := if fault && model.fault == 2 then model.count-1 else model.count
    let request := if fault && model.fault == 3 then model.request+1 else model.request
    let app := if fault && model.fault == 4 then (230 : UInt64) else 0
    let count := if app == 0 then count else 0
    let mut response := model
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,request),(32,0),
        (40,64+count),(48,app),(56,0),(64,0x31525453414d454c),(72,1),(80,5),(88,1),
        (96,0x4350000100000001),(104,77),(112,1),(120,count)] do
      response ← set response (b+offset) value
    for i in [:count.toNat] do
      response ← IO.ofExcept <| write response (b+128+i.toUInt64) 1 model.package[model.offset.toNat+i]!.toUInt64
    state.set {response with pending := false}
    return (0,128+count)
  else throw <| IO.userError "loader acquired an undeclared syscall"

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
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE"
    | throw <| IO.userError "Store fixture requires a real Lean-published package"
  let image ← IO.FS.readBinFile filename
  let before ← initial image
  let state ← IO.mkRef before
  let actual ← run state (PackageStore.load base)
  let after ← state.get
  if actual != (0,image.size.toUInt64) || after.requests.size != (image.size+127)/128 || after.pending then
    throw <| IO.userError "real loader failed its bounded ordered copied-IPC transfer"
  if after.memory.extract 65536 (65536+image.size) != image ||
      after.memory.extract (65536+image.size) 73728 != before.memory.extract (65536+image.size) 73728 ||
      after.memory.extract 0 80 != before.memory.extract 0 80 then
    throw <| IO.userError "loader changed context/tail bytes or copied an incomplete package"
  for (fault,status) in #[(1,93),(2,240),(3,101),(4,230)] do
    let failed ← IO.mkRef {before with faultRequest := some 1, fault}
    let result ← run failed (PackageStore.load base)
    let observed ← failed.get
    if result != (status,0) || observed.requests.size != 2 || observed.pending ||
        observed.memory.extract 65536 (65536+128) != image.extract 0 128 ||
        observed.memory.extract (65536+128) 73728 != before.memory.extract (65536+128) 73728 then
      throw <| IO.userError "failed reply was copied, acknowledged or retried"
  for (offset,value,status) in #[(32,0,240),(40,0,240),(56,127,242),(64,0,240),(72,1,240),
      (48,base+512,240),(8,base+16,240)] do
    let invalid ← IO.mkRef (← set before (base+offset) value)
    let result ← run invalid (PackageStore.load base)
    if result != (status,0) || !(← invalid.get).requests.isEmpty then
      throw <| IO.userError "invalid loader context consumed Store I/O"
  IO.println s!"COURSE_PACKAGE_STORE_ACTIONS:PASS {after.requests.size} genuine ordered READ calls,{image.size} exact bytes,4 reply/transport failures without failed-copy/retry,7 context guards; no install or checker authority"

end CourseStoreTests

def main : IO Unit := CourseStoreTests.check
