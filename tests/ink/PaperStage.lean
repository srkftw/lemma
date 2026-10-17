import Lemma.Platform.LemmaSim.DeviceService
import Std.Data.HashMap

/- Host-only finite RAM and literal PIO observer evaluating the real maintained
Actions. It does not emulate paper pixels or implement target transport. -/
namespace NextBulkFixture
open Lemma.Core0.Memory Lemma.Kernel Lemma.Kernel.Memory Lemma.User
open Lemma.Platform.LemmaSim
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  pio : Array (UInt64 × UInt64) := #[]
  ramWrites : Array UInt64 := #[]
  commands : Nat := 0
  errorAt : Nat := 0
  readFault : Option UInt64 := none
  paperVersion : UInt64 := 2
  paperStaging : UInt64 := 3584
  operations : Nat := 0
def word (s : State) (a : UInt64) := s.words.getD a 0
def put (s : State) (a v : UInt64) : State := {s with words := s.words.insert a v}
def byte (s : State) (a : UInt64) := (word s (a-a%8) >>> (a%8*8)) &&& 255
def putByte (s : State) (a v : UInt64) :=
  let shift := a%8*8
  put s (a-a%8) ((word s (a-a%8) &&& ~~~((255:UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))
def require (ok : Bool) (message : String) : IO Unit := if ok then pure () else throw <| IO.userError message
partial def run (r : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind a next => let (s,v) ← run r a; run r (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "fold exceeds declared fixture budget"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let (s,v) ← run r (step i.toUInt32 count value a b c d)
        status := s; value := v
    run r (next status value)
  | .platform op a b _ _ _ _ next =>
    r.modify fun s => {s with operations := s.operations+1}
    require ((← r.get).operations < 6000000) "finite Action fixture exhausted"
    if op == .installSatp then run r (next 0 0) else
    if op == .deviceRead64 then
      require (a == DeviceABI.paperBase+32 || a == DeviceABI.paperBase+40 || a == DeviceABI.paperBase+24 || a == DeviceABI.paperBase || a == DeviceABI.paperBase+8 || a == DeviceABI.paperBase+184) "unexpected PIO read"
      let s ← r.get
      let v := if a == DeviceABI.paperBase then DeviceABI.paperMagic else if a == DeviceABI.paperBase+8 then s.paperVersion else if a == DeviceABI.paperBase+184 then s.paperStaging else if a == DeviceABI.paperBase+32 then 1650 else if a == DeviceABI.paperBase+40 then 2200
        else if s.errorAt != 0 && s.commands == s.errorAt then 9 else 0
      run r (next 0 v)
    else if op == .deviceWrite64 then
      require (DeviceABI.paperBase ≤ a && a < DeviceABI.paperBase+4096 && a%8 == 0) "unexpected PIO write"
      r.modify fun s => {s with pio := s.pio.push (a,b), commands := s.commands + (if a == DeviceABI.paperBase+104 then 1 else 0)}
      run r (next 0 0)
    else
      require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000)) "physical access outside finite RAM"
      if op == .physicalRead64 || op == .physicalWrite64 then require (a%8 == 0) "unaligned physical64"
      if op == .physicalRead64 || op == .physicalRead8 then
        if (← r.get).readFault == some a then run r (next 95 0)
        else
          let s ← r.get
          run r (next 0 (if op == .physicalRead64 then word s a else byte s a))
      else if op == .physicalWrite64 then
        r.modify fun s => {(put s a b) with ramWrites := s.ramWrites.push a}
        run r (next 0 0)
      else if op == .physicalWrite8 then
        r.modify fun s => {(putByte s a b) with ramWrites := s.ramWrites.push a}
        run r (next 0 0)
      else throw <| IO.userError "unexpected physical primitive"
  | _ => throw <| IO.userError "unexpected Action constructor"
def success (r : IO.Ref State) (a : Action) : IO UInt64 := do
  let (s,v) ← run r a; require (s == 0) s!"setup status{s}"; pure v
def reset (s : State) := {s with pio := #[], ramWrites := #[], commands := 0, operations := 0}
def pointer : UInt64 := 0x10a000
def pixels (i j : UInt64) := 0x0102030405060708 ^^^ (i*0x1122334455667788) ^^^ j
def batch (s : State) (pa count : UInt64) : State := Id.run do
  let mut s := put (put (put (put s pa 2) (pa+8) count) (pa+16) 0) (pa+24) 0
  for i in [:7] do
    let fields := pa+32+i.toUInt64*32
    s := put (put (put (put s fields (i.toUInt64*32)) (fields+8) 16) (fields+16) 32) (fields+24) 32
    for j in [:64] do s := put s (pa+256+i.toUInt64*512+j.toUInt64*8) (pixels i.toUInt64 j.toUInt64)
  return reset s
def expected (count : Nat) : Array (UInt64 × UInt64) := Id.run do
  let mut writes := #[]
  for i in [:count] do
    for (offset,value) in #[(64,i.toUInt64*32),(72,16),(80,32),(88,32),(96,512)] do
      writes := writes.push (DeviceABI.paperBase+offset,value)
    for j in [:64] do writes := writes.push (DeviceABI.paperBase+0xe00+j.toUInt64*8,pixels i.toUInt64 j.toUInt64)
    writes := writes.push (DeviceABI.paperBase+104,1)
  return writes
def check : IO Unit := do
  let r ← IO.mkRef ({} : State)
  require ((← run r Lemma.Drivers.Paper.initializeNext) == ((0 : UInt8),(1650 : UInt64) ||| ((2200 : UInt64) <<< 32))) "actual Paper2 discovery"
  for version in #[0,1,3] do
    r.set { ({} : State) with paperVersion := version }
    require ((← run r Lemma.Drivers.Paper.initializeNext) == (170,0)) "old/arbitrary controller admitted by Paper2"
    require ((← r.get).pio.isEmpty) "invalid controller produced a write"
  for stage in #[0,2048,3576,3592,0xffffffffffffffff] do
    r.set { ({} : State) with paperStaging := stage }
    require ((← run r Lemma.Drivers.Paper.initializeNext) == (170,0)) "noncanonical actual staging admitted"
    require ((← r.get).pio.isEmpty) "invalid staging produced a write"
  r.set {}
  discard <| success r (Frames.configure 512 32 4)
  discard <| success r Frames.init
  let descriptor ← success r (AddressSpace.create 2)
  let user ← success r (Frames.allocate 2 4)
  let pa ← success r (Frames.resolvePurpose 2 user 4)
  discard <| success r (AddressSpace.mapUser descriptor pointer user 3)
  discard <| success r Objects.init
  discard <| success r (Capability.attach descriptor)
  let key ← success r (Objects.createEndpoint descriptor)
  let cap ← success r (Capability.grantBoot descriptor key CapabilityABI.endpointCall)
  discard <| success r (Capability.activate descriptor)
  discard <| success r (DeviceService.configure key 0 0)
  let tile := word (← r.get) (DeviceService.state+24)
  let tilePA ← success r (Frames.resolvePurpose 1 tile 1)
  let original := batch (← r.get) pa 7
  r.set original
  require ((← run r (DeviceService.surfaceV2Next descriptor cap 5 pointer 7 0)) == (0,7)) "seven tile result"
  let final ← r.get
  require (final.pio == expected 7) "metadata/payload/controller command order differs from independent literal oracle"
  require (final.commands == 7) "tile count differs"
  require (final.ramWrites.size == 480) "whole prefix was not copied exactly once"
  for i in [:3840] do require (byte final (tilePA+i.toUInt64) == byte original (pa+i.toUInt64)) "immutable copied prefix differs"
  r.set original
  for i in [:7] do
    require ((← run r (DeviceService.surfaceV2Next descriptor cap 1 (pointer+32+i.toUInt64*32)
      (pointer+256+i.toUInt64*512) 0)) == (0,512)) "ordinary reference upload failed"
  let ordinary ← r.get
  require (ordinary.pio == final.pio) "batch pixels or controller writes differ from seven ordinary uploads"
  require (final.operations < ordinary.operations) "batch did not reduce actual checked primitive work"
  IO.println s!"PRIMITIVE_WORK ordinary7={ordinary.operations} batch7={final.operations}; exact same ordered controller bytes"
  for (slot,value,status) in #[(pa,1,ABI.invalidArgument),(pa+8,6,ABI.invalidArgument),
      (pa+16,1,ABI.invalidArgument),(pa+24,1,ABI.invalidArgument),
      (pa+32+6*32+16,0,Lemma.Drivers.Paper.invalid),
      (pa+32+6*32,1640,Lemma.Drivers.Paper.invalid),
      (DeviceService.state+24,descriptor,ABI.invalidArgument),
      (DeviceService.state+24,tile+512,ABI.kernelFatal),
      (Frames.record ((tilePA-Frames.pool)/4096)+8,2,ABI.kernelFatal)] do
    r.set (put original slot value)
    let result ← run r (DeviceService.surfaceV2Next descriptor cap 5 pointer 7 0)
    require (result.1 == status && result.2 == 0) s!"invalid guard slot{slot} result{result} expected{status}"
    require ((← r.get).pio.isEmpty) "invalid late metadata or owned buffer reached controller"
  for (p,count,reserved,status) in #[(pointer,0,0,ABI.invalidArgument),(pointer,8,0,ABI.invalidArgument),
      (pointer+8,7,0,ABI.invalidRange),(pointer,7,1,ABI.invalidArgument),
      (pointer+4096,7,0,ABI.missingMapping)] do
    r.set original
    let result ← run r (DeviceService.surfaceV2Next descriptor cap 5 p count reserved)
    require (result.1 == status && result.2 == 0 && (← r.get).pio.isEmpty) "range/count/reserved reached controller"
  r.set {original with readFault := some (pa+3832)}
  require ((← run r (DeviceService.surfaceV2Next descriptor cap 5 pointer 7 0)).1 == ABI.kernelFatal) "late read failure ignored"
  require ((← r.get).pio.isEmpty) "failed complete prefix copy reached controller"
  r.set original
  require ((← run r (DeviceService.surface descriptor cap 5 pointer 7 0)) == (16,0)) "legacy surface admitted op5"
  require ((← r.get).pio.isEmpty) "legacy rejection reached controller"
  r.set {original with errorAt := 3}
  require ((← run r (DeviceService.surfaceV2Next descriptor cap 5 pointer 7 0)) == (Lemma.Drivers.Paper.deviceError,2)) "controller error lost successful prefix count"
  require ((← r.get).pio == expected 3) "controller failure executed subsequent tile"
  r.set original
  require ((← run r (Lemma.Drivers.Paper.uploadOffsetNext tile 3584 0 0 32 32)) == (0,512)) "last legal offset rejected"
  for offset in #[3585,3592,0xfffffffffffffff8] do
    r.set original
    require ((← run r (Lemma.Drivers.Paper.uploadOffsetNext tile offset 0 0 32 32)) == (Lemma.Drivers.Paper.invalid,0)) "offset alignment/bounds ignored"
    require ((← r.get).pio.isEmpty) "invalid offset reached controller"
  IO.println "PASS actual Paper-v2/Surface-v2 successor Actions: independent version/staging discovery; owned preflight complete prefix, seven literal ordered uploads, late metadata/alias/generation/purpose/range/copy faults before PIO, exact controller failure prefix, legacy op5 rejection"
end NextBulkFixture
def main := NextBulkFixture.check
