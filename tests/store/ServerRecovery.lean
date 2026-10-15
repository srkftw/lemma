import Lemma.Services.Store.ServerRecovery
import Lemma.Services.Store.ServerRecoveryAwait
import Lemma.Services.Store.RecoveryClient
import Std.Data.HashMap

namespace ServerRecoveryTests
open Lemma.Core0.Memory Lemma.Services.Store Lemma.User
structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  mediumBytes : ByteArray := ByteArray.empty
  pendingSector : Option UInt64 := none
  driverPending : Bool := true
  driverFailure : Bool := false
  readFailure : Bool := false
  barrierPending : Bool := false
  barrierFailure : Bool := false
  barrierWouldBlock : Bool := false
  barriers : Nat := 0
  calls : Array UInt64 := #[]
  reads : Array UInt64 := #[]
  replies : Array (UInt64 × Array UInt64) := #[]
  clientReply : Array UInt64 := #[]
  writeFault : UInt64 := 0
  writes : Array UInt64 := #[]
private def require (ok : Bool) (message : String) : IO Unit :=
  unless ok do throw <| IO.userError message
private def read (m : Model) (a : UInt64) : UInt64 := m.words.getD a 0
private def write (m : Model) (a v : UInt64) : Model := {m with words := m.words.insert a v}
private def memoryByte (m : Model) (a : UInt64) : UInt64 :=
  (read m (a-a%8) >>> (a%8*8)) &&& 255
