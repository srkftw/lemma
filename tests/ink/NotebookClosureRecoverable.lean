import Lemma.Applications.Notebook
import Std.Data.HashMap

/-! Actual Recovery3 Actions against explicit independently framed model outcomes.
This host fixture does not establish peer durability or selected RV64 execution.
It rejects all writes to the immutable retained source and undeclared syscalls. -/
namespace NotebookClosureRecoverableTests
open Lemma.Core0.Memory Lemma.User Lemma.Services.Store
open Lemma.Applications.Notebook

structure Model where
  allowMathSetup : Bool := false
  words : Std.HashMap UInt64 UInt64 := {}
  operations : Array UInt64 := #[]
  console : Array String := #[]
  pending : Bool := false
  replyMode : UInt64 := 3
  mountedSequence : UInt64 := 11
  epoch : UInt64 := 1
  detail : UInt64 := 2
  queryBytes : UInt64 := 344
  queryMismatch : Bool := false
  heldSource : UInt64 := ink0
  heldObject : UInt64 := 65548
  heldBytes : UInt64 := 344
  allowSaved : Bool := false
  puts : Array (UInt64 × UInt64 × UInt64) := #[]
  currentOffset : UInt64 := 0
  currentCount : UInt64 := 0
  currentRequest : UInt64 := 0
  readSequence : UInt64 := 0
  mismatchAt : UInt64 := 19
  readFault : UInt64 := 0
  replyStatus : UInt64 := 0
  corruptOffset : UInt64 := 0xffff
  corruptValue : UInt64 := 0
  wouldBlock : Bool := false
  inputEvents : Array (Array (UInt64 × UInt64)) := #[]
  inputReads : Nat := 0
  inputCursor : Nat := 0

private def read (m : Model) (a : UInt64) : UInt64 :=
  m.words.getD a (if 0x110000 ≤ a && a < 0x124000 then 0xffffffffffffffff else 0)
private def write (m : Model) (a v : UInt64) : Model := {m with words := m.words.insert a v}
private def byte (m : Model) (a : UInt64) : UInt8 :=
  ((read m (a-a%8) >>> (a%8*8)) &&& 255).toUInt8
