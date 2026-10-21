namespace Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture
open Std Lemma.Core0.Memory Lemma.Kernel.Memory
private def rb : UInt64 := Lemma.Drivers.Multimodal.base
private def rs : UInt64 := rb + 256 + 8*256
private def ringFixture : IO (IO.Ref State × UInt64 × UInt64 × UInt64) := do
  let (r,d,u,_,_) ← fixture
  let handle ← success r (Frames.allocate 1 1)
  let physical ← success r (Frames.resolvePurpose 1 handle 1)
  for (a,v) in [(state+640,handle),(state+row 8,12),(state+row 8+16,64),
      (state+row 8+24,1000000),(state+row 8+32,32792),(rb+8,2),(rs+32,7),
      (u,0x32474e52),(u+8,1),(u+16,2048),(u+24,0)] do r.modify fun s => put s a v
  require (physical != u) "ring borrowed application physical frame"
  pure (r,d,u,physical)
private def packet (r : IO.Ref State) (u count producer : UInt64) : IO Unit := do
  for (a,v) in [(u,0x32424350),(u+8,1),(u+16,count),(u+24,producer)] do r.modify fun s => put s a v
  for i in [:count.toNat] do
    let value := ((producer+i.toUInt64)*7919+311) &&& 65535
    r.modify fun s => putByte (putByte s (u+32+i.toUInt64*2) (value &&& 255)) (u+33+i.toUInt64*2) (value >>> 8)

def runRing : IO Unit := do
  let (r,d,u,physical) ← ringFixture
  let cap := (← r.get).capHandle
  require ((← success r (call d cap 18 0 0 0)) == 3) "controller2 did not negotiate service3"
  for operation in [19,20,21,22] do
    let before ← r.get
    require ((← execute r (call d 0 operation 8 0x40000 12)).1 != 0) "ring bypassed capability admission"
    require ((← r.get).writes == before.writes) "unauthorized ring changed state"
  discard <| success r (beginRing d 8 0x40000 12)
  require (word (← r.get) (rb+104) == physical && word (← r.get) (rb+112) == 2048) "ring uses caller/scratch memory or wrong capacity"
  require ((← execute r (beginRing d 8 0x40000 12)).1 == 6) "active ring reused"
  for p in [0,512,1024,1536] do
    packet r u 512 p
    require ((← success r (enqueueRing d 8 0x40000 12)) == p+512) "bounded packet lost accepted frontier"
  require (word (← r.get) (state+row 8+32) == 16408) "ring charged wire bytes rather than8/sample"
  require (word (← r.get) (rs+232) == 0 && word (← r.get) (rs+240) == 0) "accepted ring bytes invented FIFO submission or consumption"
  packet r u 1 2048
  let before ← r.get
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 == 6) "full ring overwrote unread sample"
  require (word (← r.get) physical == word before physical && word (← r.get) (rb+120) == 2048) "backpressure published or overwrote"
  r.modify fun s => put s (rb+128) 512
  packet r u 512 2048
  discard <| success r (enqueueRing d 8 0x40000 12)
  for i in [:512] do
    let expected := ((2048+i.toUInt64)*7919+311) &&& 65535
    require (byte (← r.get) (physical+i.toUInt64*2) + byte (← r.get) (physical+i.toUInt64*2+1)*256 == expected) "wrap changed arbitrary S16 data"
  packet r u 3 2560
  r.modify fun s => put s (rb+128) 1024
  require ((← success r (enqueueRing d 8 0x40000 12)) == 2563) "odd final packet failed"
  require ((← execute r (finishRing d 8 2562 12)).1 == 4) "EOF silently changed frontier"
  require ((← success r (finishRing d 8 2563 12)) == 2563) "EOF frontier changed"
  require ((← success r (finishRing d 8 2563 12)) == 2563) "same EOF not idempotent"
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 == 5) "post-EOF packet accepted"
  discard <| success r (revoke 8)
  require ((← success r (ringStatus d 8 1 12)) == 2563) "revocation hid owned raw acceptance"
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 != 0) "revoked ring gained authority"
  require ((← execute r (ringStatus (d+1) 8 1 12)).1 == 7) "foreign descriptor observed ring"
  require ((← execute r (ringStatus d 8 1 13)).1 == 4) "foreign epoch observed ring"
  let (r,d,u,physical) ← ringFixture
  r.modify fun s => put (put s (rb+144) 3) (rb+168) 258
  let before ← r.get
  require ((← execute r (beginRing d 8 0x40000 12)).1 == 6) "cancelled held audio read reused frame"
  require (word (← r.get) (state+640) == word before (state+640) && word (← r.get) physical == word before physical) "held ring wiped or freed"
  r.modify fun s => put s (rb+168) 1
  discard <| success r (beginRing d 8 0x40000 12)
  packet r u 3 0
  r.modify fun s => {s with ringExpireAfter := 2}
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 == 8) "expiry during copy published samples"
  require (word (← r.get) (rb+120) == 0 && word (← r.get) (state+row 8+32) == 32792) "unpublished expiry charged or admitted data"
  let (r,d,u,_) ← ringFixture
  discard <| success r (beginRing d 8 0x40000 12)
  packet r u 3 0
  r.modify fun s => put s (rs+32) 8
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 == 4) "changed controller epoch accepted"
  let (r,d,u,_) ← ringFixture
  r.modify fun s => put s (rb+8) 1
  require ((← execute r (beginRing d 8 0x40000 12)).1 == 2) "legacy controller pretended owned ring"
  r.modify fun s => put s (rb+8) 2
  discard <| success r (beginRing d 8 0x40000 12)
  packet r u 513 0
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 == 3) "overbound packet admitted"
  packet r u 3 1
  require ((← execute r (enqueueRing d 8 0x40000 12)).1 == 4) "stale producer silently retargeted"
  IO.println "OWNED_RING_ACTIONS_PASS kernel-frame/capability/atomic512/backpressure/wrap/odd-EOF/expiry/held-read/owner/counters"
end Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture

def main : IO Unit := do
  Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture.run
  Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture.runRing
