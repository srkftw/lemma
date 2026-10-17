import Lemma.Applications.Notebook
import Std.Data.HashMap

/-! Execute actual successor Actions against independently framed IPC replies
and owned memory. The fixture rejects every undeclared syscall or write to the
pinned failed source. These observations are not an RV64/device recovery run. -/
namespace NotebookRetryTests
open Lemma.Core0.Memory Lemma.User Lemma.Services.Store
open Lemma.Applications.Notebook

structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  operations : Array UInt64 := #[]
  console : Array String := #[]
  pending : Bool := false
  replyMode : UInt64 := 3
  replySequence : UInt64 := 11
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
      throw <| IO.userError "retry changed Console ownership or record framing"
    let bytes := ByteArray.mk ((List.range 88).toArray.map fun i => byte m (c+i.toUInt64))
    state.set {m with console := m.console.push (String.fromUTF8! bytes)}
    return (0,88)
  else if number = IPCABI.callBegin then
    let op := read m (b+16)
    if m.pending || a != 3 || b != outgoing || c != 64 || e != 300000000 || d != 501+m.operations.size.toUInt64 then
      throw <| IO.userError "retry changed single pending call, deadline or request identity"
    if read m b != Protocol.magic || read m (b+8) != 1 || read m (b+24) != 1 ||
        read m (b+48) != 0 then throw <| IO.userError "retry changed ordinary exact Store framing"
    if op = 8 then
      if read m (b+32) != 0 || read m (b+40) != 0 || read m (b+56) != 0 then
        throw <| IO.userError "retry status query attempted an opaque mutation"
    else if op = 2 then
      if m.operations != #[8] || read m (b+32) != 65548 || read m (b+40) != 12 || read m (b+56) != 344 then
        throw <| IO.userError "retry did not resubmit only the exact retained record after coherent Inspect"
    else throw <| IO.userError "retry contacted an undeclared Store operation"
    state.set {m with pending := true, operations := m.operations.push op}
    return (0,42)
  else if number = 67 then
    if !m.pending || a != 42 || b != incoming || c != 256 || d != 0 || e != 0 || m.operations.back! != 8 then
      throw <| IO.userError "retry polled a different request or consumed another operation"
    if m.wouldBlock then return (IPCABI.wouldBlock,0)
    let mut after := m
    for (offset,value) in #[(0,IPCABI.messageMagic),(8,3),(16,7),(24,501),
        (32,0),(40,64),(48,m.replyStatus),(56,0),(64,Protocol.magic),(72,1),
        (80,8),(88,1),(96,0),(104,m.replySequence),(112,m.replyMode),(120,0)] do
      after := write after (b+offset) (if offset = m.corruptOffset then m.corruptValue else value)
    state.set {after with pending := false}
    return (0,128)
  else if number = 65 then
    if a != 2 || b != 1 || c != raw || d != 0 || e != 0 then
      throw <| IO.userError "retry drain changed the bounded nonblocking input boundary"
    if m.inputCursor = m.inputEvents.size then
      state.set {m with inputReads := m.inputReads+1}
      return (174,0)
    let mut after := m
    for (offset,value) in m.inputEvents[m.inputCursor]! do after := write after (raw+offset) value
    state.set {after with inputReads := m.inputReads+1, inputCursor := m.inputCursor+1}
    return (0,0)
  else throw <| IO.userError s!"retry issued undeclared syscall {number}"

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
      | .virtualRead64 => run state (next 0 (read (← state.get) a))
      | .virtualRead8 => run state (next 0 (byte (← state.get) a).toUInt64)
      | .virtualWrite64 =>
          if !ownedWrite a then throw <| IO.userError s!"retry wrote pinned or unowned address {a}"
          state.modify fun m => write m a b
          run state (next 0 0)
      | .virtualWrite8 =>
          if !ownedWrite a then throw <| IO.userError s!"retry wrote pinned or unowned byte {a}"
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
      (616,65548),(624,0),(632,11),(640,0),(648,1)] do
    m := write m ((0x20800 : UInt64)+slot) value
  for i in [:43] do m := write m (ink0+i.toUInt64*8) (0xfedcba9876540000+i.toUInt64)
  return m

private def invariant (m : Model) : IO Unit := do
  for i in [:43] do
    if read m (ink0+i.toUInt64*8) != 0xfedcba9876540000+i.toUInt64 then
      throw <| IO.userError "failed source changed before full publication acknowledgment"
  for line in m.console do
    if line.startsWith "K1 0000000000000421" then throw <| IO.userError "Inspect or failure fabricated Saved"

