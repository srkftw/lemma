import Lemma.Multimodal.DisplayedViewport
namespace ViewportHost
open Lemma.Core0.Memory Lemma.Platform.LemmaSim
abbrev state : UInt64 := 0x80413000
abbrev frame : UInt64 := 0x80410000
abbrev params : UInt64 := 0x80411000
structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  tick : UInt64 := 100
  status : UInt64 := 0
  accepted : UInt64 := 0
  completed : UInt64 := 0
  error : UInt64 := 0
  commands : Nat := 0
  acknowledge : Nat := 0
private def get (m : Model) (a : UInt64) := m.words.getD a 0
private def put (m : Model) (a v : UInt64) : Model := {m with words := m.words.insert a v}
partial def run (r : IO.Ref Model) : Action → IO (UInt8 × UInt64)
 | .done s v => pure (s,v)
 | .bind a f => do
   let (s,v) ← run r a
   run r (f s v)
 | .boundedFoldU64 b step n initial a c d e next => do
   if b < n.toNat then throw <| IO.userError "fold exceeded"
   let mut s : UInt8 := 0
   let mut v := initial
   for i in [:n.toNat] do
    if s = 0 then
     let result ← run r (step i.toUInt32 n v a c d e)
     s := result.1
     v := result.2
   run r (next s v)
 | .platform op a v _ _ _ _ next => do
   let m ← r.get
   if op == .physicalRead64 then run r (next 0 (get m a))
   else if op == .physicalWrite64 then r.set (put m a v);run r (next 0 0)
   else if op == .deviceRead64 then
    let value ← if a == 0x200bff8 then pure m.tick
      else if a == DeviceABI.paperBase+16 then pure m.status
      else if a == DeviceABI.paperBase+24 then pure m.error
      else if a == DeviceABI.paperBase+32 then pure 2200
      else if a == DeviceABI.paperBase+40 then pure 1650
      else if a == DeviceABI.paperBase+112 then pure m.accepted
      else if a == DeviceABI.paperBase+160 then pure m.completed
      else throw <| IO.userError s!"unknown device read{a}"
    run r (next 0 value)
   else if op == .deviceWrite64 then
    if a == DeviceABI.paperBase+168 then throw <| IO.userError "history secretly acknowledged completion"
    if a == DeviceABI.paperBase+112 then r.set {m with accepted := v}
    else if a == DeviceABI.paperBase+104 then
     unless v = 2 do throw <| IO.userError "unexpected paper command"
     r.set {m with status := 1,commands := m.commands+1}
    else if a == DeviceABI.paperBase+120 || a == DeviceABI.paperBase+128 || a == DeviceABI.paperBase+136 || a == DeviceABI.paperBase+144 || a == DeviceABI.paperBase+152 then pure ()
    else throw <| IO.userError "unexpected device mutation"
    run r (next 0 0)
   else throw <| IO.userError s!"unexpected platform effect{repr op}"
 | _ => throw <| IO.userError "unexpected Action"
def check (b : Bool) (s : String) : IO Unit := unless b do throw <| IO.userError s
def capture (r : IO.Ref Model) (start finish : UInt64) : IO Unit := r.modify fun m => put (put (put m (frame+32) 1) (frame+48) start) (frame+56) finish
def main : IO Unit := do
 let r ← IO.mkRef ({} : Model)
 let call (a : Action) := run r a
 check ((← call (Lemma.Multimodal.DisplayedViewport.initialize state 9)) = (0,9)) "init"
 check ((← call (Lemma.Multimodal.DisplayedViewport.refresh state 8001 3 19 7 4 11 2200 1650 1)) = (0,11)) "actual refresh"
 check ((get (← r.get) (state+256)) = 0) "accepted request became displayed"
 check ((← call (Lemma.Multimodal.DisplayedViewport.poll state)).1 = 6) "busy not represented"
 r.modify fun m => {m with status := 2,completed := 11,tick := 200}
 check ((← call (Lemma.Multimodal.DisplayedViewport.poll state)) = (0,11)) "matching completion"
 check ((get (← r.get) (state+256)) = 1 && get (← r.get) (state+256+88) = 2000) "actual completion observation time"
 r.modify fun m => {m with tick := 300}
 capture r 2200 2208
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 1)).1 = 0) "capture bind"
 check (get (← r.get) (params+35*8) = 7 && get (← r.get) (params+37*8) = 11) "source anchors"
 check ((← call (Lemma.Multimodal.DisplayedViewport.refresh state 8002 4 20 8 5 12 2200 1650 1)).1 = 0) "new publication"
 r.modify fun m => {m with status := 2,completed := 12,tick := 500}
 check ((← call (Lemma.Multimodal.DisplayedViewport.poll state)) = (0,12)) "new completion"
 r.modify fun m => {m with tick := 600}
 capture r 2200 2208
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 1)).1 = 0) "delayed old capture"
 check (get (← r.get) (params+35*8) = 7 && get (← r.get) (params+32*8) = 8001) "delayed frame attached to latest document"
 capture r 5200 5208
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 1)).1 = 0) "current capture"
 check (get (← r.get) (params+35*8) = 8 && get (← r.get) (params+32*8) = 8002) "new anchors"
 capture r 4000 4008
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 1)).1 = 9) "inflight partial refresh relabeled"
 capture r 5200 5208
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 2)).1 = 8) "stale acquisition epoch"
 r.modify fun m => {m with tick := 650,status := 8}
 check ((← call (Lemma.Multimodal.DisplayedViewport.poll state)).2 = 9) "unsolicited reset missed"
 capture r 6600 6608
 r.modify fun m => {m with tick := 700,status := 0}
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 1)).1 = 9) "postreset sample uses old display"
 check ((← call (Lemma.Multimodal.DisplayedViewport.reset state 9)).1 = 4) "old reset epoch accepted"
 check ((← call (Lemma.Multimodal.DisplayedViewport.reset state 10)) = (0,10)) "new reset epoch"
 capture r 2200 2208
 check ((← call (Lemma.Multimodal.DisplayedViewport.bindCapture state frame params 1)).1 = 9) "reset revived retired live history"
 check ((← call (Lemma.Multimodal.DisplayedViewport.refresh state 8001 3 19 7 4 13 2199 1650 1)).1 = 2) "partial extent admitted"
 check ((← r.get).commands = 2 && (← r.get).acknowledge = 0) "unexpected controller side effect"
 IO.println "VIEWPORT_HISTORY_ACTIONS_PASS checks=22 actualRefreshCalls=2 noImplicitAcknowledge=1"
end ViewportHost
def main := ViewportHost.main
