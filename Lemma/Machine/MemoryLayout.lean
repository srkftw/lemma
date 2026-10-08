import Lemma.Machine.Layout
import Lemma.Core0.Memory

/-!
Additive Gate 5 layout contract.  The historical `core0Layout` remains
unchanged; memory-suite images explicitly select `memoryLayout`.
-/

namespace Lemma.Machine

inductive MemoryRegionClass where
  | ordinary
  | reserved
  | device
  deriving Repr, BEq, Inhabited

structure MemoryRegionSpec where
  id : Nat
  name : String
  base : Nat
  length : Nat
  widths : Array Nat
  alignment : Nat
  readable : Bool
  writable : Bool
  purpose : String
  kind : MemoryRegionClass
  deriving Repr, BEq, Inhabited

namespace MemoryRegionSpec

def stop (region : MemoryRegionSpec) : Nat := region.base + region.length

def overlaps (left right : MemoryRegionSpec) : Bool :=
  left.base < right.stop && right.base < left.stop

end MemoryRegionSpec

structure MemoryCanary where
  id : Nat
  name : String
  start : Nat
  size : Nat := 16
  purpose : String
  deriving Repr, BEq, Inhabited

namespace MemoryCanary

def stop (canary : MemoryCanary) : Nat := canary.start + canary.size

end MemoryCanary

structure MemoryFixture where
  name : String
  start : Nat
  size : Nat
  deriving Repr, BEq, Inhabited

namespace MemoryFixture

def stop (fixture : MemoryFixture) : Nat := fixture.start + fixture.size

end MemoryFixture

structure MemoryLayout where
  machine : Layout
  regions : Array MemoryRegionSpec
  canaries : Array MemoryCanary
  machineFixture : MemoryFixture
  inputFixture : MemoryFixture
  deriving Repr, BEq

private def memoryClass : Lemma.Core0.Memory.RegionKind → MemoryRegionClass
  | .ordinary => .ordinary
  | .reserved => .reserved
  | .device => .device

private def memoryPermissions : Lemma.Core0.Memory.Permission → Bool × Bool
  | .none => (false, false)
  | .readOnly => (true, false)
  | .readWrite => (true, true)

private def memoryRegion (region : Lemma.Core0.Memory.RegionSpec) : MemoryRegionSpec :=
  let permissions := memoryPermissions region.permission
  {
    id := region.id.toNat
    name := region.name
    base := region.base.toNat
    length := region.length
    widths := region.widths.map Lemma.Core0.Memory.Width.bytes
    alignment := region.alignment
    readable := permissions.1
    writable := permissions.2
    purpose := region.purpose
    kind := memoryClass region.kind
  }

private def fixedCanaries : Array MemoryCanary := #[
  ⟨1, "image", 0x807efff0, 16, "last image-envelope bytes"⟩,
  ⟨2, "stack", 0x807f0000, 16, "stack-bottom sentinel"⟩,
  ⟨3, "scratch-low", 0x80800ff0, 16, "scratch underflow sentinel"⟩,
  ⟨4, "scratch-high", 0x80802000, 16, "scratch overflow sentinel"⟩,
  ⟨5, "output-low", 0x80802ff0, 16, "output underflow sentinel"⟩,
  ⟨6, "output-high", 0x80804000, 16, "output overflow sentinel"⟩,
  ⟨7, "events-low", 0x80804ff0, 16, "events underflow sentinel"⟩,
  ⟨8, "events-high", 0x80806000, 16, "events overflow sentinel"⟩,
  ⟨9, "input-low", 0x80fffff0, 16, "input underflow sentinel"⟩,
  ⟨10, "input-high", 0x81001000, 16, "input overflow sentinel"⟩
]

private def fixedMachineFixture : MemoryFixture :=
  ⟨"machine-memory", 0x807efff0, 0x00016020⟩

private def fixedInputFixture : MemoryFixture :=
  ⟨"runtime-input", 0x80fffff0, 0x00001020⟩