private def writeByte (m : Model) (a v : UInt64) : Model :=
  let shift := a%8*8
  write m (a-a%8) ((read m (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))
private def ownedWrite (a : UInt64) : Bool :=
  (0x20200 ≤ a && a < 0x20d00) || (0x110000 ≤ a && a < 0x124000) ||
  (0x308000 ≤ a && a < 0x329000)

private def syscall (state : IO.Ref Model) (number a b c d e : UInt64) : IO (UInt8 × UInt64) := do
  let m ← state.get
  if number = CapabilityABI.console then
    if a != 4 || b != 0 || c != Console.packetAddress || d != 88 || e != 0 then
      throw <| IO.userError "recoverable changed Console ownership/framing"
    let blob := ByteArray.mk ((List.range 88).toArray.map fun i => byte m (c+i.toUInt64))
    state.set {m with console := m.console.push (String.fromUTF8! blob)}
    return (0,88)
  else if number = IPCABI.callBegin then
    let op := read m (b+16)
    if m.pending || a != 3 || b != outgoing || c != 64 || e != 300000000 || d != 501+m.operations.size.toUInt64 then
      throw <| IO.userError "changed single pending/request/deadline/endpoint"
    if read m b != Protocol.magic || read m (b+24) != 1 then throw <| IO.userError "wrong control/header namespace"
    if op = 14 || op = 15 then
      if read m (b+8) != 3 || read m (b+32) != 0 || read m (b+40) != 500 ||
          read m (b+48) != 0 || read m (b+56) != 0 then throw <| IO.userError "changed failure ticket/control shape"
    else if op = 5 then
      if read m (b+8) != 1 || read m (b+32) != m.heldObject || read m (b+40) != 0 ||
          read m (b+56) > 128 then throw <| IO.userError "reconciliation READ changed object/shape"
    else if op = 2 then
      let resumed := m.mountedSequence = 12 && m.heldObject = 65548
      let object := if resumed then 257 else m.heldObject
      let bytes := if resumed then 152 else m.heldBytes
      if read m (b+8) != 1 || read m (b+32) != object || read m (b+40) != m.mountedSequence+1 ||
          read m (b+48) != 0 || read m (b+56) != bytes then throw <| IO.userError "resubmission changed exact retained or next-stage metadata"
      if m.mountedSequence = 12 && read m (b+32) = m.heldObject then
        throw <| IO.userError "lost-ACK reconciliation duplicated the already committed original PUT"
    else throw <| IO.userError "undeclared/mutating reconciliation operation"
    state.set { m with
      pending := true
      operations := m.operations.push op
      currentOffset := read m (b+48)
      currentCount := read m (b+56)
      currentRequest := d
      puts := if op = 2 then m.puts.push (read m (b+32),read m (b+40),read m (b+56)) else m.puts }
    return (0,42)
  else if number = 67 then
    if !m.pending || a != 42 || b != incoming || c != 256 || d != 0 || e != 0 then
      throw <| IO.userError "wrong pending poll"
    if m.wouldBlock then return (IPCABI.wouldBlock,0)
    let op := m.operations.back!
    if op = 2 then throw <| IO.userError "fixture must not manufacture a mutation receipt"
    let control := op = 14 || op = 15
    let count := if control then 8 else if m.currentOffset < m.queryBytes then min m.currentCount (m.queryBytes-m.currentOffset) else 0
    let mut after := m
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,m.currentRequest),
        (32,0),(40,64+count),(48,m.replyStatus),(56,0),(64,Protocol.magic),
        (72,if control then 3 else 1),(80,op),(88,1),(96,if control then 0 else m.heldObject),
        (104,if control || m.readSequence = 0 then m.mountedSequence else m.readSequence),(112,if control then m.detail else 1),(120,count)] do
      after := write after (b+offset) (if offset = m.corruptOffset then m.corruptValue else value)
    if control then after := write after (b+128) (if m.corruptOffset = 128 then m.corruptValue else m.epoch)
    else
      for i in [:count.toNat] do
        let expected := (byte m (m.heldSource+m.currentOffset+i.toUInt64)).toUInt64
        let value := if m.queryMismatch && m.currentOffset+i.toUInt64 = m.mismatchAt then expected ^^^ 1 else expected
        after := writeByte after (b+128+i.toUInt64) value
    state.set {after with pending := false}
    return (0,128+count)
  else throw <| IO.userError s!"undeclared recoverable syscall{number}"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s value => pure (s,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "retry exceeded its bounded Action fold"
      let mut result := ((0 : UInt8),initial)
      for i in [:count.toNat] do
        if result.1 = 0 then result ← run state (step i.toUInt32 count result.2 a b c d)
      run state (next result.1 result.2)
  | .platform operation a b c d e f next => do
      match operation with
      | .virtualRead64 =>
          let m ← state.get
          if m.readFault != 0 && a = m.readFault then run state (next 1 0) else run state (next 0 (read m a))
      | .virtualRead8 => run state (next 0 (byte (← state.get) a).toUInt64)
      | .virtualWrite64 =>
          if !ownedWrite a && !((← state.get).allowMathSetup && mathematicsSave ≤ a && a < mathematicsSave+4096) then throw <| IO.userError s!"retry wrote pinned or unowned address {a}"
          state.modify fun m => write m a b
          run state (next 0 0)
      | .virtualWrite8 =>
          if !ownedWrite a && !((← state.get).allowMathSetup && mathematicsSave ≤ a && a < mathematicsSave+4096) then throw <| IO.userError s!"retry wrote pinned or unowned byte {a}"
          state.modify fun m => writeByte m a b
          run state (next 0 0)
      | .syscall =>
          let result ← syscall state a b c d e f
          run state (next result.1 result.2)
      | _ => throw <| IO.userError "retry acquired an undeclared platform primitive"
  | _ => throw <| IO.userError "retry acquired an unbounded or undeclared Action"

private def initial : Model := Id.run do
  let mut m : Model := {}
  for (slot,value) in #[(0,1),(8,2),(16,3),(24,4),(32,512),(40,320),
      (48,65535),(56,65535),(64,4095),(72,1),(80,1),(88,2),(96,14),
      (112,0),(120,ink1),(128,11),(136,2),(144,ink0),(160,0),(176,500),
      (200,0),(208,ink0),(216,344),(224,65548),(272,256),(336,65535),
      (344,65535),(424,227),(536,0),(592,1),(600,ink0),(608,344),
      (616,65548),(624,0),(632,11),(640,0),(648,1),(672,11),(680,500),(688,0)] do
    m := write m ((0x20800 : UInt64)+slot) value
  for i in [:43] do m := write m (ink0+i.toUInt64*8) (0xfedcba9876540000+i.toUInt64)
  for (offset,value) in #[(0,Lemma.Documents.Ink.magic),(8,Lemma.Documents.Ink.version),(16,2),(24,1)] do
    m := write m (pageIndex+offset) value
  return m

