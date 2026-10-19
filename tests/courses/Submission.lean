import Lemma.Courses.SchoolSubmission
import Lemma.User.Capability

/-! Transport/RAM fixture for the actual asynchronous guest queue. Opaque Store
objects and Commit replies do not model a disk barrier; durable media remains
an independent native/browser scenario. Captured bytes are observed separately. -/
namespace SubmissionTests
open Lemma.Core0.Memory Lemma.User Lemma.Services.Store Lemma.Courses Lemma.Documents

def base : UInt64 := 0x20000
def doc : UInt64 := 0x300000
def workspace : UInt64 := 0x301000
def ink : UInt64 := 0x302000
def raw : UInt64 := 0x308000
def header : UInt64 := 0x310000
structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 3604480 0)
  objects : Array (UInt64 × UInt64 × ByteArray) := #[]
  stage : ByteArray := ByteArray.empty
  stageObject : UInt64 := 0
  stageNS : UInt64 := 0
  pending : Bool := false
  request : UInt64 := 0
  operation : UInt64 := 0
  object : UInt64 := 0
  ns : UInt64 := 0
  offset : UInt64 := 0
  count : UInt64 := 0
  sequence : UInt64 := 100
  commits : UInt64 := 0
  calls : UInt64 := 0
  records : Array (Array UInt64) := #[]
  stream : ByteArray := ByteArray.empty
  streamEnds : UInt64 := 0
  slowPoll : Bool := true
  busyBegin : Bool := true
  lostCommit : Bool := false
  allocated : Array UInt64 := #[]
  failAllocate : UInt64 := 0
  clock : UInt64 := 1000
  deriving Inhabited

