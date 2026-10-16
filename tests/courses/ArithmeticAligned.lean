import Lemma.Courses.ArithmeticAligned

/-! Host-only execution of the actual maintained Actions. This fixture neither
boots a machine nor supplies rendered output to one. Historical scalar pixels
and all neighboring bytes are independent expectations for the new stores. -/
namespace ArithmeticAlignedTests
open Lemma.Core0.Memory Lemma.Courses

def document : UInt64 := 0x48000
structure State where
  pixels : ByteArray
  writes : Array (UInt64 × UInt64) := #[]
  failWrite : Nat := 0
  failRead : UInt64 := 0
  width : UInt64 := 1650
  goal : UInt64 := 1
  outcome : UInt64 := 1
  mode : UInt64 := 0

def field (m : State) (offset : UInt64) : UInt64 :=
  if offset = 40 then 12 else if offset = 48 then m.goal else
  if offset = 56 then 5 else if offset = 64 then 6 else
  if offset = 72 then 1 else if offset = 80 then 2 else if offset = 88 then 1 else
  if offset = 96 then m.outcome else if offset = 144 then 1 else if offset = 152 then 1 else
  if offset = 184 then m.mode else if offset = 192 then 2 else if offset = 216 then 1 else
  if offset = 840 then (1 : UInt64) ||| (m.goal <<< 8) ||| (m.outcome <<< 16) else
  if offset = 856 then (2 : UInt64) ||| (m.goal <<< 8) ||| ((1 : UInt64) <<< 16) else 0

partial def run (ref : IO.Ref State) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind a next => do let (s,v) ← run ref a; run ref (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
    unless count.toNat ≤ budget do throw <| IO.userError "unaligned renderer exceeded loop bound"
    let mut s : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if s == 0 then
        let r ← run ref (step i.toUInt32 count value a b c d)
        s := r.1; value := r.2
    run ref (next s value)
  | .platform op address word _ _ _ _ next => do
    let m ← ref.get
    if op == .virtualRead64 then
      unless document ≤ address && address-document < 4096 && address%8 == 0 do
        throw <| IO.userError "renderer acquired unrelated read authority"
      run ref (next (if m.failRead == address then 71 else 0) (field m (address-document)))
    else if op == .virtualWrite8 || op == .virtualWrite64 then
      let n : UInt64 := if op == .virtualWrite64 then 8 else 1
      let offset := address-Lemma.Ink.Surface.framebuffer
      let stride := (m.width+1)/2
      unless Lemma.Ink.Surface.framebuffer ≤ address && offset+n ≤ m.pixels.size.toUInt64 &&
          (n == 1 || address%8 == 0) && 160 ≤ offset/stride && offset/stride < 320 &&
          12 ≤ offset%stride && offset%stride+n ≤ 204 do
        throw <| IO.userError "renderer touched a neighbor, an unaligned word or an unowned byte"
      let writes := m.writes.push (address,n)
      if writes.size == m.failWrite then
        ref.set {m with writes}; run ref (next 72 0)
      else
        let mut pixels := m.pixels
        for i in [:n.toNat] do pixels := pixels.set! (offset.toNat+i) ((word >>> (i.toUInt64*8)).toUInt8)
        ref.set {m with pixels,writes}; run ref (next 0 0)
    else throw <| IO.userError "renderer acquired syscall or device authority"
  | _ => throw <| IO.userError "renderer acquired unsupported action"

def observe (m : State) (a : Action) : IO ((UInt8 × UInt64) × State) := do
  let ref ← IO.mkRef m
  let result ← run ref a
  pure (result,← ref.get)

def check : IO Unit := do
  for goal in #[(1 : UInt64),2,3] do
    for outcome in [:6] do
      let values : UInt64 := (5 : UInt64) ||| ((6 : UInt64) <<< 7) ||| ((1 : UInt64) <<< 14) ||| ((2 : UInt64) <<< 21) ||| ((1 : UInt64) <<< 28)
      let review := (outcome.toUInt64%4) ||| ((outcome.toUInt64%8) <<< 3) ||| ((outcome.toUInt64%5) <<< 6) ||| ((1 : UInt64) <<< 9)
      let state := outcome.toUInt64 ||| ((1 : UInt64) <<< 3) ||| ((12 : UInt64) <<< 9) ||| ((1 : UInt64) <<< 16) ||| (review <<< 24)
      for y in [:160] do
        for offset in [:192] do
          let word := ArithmeticAligned.spanWord offset.toUInt64 y.toUInt64 goal values state
          for j in [:min 8 (192-offset)] do
            let x := (offset+j).toUInt64*2
            let expected := (Arithmetic.panelPixel x y.toUInt64 goal values state <<< 4) ||| Arithmetic.panelPixel (x+1) y.toUInt64 goal values state
            unless (word >>> (j.toUInt64*8)) &&& 255 == expected do
              throw <| IO.userError s!"span differs from scalar pixels at {goal}/{outcome}/{y}/{offset}/{j}"
  for width in #[(1650 : UInt64),1651] do
    let initial : State := {pixels := ByteArray.mk (Array.replicate (((width+1)/2)*320).toNat 0xa5),width}
    let (old,baseline) ← observe initial (Arithmetic.renderSparse document width)
    let (result,actual) ← observe initial (ArithmeticAligned.render document width)
    unless old == (0,0) && result == old && actual.pixels == baseline.pixels do
      throw <| IO.userError "actual whole framebuffer differs from historical rendering"
    unless actual.writes.foldl (fun n row => n+row.2) 0 == 30720 do
      throw <| IO.userError "renderer did not visit the exact rectangle once"
    if width == 1650 then
      unless baseline.writes.size == 27360 && actual.writes.size == 4820 do
        throw <| IO.userError s!"canonical store measurement differs {baseline.writes.size}/{actual.writes.size}"
      for fault in #[2,5,31] do
        let (failed,cut) ← observe {initial with failWrite := fault} (ArithmeticAligned.render document width)
        unless failed == (72,0) && cut.writes.size == fault do throw <| IO.userError "actual write failure was swallowed"
        let mut expected := initial.pixels
        for (address,count) in cut.writes[:fault-1] do
          let offset := (address-Lemma.Ink.Surface.framebuffer).toNat
          for j in [:count.toNat] do expected := expected.set! (offset+j) baseline.pixels[offset+j]!
        unless cut.pixels == expected do throw <| IO.userError "write failure changed something beyond its successful prefix"
      let (failed,cut) ← observe {initial with failRead := document+64} (ArithmeticAligned.render document width)
      unless failed == (71,0) && cut.writes.isEmpty && cut.pixels == initial.pixels do
        throw <| IO.userError "document access failure touched framebuffer"
    else unless actual.writes == baseline.writes do throw <| IO.userError "noncanonical fallback changed memory semantics"
  IO.println "ARITHMETIC_ALIGNED1:PASS scalar spans/all30720bytes/neighbors/4820vs27360stores/writefaultprefixes/readfailure/oddstridefallback; host component only"
end ArithmeticAlignedTests

def main : IO Unit := ArithmeticAlignedTests.check
