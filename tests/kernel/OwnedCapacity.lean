import Lemma.Kernel.Syscall
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
  liftIO OwnedCapacityFixture.checkInk
