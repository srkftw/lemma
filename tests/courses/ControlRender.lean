import Lemma.Courses.ControlRender

/-! Host-only raw-memory fixture for the actual Actions. Scalar expected bytes
are independently authored by the Python reference, never supplied to a machine.
This is component qualification; RV64/wholeNotebook/pixel completion separate. -/
namespace ControlRenderTests
open Lemma.Core0.Memory Lemma.Courses.ControlRender
structure State where
  memory : ByteArray
  writes : Array (UInt64 × UInt64) := #[]
  failAt : Nat := 0
partial def run (ref : IO.Ref State) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
    let (s,v) ← run ref first
    run ref (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
    unless count.toNat ≤ budget do throw <| IO.userError "renderer exceeded bounded loop"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status == 0 then
        let result ← run ref (step i.toUInt32 count value a b c d)
        status := result.1
        value := result.2
    run ref (next status value)
  | .platform op address word _ _ _ _ next => do
    let m ← ref.get
    unless op == .virtualWrite8 || op == .virtualWrite64 do
      throw <| IO.userError "controls acquired memory read, syscall or device authority"
    let size : UInt64 := if op == .virtualWrite64 then 8 else 1
    let offset := address-Lemma.Ink.Surface.framebuffer
    unless Lemma.Ink.Surface.framebuffer ≤ address && offset+size ≤ m.memory.size.toUInt64 &&
        (size == 1 || address%8 == 0) do throw <| IO.userError "control write escaped owned aligned framebuffer"
    let writes := m.writes.push (address,size)
    if writes.size == m.failAt then
      ref.set {m with writes}
      run ref (next 72 0)
    else
      let mut memory := m.memory
      for i in [:size.toNat] do memory := memory.set! (offset.toNat+i) ((word >>> (i.toUInt64*8)).toUInt8)
      ref.set {m with memory,writes}
      run ref (next 0 0)
  | _ => throw <| IO.userError "controls acquired undeclared Action"
private def both (w h requested shown position revision context : UInt64) : Action :=
  .bind (renderControls w h requested shown position) fun s _ => if s = 0 then
  renderIdentity w h revision context else .done s 0
private def observe (m : State) (a : Action) : IO ((UInt8 × UInt64) × State) := do
  let ref ← IO.mkRef m
  let r ← run ref a
  pure (r,← ref.get)
def check : IO Unit := do
  let some directory ← IO.getEnv "LEMMA_CONTROL_REFERENCE" | throw <| IO.userError "independent reference required"
  let rows : Array (UInt64 × UInt64 × UInt64 × UInt64 × UInt64 × UInt64 × UInt64) := #[
    (1650,2200,0x123456789abc,0xfedcba987654,0x307,0x0123456789abcdef,0x630302),
    (1651,1000,0xffffffffffff,0,0xb10,0xffffffffffffffff,0),
    (1663,900,0,0x10001,1,0x8000000000000000,0x80101),
    (416,760,0x10001,0x20003,0x101,1,0xffff01)]
  for i in [:rows.size] do
    let (w,h,requested,shown,position,revision,context) := rows[i]!
    let stride := (w+1)/2
    let before : State := {memory := ByteArray.mk (Array.replicate (stride*h).toNat 0xa5)}
    let expected ← IO.FS.readBinFile (System.FilePath.mk directory/s!"case{i}.expected")
    let action := both w h requested shown position revision context
    let (result,after) ← observe before action
    unless result == (0,0) && after.memory == expected do throw <| IO.userError s!"independent full scalar pixels differ: {i}"
    unless after.writes.foldl (fun n p => n+p.2) 0 == 23040 do throw <| IO.userError "incomplete/extra row footprint"
    for (address,count) in after.writes do
      let n := address-Lemma.Ink.Surface.framebuffer
      unless 640 ≤ n/stride && n/stride < 760 && 12 ≤ n%stride && n%stride+count ≤ 204 do
        throw <| IO.userError "renderer altered a neighboring pixel or row"
    if w == 1650 && after.writes.size != 3615 then throw <| IO.userError "canonical control operation count changed"
    if i == 0 then
      let (failure,cut) ← observe {before with failAt := 2} action
      let first := (640*stride+12).toNat
      unless failure == (72,0) && cut.writes.size == 2 && cut.memory[first]! == expected[first]! &&
          cut.memory[first+1]! == 0xa5 do throw <| IO.userError "actual partial write failure lost prefix"
      let (repaired,complete) ← observe {cut with failAt := 0,writes := #[]} action
      unless repaired == (0,0) && complete.memory == expected do throw <| IO.userError "fresh reconstruction lost failed prefix repair"
  for (w,h) in (#[((0 : UInt64),2200), (415,2200),(1650,759),(4097,760),(416,4097),(4096,4096)]) do
    let (r,m) ← observe {memory := ByteArray.empty} (renderControls w h 0 0 0)
    unless r == (240,0) && m.writes.isEmpty do throw <| IO.userError "invalid geometry touched memory"
  let (r,m) ← observe {memory := ByteArray.empty} (renderControls 1650 2200 0 0 0x8000000000000000)
  unless r == (240,0) && m.writes.isEmpty do throw <| IO.userError "invalid public position reached private mode"
  IO.println "CONTROL_ALIGNED1:PASS independent fullscalar bytes/allfootprint/4strides/3615 versus20520 canonical stores/partialfailure/repair/admission; componentonly"
end ControlRenderTests

def main : IO Unit := ControlRenderTests.check
