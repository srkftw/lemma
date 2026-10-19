
/-! Host-only interpreter tests appended verbatim after the actual maintained
Notebook source. This avoids exposing private guest actions as a public API.
Only virtual memory and explicitly observed syscalls are modeled; these tests
are not guest/controller execution or visible-paper evidence. -/
namespace Lemma.Applications.Notebook
open Std Lemma.Core0.Memory Lemma.User Lemma.Ink
structure UIState where
  words : Std.HashMap UInt64 UInt64 := {}
  calls : Array (UInt64 × UInt64 × UInt64 × UInt64) := #[]
  writes : Nat := 0
  surfaceStatus : UInt64 := 0

def uiRead (s : UIState) (address : UInt64) : UInt64 := s.words.getD address 0
def uiWrite (s : UIState) (address value : UInt64) : UIState :=
  { s with words := s.words.insert address value, writes := s.writes + 1 }
partial def uiExecute (r : IO.Ref UIState) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s value => pure (s,value)
  | .bind first next =>
    let (s,value) ← uiExecute r first
    uiExecute r (next s value)
  | .boundedFoldU64 bound step count initial c0 c1 c2 c3 next =>
    if bound < count.toNat then throw <| IO.userError "loop exceeds actual declared bound"
    let mut s : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if s = 0 then
        let result ← uiExecute r (step i.toUInt32 count value c0 c1 c2 c3)
        s := result.1
        value := result.2
    uiExecute r (next s value)
  | .platform op a b c d e f next =>
    match op with
    | .virtualRead64 =>
      if a % 8 ≠ 0 then throw <| IO.userError "unaligned64"
      uiExecute r (next 0 (uiRead (← r.get) a))
    | .virtualRead8 =>
      uiExecute r (next 0 ((uiRead (← r.get) (a-a%8) >>> (a%8*8)) &&& 255))
    | .virtualWrite64 =>
      if a % 8 ≠ 0 then throw <| IO.userError "unaligned64"
      r.modify fun s => uiWrite s a b
      uiExecute r (next 0 0)
    | .virtualWrite8 =>
      r.modify fun s =>
        let old := uiRead s (a-a%8)
        uiWrite s (a-a%8) ((old &&& ~~~((255:UInt64) <<< (a%8*8))) ||| ((b &&& 255) <<< (a%8*8)))
      uiExecute r (next 0 0)
    | .syscall =>
      r.modify fun s => { s with calls := s.calls.push (a,b,c,d) }
      if a = 69 then
        if c ≠ 6 || e ≠ 0 || f ≠ 0 then throw <| IO.userError "busy CAPTURE attempted acquisition/configuration"
        uiExecute r (next 0 0)
      else if a = CapabilityABI.console then
        if c ≠ 0 || d ≠ Console.packetAddress || e ≠ 88 then throw <| IO.userError "wrong console packet"
        uiExecute r (next 0 88)
      else if a = 64 && c = 4 then uiExecute r (next 0 (← r.get).surfaceStatus)
      else if a = 5 then uiExecute r (next 0 100)
      else throw <| IO.userError s!"unexpected syscall {a}/{c}"
    | _ => throw <| IO.userError "unexpected platform operation"
  | _ => throw <| IO.userError "unexpected Action constructor"

def uiCheck (p : Bool) (message : String) : IO Unit :=
  if p then pure () else throw <| IO.userError message

def uiFixture (enabled : UInt64) : UIState := Id.run do
  let mut s : UIState := {}
  for (a,v) in #[(state+32,1650),(state+40,2200),(state+48,65535),(state+56,65535),
      (state+336,65535),(state+344,65535),(Lemma.User.Multimodal.state,99),
      (Lemma.User.Multimodal.state+16,enabled),(raw,1),(raw+8,100),(raw+16,17885),
      (raw+24,4173),(raw+40,3),(raw+64,1)] do
    s := uiWrite s a v
  return { s with writes := 0 }

def uiByte (s : UIState) (a : UInt64) : UInt64 := (uiRead s (a-a%8) >>> (a%8*8)) &&& 255

