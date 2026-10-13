import Lemma.Boot.Product
import Lemma.Boot.Recovery

open Lemma.Core0.Memory Lemma.Core0.Execution Lemma.Boot.Product
-- A host-only raw transport/RAM model. It interprets the SAME checked Action
-- source for faults; it performs no image selection, CRC or update policy.
private structure NVModel where
  ram : Array UInt64 := Array.replicate 2048 0
  sectors : Array (Array UInt64) := #[Array.replicate 64 0,Array.replicate 64 0]
  imageSectors : Array (UInt64 × Array UInt64) := #[]
  buffer : Array UInt64 := Array.replicate 64 0
  state : UInt64 := 0
  sector : UInt64 := 0
  kind : UInt64 := 0
  request : UInt64 := 0
  result : UInt64 := 0
  bytes : UInt64 := 0
  waits : Nat := 0
  writeResult : UInt64 := 0
  writeBytes : UInt64 := 512
  readResult : UInt64 := 0
  barrierResult : UInt64 := 0
  stalled : Bool := false
  cancellations : Nat := 0
  operations : Array UInt64 := #[]
  deriving Inhabited
private def rawRead (m : NVModel) (address : UInt64) : UInt8 × UInt64 × NVModel := Id.run do
  if scratch ≤ address && address < scratch+0x4000 && address &&& 7 = 0 then
    return (0,m.ram[((address-scratch)/8).toNat]!,m)
  if address < nvBase || nvBase+0x400 ≤ address then return (7,0,m)
  let offset := address-nvBase
  if offset = 24 && m.state = 1 && !m.stalled then
    if m.waits > 0 then return (0,1,{m with waits:=m.waits-1})
    else return (0,2,{m with state:=2})
  if 0x200 ≤ offset then
    if m.state = 1 then return (212,0,m)
    else return (0,m.buffer[((offset-0x200)/8).toNat]!,m)
  let value := if offset=0 then nvMagic else if offset=8 then 1 else
    if offset=16 then mediumSectors else if offset=24 then m.state else
    if offset=48 || offset=56 then m.request else if offset=64 then m.result else
    if offset=72 then m.bytes else 0
  return (0,value,m)
private def rawWrite (m : NVModel) (address word : UInt64) : UInt8 × UInt64 × NVModel := Id.run do
  if scratch ≤ address && address < scratch+0x4000 && address &&& 7 = 0 then
    return (0,0,{m with ram:=m.ram.set! (((address-scratch)/8).toNat) word})
  if address < nvBase || nvBase+0x400 ≤ address then return (7,0,m)
  let offset := address-nvBase
  if offset=32 then return (0,0,{m with sector:=word})
  if offset=80 then
    if m.request=word && m.state=2 then return (0,0,{m with state:=0}) else return (212,0,m)
  if offset=88 then return (0,0,{m with cancellations:=m.cancellations+1})
  if 0x200 ≤ offset then
    if m.state=0 then return (0,0,{m with buffer:=m.buffer.set! (((offset-0x200)/8).toNat) word})
    else return (212,0,m)
  if offset=40 && m.state=0 then
    let mut m := {m with state:=1,kind:=word,request:=m.request+1,waits:=2,operations:=m.operations.push word}
    if word=2 then
      m := {m with result:=m.writeResult,bytes:=m.writeBytes}
      if m.sector < (2 : UInt64) then
        let old := m.sectors[m.sector.toNat]!
        let mut changed := old
        for index in [:64] do
          let completed := if (index*8+8).toUInt64 ≤ m.writeBytes then 8 else
            if (index*8).toUInt64 < m.writeBytes then (m.writeBytes-(index*8).toUInt64).toNat else 0
          let mask := if completed=8 then 0xffffffffffffffff else ((1 : UInt64) <<< (completed*8).toUInt64)-1
          changed := changed.set! index ((old[index]! &&& (~~~mask)) ||| (m.buffer[index]! &&& mask))
        m := {m with sectors:=m.sectors.set! (m.sector.toNat) changed}
    else if word=3 then m := {m with result:=m.barrierResult,bytes:=0}
    else if word=1 then
      if m.sector < 2 then
        m := {m with buffer:=m.sectors[m.sector.toNat]!,result:=m.readResult,bytes:=512}
      else if let some row := m.imageSectors.find? (fun row => row.1=m.sector) then
        m := {m with buffer:=row.2,result:=m.readResult,bytes:=512}
      else m := {m with result:=9,bytes:=0}
    else m := {m with result:=9,bytes:=0}
    return (0,0,m)
  return (212,0,m)