def memoryLayout : MemoryLayout := {
  machine := core0Layout
  -- The compiler/model table is frozen first; the machine layout projects it
  -- rather than maintaining a second independently editable authority catalog.
  regions := Lemma.Core0.Memory.regionTable.map memoryRegion
  canaries := fixedCanaries
  machineFixture := fixedMachineFixture
  inputFixture := fixedInputFixture
}

private def isPowerOfTwo (value : Nat) : Bool :=
  value > 0 && value &&& (value - 1) == 0

private def containedIn (outer : Region) (base length : Nat) : Bool :=
  outer.start ≤ base && base + length ≤ outer.stop

private def sameNatSet (left right : Array Nat) : Bool :=
  left.size == right.size && left.all right.contains && right.all left.contains

def MemoryLayout.validate (layout : MemoryLayout) : Except String Unit := do
  layout.machine.validate
  let mut ids : Array Nat := #[]
  let mut names : Array String := #[]
  for region in layout.regions do
    unless region.id < 256 do throw s!"memory region {region.name} ID exceeds UInt8"
    if ids.contains region.id then throw s!"duplicate memory region ID {region.id}"
    if region.name.isEmpty || names.contains region.name then
      throw s!"empty or duplicate memory region name {region.name}"
    ids := ids.push region.id
    names := names.push region.name
    unless region.base < 2 ^ 64 && region.length > 0 &&
        region.length ≤ 2 ^ 64 - region.base do
      throw s!"memory region {region.name} has an invalid UInt64 interval"
    unless isPowerOfTwo region.alignment && region.base % region.alignment == 0 do
      throw s!"memory region {region.name} violates its alignment"
    match region.kind with
    | .ordinary =>
        unless containedIn layout.machine.ram region.base region.length do
          throw s!"RAM region {region.name} lies outside LemmaVM RAM"
        unless !region.widths.isEmpty && region.widths.all (#[1, 4, 8].contains ·) do
          throw s!"RAM region {region.name} has an unsupported width set"
    | .reserved =>
        unless containedIn layout.machine.ram region.base region.length do
          throw s!"reserved region {region.name} lies outside LemmaVM RAM"
        unless region.widths.isEmpty && !region.readable && !region.writable do
          throw s!"reserved region {region.name} accidentally grants general access"
    | .device =>
        unless region.widths.isEmpty && !region.readable && !region.writable do
          throw s!"device region {region.name} accidentally enters the RAM interface"
  let ordinary := layout.regions.filter (·.kind == .ordinary)
  for index in [:ordinary.size] do
    for j in [index + 1:ordinary.size] do
      if ordinary[index]!.overlaps ordinary[j]! then
        throw (s!"general RAM regions {ordinary[index]!.name} and " ++
          s!"{ordinary[j]!.name} overlap")
  unless layout.regions == Lemma.Core0.Memory.regionTable.map memoryRegion do
    throw "machine memory layout differs from the frozen core0-v0.4 region table"
  unless ordinary.size == 4 &&
      ordinary[1]!.base == layout.machine.input.start &&
      ordinary[1]!.length == layout.machine.input.size &&
      sameNatSet ordinary[0]!.widths #[1, 4, 8] &&
      sameNatSet ordinary[3]!.widths #[4, 8] do
    throw "Gate 5 ordinary-region contract differs from core0-v0.4"
  unless layout.machineFixture == fixedMachineFixture &&
      layout.inputFixture == fixedInputFixture &&
      layout.machineFixture.stop == 0x80806010 &&
      layout.inputFixture.stop == 0x81001010 do
    throw "Gate 5 loader fixture envelopes differ from the fixed contract"
  unless layout.canaries == fixedCanaries do
    throw "Gate 5 boundary canaries differ from the fixed contract"
  for canary in layout.canaries do
    unless canary.size == 16 && canary.start % 8 == 0 &&
        canary.start < 2 ^ 64 && canary.size ≤ 2 ^ 64 - canary.start do
      throw s!"memory canary {canary.name} has an invalid interval"

def MemoryLayout.linkerScript (layout : MemoryLayout) : Except String String := do
  layout.validate
  layout.machine.linkerScript

private def quoted (value : String) : String :=
  "\"" ++ Lemma.Compiler.Format.escapeJson value ++ "\""

private def widthsJson (widths : Array Nat) : String :=
  "[" ++ String.intercalate "," (widths.toList.map toString) ++ "]"

private def kindName : MemoryRegionClass → String
  | .ordinary => "ordinary"
  | .reserved => "reserved"
  | .device => "device"

private def regionJson (region : MemoryRegionSpec) : String :=
  "{" ++
    "\"id\":" ++ toString region.id ++ "," ++
    "\"name\":" ++ quoted region.name ++ "," ++
    "\"base\":" ++ toString region.base ++ "," ++
    "\"length\":" ++ toString region.length ++ "," ++
    "\"alignment\":" ++ toString region.alignment ++ "," ++
    "\"widths\":" ++ widthsJson region.widths ++ "," ++
    "\"read\":" ++ toString region.readable ++ "," ++
    "\"write\":" ++ toString region.writable ++ "," ++
    "\"kind\":" ++ quoted (kindName region.kind) ++ "," ++
    "\"purpose\":" ++ quoted region.purpose ++ "," ++
    "\"interval_valid\":true}"

private def canaryJson (canary : MemoryCanary) : String :=
  let h := Lemma.Compiler.Format.hexAddr
  "{" ++
    "\"id\":" ++ toString canary.id ++ "," ++
    "\"name\":" ++ quoted canary.name ++ "," ++
    "\"start\":" ++ quoted (h canary.start) ++ "," ++
    "\"size\":" ++ toString canary.size ++ "," ++
    "\"purpose\":" ++ quoted canary.purpose ++ "}"

def MemoryLayout.memoryContractJson (layout : MemoryLayout) : Except String String := do
  layout.validate
  let regions := layout.regions.toList.map regionJson
  pure <| "{" ++
    "\"byte_order\":\"little-endian\"," ++
    "\"guard_order\":[\"lookup\",\"class\",\"permission\",\"width\",\"bounds\",\"alignment\"]," ++
    "\"successful_access_volatile\":true," ++
    "\"regions\":[" ++ String.intercalate "," regions ++ "]," ++
    "\"statuses\":[" ++ String.intercalate "," [
      "{\"code\":0,\"name\":\"ok\"}",
      "{\"code\":1,\"name\":\"unknown-region\"}",
      "{\"code\":2,\"name\":\"reserved-region\"}",
      "{\"code\":3,\"name\":\"device-region\"}",
      "{\"code\":4,\"name\":\"read-denied\"}",
      "{\"code\":5,\"name\":\"write-denied\"}",
      "{\"code\":6,\"name\":\"width-denied\"}",
      "{\"code\":7,\"name\":\"out-of-bounds\"}",
      "{\"code\":8,\"name\":\"misaligned\"}",
      "{\"code\":9,\"name\":\"budget-exceeded\"}"
    ] ++ "]}"

def MemoryLayout.fixtureContractJson (layout : MemoryLayout) : Except String String := do
  layout.validate
  let canaries := layout.canaries.toList.map canaryJson
  pure <| "{" ++
    "\"schema_version\":1," ++
    "\"canaries\":[" ++ String.intercalate "," canaries ++ "]," ++
    "\"fixtures\":[" ++
      "{\"name\":\"machine-memory\",\"start\":\"0x00000000807efff0\",\"size\":\"0x0000000000016020\"}," ++
      "{\"name\":\"runtime-input\",\"start\":\"0x0000000080fffff0\",\"size\":\"0x0000000000001020\"}" ++
    "]}"

end Lemma.Machine
