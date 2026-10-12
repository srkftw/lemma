import Lemma.Kernel.Syscall
import Lemma.Kernel.Process
import Lemma.Ink.Rasterizer
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only execution fixture for production owned-memory and ink Actions.
This supplies a finite byte-addressed physical RAM model and records SATP writes;
it does not model CPU translation, interrupts, devices or persistent storage.
The independent expectations below do not call production accounting formulas.
Target compilation/boots remain separate evidence. Never imported by a guest. -/
namespace OwnedCapacityFixture
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  operations : Nat := 0
  satp : UInt64 := 0

def read64 (state : State) (address : UInt64) : UInt64 :=
  state.words.getD address 0

def write64 (state : State) (address value : UInt64) : State :=
  { state with words := if value = 0 then state.words.erase address
                       else state.words.insert address value }

def allowed (address : UInt64) : Bool :=
  (0x80400000 ≤ address && address < 0x80510000) ||
  (0x82000000 ≤ address && address < 0x84000000) ||
  (0x10000 ≤ address && address < 0x40000000)

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status, value)
  | .bind first next =>
    let (status, value) ← execute state first
    execute state (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then execute state (next 9 initial) else
    let mut acc := initial
    let mut status : UInt8 := 0
    for index in [:count.toNat] do
      if status = 0 then
        let result ← execute state (step index.toUInt32 count acc c0 c1 c2 c3)
        status := result.1
        acc := result.2
    execute state (next status acc)
  | .platform op a b _ _ _ _ next =>
    let old ← state.get
    if old.operations ≥ 50000000 then throw <| IO.userError "fixture operation budget exhausted"
    state.set { old with operations := old.operations + 1 }
    if op == .installSatp then
      state.modify fun s => { s with satp := a }
      execute state (next 0 0)
    else
      if !allowed a then throw <| IO.userError s!"fixture address outside RAM: {a}"
      match op with
      | .physicalRead64 | .virtualRead64 =>
        if a % 8 ≠ 0 then throw <| IO.userError "unaligned fixture read64"
        execute state (next 0 (read64 (← state.get) a))
      | .physicalWrite64 | .virtualWrite64 =>
        if a % 8 ≠ 0 then throw <| IO.userError "unaligned fixture write64"
        state.modify fun s => write64 s a b
        execute state (next 0 0)
      | .physicalRead8 | .virtualRead8 =>
        let value := (read64 (← state.get) (a - a % 8) >>> (a % 8 * 8)) &&& 255
        execute state (next 0 value)
      | .physicalWrite8 | .virtualWrite8 =>
        state.modify fun s =>
          let shift := a % 8 * 8
          let old := read64 s (a - a % 8)
          write64 s (a - a % 8) ((old &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift))
        execute state (next 0 0)
      | _ => throw <| IO.userError "unsupported fixture platform operation"
  | _ => throw <| IO.userError "unsupported fixture Action"

def success (state : IO.Ref State) (action : Action) : IO UInt64 := do
  let (status, value) ← execute state action
  if status ≠ 0 then throw <| IO.userError s!"unexpected Action status {status}"
  pure value

def rejected (state : IO.Ref State) (action : Action) : IO Unit := do
  let (status, _) ← execute state action
  if status = 0 then throw <| IO.userError "invalid Action accepted"

def require (value : Bool) (message : String) : IO Unit :=
  if value then pure () else throw <| IO.userError message

def checkFoldStatus : IO Unit := do
  let state ← IO.mkRef ({} : State)
  let step := fun (_ _ : UInt32) (_ _ _ _ _ : UInt64) => Action.done 10 42
  let (status, value) ← execute state (.boundedFoldU64 2 step 2 7 0 0 0 0 fun s v => .done s v)
  require (status == 10 && value == 42) "boundedFold must preserve nonzero callback status"
  IO.println "OWNED_FIXTURE_FOLD_STATUS:PASS status10 preserved"

def checkExpanded : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 8192 8192 4)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let memory ← state.get
  require (read64 memory (address + 8) == 2 && read64 memory (address + 80) == 1024 &&
    read64 memory (address + 1408) == 8) "expanded descriptor layout"
  require ((← success state (Frames.ownedCount 2)) == 21) "13 tables plus 8 registry pages"
  require ((← success state (Frames.ownedCount 1)) == 1) "descriptor charged to owner1"
  let mut finalHandle : UInt64 := 0
  let mut finalVA : UInt64 := 0
  for index in [:520] do
    let va := (0x40000 : UInt64) + index.toUInt64 * 4096 +
      (if index ≥ 192 then 4096 else 0)
    let handle ← success state (Frames.allocate 2 4)
    discard <| success state (AddressSpace.mapUser descriptor va handle 3)
    finalVA := va
    finalHandle := handle
  discard <| success state (AddressSpace.lookup descriptor finalVA 2)
  require ((← success state (Frames.ownedCount 2)) == 542) "520 data + 21 base + one extra L0 table"
  -- Four separately owned U stack leaves. The lower/upper guard PTEs remain
  -- literally absent, and a trusted map request cannot populate them.
  let guardHandle ← success state (Frames.allocate 2 5)
  rejected state (AddressSpace.mapUser descriptor 0x3fff9000 guardHandle 3)
  rejected state (AddressSpace.mapUser descriptor 0x3fffe000 guardHandle 3)
  require ((← success state (Frames.mappingCount 2 guardHandle)) == 0) "rejected guard mapping took no pin"
  discard <| success state (AddressSpace.mapUser descriptor 0x3fffa000 guardHandle 3)
  for index in [:3] do
    let handle ← success state (Frames.allocate 2 5)
    discard <| success state (AddressSpace.mapUser descriptor (0x3fffb000 + index.toUInt64 * 4096) handle 3)
  for index in [:4] do
    discard <| success state (AddressSpace.lookup descriptor (0x3fffa000 + index.toUInt64 * 4096) 2)
  rejected state (AddressSpace.lookup descriptor 0x3fff9000 1)
  rejected state (AddressSpace.lookup descriptor 0x3fffe000 1)
  let stackTable := read64 (← state.get) (address + 296)
  require (read64 (← state.get) (stackTable + 505 * 8) == 0 &&
    read64 (← state.get) (stackTable + 510 * 8) == 0) "true unmapped stack guards"
  require ((← success state (Frames.ownedCount 2)) == 546) "four User stack frames charged"
  discard <| success state (Lemma.Kernel.Syscall.ownedArenaAddress 0x7ff000)
  rejected state (Lemma.Kernel.Syscall.ownedArenaAddress 0x800000)
  rejected state (Lemma.Kernel.Syscall.ownedArenaAddress 0x100000)
  rejected state (Frames.resolve 3 finalHandle)
  rejected state (Frames.resolve 2 (finalHandle + 8192))
  rejected state (Frames.release 2 finalHandle)
  let original ← state.get
  let registry0 := read64 original (address + 1424)
  let registryPA0 := read64 original (address + 1432)
  state.modify fun s => write64 (write64 s (address + 1440) registry0) (address + 1448) registryPA0
  rejected state (AddressSpace.base descriptor)
  state.set original
  state.modify fun s => write64 s (address + 1424) (registry0 + 8192)
  rejected state (AddressSpace.base descriptor)
  state.set original
  discard <| success state (AddressSpace.destroy descriptor)
  require ((← success state (Frames.ownedCount 1)) == 0 &&
    (← success state (Frames.ownedCount 2)) == 0) "complete expanded teardown"
  require (read64 (← state.get) Frames.accounting == 8192) "all expanded frames recovered"
  IO.println s!"OWNED_CAPACITY_EXPANDED:PASS operations={(← state.get).operations} mapped=524 user_stack_pages=4"