private def evaluateNV : Nat → NVModel → Action → Except String (UInt8 × UInt64 × NVModel)
  | 0,_,_ => .error "finite raw-model fuel exhausted"
  | fuel+1,m,action => do
    match action with
    | .done s v => pure (s,v,m)
    | .bind a next =>
      let (s,v,m) ← evaluateNV fuel m a
      evaluateNV fuel m (next s v)
    | .platform op a b _ _ _ _ next =>
      let (s,v,m) := if op == .physicalRead64 || op == .deviceRead64 then rawRead m a
        else if op == .physicalWrite64 || op == .deviceWrite64 then rawWrite m a b
        else (255,0,m)
      evaluateNV fuel m (next s v)
    | .boundedFoldU64 budget step count initial a b c d next =>
      if budget < count.toNat then evaluateNV fuel m (next Status.budgetExceeded initial)
      else
        let rec go : Nat → UInt32 → UInt64 → NVModel → Except String (UInt8 × UInt64 × NVModel)
          | 0,_,acc,m => evaluateNV fuel m (next 0 acc)
          | left+1,index,acc,m => do
            let (s,v,m) ← evaluateNV fuel m (step index count acc a b c d)
            if s=0 then go left (index+1) v m else evaluateNV fuel m (next s v)
        go count.toNat 0 initial m
    | _ => .error "unsupported raw-model Action"

private def demandNV (condition : Bool) (label : String) : IO Unit :=
  unless condition do throw <| IO.userError label
private def metadataFixture (generation trial attempts : UInt64) : Array UInt64 := Id.run do
  let mut a := #[metadataMagic,1,generation,0,11,trial,(if trial=2 then 0 else 22),attempts,3]
  for _ in [:54] do a := a.push 0
  a := a.push (crcFinish (a.foldl crcWord crcInitial))
  return a
private def runNV (m : NVModel) (a : Action) : IO (UInt8 × UInt64 × NVModel) :=
  IO.ofExcept (evaluateNV 10000 m a)
