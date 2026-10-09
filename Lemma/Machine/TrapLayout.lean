import Lemma.Machine.MemoryLayout

/-! Fixed, disjoint M-mode trap storage.  These addresses are private to the
structured primitives and do not grant an ordinary checked-RAM region ID. -/

namespace Lemma.Machine

structure TrapCanary where
  name : String
  address : Nat
  value : Nat
  deriving Repr, BEq

structure TrapLayout where
  memory : MemoryLayout
  trapStack : Region
  probeContext : Region
  probeStack : Region
  probeSp : Nat
  canaries : Array TrapCanary
  deriving Repr, BEq

def trapFrameBytes : Nat := 288

def trapLayout : TrapLayout := {
  memory := memoryLayout
  trapStack := ⟨"trap-stack", 0x80810000, 0x4000, 16, .noLoad⟩
  probeContext := ⟨"trap-probe-context", 0x80815000, 0x1000, 16, .noLoad⟩
  probeStack := ⟨"trap-probe-stack", 0x80818000, 0x1000, 16, .noLoad⟩
  probeSp := 0x80818800
  canaries := #[
    ⟨"foreground-low", 0x807f0000, 0x4c4d370000000001⟩,
    ⟨"foreground-high", 0x80800000, 0x4c4d370000000011⟩,
    ⟨"trap-low", 0x80810000, 0x4c4d370000000021⟩,
    ⟨"trap-high", 0x80813ff0, 0x4c4d370000000031⟩,
    ⟨"probe-low", 0x80818000, 0x4c4d370000000041⟩,
    ⟨"probe-high", 0x80818ff0, 0x4c4d370000000051⟩
  ]
}

def TrapLayout.trapSp (layout : TrapLayout) : Nat := layout.trapStack.stop - 16

def TrapLayout.validate (layout : TrapLayout) : Except String Unit := do
  layout.memory.validate
  unless layout == trapLayout do
    throw "Gate 7 trap layout differs from its fixed machine contract"
  let privateRegions := #[layout.trapStack, layout.probeContext, layout.probeStack]
  let existing := #[layout.memory.machine.image, layout.memory.machine.stack,
    layout.memory.machine.input] ++ layout.memory.regions.filterMap fun region =>
      if region.kind == .ordinary then
        some (⟨region.name, region.base, region.length, region.alignment, .noLoad⟩ : Region)
      else none
  for index in [:privateRegions.size] do
    let region := privateRegions[index]!
    unless region.start % 16 == 0 && region.size % 16 == 0 &&
        layout.memory.machine.ram.start ≤ region.start &&
        region.stop ≤ layout.memory.machine.ram.stop do
      throw s!"private trap region {region.name} is unaligned or outside RAM"
    for other in existing do
      if region.overlaps other then
        throw s!"private trap region {region.name} overlaps {other.name}"
    for otherIndex in [index + 1:privateRegions.size] do
      if region.overlaps privateRegions[otherIndex]! then
        throw "private trap regions overlap"
  unless trapFrameBytes % 16 == 0 && layout.trapSp % 16 == 0 &&
      layout.trapStack.start + 16 + trapFrameBytes + 16 < layout.trapSp &&
      layout.probeStack.start + 16 < layout.probeSp &&
      layout.probeSp % 16 == 0 && layout.probeSp + 256 ≤ layout.probeStack.stop - 16 do
    throw "trap frame or sentinel-probe stack space is invalid"

def TrapLayout.linkerScript (layout : TrapLayout) : Except String String := do
  layout.validate
  let old ← layout.memory.linkerScript
  let h := Lemma.Compiler.Format.hexAddr
  let additions := String.intercalate "\n" [
    s!"  __trap_stack_bottom = {h layout.trapStack.start};",
    s!"  __trap_stack_top = {h layout.trapSp};",
    s!"  __trap_probe_context = {h layout.probeContext.start};",
    s!"  __trap_probe_sp = {h layout.probeSp};",
    s!"  __trap_probe_bottom = {h layout.probeStack.start};",
    s!"  __trap_probe_top = {h (layout.probeStack.stop - 16)};",
    "  ASSERT((__trap_stack_top & 15) == 0, \"unaligned trap stack\")",
    "  ASSERT((__trap_probe_sp & 15) == 0, \"unaligned probe stack\")",
    "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }"
  ]
  pure <| old.replace "  /DISCARD/ : { *(.eh_frame .eh_frame.*) }" additions

def TrapLayout.manifestJson (layout : TrapLayout) : Except String String := do
  layout.validate
  let base ← layout.memory.machine.manifestJson
  let h := Lemma.Compiler.Format.hexAddr
  let region (value : Region) : String :=
    "{\"start\":\"" ++ h value.start ++ "\",\"size\":\"" ++ h value.size ++
      "\",\"alignment\":16,\"ordinary_ram_access\":false}"
  let canaries := layout.canaries.toList.map fun canary =>
    "{\"name\":\"" ++ canary.name ++ "\",\"address\":\"" ++ h canary.address ++
      "\",\"bytes\":16,\"word0\":\"" ++ h canary.value ++
      "\",\"word1\":\"" ++ h (canary.value + 1) ++ "\"}"
  let additions := String.intercalate ",\n" [
    "  \"trap_stack\": " ++ region layout.trapStack,
    "  \"trap_probe_context\": " ++ region layout.probeContext,
    "  \"trap_probe_stack\": " ++ region layout.probeStack,
    "  \"trap_stack_pointer\": \"" ++ h layout.trapSp ++ "\"",
    "  \"trap_probe_sp\": \"" ++ h layout.probeSp ++ "\"",
    "  \"trap_stack_capacity\": {\"reserved_bytes\":16384,\"canary_bytes\":32," ++
      "\"usable_bytes\":16352,\"trap_frame_bytes\":288,\"outgoing_call_bytes\":16," ++
      "\"maximum_compiled_call_chain_bytes\":16048}",
    "  \"trap_probe_capacity\": {\"reserved_bytes\":4096,\"canary_bytes\":32," ++
      "\"writable_bytes_above_sp\":2032,\"snapshot_bytes\":248," ++
      "\"private_context_reserved_bytes\":4096,\"caller_context_bytes\":128}",
    "  \"trap_frame\": {\"bytes\":288,\"alignment\":16,\"x1_offset\":0," ++
      "\"x2_offset\":8,\"x31_offset\":240,\"mstatus_offset\":248," ++
      "\"mepc_offset\":256,\"mcause_offset\":264,\"mtval_offset\":272,\"mie_offset\":280}",
    "  \"trap_canaries\": [" ++ String.intercalate "," canaries ++ "]"
  ]
  pure <| base.replace "\n}\n" (",\n" ++ additions ++ "\n}\n")

end Lemma.Machine