def checkLegacy : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 512 32 2)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let memory ← state.get
  require (read64 memory (address + 8) == 1 && read64 memory (address + 80) == 32 &&
    read64 memory (address + 1408) == 0) "legacy descriptor unchanged"
  for index in [:21] do
    let handle ← success state (Frames.allocate 2 4)
    discard <| success state (AddressSpace.mapUser descriptor (0x40000 + index.toUInt64 * 4096) handle 3)
  rejected state (Frames.allocate 2 4)
  rejected state (Lemma.Kernel.Syscall.ownedArenaAddress 0x100000)
  discard <| success state (AddressSpace.destroy descriptor)
  require (read64 (← state.get) Frames.accounting == 512) "legacy quota and teardown preserved"
  IO.println "OWNED_CAPACITY_LEGACY:PASS"

/-- Current ordinary boot uses the same finite512-frame/quota32 pool with a
real four-page owned kernel stack. Expectations below spell out every page;
no displayed capacity field or production accounting helper supplies the sum. -/
def checkCurrentLegacyStack : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 512 32 4)
  require ((← success state Frames.runtimeStackPages) == 4) "current kernel stack selection"
  rejected state (Frames.configure 512 33 4)
  rejected state (Frames.configure 512 32 3)
  require ((← success state Frames.runtimeStackPages) == 4) "invalid constructor must leave previous selection intact"
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let result ← success state (Frames.allocateContiguous4 2 1)
  let first := read64 (← state.get) result
  let second := read64 (← state.get) (result + 8)
  let third := read64 (← state.get) (result + 16)
  let fourth := read64 (← state.get) (result + 24)
  let physical ← success state (Frames.resolvePurpose 2 first 1)
  require ((← success state (Frames.resolvePurpose 2 second 1)) == physical + 4096 &&
    (← success state (Frames.resolvePurpose 2 third 1)) == physical + 8192 &&
    (← success state (Frames.resolvePurpose 2 fourth 1)) == physical + 12288)
    "four independently owned contiguous stack frames"
  for (slot,value) in #[(2400,first),(2480,second),(2488,third),(2496,fourth),
      (2504,4),(2512,physical),(2408,physical + 16368)] do
    state.modify fun s => write64 s (address + slot) value
  state.modify fun s => write64 (write64 s physical Lemma.Kernel.Loader.stackCanary)
    (physical + 16376) Lemma.Kernel.Loader.stackCanary
  --1 data+2 User stack+1 text, separately mapped and owned.
  for (va,purpose,permissions) in #[(0x20000,4,3),(0x3fffc000,5,3),
      (0x3fffd000,5,3),(0x10000,3,5)] do
    let handle ← success state (Frames.allocate 2 purpose)
    discard <| success state (AddressSpace.mapUser descriptor va handle permissions)
  require ((← success state (Frames.ownedCount 2)) == 19) "11 tables+1 data+2 User stack+4 kernel stack+1 text"
  require ((← success state (Frames.ownedCount 1)) == 1 &&
    (← success state Frames.remaining) == 492) "separate descriptor makes20 actual global frames"
  require ((← success state (Lemma.Kernel.Process.validateStack descriptor)) == physical + 16368)
    "published current stack top"
  let original ← state.get
  for (slot,value) in #[(physical,0),(physical + 16376,0),(address + 2488,second),
      (address + 2496,fourth + 512),(address + 2408,physical + 8192),(address + 2400,0)] do
    state.modify fun s => write64 s slot value
    rejected state (Lemma.Kernel.Process.validateStack descriptor)
    state.set original
  discard <| success state (Frames.pin 2 first)
  rejected state (Lemma.Kernel.Process.validateStack descriptor)
  discard <| success state (Frames.unpin 2 first)
  discard <| success state (Lemma.Kernel.Loader.teardown descriptor)
  require ((← success state (Frames.ownedCount 2)) == 0 &&
    (← success state (Frames.ownedCount 1)) == 0 && (← success state Frames.remaining) == 512)
    "inactive four-page stack/leaf/descriptor teardown restores exact supply"
  -- Genuine failure state before contiguous stack publication: cleanup still
  -- reclaims the eleven AS table frames and the separate owner1 descriptor.
  let empty ← success state (AddressSpace.create 3)
  let emptyAddress ← success state (AddressSpace.base empty)
  state.modify fun s => write64 s (emptyAddress + 2504) 4
  discard <| success state (Lemma.Kernel.Loader.teardown empty)
  require ((← success state Frames.remaining) == 512 &&
    (← success state (Frames.ownedCount 3)) == 0) "empty unpublished four-page constructor cleanup"
  IO.println "OWNED_CURRENT_KERNEL_STACK:PASS allocated4 usable16352 ownerbase18/global19;canaries/generation/contiguity/pins/teardown"