private def invariant (m : Model) : IO Unit := do
  for i in [:43] do
    if read m (ink0+i.toUInt64*8) != 0xfedcba9876540000+i.toUInt64 then
      throw <| IO.userError "failed source changed before full publication acknowledgment"
  for line in m.console do
    if line.startsWith "K1 0000000000000421" && !m.allowSaved then throw <| IO.userError "Inspect or failure fabricated Saved"

private def advance (model : Model) : IO Model := do
  let cell ← IO.mkRef model
  if (← run cell (closureRecoverableToolbar 7)).1 != 0 then throw <| IO.userError "explicit recovery did not start"
  for _ in [:12] do
    if read (← cell.get) (state+160) != 1 && read (← cell.get) (state+136) != 2 then
      if (← run cell closureRecoverablePumpSave).1 != 0 then throw <| IO.userError "recovery pump failed fixture Action"
  invariant (← cell.get)
  return ← cell.get

def checkRawCompatibility : IO Unit := do
  let exact ← advance initial
  if exact.operations != #[14,2] || read exact (state+136) != 1 || read exact (state+160) != 1 ||
      read exact (state+208) != ink0 || read exact (state+216) != 344 then
    throw <| IO.userError "checked mount at exact ACK did not start exact new Pending"
  let persisted ← advance {initial with mountedSequence := 12}
  if persisted.operations != #[14,5,5,5,5,2] || read persisted (state+704) != 344 ||
      read persisted (state+128) != 12 || read persisted (state+384) != 13 ||
      persisted.puts != #[(257,13,152)] || read persisted (pageIndex+32) != 1 then
    throw <| IO.userError "lost ACK did not compare whole payload+EOF and resume next page stage without duplicate original PUT"
  let rootHeld := Id.run do
    let mut m := { initial with
      mountedSequence := 12
      heldSource := rootBuffer
      heldObject := 1
      heldBytes := 64
      queryBytes := 64
      allowSaved := true }
    for (slot,value) in #[(208,rootBuffer),(216,64),(224,1),(200,2),(600,rootBuffer),(608,64),(616,1),(624,2)] do
      m := write m (state+slot) value
    for (offset,value) in #[(0,Lemma.Documents.Ink.magic),(8,Lemma.Documents.Ink.version),(16,1),(24,1),(32,2),(40,512)] do
      m := write m (rootBuffer+offset) value
    return m
  let rootDone ← advance rootHeld
  if rootDone.operations != #[14,5,5] || !rootDone.puts.isEmpty || read rootDone (state+128) != 12 ||
      read rootDone (state+672) != 12 || read rootDone (state+648) != 0 ||
      read rootDone (state+136) != 0 || !rootDone.console.any (·.startsWith "K1 0000000000000421") then
    throw <| IO.userError "barrier-backed exact root recovery did not finish original publication once"
  let rootNoBarrier ← advance {rootHeld with replyStatus := 227,allowSaved := false}
  if !rootNoBarrier.puts.isEmpty || read rootNoBarrier (state+136) != 2 then
    throw <| IO.userError "failed remount durability barrier permitted root Saved"
  let waiting ← IO.mkRef {initial with detail := 1}
  let _ ← run waiting (closureRecoverableToolbar 7)
  let _ ← run waiting closureRecoverablePumpSave
  if (← waiting.get).operations != #[14,15] || read (← waiting.get) (state+136) != 1 then
    throw <| IO.userError "Pending remount became a mutation or success"
  waiting.modify fun m => {m with detail := 2}
  let _ ← run waiting closureRecoverablePumpSave
  if (← waiting.get).operations != #[14,15,2] then throw <| IO.userError "complete status could not start exact retry"
  invariant (← waiting.get)
  let pending ← IO.mkRef {initial with wouldBlock := true}
  let _ ← run pending (closureRecoverableToolbar 7)
  let old ← pending.get
  let _ ← run pending closureRecoverablePumpSave
  if (← pending.get).operations != old.operations || !(← pending.get).pending then
    throw <| IO.userError "wouldBlock retried or consumed a live control call"
  for m in #[{initial with mountedSequence := 10},{initial with mountedSequence := 13},
      {initial with epoch := 0},{initial with epoch := 1,words := initial.words.insert (state+688) 1},
      {initial with words := initial.words.insert (state+672) 12},
      {initial with mountedSequence := 12,queryMismatch := true},
      {initial with mountedSequence := 12,queryMismatch := true,mismatchAt := 343},
      {initial with mountedSequence := 12,readSequence := 11},
      {initial with mountedSequence := 12,readSequence := 13},
      {initial with mountedSequence := 12,readFault := ink0+336},
      {initial with mountedSequence := 12,queryBytes := 352},
      {initial with mountedSequence := 12,queryBytes := 336},
      {initial with replyStatus := 227},
      {initial with corruptOffset := 24,corruptValue := 500},
      {initial with corruptOffset := 72,corruptValue := 1},
      {initial with corruptOffset := 112,corruptValue := 0},
      {initial with corruptOffset := 120,corruptValue := 0}] do
    let after ← advance m
    if after.operations.contains 2 || read after (state+136) != 2 then
      throw <| IO.userError "regressed/foreign/short/long/different/ambiguous outcome permitted a mutation"
  for (slot,value) in #[(640,3),(600,ink0+8),(608,27784),(616,0),(624,3),
      (648,0),(160,1),(536,1),(104,13),(680,0)] do
    let cell ← IO.mkRef (write initial (state+slot) value)
    let _ ← run cell (closureRecoverableToolbar 7)
    if !(← cell.get).operations.isEmpty then throw <| IO.userError "invalid/busy/limit state acquired recovery call"
  IO.println "NOTEBOOK_RECOVERABLE_ACTION:PASS exact prior ACK permits new Pending; full byte-equal+EOF/barrier known+1 resumes original record once (no duplicate PUT); root completion only after complete durability evidence; regressed/higher/stale/foreign/partial/different/long payload and limits reject; retained source immutable; no connected RV64/peer Saved claim"