def nvGuestPolicyTests : IO Unit := do
  let good := metadataFixture 7 noTrial 0
  let staged := metadataFixture 8 1 0
  let mut ram := Array.replicate 2048 0
  for i in [:64] do ram := ram.set! (0x1000/8+i) staged[i]!
  let base : NVModel := {ram,sectors:=#[good,good]}
  let (s,selected,m) ← runNV base (publishMetadata 0 headerBuffer)
  demandNV (s=0 && selected=1 && m.operations == #[2,3] && m.sectors[0]! == good && m.sectors[1]! == staged) "publication requires real write + barrier"
  let (s,_,m) ← runNV {base with writeResult:=5,writeBytes:=17} (publishMetadata 0 headerBuffer)
  demandNV (s=ioFailure && m.operations == #[2] && m.sectors[0]! == good && m.sectors[1]! != good) "partial failed write persistence must be retained"
  let (s,_,m) ← runNV {base with barrierResult:=7} (publishMetadata 0 headerBuffer)
  demandNV (s=ioFailure && m.operations == #[2,3] && m.sectors[0]! == good && m.sectors[1]! == staged) "failed barrier must not acknowledge or roll back observed bytes"
  let (s,_,m) ← runNV {base with stalled:=true} (transaction 3 0)
  demandNV (s=timeout && m.cancellations=1 && m.state=1 && m.operations == #[3]) "bounded pending cancellation without fake barrier success"
  let (s,selected,m) ← runNV base selectedMetadata
  demandNV (s=0 && selected=0 && m.operations == #[1,1]) "fresh valid metadata selection through raw reads"
  let (s,_,m) ← runNV {base with readResult:=9} selectedMetadata
  demandNV (s=ioFailure && m.operations == #[1,1]) "failed metadata reads must not authorize recovery installation"
  let mut confirmed := staged.set! 2 9 |>.set! 3 1 |>.set! 4 22 |>.set! 5 noTrial |>.set! 6 0
  confirmed := confirmed.set! 63 (crcFinish ((confirmed.extract 0 63).foldl crcWord crcInitial))
  let mut context := ram
  for (index,word) in #[(0,contextMagic),(1,1),(2,1),(3,22),(4,8),(5,1)] do
    context := context.set! index word
  let trialBase : NVModel := {ram:=context,sectors:=#[staged,good]}
  let (s,selector,m) ← runNV trialBase (confirm 0 headerBuffer)
  demandNV (s=0 && selector=1 && m.operations == #[2,3] && m.sectors[0]! == staged && m.sectors[1]! == confirmed) "confirmation binds actual boot receipt and requires write/barrier"
  let (s,_,m) ← runNV {trialBase with ram:=context.set! 4 7} (confirm 0 headerBuffer)
  demandNV (s=wrongReceipt && m.operations.isEmpty && m.sectors == trialBase.sectors) "stale boot generation cannot confirm"
  let (s,_,m) ← runNV {trialBase with barrierResult:=7} (confirm 0 headerBuffer)
  demandNV (s=ioFailure && m.operations == #[2,3] && m.sectors[0]! == staged && m.sectors[1]! == confirmed) "failed confirmation barrier may persist bytes without acknowledgement"
  let bytes := (Array.replicate 64 (0 : UInt64)).set! 0 0x0807060504030201
  let discovery := (Array.replicate 64 (0 : UInt64)).set! 0 0x28000000edfe0dd0
  let discoveryCRC := crcFinish ((discovery.extract 0 5).foldl crcWord crcInitial)
  let mut image := (Array.replicate 64 (0 : UInt64)).set! 0 imageMagic |>.set! 1 1
    |>.set! 2 22 |>.set! 3 compatibility |>.set! 4 1 |>.set! 5 ramFirst
    |>.set! 6 40 |>.set! 7 discoveryCRC
    |>.set! 8 4096 |>.set! 9 8 |>.set! 10 8 |>.set! 11 ramFirst
    |>.set! 12 (crcFinish (crcWord crcInitial bytes[0]!))
  image := image.set! 63 (crcFinish ((image.extract 0 63).foldl crcWord crcInitial))
  let payloads := #[(slotFirst 1,image),(slotFirst 1+1,discovery),(slotFirst 1+8,bytes)]
  let attempted := metadataFixture 8 1 2
  let mut replayRAM := ram
  for i in [:64] do replayRAM := replayRAM.set! (0x2000/8+i) attempted[i]!
  let replayBase : NVModel := {ram:=replayRAM,sectors:=#[attempted,good],imageSectors:=payloads}
  let (s,selector,m) ← runNV replayBase (finishInstall 0 metadata0Buffer 22)
  demandNV (s=0 && selector=0 && m.operations == #[3,1,1,1,1] && m.sectors == replayBase.sectors) "lost publication ACK reconciles fresh verified image without resetting attempts or generation"
  demandNV ((m.ram.extract (0x2000/8) (0x2000/8+64)) == attempted) "lost ACK must retain attempted metadata bytes"
  let (s,_,m) ← runNV replayBase (finishInstall 0 metadata0Buffer 23)
  demandNV (s=malformed && m.operations == #[3,1] && m.sectors == replayBase.sectors) "different image identity cannot reuse trial receipt"
  for i in [:64] do replayRAM := replayRAM.set! (0x2000/8+i) good[i]!
  let (s,selector,m) ← runNV {replayBase with ram:=replayRAM,sectors:=#[good,good]} (finishInstall 0 metadata0Buffer 22)
  demandNV (s=0 && selector=1 && m.operations == #[3,1,1,1,1,2,3] && m.sectors[0]! == good && m.sectors[1]! == staged) "new update validates payload then publishes trial via actual write/barrier"
  let changedDiscovery := discovery.set! 4 1
  let (s,_,m) ← runNV {replayBase with imageSectors:=#[(slotFirst 1,image),(slotFirst 1+1,changedDiscovery),(slotFirst 1+8,bytes)]} (finishInstall 0 metadata0Buffer 22)
  demandNV (s=malformed && m.operations == #[3,1,1,1] && m.sectors == replayBase.sectors) "corrupt discovery bytes cannot publish or reconcile image"
  IO.println "BOOT_NV_GUEST_POLICY:PASS real-source update/receipt/confirmation, failed read denial, partial persistence, failed barriers and bounded stalled cancellation"
#eval nvGuestPolicyTests

def recoveryStatusTests : IO Unit := do
  let metadata := metadataFixture 8 1 2
  let good := metadataFixture 7 noTrial 0
  let bytes := (Array.replicate 64 (0 : UInt64)).set! 0 0x0807060504030201
  let discovery := (Array.replicate 64 (0 : UInt64)).set! 0 0x28000000edfe0dd0
  let discoveryCRC := crcFinish ((discovery.extract 0 5).foldl crcWord crcInitial)
  let mut image := (Array.replicate 64 (0 : UInt64)).set! 0 imageMagic |>.set! 1 1
    |>.set! 2 22 |>.set! 3 compatibility |>.set! 4 1 |>.set! 5 ramFirst
    |>.set! 6 40 |>.set! 7 discoveryCRC
    |>.set! 8 4096 |>.set! 9 8 |>.set! 10 8 |>.set! 11 ramFirst
    |>.set! 12 (crcFinish (crcWord crcInitial bytes[0]!))
  image := image.set! 63 (crcFinish ((image.extract 0 63).foldl crcWord crcInitial))
  let base : NVModel := {sectors := #[metadata,good],imageSectors :=
    #[(slotFirst 1,image),(slotFirst 1+1,discovery),(slotFirst 1+8,bytes)]}
  let (s,v,m) ← runNV {base with barrierResult := 7} (Lemma.Boot.Recovery.imageStatus 1 22)
  demandNV (s=ioFailure && v=0 && m.operations == #[3]) "failed barrier cannot acknowledge observed trial metadata"
  let (s,v,m) ← runNV base (Lemma.Boot.Recovery.imageStatus 1 22)
  demandNV (s=0 && v=2 && m.operations == #[3,1,1,1,1,1,1]) "successful status must establish barrier and verify full image"
  let (s,v,m) ← runNV {base with imageSectors := #[(slotFirst 1,image),(slotFirst 1+1,discovery),(slotFirst 1+8,bytes.set! 0 1)]} (Lemma.Boot.Recovery.imageStatus 1 22)
  demandNV (s=malformed && v=0 && m.operations == #[3,1,1,1,1,1,1]) "corrupt observed payload cannot reconcile durability"
  let (s,v,m) ← runNV base (Lemma.Boot.Recovery.imageStatus 1 23)
  demandNV (s=wrongReceipt && v=0 && m.operations == #[3,1,1]) "image receipt identity cannot change on reconciliation"
  demandNV (m.sectors == base.sectors) "status must not reset generation or attempt counters"
  IO.println "BOOT_RECOVERY_STATUS:PASS actual barrier/integrity/read-only reconciliation; failed barrier/corrupt image/wrong receipt rejected"
#eval recoveryStatusTests
