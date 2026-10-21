import Lemma.Courses.PackageInstaller
import Lemma.Courses.PackageReference

/-! Actual guest selection Action over opaque copied IPC. This finite transport
fixture supplies existing package bytes and fault replies; it neither implements
Store journal recovery nor claims durability. Native cold reopen is separate. -/
namespace CourseSelectionTests
open Lemma.Core0.Memory Lemma.Courses Lemma.Services.Store Lemma.User
open Lemma.Courses.PackageInstaller

def base : UInt64 := 0x20000
structure Model where
  memory : ByteArray
  image : ByteArray
  requests : Array (UInt64 × UInt64) := #[]
  pending : Bool := false
  operation : UInt64 := 0
  request : UInt64 := 0
  offset : UInt64 := 0
  count : UInt64 := 0
  faultOperation : UInt64 := 0
  fault : UInt64 := 0
  ordinal : UInt64 := 0

private def read (model : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || model.memory.size.toUInt64 < width || model.memory.size.toUInt64-width < address-base then
    throw "selection escaped the owned fixture arena"
  return (List.range width.toNat).foldl (fun value i =>
    value ||| (model.memory[(address-base).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0
private def write (model : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read model address width
  return {model with memory := (List.range width.toNat).foldl (fun bytes i =>
    bytes.set! ((address-base).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) model.memory}
private def set (model : Model) (address value : UInt64) : IO Model := IO.ofExcept (write model address 8 value)

private def syscall (state : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let model ← state.get
  if number = IPCABI.callBegin then
    if model.pending || a != 16 || b != outgoing || e != 300000000 then
      throw <| IO.userError "selection changed copied IPC authority/deadline"
    let get (offset : UInt64) := IO.ofExcept <| read model (b+offset) 8
    let magic ← get 0
    let version ← get 8
    let operation ← get 16
    let ns ← get 24
    let object ← get 32
    let transaction ← get 40
    let offset ← get 48
    let count ← get 56
    if magic != Protocol.magic || version != 1 || c != (if operation == 3 then 64+count else 64) then
      throw <| IO.userError "selection changed actual Store framing"
    if operation == 5 then
      if ns != 1 || object != PackageFormat.object 802 1 || transaction != 0 ||
          d != 1000+offset/128 || offset%128 != 0 || count != min 128 (model.image.size.toUInt64-offset) then
        throw <| IO.userError "selection did not read the exact installed edition in bounded pieces"
    else
      if ns != 2 || object != PackageCommand.selectedObject || transaction != 7 || offset != 0 ||
          d != (if operation == 2 then 1256 else if operation == 3 then 1257 else if operation == 4 then 1258 else 1259) ||
          count != (if operation == 2 || operation == 3 then 64 else 0) then
        throw <| IO.userError "selection retargeted its owned durable record/transaction"
      let writes := model.requests.filter (fun row => row.2 != 5)
      if operation == 2 then
        if !writes.isEmpty then throw <| IO.userError "selection Begin out of order"
      else if operation == 3 then
        if writes.map (·.2) != #[2] then throw <| IO.userError "selection Chunk out of order"
        let crc := (List.range 8).foldl (fun x i => x |||
          (model.image[80+i]!.toUInt64 <<< (i.toUInt64*8))) (0 : UInt64)
        for (i,value) in (#[PackageCommand.selectedMagic,1,1,802,1,crc,model.ordinal,0]).zipIdx do
          if (← IO.ofExcept <| read model (b+64+value.toUInt64*8) 8) != i then
            throw <| IO.userError "selection copied the wrong immutable package binding"
      else if operation == 4 then
        if writes.map (·.2) != #[2,3] then throw <| IO.userError "selection Commit preceded its complete record"
      else if operation == 9 then
        if writes.any (fun row => row.2 == 4) then throw <| IO.userError "selection aborted uncertain Commit"
      else throw <| IO.userError "selection acquired an undeclared protocol operation"
    state.set {model with requests := model.requests.push (d,operation), pending := true, operation, request := d, offset, count}
    if operation == model.faultOperation && model.fault == 1 then
      state.modify fun m => {m with pending := false}
      return (93,0)
    return (0,42)
  else if number = IPCABI.callWait then
    if !model.pending || a != 42 || b != incoming || c != 256 || d != 0 || e != 0 then
      throw <| IO.userError "selection changed copied reply framing"
    let fault := model.operation == model.faultOperation
    let app : UInt64 := if fault && model.fault == 2 then 230 else 0
    let count := if model.operation == 5 && app == 0 then model.count else 0
    let detail : UInt64 := if model.operation == 3 then 64 else if model.operation == 4 then 1 else 0
    let detail := if fault && model.fault == 3 then detail+1 else if fault && model.fault == 4 then 0 else detail
    let sequence : UInt64 := if model.operation == 4 then if fault && model.fault == 5 then 0 else 37 else 0
    let ns : UInt64 := if model.operation == 5 then 1 else 2
    let object := if model.operation == 5 then PackageFormat.object 802 1 else PackageCommand.selectedObject
    let mut response := model
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,model.request),(32,0),
        (40,64+count),(48,app),(56,0),(64,Protocol.magic),(72,1),(80,model.operation),(88,ns),
        (96,object),(104,sequence),(112,detail),(120,count)] do
      response ← set response (b+offset) value
    for i in [:count.toNat] do
      response ← IO.ofExcept <| write response (b+128+i.toUInt64) 1 model.image[model.offset.toNat+i]!.toUInt64
    state.set {response with pending := false}
    return (0,128+count)
  else throw <| IO.userError "selection acquired undeclared syscall"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if count.toNat > budget then throw <| IO.userError "selection exceeded its bounded fold"
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
          let value ← IO.ofExcept <| read (← state.get) a (if operation == .virtualRead8 then 1 else 8)
          run state (next 0 value)
        | .virtualWrite8 | .virtualWrite64 =>
          state.set (← IO.ofExcept <| write (← state.get) a (if operation == .virtualWrite8 then 1 else 8) b)
          run state (next 0 0)
        | .syscall =>
          let (s,value) ← syscall state a b c d e f
          run state (next s value)
        | _ => throw <| IO.userError "selection acquired undeclared platform operation"
  | _ => throw <| IO.userError "selection acquired undeclared Action"

private def initial (image : ByteArray) : IO Model := do
  let mut model : Model := {memory := ByteArray.mk (Array.replicate 196608 0xa5), image}
  for (address,value) in #[(state+8,16),(context,16),(context+8,outgoing),(context+16,incoming),
      (context+24,1),(context+32,802),(context+40,1),(context+48,loaded),(context+56,32768),(context+64,1000),(context+72,0)] do
    model ← set model address value
  return model

def check : IO Unit := do
  let image ← IO.ofExcept <| (Package.encode {PackageReference.arithmetic with identity := 802}).mapError (·.render)
  let before ← initial image
  let crc := (List.range 8).foldl (fun x i => x ||| (image[80+i]!.toUInt64 <<< (i.toUInt64*8))) (0 : UInt64)
  let actual ← IO.mkRef before
  if (← run actual (selectInstalled 802 1 7 crc)) != (0,37) then throw <| IO.userError "selection did not require actual positive Commit"
  let after ← actual.get
  if after.requests.map (·.2) != (Array.replicate ((image.size+127)/128) 5) ++ #[2,3,4] then
    throw <| IO.userError "selection did not read complete installed package before writing"
  let node ← IO.mkRef {before with ordinal := 2}
  if (← run node (selectInstalledAt 802 1 7 crc 2)) != (0,37) then
    throw <| IO.userError "ordinary review node was not selected through actual installed bytes"
  let absent ← IO.mkRef before
  if (← run absent (selectInstalledAt 802 1 7 crc 8)) != (244,0) || (← absent.get).requests.any (fun row => row.2 != 5) then
    throw <| IO.userError "absent selected node wrote durable selection"
  for (op,fault,status,last) in #[(5,1,93,5),(5,2,230,5),(2,1,93,2),(2,2,230,2),
      (3,1,93,9),(3,2,230,9),(3,3,240,9),(4,1,93,4),(4,2,230,4),(4,4,240,4),(4,5,240,4)] do
    let failure ← IO.mkRef {before with faultOperation := op, fault}
    let result ← run failure (selectInstalled 802 1 7 crc)
    if result != (status,0) || (← failure.get).requests.back!.2 != last || (← failure.get).pending then
      throw <| IO.userError s!"selection invented commit/retried uncertain write: {op}/{fault} {result}"
  let stale ← IO.mkRef before
  if (← run stale (selectInstalled 802 1 7 (crc ^^^ 1))) != (243,0) || (← stale.get).requests.any (fun row => row.2 != 5) then
    throw <| IO.userError "stale expected CRC changed selected publication"
  for (offset,value,status) in #[(24,2,240),(48,loaded+8,240),(64,0x7ffffffffffffeff,242)] do
    let invalid ← IO.mkRef (← set before (context+offset) value)
    if (← run invalid (selectInstalled 802 1 7 crc)) != (status,0) || !(← invalid.get).requests.isEmpty then
      throw <| IO.userError "invalid selection context consumed Store I/O"
  if PackageCommand.shape PackageCommand.magic 1 9 802 1 0 7 crc != 241 ||
      PackageCommand.selectionCommandShape PackageCommand.magic 1 9 802 1 0 7 crc != 241 ||
      PackageCommand.selectionShape PackageCommand.selectedMagic 1 1 802 1 crc 0 0 != 1 ||
      PackageCommand.selectionShape PackageCommand.selectedMagic 1 1 802 1 crc 0 1 != 0 then
    throw <| IO.userError "version/record authority boundary changed"
  if PackageCommand.selectionCommandShape PackageCommand.magic 4 9 802 1 2 7 crc != 0 ||
      PackageCommand.selectionCommandShape PackageCommand.magic 2 9 802 1 2 7 crc != 240 ||
      PackageCommand.ackCommandShape PackageCommand.magic 3 10 0x5351000000000065 777 0 101 crc != 0 ||
      PackageCommand.ackCommandShape PackageCommand.magic 3 10 0x5351000000000065 777 0 0 crc != 240 then
    throw <| IO.userError "review/ack additive wire versions lost their guards"
  IO.println s!"COURSE_SELECTION_ACTIONS:PASS exact installed802/1,{image.size} bytes,ordered64-byte record/Commit,reviewnode/absentnode,v3ACKguards,11 transport/application/ack failures,stale CRC,3 context guards; component only"
end CourseSelectionTests

def main : IO Unit := CourseSelectionTests.check