private def mathInitial : IO Model := do
  let mut m := { initial with
    heldSource := mathematicsSave, heldObject := 0x8001,
    heldBytes := 2496, queryBytes := 2496, allowSaved := true, allowMathSetup := true }
  for (slot,value) in #[(144,0),(200,3),(208,mathematicsSave),(216,2496),(224,0x8001),
      (576,7),(592,3),(600,mathematicsSave),(608,2496),(616,0x8001),(624,3)] do
    m := write m (state+slot) value
  let cell ← IO.mkRef m
  if (← run cell (Lemma.Documents.MathematicsClosure.create mathematicsSave 1 1)).1 != 0 then
    throw <| IO.userError "actual Doc8 creation failed posed Action model"
  if (← run cell (Lemma.Documents.Mathematics.put mathematicsSave 56 5)).1 != 0 then throw <| IO.userError "posed exact numerator write failed"
  if (← run cell (Lemma.Documents.Mathematics.put mathematicsSave 64 6)).1 != 0 then throw <| IO.userError "posed exact denominator write failed"
  if (← run cell (Lemma.Documents.MathematicsClosure.completeExecution mathematicsSave 1 1 1 77 8)).1 != 0 then
    throw <| IO.userError "actual Doc8 posed execution identity/history creation failed"
  return { (← cell.get) with allowMathSetup := false }