private def read (m : Model) (address width : UInt64) : Except String UInt64 := do
  if address < base || m.memory.size.toUInt64 < width || m.memory.size.toUInt64-width < address-base then
    throw "submission escaped private fixture RAM"
  return (List.range width.toNat).foldl (fun value i => value |||
    (m.memory[(address-base).toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0
private def write (m : Model) (address width value : UInt64) : Except String Model := do
  let _ ← read m address width
  return {m with memory := (List.range width.toNat).foldl (fun bytes i =>
    bytes.set! ((address-base).toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) m.memory}
private def set (state : IO.Ref Model) (address value : UInt64) : IO Unit :=
  state.modify fun m => (write m address 8 value).toOption.get!
private def word (state : IO.Ref Model) (address : UInt64) : IO UInt64 := do
  IO.ofExcept <| read (← state.get) address 8
private def extract (m : Model) (address count : UInt64) : ByteArray :=
  m.memory.extract (address-base).toNat (address-base+count).toNat
private def objectBytes (m : Model) (ns object : UInt64) : Option ByteArray :=
  (m.objects.find? (fun (a,b,_) => a == ns && b == object)).map (·.2.2)
private def parseHex (m : Model) (address : UInt64) : IO UInt64 := do
  let mut value : UInt64 := 0
  for i in [:16] do
    let byte ← IO.ofExcept <| read m (address+i.toUInt64) 1
    let digit := if byte ≤ 57 then byte-48 else byte-87
    if digit > 15 then throw <| IO.userError "guest emitted malformed hex"
    value := value*16+digit
  return value
private def syscall (state : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let m ← state.get
  if number == ABI.allocatePages then
    if a < Lemma.Courses.SchoolSubmission.arena || Lemma.Courses.SchoolSubmission.arena+32768 ≤ a || a%4096 != 0 then throw <| IO.userError "queue allocation escaped eight pages"
    if a == m.failAllocate then return (ABI.quotaExceeded,0)
    if m.allocated.contains a then throw <| IO.userError "queue allocated a page twice"
    state.set {m with allocated := m.allocated.push a}
    return (0,a)
  else if number == ABI.releasePages then
    if !m.allocated.contains a then throw <| IO.userError "queue released unowned pages"
    state.set {m with allocated := m.allocated.filter (· != a)}
    return (0,1)
  else if number == ABI.time then return (0,m.clock)
  else if number == CapabilityABI.console then
    if a != 17 || b != 0 || c != Console.packetAddress || d != 88 then throw <| IO.userError "queue acquired other Console authority"
    let mut values := #[]
    for offset in #[3,20,37,54,71] do values := values.push (← parseHex m (c+offset))
    let tag := values[0]!
    if m.commits < 2 then throw <| IO.userError "bytes escaped before both real Store Commit replies"
    let mut next := m
    if tag == 0x72e then
      if values[1]! >>> 48 != 0x5351 || values[2]! == 0 then throw <| IO.userError "missing stable stream queue/commit"
      next := {next with stream := ByteArray.empty}
    else if tag == 0x72f then
      let offset := values[2]! &&& 0x0000ffffffffffff
      let count := values[2]! >>> 48
      if offset != m.stream.size.toUInt64 || count == 0 || 16 < count then throw <| IO.userError "guest stream gaps/truncates a boundary"
      let mut stream := m.stream
      for i in [:count.toNat] do
        let v := if i < 8 then values[3]! else values[4]!
        stream := stream.push ((v >>> (i.toUInt64%8*8)).toUInt8)
      next := {next with stream}
    else if tag == 0x730 then
      if values[3]! != m.stream.size.toUInt64 || values[4]! != 0 then throw <| IO.userError "guest stream invented completion"
      next := {next with streamEnds := next.streamEnds+1}
    else throw <| IO.userError "queue emitted another Console protocol"
    state.set {next with records := next.records.push values}
    return (0,88)
  else if number == IPCABI.callBegin then
    if m.pending || a != 16 || b != Lemma.Courses.SchoolSubmission.outgoing || e != 300000000 then throw <| IO.userError "queue changed IPC authority/deadline"
    let get (offset : UInt64) := IO.ofExcept <| read m (b+offset) 8
    let magic ← get 0
    let version ← get 8
    let operation ← get 16
    let ns ← get 24
    let object ← get 32
    let offset ← get 48
    let count ← get 56
    if magic != Protocol.magic || version != 1 || c != (if operation == 3 then 64+count else 64) || count > 16384 then
      throw <| IO.userError "queue changed actual packet framing"
    state.set {m with pending := true, request := d, operation, ns, object, offset, count, calls := m.calls+1}
    if operation == 3 then
      if m.stageNS != ns || m.stageObject != object || offset != m.stage.size.toUInt64 then throw <| IO.userError "queue staged out of order"
      state.modify fun next => {next with stage := next.stage ++ extract m (b+64) count}
    return (0,42)
  else if number == 67 then
    if !m.pending || a != 42 || b != Lemma.Courses.SchoolSubmission.incoming || c != 256 || d != 0 || e != 0 then throw <| IO.userError "queue changed poll ownership"
    if m.slowPoll then
      state.set {m with slowPoll := false}
      return (IPCABI.wouldBlock,0)
    let mut app : UInt64 := 0
    let mut data := ByteArray.empty
    let mut detail : UInt64 := 0
    let mut next := m
    if m.operation == 5 then
      match objectBytes m m.ns m.object with
      | none => app := 230
      | some image =>
        let offset := min image.size m.offset.toNat
        data := image.extract offset (min image.size (offset+m.count.toNat))
        detail := 1
    else if m.operation == 2 then
      if m.busyBegin then
        app := 231
        next := {m with busyBegin := false}
      else if m.object >>> 48 == 0x5351 && (objectBytes m m.ns m.object).isSome then app := 223
      else next := {m with stage := ByteArray.empty, stageObject := m.object, stageNS := m.ns}
    else if m.operation == 3 then detail := m.stage.size.toUInt64
    else if m.operation == 4 then
      if m.stageNS != m.ns || m.stageObject != m.object then throw <| IO.userError "queue committed another staging owner"
      next := {m with
        sequence := m.sequence+1
        commits := m.commits+1
        objects := (m.objects.filter (fun (ns,obj,_) => ns != m.ns || obj != m.object)).push (m.ns,m.object,m.stage) }
      detail := 1
      if m.lostCommit then
        state.set {next with pending := false, lostCommit := false}
        return (IPCABI.timeout,0)
    else if m.operation == 9 then next := {m with stage := ByteArray.empty, stageObject := 0, stageNS := 0}
    else throw <| IO.userError "queue acquired unexpected Store operation"
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,m.request),(32,0),(40,64+data.size.toUInt64),
      (48,app),(56,0),(64,Protocol.magic),(72,1),(80,m.operation),(88,m.ns),(96,m.object),
      (104,next.sequence),(112,detail),(120,data.size.toUInt64)] do
      next ← IO.ofExcept <| write next (b+offset) 8 value
    for i in [:data.size] do next ← IO.ofExcept <| write next (b+128+i.toUInt64) 1 data[i]!.toUInt64
    state.set {next with pending := false}
    return (0,128+data.size.toUInt64)
  else throw <| IO.userError s!"queue acquired syscall{number}"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
    let (s,value) ← run state first
    run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if budget < count.toNat then throw <| IO.userError "queue exceeded actual declared fold"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status == 0 then
        let result ← run state (step i.toUInt32 count value a b c d)
        status := result.1
        value := result.2
    run state (next status value)
  | .platform op a b c d e f next => do
    if op == .virtualRead8 || op == .virtualRead64 then
      run state (next 0 (← IO.ofExcept <| read (← state.get) a (if op == .virtualRead8 then 1 else 8)))
    else if op == .virtualWrite8 || op == .virtualWrite64 then
      state.set (← IO.ofExcept <| write (← state.get) a (if op == .virtualWrite8 then 1 else 8) b)
      run state (next 0 0)
    else if op == .syscall then
      let (s,v) ← syscall state a b c d e f
      run state (next s v)
    else throw <| IO.userError "queue acquired unexpected platform operation"
  | _ => throw <| IO.userError "queue acquired unexpected Action"
private def ok (state : IO.Ref Model) (action : Action) : IO UInt64 := do
  let (s,value) ← run state action
  if s != 0 then throw <| IO.userError s!"actual guest queue Action failed{s} phase{← word state Lemma.Courses.SchoolSubmission.arena}"
  return value
private def advanceTo (state : IO.Ref Model) (phase : UInt64) : IO Unit := do
  for _ in [:30000] do
    if (← word state Lemma.Courses.SchoolSubmission.arena) == phase then return
    let before ← state.get
    let _ ← ok state Lemma.Courses.SchoolSubmission.pump
    let after ← state.get
    if before.calls+1 < after.calls || before.records.size+1 < after.records.size then throw <| IO.userError "one pump exceeded IPC/Console budget"
  throw <| IO.userError s!"queue did not reach bounded phase{phase}, actual{← word state Lemma.Courses.SchoolSubmission.arena}"

def check : IO Unit := do
  let state ← IO.mkRef ({} : Model)
  let _ ← ok state (Lemma.Documents.MathematicsClosure.create doc 1 1)
  let _ ← ok state (PackageWorkspace.create workspace doc 1 1)
  let _ ← ok state (Ink.emptyPage ink 1)
  let _ ← ok state (Ink.addEntry ink 65537 1)
  let _ ← ok state (Ink.chunk raw 1 1 512 4095)
  for (offset,value) in #[(72,1000),(80,1000),(96,1024),(104,768)] do set state (raw+offset) value
  let bytes ← ok state (Ink.finishChunk raw 1 3)
  let rawBytes := extract (← state.get) raw bytes
  state.modify fun m => {m with objects := #[(1,65537,rawBytes)]}
  let revision ← word state (doc+40)
  for (offset,value) in #[(0,Lemma.Courses.SchoolSubmission.magic),(8,1),(32,100),(40,1),(48,1),(56,revision),(64,802),(72,1),
    (80,3),(88,123),(96,9),(104,2),(112,1000),(120,0),(128,Lemma.Multimodal.SchoolPacket.magic),
    (136,1),(144,1),(176,5),(184,1),(192,1000000000),(200,9),(208,77),(216,802),(224,1)] do
    set state (header+offset) value
  let _ ← ok state (Lemma.Courses.SchoolSubmission.initializeQueue 16 17 1000)
  let prepared ← state.get
  let queue ← ok state (Lemma.Courses.SchoolSubmission.start header workspace ink)
  -- Live edits after capture cannot change the frozen version or raw reference.
  set state (doc+56) 99
  let _ ← ok state (Ink.addEntry ink 65538 2)
  advanceTo state 26
  let completed ← state.get
  let frozen := (objectBytes completed 2 queue).get!
  let expected := frozen ++ rawBytes
  if completed.stream != expected || completed.streamEnds != 1 || completed.commits != 2 then
    throw <| IO.userError "queue did not transmit exact frozen metadata and original raw chunk"
  let checksum := (completed.stream.data.foldl (fun crc byte => PackageFormat.crcByte crc byte.toUInt64) 0xffffffff) ^^^ 0xffffffff
  if (← word state (Lemma.Courses.SchoolSubmission.arena+280)) != checksum then throw <| IO.userError "guest stream CRC differs from separately observed bytes"
  let _ ← ok state Lemma.Courses.SchoolSubmission.retry
  let _ ← ok state Lemma.Courses.SchoolSubmission.pump
  advanceTo state 26
  if (← state.get).stream != expected || (← state.get).commits != 2 then throw <| IO.userError "retry duplicated assessment identity or wrote a new queue"
  -- Cold component restart retains only Store objects, not any guest RAM.
  let restored ← IO.mkRef {objects := completed.objects, sequence := completed.sequence, commits := completed.commits, busyBegin := false : Model}
  let _ ← ok restored (Lemma.Courses.SchoolSubmission.initializeQueue 16 17 9000)
  let _ ← ok restored (Lemma.Courses.SchoolSubmission.restore 1)
  advanceTo restored 26
  if (← restored.get).stream != expected || (← restored.get).commits != 2 then throw <| IO.userError "restart retargeted or recommitted pending attempt"
  let paused ← IO.mkRef prepared
  let _ ← ok paused (Lemma.Courses.SchoolSubmission.start header workspace ink)
  advanceTo paused 7
  if (← ok paused Lemma.Courses.SchoolSubmission.suspend) != 1 then throw <| IO.userError "open staging was not reported"
  advanceTo paused 46
  if (← paused.get).stageObject != 0 || (← paused.get).commits != 0 ||
      (← ok paused Lemma.Courses.SchoolSubmission.writerActive) != 0 then
    throw <| IO.userError "suspension did not release the actual Store stage"
  let _ ← ok paused Lemma.Courses.SchoolSubmission.resume
  advanceTo paused 26
  if (← paused.get).stream != expected || (← paused.get).commits != 2 then throw <| IO.userError "suspension retargeted frozen attempt"
  let cancelled ← IO.mkRef prepared
  let _ ← ok cancelled (Lemma.Courses.SchoolSubmission.start header workspace ink)
  advanceTo cancelled 21
  let _ ← ok cancelled Lemma.Courses.SchoolSubmission.pump
  let _ ← ok cancelled (Lemma.Courses.SchoolSubmission.cancel queue)
  advanceTo cancelled 29
  let withdrawn := (objectBytes (← cancelled.get) 2 Lemma.Courses.SchoolSubmission.pointerObject).get!
  if withdrawn[16]! != 2 || (← cancelled.get).streamEnds != 0 then throw <| IO.userError "cancel did not stop partial presentation and persist withdrawal"
  let invalid ← IO.mkRef prepared
  for i in [:8] do let _ ← ok invalid (Ink.addEntry ink (65538+i.toUInt64) (2+i.toUInt64)); pure ()
  let invalidResult ← run invalid (Lemma.Courses.SchoolSubmission.start header workspace ink)
  if invalidResult.1 != 242 || (← invalid.get).calls != 0 then
    throw <| IO.userError s!"ninth chunk was silently truncated:{invalidResult},calls{(← invalid.get).calls},count{← word invalid (ink+32)}"
  let allocation ← IO.mkRef {failAllocate := Lemma.Courses.SchoolSubmission.arena+4*4096 : Model}
  if (← run allocation (Lemma.Courses.SchoolSubmission.initializeQueue 16 17 1000)) != (38,0) || !(← allocation.get).allocated.isEmpty then
    throw <| IO.userError "partial allocation leaked pages or erased quota error"
  allocation.modify fun m => {m with failAllocate := 0}
  let _ ← ok allocation (Lemma.Courses.SchoolSubmission.initializeQueue 16 17 1000)
  let ack := (#[Lemma.Courses.SchoolSubmission.ackMagic,1,queue,777,(← word restored (Lemma.Courses.SchoolSubmission.arena+152)),checksum,0,0]).foldl (fun bytes value =>
    (List.range 8).foldl (fun out i => out.push ((value >>> (i.toUInt64*8)).toUInt8)) bytes) ByteArray.empty
  restored.modify fun m => {m with objects := m.objects.push (2,Lemma.Courses.SchoolSubmission.ackObject,ack)}
  advanceTo restored 29
  let acknowledged := (objectBytes (← restored.get) 2 Lemma.Courses.SchoolSubmission.pointerObject).get!
  if acknowledged[16]! != 3 || (← word restored (Lemma.Courses.SchoolSubmission.arena+312)) != 777 then throw <| IO.userError "actual bound school ACK was not durably recorded"
  let lost ← IO.mkRef {completed with
    memory := ({} : Model).memory
    records := #[]
    stream := ByteArray.empty
    streamEnds := 0
    objects := #[(1,65537,rawBytes)]
    pending := false
    commits := 0
    lostCommit := true
    allocated := #[]
    busyBegin := false}
  let _ ← ok lost (Lemma.Courses.SchoolSubmission.initializeQueue 16 17 12000)
  -- Restore fresh original snapshots only as opaque fixture stimuli.
  for (source,count) in #[(header,256),(workspace,3712),(ink,Ink.pageBytes)] do
    for i in [:count.toNat] do
      let value ← IO.ofExcept <| read completed (source+i.toUInt64) 1
      lost.modify fun m => (write m (source+i.toUInt64) 1 value).toOption.get!
  let _ ← ok lost (Ink.emptyPage ink 1)
  let _ ← ok lost (Lemma.Courses.SchoolSubmission.start header workspace ink)
  for _ in [:400] do
    if (← word lost Lemma.Courses.SchoolSubmission.arena) != 30 then let _ ← run lost Lemma.Courses.SchoolSubmission.pump; pure ()
  if (← word lost Lemma.Courses.SchoolSubmission.arena) != 30 || !(← lost.get).records.isEmpty || (← lost.get).commits != 1 then
    throw <| IO.userError "uncertain queue Commit retried or emitted an acknowledgement"
  IO.println s!"SCHOOL_SUBMISSION_ACTIONS:PASS exact{expected.size}-byte frozen/rawstream,16-byte boundaries,Busy/wouldBlock,retry,coldpendingrestore,boundACKdurablepointer,suspend/Abort/resume,partialstreamcancel,ninthchunkreject,allocationrollback,lostCommitnooutput; component only"
end SubmissionTests

def main : IO Unit := SubmissionTests.check
