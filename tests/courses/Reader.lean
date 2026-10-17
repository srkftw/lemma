import Lemma.Courses.PackageReader
import Lemma.Courses.PackageBinding

/-! Independent literal copied-IPC fixture for the cooperative guest reader. The fixture
supplies package bytes and framed transport outcomes only; it does not mount a
journal, install a package, evaluate an answer or create guest proof evidence. -/
namespace CourseReaderTests
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
  pollsBlocked : Nat := 0
  canceled : Bool := false
  cancelAlreadyCompleted : Bool := false
  syscalls : Array UInt64 := #[]
  writeFault : Option UInt64 := none

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
    state.set {model with requests := model.requests.push (d,offset,count), pending := true, request := d, offset, count,syscalls := model.syscalls.push number}
    if model.faultRequest == some model.requests.size && model.fault == 1 then
      state.modify fun next => {next with pending := false}
      return (93,0)
    return (0,42)
  else if number = 67 then
    if !model.pending || a != 42 || b != base+768 || c != 256 || d != 0 || e != 0 then
      throw <| IO.userError "loader changed its actual transaction wait"
    if model.pollsBlocked != 0 then
      state.set {model with pollsBlocked := model.pollsBlocked-1,syscalls := model.syscalls.push number}
      return (12,0)
    if model.canceled && !model.cancelAlreadyCompleted then
      state.set {model with pending := false,syscalls := model.syscalls.push number}
      return (94,0)
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
    state.set {response with pending := false,syscalls := model.syscalls.push number}
    return (0,128+count)
  else if number = 25 then
    if !model.pending || a != 42 || b ||| c ||| d ||| e != 0 then
      throw <| IO.userError "reader canceled the wrong actual owned transaction"
    state.set {model with canceled := true,syscalls := model.syscalls.push number}
    return (if model.cancelAlreadyCompleted then 100 else 0,0)
  else throw <| IO.userError "reader acquired an undeclared syscall"

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
          let fault := (← state.get).writeFault.any fun point => a ≤ point && point < a+width
          if fault then run state (next 17 0) else
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
      (48,target),(56,8192),(64,1000),(72,0),(80,0),(88,0),(96,0),(104,0),(112,0),(120,0)] do
    model ← set model (base+offset) value
  return model

private def field (state : IO.Ref Model) (offset : UInt64) : IO UInt64 := do
  IO.ofExcept <| read (← state.get) (base+offset) 8

private def fetch (state : IO.Ref Model) : IO (UInt8 × UInt64) := do
  if (← run state (PackageReader.start base)) != (0,0) then
    throw <| IO.userError "reader did not initialize owned state"
  let mut result : UInt8 × UInt64 := (0,0)
  for _ in [:1024] do
    if (← field state 72) < 2 && result.1 == 0 then
      let before := (← state.get).syscalls.size
      result ← run state (PackageReader.step base)
      let after := (← state.get).syscalls.size
      if after-before > 1 then throw <| IO.userError "reader step waited or acquired multiple I/O operations"
  return result