/-- Host Action-model regression for the exact silicon development boot choice.
The literal workload charges exercise the actual allocator and map policies;
this is separate from execution by the RTL CPU. -/
def checkSiliconDevelopment : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 1024 128 4)
  for (amount,quota,pages) in #[(1024,127,4),(1024,129,4),(1024,128,2),(2048,128,4)] do
    rejected state (Frames.configure amount quota pages)
  require ((← success state Frames.runtimeCount) == 1024 &&
    (← success state Frames.runtimeQuota) == 128 &&
    (← success state Frames.runtimeStackPages) == 4) "exact silicon boot selection survives rejected constructors"
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let middleHandle := read64 (← state.get) (address + 136)
  let middle ← success state (Frames.resolvePurpose 2 middleHandle 2)
  require (read64 (← state.get) (middle + 17 * 8) == 0x208800c7 &&
    read64 (← state.get) (middle + 18 * 8) == 0) "exact4MiB S-only pool map, no extra32MiB aliases"
  require ((← success state (Frames.ownedCount 2)) == 21) "13 table + 8 registry frames"
  let stackResult ← success state (Frames.allocateContiguous4 2 1)
  let memory ← state.get
  let kernelStack := (List.range 4).map fun i => read64 memory (stackResult + i.toUInt64 * 8)
  for index in [:12] do
    let handle ← success state (Frames.allocate 2 3)
    discard <| success state (AddressSpace.mapUser descriptor (0x1000000 + index.toUInt64 * 4096) handle 5)
  let data ← success state (Frames.allocate 2 4)
  discard <| success state (AddressSpace.mapUser descriptor 0x20000 data 3)
  for index in [:4] do
    let handle ← success state (Frames.allocate 2 5)
    discard <| success state (AddressSpace.mapUser descriptor (0x3fffa000 + index.toUInt64 * 4096) handle 3)
  for index in [:41] do
    let handle ← success state (Frames.allocate 2 4)
    discard <| success state (AddressSpace.mapUser descriptor (0x300000 + index.toUInt64 * 4096) handle 3)
  for index in [:40] do
    let handle ← success state (Frames.allocate 2 4)
    discard <| success state (AddressSpace.mapUser descriptor (0x110000 + index.toUInt64 * 4096) handle 3)
  require ((← success state (Frames.ownedCount 2)) == 125) "literal512x640 notebook charges including two new L0 tables"
  discard <| success state (AddressSpace.lookup descriptor 0x328000 2)
  discard <| success state (AddressSpace.lookup descriptor 0x137000 2)
  rejected state (AddressSpace.lookup descriptor 0x329000 2)
  rejected state (AddressSpace.lookup descriptor 0x3fff9000 1)
  rejected state (AddressSpace.lookup descriptor 0x3fffe000 1)
  rejected state (Frames.resolve 3 data)
  rejected state (Frames.resolve 2 (data + 1024))
  let mut spare : Array UInt64 := #[]
  for _ in [:3] do spare := spare.push (← success state (Frames.allocate 2 4))
  rejected state (Frames.allocate 2 4)
  for handle in spare do discard <| success state (Frames.release 2 handle)
  for handle in kernelStack do discard <| success state (Frames.release 2 handle)
  discard <| success state (AddressSpace.destroy descriptor)
  require ((← success state Frames.remaining) == 1024 &&
    (← success state (Frames.ownedCount 1)) == 0 &&
    (← success state (Frames.ownedCount 2)) == 0) "complete silicon teardown restores exact1024 supply"
  IO.println "OWNED_SILICON_DEVELOPMENT:PASS frames1024/quota128/stack4 notebook125 pages;pool4MiB/guards/ownership/generation/teardown"

