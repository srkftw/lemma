import Lemma.Platform.LemmaSim.BootHealth
import Std.Data.HashMap

/-! Host-only execution of the actual product health Actions. The fixture
supplies raw RAM, controller registers and external barrier outcomes. It never
selects, confirms or recovers an image on behalf of the production policy.
These checks do not establish CPU, Sv39, RTL boot or physical behavior. -/
namespace BootHealthFixture
open Lemma.Core0.Memory Lemma.Kernel Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  sectors : Array (Array UInt64) := #[Array.replicate 64 0, Array.replicate 64 0]
  buffer : Array UInt64 := Array.replicate 64 0
  controllerState : UInt64 := 0
  sector : UInt64 := 0
  request : UInt64 := 0
  result : UInt64 := 0
  bytes : UInt64 := 0
  pendingPolls : Nat := 0
  barrierError : UInt64 := 0
  operations : Array UInt64 := #[]
  accesses : Nat := 0
  uart : Array UInt8 := #[]

def read (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def write (s : State) (a v : UInt64) : State :=
  {s with words := if v = 0 then s.words.erase a else s.words.insert a v}

private def rawRead (s : State) (a : UInt64) : UInt8 × UInt64 × State := Id.run do
  if a % 8 != 0 then return (8,0,s)
  if Lemma.Boot.Product.nvBase ≤ a && a < Lemma.Boot.Product.nvBase + 0x400 then
    let o := a - Lemma.Boot.Product.nvBase
    if o = 24 && s.controllerState = 1 then
      if s.pendingPolls > 0 then return (0,1,{s with pendingPolls := s.pendingPolls-1})
      return (0,2,{s with controllerState := 2})
    if 0x200 ≤ o then return (0,s.buffer[((o-0x200)/8).toNat]!,s)
    let v := if o=0 then 0x564e424c else if o=8 then 1 else
      if o=16 then 65544 else if o=24 then s.controllerState else
      if o=48 || o=56 then s.request else if o=64 then s.result else
      if o=72 then s.bytes else 0
    return (0,v,s)
  if (0x80400000 ≤ a && a < 0x80510000) ||
     (0x82000000 ≤ a && a < 0x84000000) ||
     (0x81fc0000 ≤ a && a < 0x81fc4000) ||
     (DeviceABI.paperBase ≤ a && a < DeviceABI.paperBase+0x1000) then
    return (0,read s a,s)
  return (7,0,s)

private def rawWrite (s : State) (a v : UInt64) : UInt8 × UInt64 × State := Id.run do
  if a % 8 != 0 then return (8,0,s)
  if Lemma.Boot.Product.nvBase ≤ a && a < Lemma.Boot.Product.nvBase+0x400 then
    let o := a-Lemma.Boot.Product.nvBase
    if o=32 then return (0,0,{s with sector := v})
    if o=80 then
      if s.controllerState=2 && s.request=v then
        return (0,0,{s with controllerState := 0})
      return (212,0,s)
    if 0x200 ≤ o then
      if s.controllerState=0 then
        return (0,0,{s with buffer := s.buffer.set! (((o-0x200)/8).toNat) v})
      return (212,0,s)
    if o=40 && s.controllerState=0 then
      let s := {s with controllerState := 1, request := s.request+1, pendingPolls := 2, operations := s.operations.push v}
      if v=1 && s.sector<2 then
        return (0,0,{s with buffer := s.sectors[s.sector.toNat]!,result := 0,bytes := 512})
      if v=2 && s.sector<2 then
        return (0,0,{s with sectors := s.sectors.set! (s.sector.toNat) s.buffer, result := 0,bytes := 512})
      if v=3 then return (0,0,{s with result := s.barrierError,bytes := 0})
    return (212,0,s)
  if (0x80400000 ≤ a && a < 0x80510000) ||
     (0x82000000 ≤ a && a < 0x84000000) ||
     (0x81fc0000 ≤ a && a < 0x81fc4000) then return (0,0,write s a v)
  return (7,0,s)

partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute ref first
    execute ref (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    if budget < count.toNat then execute ref (next 9 initial) else
    let mut result : UInt8 × UInt64 := (0,initial)
    for i in [:count.toNat] do
      if result.1=0 then result ← execute ref (step i.toUInt32 count result.2 a b c d)
    execute ref (next result.1 result.2)
  | .platform op a b _ _ _ _ next =>
    let old ← ref.get
    if old.accesses ≥ 2000000 then throw <| IO.userError "finite health fixture access limit"
    let old := {old with accesses := old.accesses+1}
    let (s,v,updated) := if op == .physicalRead64 || op == .deviceRead64 then rawRead old a
      else if op == .physicalWrite64 || op == .deviceWrite64 then rawWrite old a b
      else (255,0,old)
    ref.set updated
    execute ref (next s v)
  | .uartReadStatus next => execute ref (next 0 0x60)
  | .uartWriteByte byte next =>
    ref.modify fun s => {s with uart := s.uart.push byte}
    execute ref (next 0)
  | _ => throw <| IO.userError "unsupported health fixture Action"

def success (ref : IO.Ref State) (a : Action) : IO UInt64 := do
  let (s,v) ← execute ref a
  if s != 0 then throw <| IO.userError s!"health Action failed: {s}"
  pure v
def demand (b : Bool) (reason : String) : IO Unit :=
  unless b do throw <| IO.userError reason

-- Independent byte/bit CRC, deliberately not the guest's unrolled crcWord.
private def checksum (words : Array UInt64) : UInt64 := Id.run do
  let mut c : UInt32 := 0xffffffff
  for word in words do
    for byte in [:8] do
      c := c ^^^ ((word >>> (byte*8).toUInt64) &&& 255).toUInt32
      for _ in [:8] do
        c := if c &&& 1 = 0 then c >>> 1 else (c >>> 1) ^^^ 0xedb88320
  return (c ^^^ 0xffffffff).toUInt64
private def metadata (generation trial : UInt64) : Array UInt64 := Id.run do
  let mut a := Array.replicate 64 (0 : UInt64)
  for (i,v) in #[(0,0x31444d42414d454c),(1,1),(2,generation),(3,0),(4,11),
    (5,trial),(6,if trial=1 then 22 else 0),(7,0),(8,3)] do a := a.set! i v
  return a.set! 63 (checksum (a.extract 0 63))

def setup : IO (State × UInt64 × UInt64 × UInt64) := do
  let ref ← IO.mkRef ({} : State)
  discard <| success ref (Frames.configure 8192 8192 4)
  discard <| success ref Frames.init
  let store ← success ref (AddressSpace.create 2)
  let notebook ← success ref (AddressSpace.create 3)
  discard <| success ref Task.init
  let table ← success ref Task.table
  -- Fixture publication supplies two independent, genuinely allocated live AS
  -- handles. The policy must subsequently resolve both generations/purposes.
  for (offset,descriptor,image) in #[(0,store,0),(512,notebook,1)] do
    ref.modify fun s => write (write (write s (table+offset) descriptor)
      (table+offset+8) 2) (table+offset+96) image
  for (offset,v) in #[(0,0x31585443414d454c),(8,1),(16,1),(24,22),(32,8),(40,1)] do
    ref.modify fun s => write s (0x81fc0000+offset) v
  ref.modify fun s => {s with sectors := #[metadata 8 1,metadata 7 2]}
  discard <| success ref (BootHealth.configure store notebook)
  return (← ref.get,store,notebook,table)

private def complete (s : State) : State :=
  write (write (write (write s (DeviceABI.paperBase+160) 9)
    (DeviceABI.paperBase+112) 9) (DeviceABI.paperBase+136) 1650)
    (DeviceABI.paperBase+144) 2200

def check : IO Unit := do
  let (base,store,notebook,table) ← setup
  let ref ← IO.mkRef base
  discard <| success ref BootHealth.step
  demand ((← ref.get).operations.isEmpty && read (← ref.get) BootHealth.state=1)
    "no completed panel must leave trial pending without external I/O"
  let full := complete base
  for altered in #[write full (DeviceABI.paperBase+112) 10,
    write full (DeviceABI.paperBase+16) 1,write full (DeviceABI.paperBase+24) 7,
    write full (DeviceABI.paperBase+120) 1,write full (DeviceABI.paperBase+136) 1649,
    write full (DeviceABI.paperBase+144) 2199] do
    ref.set altered
    discard <| success ref BootHealth.step
    demand ((← ref.get).operations.isEmpty && read (← ref.get) BootHealth.state=1)
      "partial, pending, mismatched or erroneous display cannot authorize confirmation"
  for altered in #[write full (table+8) 6,write full (table+512+96) 0,
    write full (BootHealth.state+8) (store+8192)] do
    ref.set altered
    let (s,_) ← execute ref BootHealth.step
    demand (s != 0 && (← ref.get).operations.isEmpty)
      "dead service, wrong image or stale AS handle cannot authorize confirmation"
  ref.set full
  discard <| success ref BootHealth.step
  let accepted ← ref.get
  let expected := (metadata 9 2).set! 3 1 |>.set! 4 22
  let expected := expected.set! 63 (checksum (expected.extract 0 63))
  demand (accepted.operations == #[1,1,2,3] && accepted.sectors[1]! == expected &&
    read accepted BootHealth.state=3 && read accepted (BootHealth.state+24)=0 &&
    read accepted (BootHealth.state+32)=9 && !accepted.uart.isEmpty)
    "actual health completion must bind fresh boot receipt and exact write/barrier"
  discard <| success ref BootHealth.step
  demand ((← ref.get).operations == accepted.operations)
    "confirmed health must not repeat an irreversible publication"
  ref.set {full with barrierError := 7}
  discard <| success ref BootHealth.step
  let failed ← ref.get
  demand (failed.operations == #[1,1,2,3] && failed.sectors[1]! == expected &&
    read failed BootHealth.state=4 && read failed (BootHealth.state+24)=Lemma.Boot.Product.ioFailure.toUInt64)
    "failed barrier must preserve changed bytes without confirmed health"
  discard <| success ref BootHealth.step
  demand ((← ref.get).operations == failed.operations)
    "failed health must not resubmit or manufacture success on the next scheduler step"
  ref.set (write full 0x81fc0020 7)
  discard <| success ref BootHealth.step
  demand ((← ref.get).operations == #[1,1] && read (← ref.get) BootHealth.state=4)
    "stale boot receipt may read metadata but must never write confirmation"
  ref.set (write base 0x81fc0028 0)
  discard <| success ref (BootHealth.configure store notebook)
  discard <| success ref BootHealth.step
  demand ((← ref.get).operations.isEmpty && read (← ref.get) BootHealth.state=0)
    "known-good boot never needs a confirmation publication"
  IO.println "PRODUCT_BOOT_HEALTH:PASS actual owned services/full refresh/receipt/write+barrier; failed barrier retains bytes; stale/dead/partial denial; no repeated publication"

end BootHealthFixture
#eval BootHealthFixture.check
