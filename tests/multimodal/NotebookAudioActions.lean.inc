
namespace Lemma.User.Multimodal
open Std Lemma.Core0.Memory
structure AudioFixture where
  words : Std.HashMap UInt64 UInt64 := {}
  epoch : UInt64 := 6
  ticks : UInt64 := 1000
  consumed : UInt64 := 900
  accepts : UInt64 := 16
  calls : Array (UInt64 × UInt64 × UInt64 × UInt64) := #[]
  packets : Array (Array UInt64) := #[]
  receipts : Array String := #[]
  revoked : Nat := 0
  allocated : Nat := 0
  deriving Inhabited
private def afRead (s : AudioFixture) (address : UInt64) : UInt64 := s.words.getD address 0
private def afPut (s : AudioFixture) (address value : UInt64) : AudioFixture :=
  {s with words := s.words.insert address value}
private def afByte (s : AudioFixture) (address : UInt64) : UInt8 :=
  ((afRead s (address-address%8) >>> (address%8*8)) &&& 255).toUInt8
private def afCheck (p : Bool) (message : String) : IO Unit :=
  if p then pure () else throw <| IO.userError message
partial def afExecute (r : IO.Ref AudioFixture) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s value => pure (s,value)
  | .bind first next =>
    let (s,value) ← afExecute r first
    afExecute r (next s value)
  | .boundedFoldU64 bound step count initial c0 c1 c2 c3 next =>
    if bound < count.toNat then throw <| IO.userError "unbounded fixture Action"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let result ← afExecute r (step i.toUInt32 count value c0 c1 c2 c3)
        status := result.1
        value := result.2
    afExecute r (next status value)
  | .platform op a b c d e f next =>
    match op with
    | .virtualRead64 => afExecute r (next 0 (afRead (← r.get) a))
    | .virtualWrite64 =>
      r.modify fun s => afPut s a b
      afExecute r (next 0 0)
    | .virtualWrite8 =>
      r.modify fun s =>
        let old := afRead s (a-a%8)
        afPut s (a-a%8) ((old &&& ~~~((255:UInt64) <<< (a%8*8))) ||| ((b &&& 255) <<< (a%8*8)))
      afExecute r (next 0 0)
    | .syscall =>
      if a = ABI.allocatePages then
        afCheck (b = audioPage && c = 1) "audio allocated another owner or extent"
        r.modify fun s => {s with allocated := s.allocated+1}
        afExecute r (next 0 b)
      else if a = CapabilityABI.console then
        afCheck (c = 0 && d = Console.packetAddress && e = 88) "unexpected receipt packet"
        let s ← r.get
        let bytes := ByteArray.mk <| (Array.range 88).map fun i => afByte s (d+i.toUInt64)
        r.modify fun s => {s with receipts := s.receipts.push (String.fromUTF8! bytes)}
        afExecute r (next 0 88)
      else if a = 69 then
        afCheck (b = 99 && (if c = 10 then d = 0 else d = 8)) "audio used another capability or acquisition grant"
        r.modify fun s => {s with calls := s.calls.push (c,d,e,f)}
        let s ← r.get
        if c = 11 then afExecute r (next 0 s.epoch)
        else if c = 10 then afExecute r (next 0 s.ticks)
        else if c = 15 then afExecute r (next 0 s.consumed)
        else if c = 2 then
          afCheck (afRead s e = 0x31474d4d && afRead s (e+16) = 64 &&
            afRead s (e+24) = 16000 && afRead s (e+32) = 128 &&
            afRead s (e+40) = s.ticks+100000000 && afRead s (e+48) = s.epoch) "audio grant widened scope or budget"
          r.modify fun s => {s with epoch := s.epoch+1}
          afExecute r (next 0 (s.epoch+1))
        else if c = 3 then
          afCheck (f = s.epoch && afRead s e = 1 && afRead s (e+8) = 6250 && afRead s (e+16) = 1) "wrong bounded PCM configuration"
          afExecute r (next 0 0)
        else if c = 16 || c = 17 then
          afCheck (f = s.epoch) "start or arm used stale epoch"
          afExecute r (next 0 0)
        else if c = 14 then
          afCheck (f = s.epoch && afRead s e = 0x31424350 && afRead s (e+8) = 1 &&
            afRead s (e+16) = 16 && afRead s (e+24) = 0) "not a bounded version1 arbitrary PCM packet"
          let values := (Array.range 16).map fun i =>
            (afRead s (e+32+(i/4).toUInt64*8) >>> ((i%4).toUInt64*16)) &&& 65535
          r.modify fun s => {s with packets := s.packets.push values}
          afExecute r (next 0 s.accepts)
        else if c = 6 then
          r.modify fun s => {s with revoked := s.revoked+1, epoch := s.epoch+1}
          afExecute r (next 0 0)
        else throw <| IO.userError s!"unexpected audio service operation {c}"
      else throw <| IO.userError s!"unexpected syscall {a}"
    | _ => throw <| IO.userError "unexpected platform Action"
  | _ => throw <| IO.userError "unexpected fixture Action"
private def afInitial : AudioFixture :=
  afPut (afPut (afPut (afPut ({} : AudioFixture) state 99) (state+8) 9) (state+16) 1) (state+64) 123