private def writeByte (m : Model) (a v : UInt64) : Model :=
  let shift := a%8*8
  write m (a-a%8) ((read m (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))
private def syscall (cell : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let m ← cell.get
  if number = 66 then
    require (a = 1 && e = 0) "changed sole block grant/reserved boundary"
    cell.set {m with calls := m.calls.push b}
    if b = 7 then
      require (c = 0 && d = 0) "epoch read changed arguments"
      return (0,0)
    if b = 5 then
      require (c = 91 && d = 1) "recovery begin changed ticket/epoch"
      return (168,1)
    if b = 6 then
      require (c = 91 && d = 1) "receipt poll changed ticket/epoch"
      if m.driverFailure then return (167,0)
      return if m.driverPending then (168,0) else (0,1)
    if b = 1 then
      require (m.pendingSector.isNone && d = Remount.shadowBuffer && c < 524288)
        "shadow READ ownership or sector bound changed"
      cell.modify fun m => {m with pendingSector := some c, reads := m.reads.push c}
      return (168,0)
    if b = 3 then
      require (c ||| d = 0 && !m.barrierPending && m.pendingSector.isNone && m.reads.size = 36 &&
        read m (Server.state+192) = 3 && read m (Server.state+24) = 3 && read m (Server.state+256) = 1)
        "barrier preceded complete valid shadow scan or changed ownership"
      cell.modify fun m => {m with barrierPending := true, barriers := m.barriers+1}
      return (168,0)
    if b = 4 then
      if m.barrierPending then
        require (c = 0 && d = Remount.shadowBuffer) "barrier completion changed owned buffer"
        if m.barrierWouldBlock then return (168,0)
        cell.modify fun m => {m with barrierPending := false}
        return if m.barrierFailure then (167,0) else (0,3)
      let some sector := m.pendingSector | throw <| IO.userError "completion without actual READ"
      require (c = 0 && d = Remount.shadowBuffer) "shadow completion changed buffer"
      if m.readFailure then
        cell.modify fun m => {m with pendingSector := none}
        return (167,0)
      let mut after ← cell.get
      for word in [:64] do
        let offset := sector.toNat*512+word*8
        let value := (List.range 8).foldl (fun v i => v ||| (m.mediumBytes[offset+i]!.toUInt64 <<< (i.toUInt64*8))) 0
        after := write after (Remount.shadowBuffer+word.toUInt64*8) value
      cell.set {after with pendingSector := none}
      return (0,1)
    throw <| IO.userError "recovery attempted WRITE/format or unknown block operation"
  if number = IPCABI.reply then
    require (a = 77 && b = Server.outgoing && (c = 64 || c = 72) && e = 0) "reply identity/framing changed"
    let fields := (Array.range (c/8).toNat).map fun i => read m (b+i.toUInt64*8)
    cell.modify fun m => {m with replies := m.replies.push (d,fields)}
    return (0,0)
  if number = IPCABI.receive then
    require (a = 2 && b = Server.incoming && c = 256) "receive endpoint/owned buffer changed"
    return (IPCABI.wouldBlock,0)
  if number = ABI.sleep then
    require (a = 10000 && b ||| c ||| d ||| e = 0) "unbounded recovery wait"
    return (0,0)
  if number = ABI.time then return (0,1)
  if number = 67 then
    require (a = 42 && b = 0x30000 && c = 256 && d ||| e = 0 && m.clientReply.size = 17)
      "client changed pending/owned reply boundary"
    let mut after := m
    for i in [:17] do after := write after (b+i.toUInt64*8) m.clientReply[i]!
    cell.set after
    return (0,136)
  throw <| IO.userError s!"undeclared recovery syscall{number}"
partial def run (cell : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
      let (s,v) ← run cell first
      run cell (next s v)
  | .boundedFoldU64 bound step count initial a b c d next => do
      require (count.toNat ≤ bound) "static Action fold exceeded"
      let mut result := (0,initial)
      for i in [:count.toNat] do
        if result.1 = 0 then result ← run cell (step i.toUInt32 count result.2 a b c d)
      run cell (next result.1 result.2)
  | .platform op a b c d e f next => do
      let m ← cell.get
      if op = .virtualRead64 then run cell (next 0 (read m a)) else
      if op = .virtualRead8 then run cell (next 0 (memoryByte m a)) else
      if op = .virtualWrite64 then
        if m.writeFault != 0 && a = m.writeFault then run cell (next 1 0) else
        if a ≥ Remount.current && a < Remount.current+4096 && read m (Server.state+192) = 3 then
          require (read m (Server.state+24) = 3 && read m (Server.state+256) = 1)
            "shadow copy exposed writable mode or complete receipt before full adoption"
        cell.set {write m a b with writes := m.writes.push a}
        run cell (next 0 0)
      else if op = .virtualWrite8 then
        cell.set (writeByte m a b)
        run cell (next 0 0)
      else if op = .syscall then
        let (s,v) ← syscall cell a b c d e f
        run cell (next s v)
      else throw <| IO.userError "recovery acquired undeclared platform/MMIO/host effect"
  | _ => throw <| IO.userError "recovery acquired unbounded Action"

private def initial (mediumBytes : ByteArray) : Model := Id.run do
  let mut m : Model := {mediumBytes := mediumBytes}
  for (o,v) in #[(0,1),(8,2),(24,3)] do m := write m (Server.state+o) v
  for (o,v) in #[(0,0),(24,Server.buffer),(32,227),(40,11),(48,524288),(104,Server.index0),(336,1)] do
    m := write m (Server.context+o) v
  for i in [:6144] do m := write m (Server.index0+i.toUInt64*8) (0xabbccdd000000000+i.toUInt64)
  return m
private def unchanged (before after : Model) : IO Unit := do
  for (base,count) in #[(Server.context,512),(Server.index0,6144)] do
    for i in [:count] do
      require (read before (base+i.toUInt64*8) == read after (base+i.toUInt64*8))
        "failed/pending shadow mount changed live context/index"
private def application (cell : IO.Ref Model) (version op ns object ticket offset count : UInt64) : IO Unit := do
  cell.modify fun m => Id.run do
    let mut m := m
    for (o,v) in #[(0,Protocol.magic),(8,version),(16,op),(24,ns),(32,object),(40,ticket),(48,offset),(56,count)] do
      m := write m (Server.incoming+64+o) v
    return m
  require ((← run cell (ServerRecovery.application 65538 77 64)).1 = 0) "recovery application did not finish its reply"

/-- Exercise the actual mounted operation through the joined dispatcher. A
pending/shadow context must not become Ready merely because a peer attached.
The same request becomes usable only after the existing real barrier/adoption.
-/
private def checkMountPublication (cell : IO.Ref Model) (writable : Bool) : IO Unit := do
  let before ← cell.get
  cell.modify fun m => Id.run do
    let mut m := m
    for (o,v) in #[(0,Protocol.magic),(8,Lemma.Courses.PackageAwaitProtocol.version),
        (16,Lemma.Courses.PackageAwaitProtocol.operation),(24,1),(32,0),(40,0),(48,0),(56,0)] do
      m := write m (Server.incoming+64+o) v
    return m
  require ((← run cell (ServerRecoveryAwait.applicationAwait 65538 77 64)).1 = 0)
    "joined mounted/recovery dispatch failed"
  let after ← cell.get
  let (status,fields) := after.replies.back!
  require (fields.size = 8 && fields[0]! = Protocol.magic &&
    fields[1]! = Lemma.Courses.PackageAwaitProtocol.version && fields[2]! = 16 &&
    fields[3]! = 1 && fields[4]! = 0)
    "joined mounted response changed framing or namespace"
  require (Lemma.Courses.PackageAwaitProtocol.resultValid status fields[6]! fields[5]! fields[7]! = 1)
    "joined mounted response is not independently admissible"
  if writable then
    require (status = 0 && fields[6]! = 1 && fields[5]! = 11 && fields[7]! > 0)
      "validated barrier-backed mount not published"
  else
    require (status = Format.readOnly.toUInt64 && fields[6]! = 3)
      "unresolved/shadow recovery manufactured usable mounted success"
  require (after.calls = before.calls && after.reads = before.reads && after.barriers = before.barriers)
    "mount observation performed backing I/O"
  unchanged before after

def check (mediumBytes : ByteArray) (joined : Bool) : IO Unit := do
  let service := if joined then ServerRecoveryAwait.stepAwait else ServerRecovery.step
  require (mediumBytes.size = 268435456) "retained full opaque medium required"
  let before := initial mediumBytes
  for (o,v) in #[(24,1),(32,1),(40,77),(48,65538),(128,1)] do
    let original := write before (Server.state+o) v
    let rejected ← IO.mkRef original
    application rejected 3 14 1 0 91 0 0
    require ((← rejected.get).calls.isEmpty) "busy/writable/staging/checkpoint guard contacted raw transport"
    unchanged original (← rejected.get)
  for (version,ns,object,ticket,offset,count) in #[(1,1,0,91,0,0),(3,2,0,91,0,0),
      (3,1,1,91,0,0),(3,1,0,0,0,0),(3,1,0,91,1,0),(3,1,0,91,0,1)] do
    let rejected ← IO.mkRef before
    application rejected version 14 ns object ticket offset count
    require ((← rejected.get).calls.isEmpty && (← rejected.get).replies.back!.1 = 234)
      "wrong control frame acquired recovery authority"
  let cell ← IO.mkRef before
  application cell 3 14 1 0 91 0 0
  require ((← cell.get).calls = #[7,5] && (← cell.get).replies.back! =
    (0,#[Protocol.magic,3,14,1,0,11,1,8,1])) "Pending receipt or raw request identity differs"
  unchanged before (← cell.get)
  require ((← run cell service).1 = 0 && read (← cell.get) (Server.state+24) = 3)
    "unresolved raw receipt made Store writable"
  if joined then checkMountPublication cell false
  let pending ← cell.get
  let foreign ← IO.mkRef pending
  require ((← run foreign (ServerRecovery.status 65539 77 15 1 91)).1 = 0)
    "foreign status reply failed"
  require ((← foreign.get).replies.back!.1 = 232 && (← foreign.get).calls = pending.calls)
    "foreign full sender consumed or advanced recovery"
  let failed ← IO.mkRef {pending with driverFailure := true}
  require ((← run failed service).1 = 0 && read (← failed.get) (Server.state+24) = 3 &&
    read (← failed.get) (Server.state+256) = 3) "failed raw reconciliation made Store writable"
  unchanged before (← failed.get)
  cell.modify fun m => {m with driverPending := false}
  require ((← run cell service).1 = 0) "actual reconciled epoch did not start shadow scan"
  unchanged before (← cell.get)
  let started ← cell.get
  let readFailed ← IO.mkRef {started with readFailure := true}
  require ((← run readFailed service).1 = 0 && (← run readFailed service).1 = 0)
    "failed shadow READ did not remain a bounded service result"
  require (read (← readFailed.get) (Server.state+24) = 3 && read (← readFailed.get) (Server.state+256) = 3)
    "failed shadow READ published writable mode"
  unchanged before (← readFailed.get)
  let mut finalPending : Option Model := none
  let mut barrierCut : Option Model := none
  let mut complete := false
  for _ in [:200] do
    if !complete then
      let observed ← cell.get
      if observed.reads.size = 36 && observed.pendingSector.isSome then finalPending := some observed
      if observed.barrierPending then barrierCut := some observed
      require ((← run cell service).1 = 0) "actual shadow READ/Engine scan failed"
      if read (← cell.get) (Server.state+256) = 2 then complete := true else unchanged before (← cell.get)
  require complete "shadow scan exceeded200-step fixture resource bound"
  let some lastCut := finalPending | throw <| IO.userError "actual final shadow READ cut was not observed"
  let finalFailure ← IO.mkRef {lastCut with readFailure := true}
  require ((← run finalFailure service).1 = 0)
    "completed final failed READ did not retain a bounded failed result"
  require (read (← finalFailure.get) (Server.state+24) = 3 &&
    read (← finalFailure.get) (Server.state+256) = 3)
    "failed final READ reached writable/complete publication"
  unchanged before (← finalFailure.get)
  let some barrierBoundary := barrierCut | throw <| IO.userError "actual pending barrier cut was not observed"
  let barrierFailure ← IO.mkRef {barrierBoundary with barrierFailure := true}
  require ((← run barrierFailure service).1 = 0 &&
    read (← barrierFailure.get) (Server.state+24) = 3 && read (← barrierFailure.get) (Server.state+256) = 3)
    "failed durability barrier published writable/complete"
  unchanged before (← barrierFailure.get)
  let barrierWaiting ← IO.mkRef {barrierBoundary with barrierWouldBlock := true}
  require ((← run barrierWaiting service).1 = 0 &&
    read (← barrierWaiting.get) (Server.state+24) = 3 && read (← barrierWaiting.get) (Server.state+256) = 1)
    "pending durability barrier published writable/complete"
  unchanged before (← barrierWaiting.get)
  for fault in #[Remount.current,Remount.current+208,Remount.current+336,Remount.current+4088] do
    let broken ← IO.mkRef {barrierBoundary with writeFault := fault}
    require ((← run broken service).1 != 0)
      "partial shadow adoption fault fell through to normal service/settle"
    require (read (← broken.get) (Server.state+24) = 3 &&
      read (← broken.get) (Server.state+256) = 1)
      "partial shadow adoption fault published ready/complete"
  if joined then checkMountPublication cell true
  let mounted ← cell.get
  require (mounted.barriers = 1 && mounted.reads.size = 36 && read mounted (Server.state+24) = 1 && read mounted (Server.context+336) = 0 &&
    read mounted (Server.context+40) = 11 && read mounted (Server.context+104) = Server.index1)
    "actual validated mount did not publish exact observed context"
  application cell 3 15 1 0 91 0 0
  require ((← cell.get).replies.back! = (0,#[Protocol.magic,3,15,1,0,11,2,8,1]))
    "mount completion receipt was not exact observed epoch/sequence"
  let response := #[IPCABI.messageMagic,3,65539,1001,0,72,0,0,Protocol.magic,3,15,1,0,11,2,8,1]
  let client ← IO.mkRef {clientReply := response : Model}
  require ((← run client (RecoveryClient.pollCall 42 0x30000 15 1 1001)) = (0,11)) "valid control reply rejected"
  for (index,value) in #[(0,0),(1,2),(2,0),(3,1002),(4,77),(5,64),(6,1),(7,1),
      (8,0),(9,1),(10,14),(11,2),(12,1),(13,0xffffffffffffffff),(14,0),(15,0),(16,0)] do
    let rejected ← IO.mkRef {clientReply := response.set! index value : Model}
    require ((← run rejected (RecoveryClient.pollCall 42 0x30000 15 1 1001)).1 = IPCABI.invalidPacket)
      "bad stamped/control/epoch reply admitted"
  IO.println "STORE_RECOVERY_ACTION:PASS real shadow Engine36 READs + one real-request barrier after exact receipt epoch; pending/foreign/failed/final-read-error guards keep readonly context/index; pending/failed barrier readonly; four partial-copy faults stay fatal/mode3;17 client frame mutants reject; no WRITE/format/Saved/CPU claim; block receipts are posed Action boundary outcomes"
end ServerRecoveryTests
def main (args : List String) : IO Unit := do
  let [path] := args | throw <| IO.userError "one opaque retained medium required"
  let medium ← IO.FS.readBinFile path
  ServerRecoveryTests.check medium false
  ServerRecoveryTests.check medium true
  IO.println "MOUNT_RECOVERY_JOIN_ACTION:PASS original and joined real shadow/barrier paths; operation16 stays readonly while pending and publishes only actual validated mounted context; no backing operations from mount observation"
