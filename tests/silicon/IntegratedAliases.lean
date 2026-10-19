import tests.multimodal.AddressSpaceAliases
import Lemma.Platform.LemmaSim.IntegratedKernel

/-! The same finite physical RAM fixture executes the actual Integrated15
boot mapping action, preserving Product10 NV and testing both failure prefixes.
This is an Action-level authority check, separate from RV64 execution. -/
namespace IntegratedAliases
open MultimodalASFixture
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim

def run : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure 8192 8192 4)
  discard <| success state Frames.init
  discard <| success state (Access.write64 AddressSpace.productSelection 7)
  let descriptor ← success state (AddressSpace.createProduct 2)
  let root ← success state (AddressSpace.root descriptor)
  let middle := (word (← state.get) root >>> 10) <<< 12
  let low := (word (← state.get) (middle+128*8) >>> 10) <<< 12
  let original := resetTrace (← state.get)
  let nv := leaf original root 0x10012000
  require (nv == ((0x10012000 : UInt64) >>> 12 <<< 10 ||| 0xc7)) "actual Product NV alias absent"
  state.set original
  discard <| success state (IntegratedKernel.installRoot 2 root)
  let mapped ← state.get
  require (mapped.writes == 2 && mapped.flushes == 0) "boot helper writes/flush scope differs"
  for va in [0x10014000,0x10015000] do
    require (leaf mapped root va == (va >>> 12 <<< 10 ||| 0xc7)) "S-only RW/NX MM alias differs"
  require (leaf mapped root 0x10012000 == nv) "Product NV changed"
  for i in [:512] do
    if i != 20 && i != 21 then require (word mapped (low+i.toUInt64*8) == word original (low+i.toUInt64*8)) "neighbor PTE changed"
  let lowRecord := Frames.record ((low-Frames.pool)/4096)
  let rootRecord := Frames.record ((root-Frames.pool)/4096)
  let middleRecord := Frames.record ((middle-Frames.pool)/4096)
  let mutations : List (UInt64 × UInt64) :=
    [(root,0),(root,word original root ||| 16),(middle+128*8,0),
     (rootRecord,3),(middleRecord,3),(lowRecord,3),(lowRecord+8,3),
     (lowRecord+16,0),(lowRecord+16,2),(lowRecord+24,0),
     (low+20*8,0x40050c7),(low+21*8,0x40054c7)]
  for (a,v) in mutations do
    state.set (put original a v)
    let result ← execute state (IntegratedKernel.installRoot 2 root)
    require (result.1 != 0 && (← state.get).writes == 0) s!"malformed authority published at {a}"
  for a in [root,middle+128*8,low+20*8,low+21*8,lowRecord+16] do
    state.set {original with failRead := some a}
    let result ← execute state (IntegratedKernel.installRoot 2 root)
    require (result.1 == 95 && (← state.get).writes == 0) "read failure hidden/published"
  for (a,v,n) in [(low+20*8,0x40050c7,0),(low+21*8,0x40054c7,1)] do
    state.set {original with failWrite := some (a,v)}
    let result ← execute state (IntegratedKernel.installRoot 2 root)
    require (result.1 == 96 && (← state.get).writes == n && (← state.get).flushes == 0) "write prefix failure hidden"
  state.set (resetTrace mapped)
  let retry ← execute state (IntegratedKernel.installRoot 2 root)
  require (retry.1 != 0 && (← state.get).writes == 0) "duplicate boot helper silently accepted"
  IO.println "INTEGRATED_ALIASES:PASS ProductNV preserved, exact2 S-only RW/NX MM leaves,12 malformed authorities,5 read and2 write fault boundaries"
end IntegratedAliases
#eval IntegratedAliases.run