private def mathInvariant (before after : Model) : IO Unit := do
  for i in [:312] do
    if read before (mathematicsSave+i.toUInt64*8) != read after (mathematicsSave+i.toUInt64*8) then
      throw <| IO.userError "stage3 retained source/execution/semantic history mutated"

private def advanceMath (model : Model) : IO Model := do
  let cell ← IO.mkRef model
  if (← run cell (closureRecoverableToolbar 7)).1 != 0 then
    throw <| IO.userError "stage3 explicit Action retry failed unexpectedly"
  for _ in [:26] do
    if read (← cell.get) (state+160) != 1 && read (← cell.get) (state+136) != 2 then
      if (← run cell closureRecoverablePumpSave).1 != 0 then
        throw <| IO.userError "stage3 Action pump failed unexpectedly"
  let after ← cell.get
  mathInvariant model after
  return after

private def mustFailMath (model : Model) : IO Unit := do
  let after ← advanceMath model
  if !after.puts.isEmpty || read after (state+136) != 2 ||
      after.console.any (·.startsWith "K1 0000000000000421") then
    throw <| IO.userError "invalid/ambiguous stage3 result published Saved or new PUT"

def checkMath : IO Unit := do
  let initialMath ← mathInitial
  let exact ← advanceMath initialMath
  if exact.operations != #[14,2] || exact.puts != #[(0x8001,12,2496)] ||
      read exact (state+136) != 1 || read exact (state+648) != 1 then
    throw <| IO.userError "genuine old sequence did not retain exact full Doc8 Pending"
  let persisted ← advanceMath {initialMath with mountedSequence := 12}
  if persisted.operations != #[14] ++ Array.replicate 21 5 || !persisted.puts.isEmpty ||
      read persisted (state+128) != 12 || read persisted (state+672) != 12 ||
      read persisted (state+648) != 0 || read persisted (state+640) != 0 ||
      read persisted (state+136) != 0 || read persisted (state+704) != 2496 ||
      !persisted.console.any (·.startsWith "K1 0000000000000421 000000000000000c 0000000000000001 0000000000000001 0000000000008001") then
    throw <| IO.userError "barrier-backed known+1 Doc8 failed exact original stage3 once/no duplicate PUT"
  for i in [:312] do
    mustFailMath {initialMath with
      mountedSequence := 12, queryMismatch := true,
      mismatchAt := i.toUInt64*8}
  for i in [:312] do
    mustFailMath {initialMath with
      mountedSequence := 12, readFault := mathematicsSave+i.toUInt64*8}
  let cases := #[{initialMath with mountedSequence := 10},
    {initialMath with mountedSequence := 13}, {initialMath with epoch := 0},
    {initialMath with words := initialMath.words.insert (state+688) 1},
    {initialMath with mountedSequence := 12, queryBytes := 2488},
    {initialMath with mountedSequence := 12, queryBytes := 2504},
    {initialMath with mountedSequence := 12, readSequence := 11},
    {initialMath with mountedSequence := 12, readSequence := 13},
    {initialMath with replyStatus := 227},
    {initialMath with words := initialMath.words.insert (mathematicsSave+8) 7},
    {initialMath with words := initialMath.words.insert (mathematicsSave+56) 0},
    {initialMath with words := initialMath.words.insert (mathematicsSave+24) 2},
    {initialMath with words := initialMath.words.insert (mathematicsSave+32) 2},
    {initialMath with words := initialMath.words.insert (state+616) 0x8002},
    {initialMath with words := initialMath.words.insert (state+608) 2488},
    {initialMath with words := initialMath.words.insert (state+600) (mathematicsSave+8)},
    {initialMath with words := initialMath.words.insert (state+536) 1}]
  for model in cases do mustFailMath model
  IO.println s!"CLOSURE_RECOVERY_ACTION:PASS two exact old/known+1 positives; all312 full-word mismatches+312 readfault prefixes+{cases.size} semantic/epoch/length/barrier negatives; immutable2496B semantic/execution history; no duplicate PUT or math RPC; no connected/LLVM/CPU durability claim"
end NotebookClosureRecoverableTests
def main : IO Unit := do
  NotebookClosureRecoverableTests.checkRawCompatibility
  NotebookClosureRecoverableTests.checkMath