def uiMain : IO Unit := do
  let bar ← IO.mkRef (uiFixture 1)
  uiCheck ((← uiExecute bar multimodalBar).1 = 0) "actual bar failed"
  let s ← bar.get
  uiCheck (uiRead s (state+456) = 23) "bar did not enqueue all23 intersecting controller tiles"
  for i in [:23] do
    let index := (220+i).toUInt64
    let word := uiRead s (dirtyQueue+(i/4).toUInt64*8)
    uiCheck (((word >>> ((i%4).toUInt64*16)) &&& 65535) = index) "wrong actual dirty queue tile"
    uiCheck (uiByte s (dirtyBitmap+index/8) &&& ((1:UInt64) <<< (index%8)) ≠ 0) "queued tile lacks bitmap ownership"
  uiCheck ((uiRead s (state+336),uiRead s (state+344),uiRead s (state+352),uiRead s (state+360)) = (400,132,1120,147)) "wrong actual dirty extent"
  -- Independent row-major3x5 ACTIVE glyph literals, not producer expectations.
  for (i,bits) in ( #[(0,0x2bed),(1,0x7927),(2,0x7492),(3,0x7497),(4,0x5b6a),(5,0x79a7)] : Array (UInt64 × UInt64)) do
    for y in [:15] do
      for x in [:12] do
        let px := 400+i*12+x.toUInt64
        let byte := uiByte s (Surface.framebuffer+(132+y.toUInt64)*825+px/2)
        let actual := (byte >>> (if px%2 = 0 then 4 else 0)) &&& 15
        let expected := if x < 9 && (bits >>> (14-(y/3*3+x/3).toUInt64)) &&& 1 = 1 then 0 else 15
        uiCheck (actual = expected) "ACTIVE pixels differ from independent glyph literal"
  for (i,bits) in (#[(0,0x124e),(1,0x7b6f),(2,0x7497),(3,0x5ffd)] : Array (UInt64 × UInt64)) do
    for y in [:15] do
      for x in [:12] do
        let px := 1024+i*12+x.toUInt64
        let byte := uiByte s (Surface.framebuffer+(132+y.toUInt64)*825+px/2)
        let actual := (byte >>> (if px%2 = 0 then 4 else 0)) &&& 15
        let expected := if x < 9 && (bits >>> (14-(y/3*3+x/3).toUInt64)) &&& 1 = 1 then 0 else 15
        uiCheck (actual = expected) "JOIN label pixels differ from independent glyph literal"
  uiCheck ((← uiExecute bar multimodalBar).1 = 0) "repaint failed"
  uiCheck (uiRead (← bar.get) (state+456) = 23) "bar duplicated already queued tile"
  let narrow ← IO.mkRef (uiWrite (uiFixture 0) (state+32) 1119)
  let before ← narrow.get
  uiCheck ((← uiExecute narrow multimodalBar).1 = 16) "undersized framebuffer accepted"
  uiCheck ((← narrow.get).writes = before.writes) "rejected bar modified memory"
  let held ← IO.mkRef { uiFixture 1 with surfaceStatus := 1 }
  held.modify fun s => uiWrite s (Lemma.User.Multimodal.state+32) 1
  let before ← held.get
  uiCheck ((← uiExecute held multimodalPumpBar).1 = 0) "owned surface pump failed"
  uiCheck ((← held.get).writes = before.writes) "bar wrote before display ownership returned"
  let busy ← IO.mkRef (uiFixture 1)
  busy.modify fun s => uiWrite (uiWrite (uiWrite s (state+160) 1) (state+536) 1) (state+336) 0
  for i in [:64] do busy.modify fun s => uiWrite s (Lemma.User.Multimodal.records+i.toUInt64*8) 12345
  uiCheck ((← uiExecute busy multimodalInputSample).1 = 0) "busy CAPTURE stop failed"
  let stopped ← busy.get
  uiCheck (uiRead stopped (Lemma.User.Multimodal.state+16) = 0) "busy CAPTURE did not revoke"
  let calls := stopped.calls.filter fun c => c.1 = 69
  uiCheck (calls.size = 9) "busy CAPTURE did not revoke every endpoint"
  for i in [:9] do uiCheck (calls[i]! = (69,99,6,i.toUInt64)) "wrong local revoke authority/stream"
  for i in [:64] do uiCheck (uiRead stopped (Lemma.User.Multimodal.records+i.toUInt64*8) = 0) "revoked raw window retained"
  uiCheck (uiRead stopped (state+160) = 1 && uiRead stopped (state+536) = 1 && uiRead stopped (state+336) = 0) "safety stop changed pending Store/checker/display"
  let inactive ← IO.mkRef (uiWrite (uiFixture 0) (state+160) 1)
  uiCheck ((← uiExecute inactive multimodalInputSample).1 = 0) "inactive busy tap failed"
  uiCheck ((← inactive.get).calls.isEmpty) "inactive busy tap silently started collection"
  let intent ← IO.mkRef (uiWrite (uiWrite (uiWrite (uiFixture 0) (raw+16) 34577) (state+160) 1) (state+536) 1)
  let before ← intent.get
  uiCheck ((← uiExecute intent multimodalInputSample).1 = 0) "busy ASK raw admission failed"
  let queued ← intent.get
  uiCheck (uiRead queued (tutorState+16) = 3) "busy ASK was dropped by the math-only queue"
  uiCheck (uiRead queued (state+160) = 1 && uiRead queued (state+536) = 1) "queued ASK changed Store/checker ownership"
  uiCheck (uiRead queued (state+336) = uiRead before (state+336)) "queued ASK changed the framebuffer frontier"
  let before ← intent.get
  uiCheck ((← uiExecute intent multimodalPumpTutor).1 = 0) "busy tutor pump failed"
  uiCheck ((← intent.get).writes = before.writes) "pending tutor ran ahead of Store/checker"
  uiCheck ((← uiExecute intent (multimodalQueueTutor 3)).1 = 0) "identical queued ASK failed"
  uiCheck (uiRead (← intent.get) (tutorState+16) = 3) "identical ASK changed pending intent"
  uiCheck ((← uiExecute intent (multimodalQueueTutor 4)).1 = 0) "bounded different-intent receipt failed"
  uiCheck (uiRead (← intent.get) (tutorState+16) = 3) "LOAD overwrote an earlier pending ASK"
  intent.modify fun s => { uiWrite (uiWrite s (state+160) 0) (state+536) 0 with surfaceStatus := 1 }
  let before ← intent.get
  uiCheck ((← uiExecute intent multimodalPumpTutor).1 = 0) "owned-paper tutor pump failed"
  uiCheck ((← intent.get).writes = before.writes) "tutor dispatched while paper owned the framebuffer"
  intent.modify fun s => { s with surfaceStatus := 0 }
  uiCheck ((← uiExecute intent multimodalPumpTutor).1 = 0) "idle intent dispatch did not preserve control error receipt"
  uiCheck (uiRead (← intent.get) (tutorState+16) = 0) "terminal dispatch retained the same intent"
  let before ← intent.get
  uiCheck ((← uiExecute intent multimodalPumpTutor).1 = 0) "empty tutor pump failed"
  uiCheck ((← intent.get).writes = before.writes && (← intent.get).calls = before.calls) "intent dispatched more than once"
  let book ← IO.mkRef (uiFixture 0)
  book.modify fun s => uiWrite (uiWrite (uiWrite (uiWrite (uiWrite (uiWrite (uiWrite s
    (raw+16) 10494) (raw+24) 19972) (state+512) 1) (state+80) 1)
    (packageState+128) 1) (packageState+136) 2) (state+160) 1
  uiCheck ((← uiExecute book multimodalInputSample).1 = 0) "busy chooser LOAD raw admission failed"
  let queued ← book.get
  uiCheck (uiRead queued (tutorState+16) = 6) "busy chooser LOAD disappeared after EDIT+"
  uiCheck (uiRead queued (tutorState+32) = 1 && uiRead queued (tutorState+40) = 1 && uiRead queued (tutorState+48) = 2) "chooser intent did not snapshot its page/request"
  uiCheck (uiRead queued (packageState+32) = 0 && uiRead queued (state+160) = 1) "queued chooser LOAD started a read or changed Store ownership"
  let before ← book.get
  uiCheck ((← uiExecute book multimodalPumpTutor).1 = 0) "busy chooser pump failed"
  uiCheck ((← book.get).writes = before.writes) "chooser dispatched before Store completion"
  book.modify fun s => uiWrite (uiWrite s (state+160) 0) (packageState+136) 3
  uiCheck ((← uiExecute book multimodalPumpTutor).1 = 0) "stale chooser terminal receipt failed"
  let stale ← book.get
  uiCheck (uiRead stale (tutorState+16) = 0 && uiRead stale (packageState+32) = 0) "changed publication started the stale queued LOAD"
  let expected := "K1 0000000000000712 0000000000000006 00000000000000af 0000000000000000 0000000000000000\n".toUTF8
  for i in [:expected.size] do
    uiCheck (uiByte stale (Console.packetAddress+i.toUInt64) = expected[i]!.toUInt64) "stale chooser intent did not report cancellation"
  let ready ← IO.mkRef (uiFixture 0)
  for (a,v) in #[(state+512,1),(state+80,1),(state+72,1),(state+16,77),(state+176,1),
      (packageAllocationAddress,12),(packageState+128,1),(packageState+136,2),
      (tutorState+16,6),(tutorState+32,1),(tutorState+40,1),(tutorState+48,2)] do
    ready.modify fun s => uiWrite s a v
  uiCheck ((← uiExecute ready multimodalPumpTutor).1 = 0) "ready chooser LOAD failed actual dispatcher"
  let loaded ← ready.get
  uiCheck (uiRead loaded (tutorState+16) = 0 && uiRead loaded (packageState+32) = 1) "ready chooser LOAD did not start reader phase1"
  uiCheck (uiRead loaded (packageContext+32) = 1 && uiRead loaded (packageContext+40) = 2 && uiRead loaded (packageContext+80) = 0) "ready chooser reader configured the wrong identity/edition or fabricated IPC"
  uiCheck (uiRead loaded (state+176) = 258 && uiRead loaded (packageState+40) = 300000100) "ready chooser LOAD did not reserve its real request range/deadline"
  let rejected ← IO.mkRef (uiFixture 0)
  for (a,v) in #[(packageAllocationAddress,12),(packageState+32,2),
      (packageState+72,1),(packageState+144,1),(packageState+152,1),(tutorState+16,3)] do
    rejected.modify fun s => uiWrite s a v
  uiCheck ((← uiExecute rejected bookmarkBusy) = (0,1)) "rejected pending-view fixture is not busy"
  let before ← rejected.get
  uiCheck ((← uiExecute rejected multimodalPumpTutor).1 = 0) "pending-view tutor wait failed"
  uiCheck ((← rejected.get).writes = before.writes) "ASK bypassed unfinished presentation"
  uiCheck ((← uiExecute rejected multimodalAbandonPresentation).1 = 0) "actual rejected-view cleanup failed"
  let abandoned ← rejected.get
  uiCheck (abandoned.writes = before.writes+4) "rejection cleanup altered more than its four presentation words"
  uiCheck (uiRead abandoned (packageState+32) = 4 && uiRead abandoned (packageState+72) = 0 &&
    uiRead abandoned (packageState+144) = 0 && uiRead abandoned (packageState+152) = 0) "rejected view retained pending presentation work"
  uiCheck ((← uiExecute rejected bookmarkBusy) = (0,0)) "rejected view permanently blocks fresh controls"
  uiCheck ((← uiExecute rejected multimodalPumpTutor).1 = 0) "ASK could not dispatch after rejection cleanup"
  uiCheck (uiRead (← rejected.get) (tutorState+16) = 0) "rejected view retained the fresh ASK intent forever"
  for (identity,action) in (#[(60001,multimodalLoadTutor),(60000,multimodalJoinSchool)] : Array (UInt64 × Action)) do
    let envelope ← IO.mkRef (uiFixture 0)
    for (a,v) in #[(packageAllocationAddress,12),(packageState+32,2),(packageState+96,4),
        (packageState+160,0xdeadbeef),(packageState+176,5),(tutorState,17),
        (state+16,77),(state+72,1),(state+176,1)] do
      envelope.modify fun s => uiWrite s a v
    uiCheck ((← uiExecute envelope action).1 = 0) "explicit envelope read failed"
    let selected ← envelope.get
    uiCheck (uiRead selected (packageState+160) = 0 && uiRead selected (packageState+176) = 0) "school envelope inherited the original reader CRC/node guard"
    uiCheck (uiRead selected (packageContext+32) = identity && uiRead selected (packageContext+40) = 17 &&
      uiRead selected (packageState+32) = 1) "explicit envelope did not start its requested immutable package"
    uiCheck (uiRead selected tutorState = 17 && uiRead selected (state+160) = 0) "envelope read changed its sequence or Store ownership"
  let contact ← IO.mkRef (uiWrite (uiFixture 1) (state+408) 1)
  uiCheck ((← uiExecute contact multimodalInputSample).1 = 0) "held contact failed"
  uiCheck ((← contact.get).calls.isEmpty) "held contact repeated control"
  IO.println "NOTEBOOK21_UI_ACTIONS_PASS actual23tilequeue/bitmap/pixels/coalescing/extent; narrow/owned-negative; busy-stop9revokes/raw-wipe/no-Store-checker-mutation; retained busyASK/coalescedASK/boundedLOAD/owned-paper/exact-once; rejected-view cleanup/fresh-ASK dispatch; inactive/held-contact noacquisition"
end Lemma.Applications.Notebook

def main : IO Unit := Lemma.Applications.Notebook.uiMain
