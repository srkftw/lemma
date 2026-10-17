import Lemma.Courses.PackageStore

/-! The actual guest mount-wait Action with opaque independently framed status
replies. No journal recovery or host readiness flag is supplied. The fixture
rejects every operation except time, sleep and read-only Store status8. -/
namespace CourseMountTests
open Lemma.Core0.Memory Lemma.Courses Lemma.Services.Store Lemma.User
def base : UInt64 := 0x40000
structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 8192 0xa5)
  modes : Array UInt64 := #[1]
  requests : Array UInt64 := #[]
  sleeps : Array UInt64 := #[]
  pending : Bool := false
  now : UInt64 := 100
  waitDelay : UInt64 := 0
  beginFailure : UInt8 := 0
  waitFailure : UInt8 := 0
  expectedPause : UInt64 := 1000000

private def read (m : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || m.memory.size.toUInt64 < width || m.memory.size.toUInt64-width < address-base then
    throw "mount Action touched outside the owned fixture arena"
  return (List.range width.toNat).foldl (fun value i =>
    value ||| (m.memory[(address-base).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0
private def write (m : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read m address width
  return {m with memory := (List.range width.toNat).foldl (fun bytes i =>
    bytes.set! ((address-base).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) m.memory}
private def set (m : Model) (address value : UInt64) : IO Model := IO.ofExcept (write m address 8 value)

private def syscall (state : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let m ← state.get
  if number = ABI.time then
    if a != 0 || b != 0 || c != 0 || d != 0 || e != 0 then throw <| IO.userError "changed time ABI"
    return (0,m.now)
  else if number = ABI.sleep then
    if a != m.expectedPause || b != 0 || c != 0 || d != 0 || e != 0 || m.pending then
      throw <| IO.userError "mount wait failed to yield only after completed status"
    state.set {m with now := m.now+a, sleeps := m.sleeps.push a}
    return (0,0)
  else if number = IPCABI.callBegin then
    if m.pending || a != 16 || b != base+512 || c != 64 || e != 300000000 || d != 1000+m.requests.size.toUInt64 then
      throw <| IO.userError "mount wait changed owned framing or stable status request IDs"
    for (offset,value) in #[(0,Protocol.magic),(8,1),(16,8),(24,1),(32,0),(40,0),(48,0),(56,0)] do
      if (← IO.ofExcept <| read m (b+offset) 8) != value then
        throw <| IO.userError "mount wait attempted a mutation or noncanonical status request"
    state.set {m with requests := m.requests.push d, pending := m.beginFailure == 0}
    return if m.beginFailure == 0 then (0,42) else (m.beginFailure,0)
  else if number = IPCABI.callWait then
    if !m.pending || a != 42 || b != base+768 || c != 256 || d != 0 || e != 0 then
      throw <| IO.userError "mount wait changed its actual transaction wait"
    if m.waitFailure != 0 then
      state.set {m with pending := false}
      return (m.waitFailure,0)
    let i := min (m.requests.size-1) (m.modes.size-1)
    let mode := m.modes[i]!
    let mut reply := m
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,m.requests.back!),
        (32,0),(40,64),(48,0),(56,0),(64,Protocol.magic),(72,1),(80,8),(88,1),
        (96,0),(104,77),(112,mode),(120,0)] do
      reply ← set reply (b+offset) value
    state.set {reply with pending := false, now := m.now+m.waitDelay}
    return (0,128)
  else throw <| IO.userError "mount wait acquired an undeclared or mutating syscall"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s value => pure (s,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if count.toNat > budget then throw <| IO.userError "mount wait exceeded its static fold"
      let mut status : UInt8 := 0
      let mut value := initial
      for i in [:count.toNat] do
        if status == 0 then
          let result ← run state (step i.toUInt32 count value a b c d)
          status := result.1
          value := result.2
      run state (next status value)
  | .platform operation a b c d e f next => do
      match operation with
      | .virtualRead64 =>
          let value ← IO.ofExcept <| read (← state.get) a 8
          run state (next 0 value)
      | .virtualWrite64 =>
          state.set (← IO.ofExcept <| write (← state.get) a 8 b)
          run state (next 0 0)
      | .syscall =>
          let result ← syscall state a b c d e f
          run state (next result.1 result.2)
      | _ => throw <| IO.userError "mount wait acquired an undeclared platform operation"
  | _ => throw <| IO.userError "mount wait acquired an undeclared Action"

private def initial : IO Model := do
  let mut m : Model := {}
  for (offset,value) in #[(0,16),(8,base+512),(16,base+768),(24,1),(32,1),(40,1),
      (48,base+4096),(56,4096),(64,1000),(72,0)] do
    m ← set m (base+offset) value
  return m

def check : IO Unit := do
  let before ← initial
  let ready ← IO.mkRef {before with modes := #[0,0,1]}
  if (← run ready (PackageStore.awaitReady base)) != (0,77) then throw <| IO.userError "real guest mount wait did not admit ready"
  let after ← ready.get
  if after.requests != #[1000,1001,1002] || after.sleeps != #[1000000,1000000] || after.pending ||
      after.memory.extract 0 80 != before.memory.extract 0 80 || after.memory.extract 4096 8192 != before.memory.extract 4096 8192 then
    throw <| IO.userError "mount wait mutated context/package or did not yield/order requests"
  for (mode,status) in #[(1,0),(2,221),(3,223),(4,240)] do
    let state ← IO.mkRef {before with modes := #[mode]}
    let result ← run state (PackageStore.awaitReady base)
    if result.1 != status || (status == 0 && result.2 != 77) || (← state.get).requests != #[1000] || !(← state.get).sleeps.isEmpty then
      throw <| IO.userError "mount status was reformatted, retried or misclassified"
  for failed in #[{before with beginFailure := 93},{before with waitFailure := 94},
      {before with waitDelay := 6000000000},{before with now := 0xffffffffffffffff}] do
    let state ← IO.mkRef failed
    let result ← run state (PackageStore.awaitReady base)
    let expected := if failed.beginFailure != 0 then failed.beginFailure else if failed.waitFailure != 0 then failed.waitFailure
      else if failed.waitDelay != 0 then IPCABI.timeout else PackageFormat.resourceLimit
    if result != (expected,0) || !(← state.get).sleeps.isEmpty then throw <| IO.userError "actual transport/deadline failure became readiness"
  for (offset,value,status) in #[(64,0,240),(72,1,240),(24,3,240),(48,base+512,240),
      (56,127,242),(64,Format.maximumSequence-5999,242)] do
    let state ← IO.mkRef (← set before (base+offset) value)
    if (← run state (PackageStore.awaitReady base)) != (status,0) || !(← state.get).requests.isEmpty then
      throw <| IO.userError "invalid mount context consumed Store I/O"
  let initialized ← IO.mkRef {before with modes := #[2,0,1],expectedPause := 1000000}
  if (← run initialized (PackageStore.awaitPublished base 1)) != (0,77) ||
      (← initialized.get).sleeps != #[1000000,1000000] || (← initialized.get).requests != #[1000,1001,1002] then
    throw <| IO.userError "initializer status wait formatted, failed to yield or published unmounted readiness"
  let unopened ← IO.mkRef {before with modes := #[2],expectedPause := 1000000}
  if (← run unopened (PackageStore.awaitPublished base 0)) != (221,0) || !(← unopened.get).sleeps.isEmpty then
    throw <| IO.userError "ordinary cold startup changed unformatted failure"
  let invalidPolicy ← IO.mkRef before
  if (← run invalidPolicy (PackageStore.awaitPublished base 2)) != (240,0) || !(← invalidPolicy.get).requests.isEmpty then
    throw <| IO.userError "unadmitted startup policy consumed I/O"
  IO.println "COURSE_MOUNT_ACTIONS:PASS ordered object0/status8, pending yields, ready/failed modes, real errors/deadline/overflow, context guards; no format/write/Commit"
end CourseMountTests
def main : IO Unit := CourseMountTests.check