private def completeReceipt : String := "K1 0000000000000716 0000000000000001 0000000000000010 0000000000000010 0000000000000000\n"
def afMain : IO Unit := do
  let r ← IO.mkRef afInitial
  afCheck ((← afExecute r testAudio).1 = 0) "actual explicit test failed"
  let started ← r.get
  afCheck (started.allocated = 1 && afRead started (state+128) = 1) "audio owner not allocated exactly once"
  afCheck (started.calls.map (·.1) = #[10,11,2,3,16,15,14,17]) "output must grant, arm, prefill, then start"
  afCheck (started.packets = #[#[0,4096,7568,9888,10752,9888,7568,4096,0,61440,57968,55648,54784,55648,57968,61440]]) "signed16 samples changed"
  afCheck (started.receipts.size = 1 && afRead started (audioPage+16) = 16 && afRead started (audioPage+32) = 0) "acceptance became consumed receipt"
  afCheck ((← afExecute r testAudio).1 = 6) "active test replaced without explicit stop"
  r.modify fun s => {s with consumed := 903}
  afCheck ((← afExecute r pumpAudio) = (0,3)) "actual partial consumed count not tracked"
  afCheck ((← afExecute r (control 1)).1 = 0) "local mute failed"
  let muted ← r.get
  afCheck (muted.revoked = 1 && afRead muted audioPage = 0 && afRead muted (audioPage+32) = 3) "mute lost prefix or failed local inhibition"
  afCheck (muted.receipts[1]! = "K1 0000000000000716 0000000000000001 0000000000000010 0000000000000003 0000000000000001\n") "mute claimed complete or wrong packet"
  afCheck (afRead muted (state+16) = 1 && afRead muted (state+64) = 123) "mute changed independent acquisition permission"
  let r ← IO.mkRef afInitial
  afCheck ((← afExecute r testAudio).1 = 0) "completion fixture start failed"
  r.modify fun s => {s with consumed := 916}
  afCheck ((← afExecute r pumpAudio).1 = 0) "actual completion failed"
  let completed ← r.get
  afCheck (completed.receipts[1]! = completeReceipt && completed.revoked = 1) "no actual bounded consumption receipt"
  afCheck ((← afExecute r pumpAudio).1 = 0 && (← r.get).receipts.size = 2) "completion duplicated"
  afCheck ((← afExecute r testAudio).1 = 0 && (← r.get).allocated = 1 && afRead (← r.get) (audioPage+56) = 2) "successor lost owner or sequence"
  let r ← IO.mkRef afInitial
  afCheck ((← afExecute r testAudio).1 = 0) "expiry fixture start failed"
  r.modify fun s => {s with consumed := 904, ticks := 100001000}
  afCheck ((← afExecute r pumpAudio).1 = 0) "expiry cleanup failed"
  let expired ← r.get
  afCheck (expired.revoked = 1 && expired.receipts[1]! = "K1 0000000000000716 0000000000000001 0000000000000010 0000000000000004 0000000000000002\n") "expiry falsely completed"
  let r ← IO.mkRef afInitial
  afCheck ((← afExecute r testAudio).1 = 0) "stale fixture start failed"
  r.modify fun s => {s with consumed := 902}
  afCheck ((← afExecute r pumpAudio) = (0,2)) "stale fixture prefix failed"
  r.modify fun s => {s with consumed := 9999, epoch := 40}
  afCheck ((← afExecute r pumpAudio).1 = 0) "superseded cleanup failed"
  let stale ← r.get
  afCheck (stale.revoked = 0 && stale.epoch = 40 && afRead stale (audioPage+32) = 2) "stale background cancelled or charged successor"
  afCheck (stale.receipts[1]! = "K1 0000000000000716 0000000000000001 0000000000000010 0000000000000002 0000000000000004\n") "superseded receipt fabricated later consumption"
  let r ← IO.mkRef afInitial
  afCheck ((← afExecute r testAudio).1 = 0) "explicit mute successor fixture start failed"
  r.modify fun s => {s with consumed := 903}
  afCheck ((← afExecute r pumpAudio) = (0,3)) "explicit mute successor fixture prefix failed"
  r.modify fun s => {s with consumed := 9999, epoch := 40}
  afCheck ((← afExecute r (control 1)).1 = 0) "explicit mute did not revoke successor"
  let explicitlyMuted ← r.get
  afCheck (explicitlyMuted.revoked = 1 && explicitlyMuted.epoch = 41 && afRead explicitlyMuted (audioPage+32) = 3) "explicit local mute lost authority or claimed successor output"
  let r ← IO.mkRef {afInitial with accepts := 5}
  afCheck ((← afExecute r testAudio).1 = 6) "partial accepted packet reported complete"
  let partialPacket ← r.get
  afCheck (partialPacket.revoked = 1 && !(partialPacket.calls.map (·.1)).contains 17 && afRead partialPacket (audioPage+16) = 5) "partial packet started or lost accepted prefix"
  let r ← IO.mkRef afInitial
  afCheck ((← afExecute r (control 1)).1 = 0 && (← r.get).allocated = 0 && (← r.get).revoked = 1) "mute before allocation failed or allocated output"
  let r ← IO.mkRef {afInitial with consumed := 0xfffffffffffffff0}
  afCheck ((← afExecute r testAudio).1 = 14) "unrepresentable consumed-counter wrap accepted"
  afCheck ((← r.get).revoked = 1 && (← r.get).packets.isEmpty && (← r.get).receipts.isEmpty) "counter overflow enqueued or fabricated output"
  IO.println "NOTEBOOK_AUDIO_ACTIONS_PASS"
end Lemma.User.Multimodal

def main : IO Unit := Lemma.User.Multimodal.afMain
