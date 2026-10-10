import Lean
import Lemma.Platform.LemmaSim.DescriptorDTB

/-! Host-only effect harness for actual guest FDT validation declarations.
The fixture is a DTB emitted by pinned patched QEMU. Supplied effects are only
memory/device reads. This is distinct from actual RV64 boot evidence. -/
namespace DescriptorProbe
open Lemma.Core0.Memory

def pointer : UInt64 := 0x87e00000
def metadata : UInt64 := 0x80400000
structure VM where
  dtb : ByteArray
  ram : Array UInt8 := Array.replicate 4096 0

def write (memory : Array UInt8) (offset value : UInt64) : Array UInt8 := Id.run do
  let mut result := memory
  for i in [:8] do result := result.set! (offset.toNat + i) ((value >>> UInt64.ofNat (i * 8)).toUInt8)
  return result

def readByte (state : VM) (address : UInt64) : Except String UInt64 :=
  if metadata ≤ address && address < metadata + 4096 then .ok state.ram[(address - metadata).toNat]!.toUInt64
  else if pointer ≤ address && address - pointer < state.dtb.size.toUInt64 then .ok state.dtb[(address - pointer).toNat]!.toUInt64
  else .error s!"host probe denied physical read at {address}"
def read (state : VM) (address : UInt64) (bytes : Nat) : Except String UInt64 := do
  let mut result := 0
  for i in [:bytes] do result := result ||| ((← readByte state (address + i.toUInt64)) <<< UInt64.ofNat (8 * i))
  return result

def device (address : UInt64) : Except String UInt64 :=
  if address = 0x10001000 then .ok 0x74726976 else if address = 0x10001004 then .ok 2 else
  if address = 0x10001008 then .ok 2 else if address = 0x10010000 then .ok 1280331856 else
  if address = 0x10010008 then .ok 1 else if address = 0x10011000 then .ok 1280331854 else
  if address = 0x10011008 then .ok 1 else .error "host probe denied undeclared device read"

partial def run (vm : IO.Ref VM) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
      let (s,v) ← run vm first
      run vm (next s v)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next => do
      if budget < count.toNat then run vm (next 9 initial) else
      let mut value := initial
      let mut status : UInt8 := 0
      for i in [:count.toNat] do
        if status = 0 then
          let (s,v) ← run vm (step (UInt32.ofNat i) count value c0 c1 c2 c3)
          status := s
          value := v
      run vm (next (if status = 10 then 0 else status) value)
  | .platform operation a b _ _ _ _ next => do
      match operation with
      | .physicalRead8 | .physicalRead64 =>
          let value ← IO.ofExcept (read (← vm.get) a (if operation == .physicalRead8 then 1 else 8))
          run vm (next 0 value)
      | .physicalWrite64 =>
          unless metadata ≤ a && a ≤ metadata + 4096 - 8 do throw <| IO.userError "host probe denied metadata write"
          vm.modify fun state => { state with ram := write state.ram (a - metadata) b }
          run vm (next 0 0)
      | .deviceRead32 | .deviceRead64 =>
          let value ← IO.ofExcept (device a)
          run vm (next 0 value)
      | _ => throw <| IO.userError "host probe denied unsupported primitive"
  | _ => throw <| IO.userError "host probe denied unsupported Action"

def main (args : List String) : IO UInt32 := do
  unless args.length = 1 do throw <| IO.userError "descriptor probe requires one DTB path"
  let dtb ← IO.FS.readBinFile args[0]!
  let vm ← IO.mkRef {dtb, ram := write (Array.replicate 4096 0) 8 pointer}
  let (status,value) ← run vm (Lemma.Platform.LemmaSim.DescriptorDTB.validate pointer dtb.size.toUInt64 1650 2200 4095)
  IO.println s!"DESCRIPTOR_HOST_ACTION:{status}:{value}"
  pure <| if status = 0 then 0 else 1
end DescriptorProbe

def main := DescriptorProbe.main