def check : IO Unit := do
  let readonly ← IO.mkRef initial
  if (← run readonly (retryToolbar 7)).1 != 0 then throw <| IO.userError "explicit retry did not issue read-only Inspect"
  if (← readonly.get).operations != #[8] || read (← readonly.get) ((0x20800 : UInt64)+640) != 1 then
    throw <| IO.userError "retry was automatic, uncounted or changed the query operation"
  if (← run readonly retryPumpSave).1 != 0 || read (← readonly.get) ((0x20800 : UInt64)+136) != 2 ||
      read (← readonly.get) ((0x20800 : UInt64)+424) != 234 || (← readonly.get).operations != #[8] then
    throw <| IO.userError "read-only Store became writable or Saved"
  invariant (← readonly.get)
  let writable ← IO.mkRef {initial with replyMode := 1}
  let _ ← run writable (retryToolbar 7)
  if (← run writable retryPumpSave).1 != 0 || (← writable.get).operations != #[8,2] ||
      read (← writable.get) ((0x20800 : UInt64)+208) != ink0 || read (← writable.get) ((0x20800 : UInt64)+216) != 344 ||
      read (← writable.get) ((0x20800 : UInt64)+224) != 65548 || read (← writable.get) ((0x20800 : UInt64)+160) != 1 then
    throw <| IO.userError "coherent status did not begin exact retained source/metadata as a new Pending operation"
  invariant (← writable.get)
  for model in #[{initial with replyMode := 0},{initial with replyMode := 2},
      {initial with replyMode := 4},{initial with replyMode := 1,replySequence := 10},
      {initial with replyMode := 1,replySequence := 12},{initial with replyStatus := 227},
      {initial with corruptOffset := 24,corruptValue := 500},
      {initial with corruptOffset := 88,corruptValue := 2},
      {initial with corruptOffset := 120,corruptValue := 1}] do
    let state ← IO.mkRef model
    let _ ← run state (retryToolbar 7)
    let _ ← run state retryPumpSave
    if (← state.get).operations != #[8] || read (← state.get) ((0x20800 : UInt64)+136) != 2 then
      throw <| IO.userError "uncertain/malformed/error status permitted another opaque operation"
    invariant (← state.get)
  let pending ← IO.mkRef {initial with wouldBlock := true}
  let _ ← run pending (retryToolbar 7)
  let before ← pending.get
  let _ ← run pending retryPumpSave
  if (← pending.get).words != before.words || (← pending.get).operations != #[8] || !(← pending.get).pending then
    throw <| IO.userError "wouldBlock altered a live reply or retried the call"
  for (slot,value) in #[(640,3),(600,ink0+8),(608,27784),(616,0),(624,3),
      (648,0),(160,1),(536,1),(104,13),(424,234)] do
    let state ← IO.mkRef (write initial ((0x20800 : UInt64)+slot) value)
    let _ ← run state (retryToolbar 7)
    if !(← state.get).operations.isEmpty then throw <| IO.userError "invalid or busy state contacted Store"
    invariant (← state.get)
  let ink ← IO.mkRef initial
  for (offset,value) in #[(0,2),(8,1002),(16,20000),(24,40000),(32,2047),(40,3),(48,1),(56,0),(64,1)] do
    ink.modify fun m => write m (raw+offset) value
  let _ ← run ink retryInputSample
  let drawn ← ink.get
  if read drawn ((0x20800 : UInt64)+104) != 14 || read drawn ((0x20800 : UInt64)+112) != 1 ||
      read drawn ((0x20800 : UInt64)+136) != 2 || !drawn.operations.isEmpty ||
      (byte drawn (0x110000+193*256+77)).toUInt64 &&& 15 != 0 then
    throw <| IO.userError "Failed offline input did not start/rasterize an independently located point without changing commit state"
  invariant drawn
  let offline ← IO.mkRef (write initial ((0x20800 : UInt64)+104) 13)
  let original := #[(0,51),(8,1001),(16,14000),(24,42000),(32,0),(40,2),(48,1),(56,0),(64,1)]
  for (offset,value) in original do offline.modify fun m => write m (raw+offset) value
  let _ ← run offline retryAppendRaw
  let m ← offline.get
  if read m ((0x20800 : UInt64)+112) != 1 || read m ((0x20800 : UInt64)+104) != 0 || read m ((0x20800 : UInt64)+136) != 2 ||
      !m.operations.isEmpty then throw <| IO.userError "offline release failed to retain bounded raw bytes or contacted Store"
  for (offset,value) in original do
    if read m (ink1+128+offset) != value then throw <| IO.userError "offline raw input was synthesized or altered"
  invariant m
  let full ← IO.mkRef (write (write (write initial ((0x20800 : UInt64)+112) 384) ((0x20800 : UInt64)+104) 13) ((0x20800 : UInt64)+160) 7)
  let _ ← run full retryInputLimit
  if read (← full.get) ((0x20800 : UInt64)+112) != 384 || read (← full.get) ((0x20800 : UInt64)+160) != 7 ||
      read (← full.get) ((0x20800 : UInt64)+664) != 1 || read (← full.get) ((0x20800 : UInt64)+136) != 2 then
    throw <| IO.userError "bounded exhaustion dropped bytes, released a pending call or fabricated success"
  invariant (← full.get)
  let event := #[(0,2),(8,1002),(16,54527),(24,1908),(32,2047),(40,3),(48,1),(56,0),(64,1)]
  let healthyFull ← IO.mkRef {write (write initial ((0x20800 : UInt64)+112) 384) ((0x20800 : UInt64)+648) 0 with inputEvents := #[event]}
  if (← run healthyFull (drainRetryInput 2)) != (0,0) || (← healthyFull.get).inputReads != 0 then
    throw <| IO.userError "new drain changed healthy full-buffer backpressure"
  let failedFull ← IO.mkRef {write initial ((0x20800 : UInt64)+112) 384 with inputEvents := #[event]}
  if (← run failedFull (drainRetryInput 2)) != (0,1) || (← failedFull.get).inputReads != 1 ||
      (← failedFull.get).operations != #[8] || read (← failedFull.get) ((0x20800 : UInt64)+112) != 384 then
    throw <| IO.userError "full failed offline buffer blocked explicit status or discarded raw bytes"
  invariant (← failedFull.get)
  IO.println "NOTEBOOK_RETRY_ACTION:PASS exact retained source, readonly/ambiguous/malformed failure, max3/busy gates, real wouldBlock, other-buffer raw release and pending-safe exhaustion; no Saved/target execution"
end NotebookRetryTests
def main : IO Unit := NotebookRetryTests.check