def checkInk : IO Unit := do
  let state ← IO.mkRef ({} : State)
  let context := (0x40000 : UInt64)
  let tile := (0x41000 : UInt64)
  -- Normalized horizontal segment from pixel (0,10) to (20,10), 2px brush.
  let qy := (10 * 0x1000000 + 30) / 31
  let qx := (20 * 0x1000000 + 30) / 31
  for (offset, value) in #[(0,0), (8,qy), (16,qx), (24,qy), (32,4095),
      (40,4095), (48,512), (56,4095)] do
    state.modify fun s => write64 s (context + offset) value
  discard <| success state (Lemma.Ink.Rasterizer.clearTile tile)
  let changed ← success state (Lemma.Ink.Rasterizer.segment context tile 0 0 32 32)
  require (changed == 64) "literal raster: 21+22+21 integer-covered pixels"
  let memory ← state.get
  -- Rows9/11 have x0..20; row10 has x0..21. Even x is high nibble.
  require (read64 memory (tile + 160) == 0 &&
    ((read64 memory (tile + 168) >>> 16) &&& 255) == 0 &&
    ((read64 memory (tile + 168) >>> 24) &&& 255) == 255)
    "Gray4 literal packed bytes"
  require ((← success state (Lemma.Ink.Rasterizer.segment context tile 0 0 32 32)) == 0)
    "repeated segment has no dirty pixels"
  rejected state (Lemma.Ink.Rasterizer.segment context tile 1 0 32 32)
  rejected state (Lemma.Ink.Rasterizer.segment context tile 0 0 0 32)
  IO.println "INK_TILE_ACTION:PASS"

end OwnedCapacityFixture

open Lean Elab Command
run_cmd do
  liftIO OwnedCapacityFixture.checkFoldStatus
  liftIO OwnedCapacityFixture.checkExpanded
  liftIO OwnedCapacityFixture.checkLegacy
  liftIO OwnedCapacityFixture.checkCurrentLegacyStack
  liftIO OwnedCapacityFixture.checkSiliconDevelopment
  liftIO OwnedCapacityFixture.checkInk