def check : IO Unit := do
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE"
    | throw <| IO.userError "reader fixture requires a real Lean-published package"
  let image ← IO.FS.readBinFile filename
  if image.size < 128 || image.size > 8192 then throw <| IO.userError "unexpected qualification package size"
  let before ← initial image
  let state ← IO.mkRef before
  let actual ← fetch state
  let after ← state.get
  if actual != (0,image.size.toUInt64) || after.requests.size != (image.size+127)/128 || after.pending ||
      (← field state 72) != 2 then
    throw <| IO.userError "reader failed ordered cooperative raw retrieval"
  if after.memory.extract 65536 (65536+image.size) != image ||
      after.memory.extract (65536+image.size) 73728 != before.memory.extract (65536+image.size) 73728 ||
      after.memory.extract 0 72 != before.memory.extract 0 72 then
    throw <| IO.userError "reader changed configuration/tail or an unrelated active buffer"
  if (← run state (PackageReader.finish base)) != (0,image.size.toUInt64) ||
      (← field state 72) != 3 || (← state.get).syscalls != after.syscalls then
    throw <| IO.userError "raw bytes were published before genuine full decoder validation"

  let pending ← IO.mkRef {before with pollsBlocked := 2}
  let _ ← run pending (PackageReader.start base)
  let _ ← run pending (PackageReader.step base)
  let memory := (← pending.get).memory
  if (← run pending (PackageReader.finish base)) != (231,0) then
    throw <| IO.userError "pending transaction became a validated package"
  for _ in [:2] do
    if (← run pending (PackageReader.step base)) != (12,0) ||
        (← pending.get).memory != memory || !(← pending.get).pending then
      throw <| IO.userError "wouldBlock consumed bytes/transaction or changed unpublished state"
  if (← run pending (PackageReader.start base)) != (231,0) ||
      (← pending.get).requests.size != 1 then
    throw <| IO.userError "initialization orphaned a live transaction"

  for completed in #[false,true] do
    let canceled ← IO.mkRef {before with cancelAlreadyCompleted := completed}
    let _ ← run canceled (PackageReader.start base)
    let _ ← run canceled (PackageReader.step base)
    let memory := (← canceled.get).memory.extract 65536 73728
    if (← run canceled (PackageReader.cancel base)) != (94,0) || (← canceled.get).pending ||
        (← field canceled 72) != 5 || (← field canceled 80) != 0 ||
        (← canceled.get).syscalls != #[22,25,67] ||
        (← canceled.get).memory.extract 65536 73728 != memory then
      throw <| IO.userError "cancel failed exactly one terminal consumption or copied a discarded result"
    if (← run canceled (PackageReader.step base)) != (94,0) ||
        (← run canceled (PackageReader.finish base)) != (231,0) ||
        (← canceled.get).syscalls != #[22,25,67] then
      throw <| IO.userError "canceled state generated publication or duplicate I/O"

  for (fault,status) in #[(1,93),(2,240),(3,101),(4,230)] do
    let failed ← IO.mkRef {before with faultRequest := some 1, fault}
    let result ← fetch failed
    let observed ← failed.get
    if result != (status,0) || observed.requests.size != 2 || observed.pending ||
        (← field failed 72) != 4 || (← field failed 120) != status.toUInt64 ||
        observed.memory.extract 65536 (65536+128) != image.extract 0 128 ||
        observed.memory.extract (65536+128) 73728 != before.memory.extract (65536+128) 73728 then
      throw <| IO.userError "failed reply was copied, published or retried"
    let count := observed.syscalls.size
    if (← run failed (PackageReader.step base)) != (status,0) ||
        (← failed.get).syscalls.size != count then
      throw <| IO.userError "reader retried a failed request"

  let corrupted ← IO.mkRef {before with package := image.set! (image.size-1) (image[image.size-1]! ^^^ 1)}
  let _ ← fetch corrupted
  if (← run corrupted (PackageReader.finish base)) != (243,0) || (← field corrupted 72) != 4 then
    throw <| IO.userError "transport-complete corrupt package bypassed real guest CRC validation"

  for faultByte in #[0,1,7,8,127] do
    let failed ← IO.mkRef {before with writeFault := some (target+128+faultByte)}
    let result ← fetch failed
    let observed ← failed.get
    -- The existing aligned Format.copy publishes whole ordered64-bit words.
    -- A failed admitted word publishes none of its bytes.
    let copied := 128+(faultByte/8*8).toNat
    if result != (17,0) || observed.pending || observed.requests.size != 2 ||
        (← field failed 72) != 4 || (← field failed 120) != 17 ||
        observed.memory.extract 65536 (65536+copied) != image.extract 0 copied ||
        observed.memory.extract (65536+copied) 73728 != before.memory.extract (65536+copied) 73728 ||
        (← run failed (PackageReader.finish base)) != (231,0) then
      throw <| IO.userError "partial staging fault changed its exact prefix/error or published raw bytes"

  for (offset,value,status) in #[(32,0,240),(40,0,240),(56,127,242),(64,0,240),
      (48,base+512,240),(8,base+16,240),(72,6,240),(80,42,231)] do
    let invalid ← IO.mkRef (← set before (base+offset) value)
    let result ← run invalid (PackageReader.start base)
    if result != (status,0) || !(← invalid.get).requests.isEmpty then
      throw <| IO.userError "invalid reader configuration consumed Store I/O"

  -- A selection anchor supplements original checker identity; it never
  -- overwrites a mathematical document or invokes that checker.
  let binding := base+4096
  let bound ← IO.mkRef after
  for (ordinal,node,goal) in #[(2,3,1),(5,6,2)] do
    if (← run bound (PackageBinding.capture binding target image.size.toUInt64 ordinal 7)) != (0,node) then
      throw <| IO.userError "admitted exact exercise could not capture provenance"
    let fields ← (List.range 16).toArray.mapM fun i => do
      IO.ofExcept <| read (← bound.get) (binding+i.toUInt64*8) 8
    let expected := #[0x31444e494253434c,1,1,1,
      (← IO.ofExcept <| read after (target+80) 8),node,node,3,goal,0x0001000000000001,
      goal,0,8,(← IO.ofExcept <| read after (target+104) 8),
      (← IO.ofExcept <| read after (target+120) 8),7]
    if fields != expected || (← run bound (PackageBinding.validate binding)) != (0,goal) ||
        (← run bound (PackageBinding.applicable binding 7 goal goal 0)) != (0,1) then
      throw <| IO.userError "literal package/edition/CRC/source/rights/exact-goal binding differs"
    for (revision,observedGoal,domain,assumptions) in #[(8,goal,goal,0),(7,3,goal,0),(7,goal,3,0),(7,goal,goal,1)] do
      if (← run bound (PackageBinding.applicable binding revision observedGoal domain assumptions)) != (0,0) then
        throw <| IO.userError "edited or different submission retained old applicability"
    if (← bound.get).syscalls != after.syscalls ||
        (← bound.get).memory.extract 65536 73728 != after.memory.extract 65536 73728 then
      throw <| IO.userError "binding changed package/Store effects or mathematical authority"
  for ordinal in #[0,1,3,4,6,7] do
    let memory := (← bound.get).memory
    if (← run bound (PackageBinding.capture binding target image.size.toUInt64 ordinal 7)) != (241,0) ||
        (← bound.get).memory != memory then
      throw <| IO.userError "author text/unsupported goal created a checking selection"
  for (offset,value,status) in #[(8,2,241),(16,0,240),(24,0,240),(32,0x100000000,240),
      (40,0,240),(48,7,240),(56,4,241),(64,3,241),(72,0,241),(80,1,240),
      (88,1,241),(96,7,240),(104,0,240),(112,0,240),(120,0,240)] do
    let invalid ← IO.mkRef (← set (← bound.get) (binding+offset) value)
    if (← run invalid (PackageBinding.validate binding)) != (status,0) then
      throw <| IO.userError "corrupt/unsupported binding became applicable"
  let failed ← IO.mkRef {after with writeFault := some (binding+80)}
  if (← run failed (PackageBinding.capture binding target image.size.toUInt64 2 7)) != (17,0) ||
      (← run failed (PackageBinding.validate binding)) != (240,0) ||
      (← failed.get).syscalls != after.syscalls then
    throw <| IO.userError "partial binding write published its commit tag or changed original error"
  IO.println s!"COURSE_PACKAGE_READER_ACTIONS:PASS {after.requests.size} one-operation READ/poll phases,{image.size} exact raw bytes,full validation separate; pending/cancel-discard including accepted result; 4 failures/no retry,CRC,8 context guards; no CPU/journal/checker authority"
  IO.println "COURSE_PACKAGE_BINDING_ACTIONS:PASS two literal exact-goal/source/rights bindings,8 applicability mismatches,6 unsupported nodes,15 mutations,partial-write failure; original package unchanged/no proof evidence"

end CourseReaderTests

def main : IO Unit := CourseReaderTests.check
