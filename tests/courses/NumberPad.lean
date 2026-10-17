import Lemma.Courses.NumberPad

/-! Host-only raw-memory fixture for the actual Actions. Scalar expected bytes
are independently authored by the Python reference, never supplied to a machine.
This is component qualification; RV64/wholeNotebook/pixel completion separate. -/
namespace NumberPadTests
open Lemma.Core0.Memory Lemma.Courses.NumberPad
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
private def observe (m : State) (a : Action) : IO ((UInt8 × UInt64) × State) := do
  let ref ← IO.mkRef m
  let r ← run ref a
  pure (r,← ref.get)
def check : IO Unit := do
  let some directory ← IO.getEnv "LEMMA_NUMBER_PAD_REFERENCE" | throw <| IO.userError "independent reference required"
  for (i,w) in (#[(0,1650),(1,1651),(2,832)] : Array (Nat × UInt64)) do
    let stride := (w+1)/2
    let before : State := {memory := ByteArray.mk (Array.replicate (stride*760).toNat 0xa5)}
    let expected ← IO.FS.readBinFile (System.FilePath.mk directory/s!"case{i}.expected")
    let action := render w 760 (if i == 1 then 1 else 0)
    let (result,after) ← observe before action
    unless result == (0,0) && after.memory == expected do throw <| IO.userError s!"independent whole framebuffer differs: {i}"
    unless after.writes.foldl (fun n p => n+p.2) 0 == 38400 do throw <| IO.userError "incomplete/extra pad footprint"
    for (address,count) in after.writes do
      let n := address-Lemma.Ink.Surface.framebuffer
      unless 160 ≤ n/stride && n/stride < 360 && 224 ≤ n%stride && n%stride+count ≤ 416 do
        throw <| IO.userError "pad altered neighboring pixels"
    if i == 0 then
      let (failure,cut) ← observe {before with failAt := 2} action
      let first := (160*stride+224).toNat
      unless failure == (72,0) && cut.writes.size == 2 && cut.memory[first]! == expected[first]! &&
          cut.memory[first+8]! == 0xa5 do throw <| IO.userError "actual partial failure lost prefix"
      let (repaired,complete) ← observe {cut with failAt := 0,writes := #[]} action
      unless repaired == (0,0) && complete.memory == expected do throw <| IO.userError "fresh reconstruction failed"
  for (w,h,limited) in (#[((831 : UInt64),760,0),(4097,760,0),(1650,359,0),(1650,4097,0),(4096,4096,0),(1650,760,2)]) do
    let (r,m) ← observe {memory := ByteArray.empty} (render w h limited)
    unless r == (240,0) && m.writes.isEmpty do throw <| IO.userError "invalid geometry wrote memory"
  for row in [:4] do
    for column in [:3] do
      let expected : UInt64 := if row < 3 then (row*3+column+1).toUInt64 else
        if column == 0 then 10 else if column == 1 then 0 else 11
      for (dx,dy) in (#[(0,0),(127,39)] : Array (UInt64 × UInt64)) do
        unless key (column.toUInt64*128+dx) (40+row.toUInt64*40+dy) == expected do
          throw <| IO.userError "key boundary differs"
  unless key 384 40 == 12 && key 0 39 == 12 && key 0 200 == 12 do
    throw <| IO.userError "outside key admitted"
  IO.println "NUMBER_PAD1:PASS actual Actions/independent whole framebuffer/3strides/footprint/partial-failure/repair/key-boundaries; component only"
end NumberPadTests

def main : IO Unit := NumberPadTests.check
