namespace Lemma.User.Multimodal
open Std Lemma.Core0.Memory
private def ringInitial : AudioFixture := afPut afInitial (state+136) 3
private def ringCheckNoFault (r : IO.Ref AudioFixture) (a : Action) (label : String) : IO Unit := do
  let result ← afExecute r a
  afCheck (result.1 = 0) s!"{label} failed: {result}"

def afRingMain : IO Unit := do
  let r ← IO.mkRef ringInitial
  ringCheckNoFault r testAudio "ring test start"
  let started ← r.get
  afCheck (started.allocated = 1 && started.ringAccepted = 2048 && started.ringSubmitted = 500 && started.consumed = 900) "prefill invented submitted/consumed samples"
  afCheck (started.packets.size = 4 && afRead started audioPage = 2) "ring was not bounded-prefilled"
  afCheck ((← afExecute r testAudio).1 = 6) "active ring replaced"
  ringCheckNoFault r pumpAudio "full-ring backpressure"
  afCheck ((← r.get).packets.size = 4 && (← r.get).ringAccepted = 2048) "full ring dropped/changed next sample"
  for i in [:5] do
    r.modify fun s => {s with ringFetched := s.ringAccepted, ringSubmitted := 500+s.ringAccepted, consumed := 900+(if s.ringAccepted < 16 then 0 else s.ringAccepted-16)}
    ringCheckNoFault r pumpAudio s!"refill{i}"
  let filled ← r.get
  afCheck (filled.ringAccepted = 4099 && filled.ringEOF && filled.packets.size = 9) "wrap/refill/odd EOF missing"
  let samples := filled.packets.foldl (fun a packet => a ++ packet) #[]
  afCheck (samples.size = 4099) "refill changed total sample count"
  for i in [:4099] do
    afCheck (samples[i]! = ((i.toUInt64*7919+311) &&& 65535)) s!"arbitrary signed sample changed at{i}"
  afCheck (afRead filled (audioPage+32) < 4099 && afRead filled audioPage = 2) "accepted packet claimed completion"
  r.modify fun s => {s with ringFetched := 4099,ringSubmitted := 4599,consumed := 4999,ringMode := 2}
  ringCheckNoFault r pumpAudio "exact consumed completion"
  let completed ← r.get
  afCheck (completed.revoked = 1 && afRead completed audioPage = 0 && afRead completed (audioPage+16) = 4099 && afRead completed (audioPage+32) = 4099) "completion did not retain independent counters/revoke"
  afCheck (completed.receipts.any (·.startsWith "K1 0000000000000718")) "raw gap/held terminal receipt missing"
  let receipts := completed.receipts.size
  ringCheckNoFault r pumpAudio "idle completion"
  afCheck ((← r.get).receipts.size = receipts) "terminal ring receipt duplicated"
  let r ← IO.mkRef ringInitial
  ringCheckNoFault r testAudio "mute start"
  r.modify fun s => {s with ringFetched := 1024,ringSubmitted := 1400,consumed := 1400,ringHeld := 258,calls := #[]}
  ringCheckNoFault r (control 1) "explicit local mute"
  let muted ← r.get
  afCheck (muted.calls[0]!.1 = 11 && muted.calls[1]!.1 = 6 && muted.calls[2]!.1 = 22) "MUTE queried counters before actual revocation"
  afCheck (muted.revoked = 1 && afRead muted audioPage = 0 && afRead muted (audioPage+16) = 900 && afRead muted (audioPage+32) = 500 && afRead muted (audioPage+3584+56) = 258) "mute invented completion or discarded actual prefixes/held read"
  let r ← IO.mkRef ringInitial
  ringCheckNoFault r testAudio "supersession start"
  r.modify fun s => {s with epoch := s.epoch+1,ringSubmitted := 9000,consumed := 10000}
  ringCheckNoFault r pumpAudio "supersession stop"
  afCheck ((← r.get).revoked = 0 && afRead (← r.get) (audioPage+16) = 0 && afRead (← r.get) (audioPage+32) = 0) "old ring revoked or claimed successor output"
  let r ← IO.mkRef ringInitial
  ringCheckNoFault r testAudio "expiry start"
  r.modify fun s => {s with ticks := 500001000}
  ringCheckNoFault r pumpAudio "expiry stop"
  afCheck ((← r.get).revoked = 1 && afRead (← r.get) audioPage = 0) "expired ring continued"
  IO.println "NOTEBOOK_RING_ACTIONS_PASS4099/arbitrary-S16/prefill/refill/wrap/odd-EOF/backpressure/consumed/mute/supersession/expiry"
end Lemma.User.Multimodal

def main : IO Unit := do
  Lemma.User.Multimodal.afMain
  Lemma.User.Multimodal.afRingMain
