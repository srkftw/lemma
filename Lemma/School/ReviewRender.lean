import Lemma.School.Submission
import Lemma.Ink.Rasterizer

/-! Authorized hosted review of immutable guest ink. The interpreter executes
the same maintained Rasterizer.segmentSurface Action used by Notebook. It has
only bounded private RAM; device, syscall, allocation and file Actions reject.
This is a hosted preview, never a guest execution or handwriting interpretation.
The caller presents the original prompt/rubric separately from this ink layer. -/
namespace Lemma.School.ReviewRender
open Lean Lemma.Core0.Memory Lemma.Documents Lemma.Ink

def context : UInt64 := 0x10000
def framebuffer : UInt64 := 0x20000
def width : UInt64 := 1650
def height : UInt64 := 2200
def stride : UInt64 := (width+1)/2
def maximumTiles : Nat := 8192

private def fail {α : Type} (message : String) : IO α := throw (IO.userError message)

private def index (address : UInt64) (bytes : Nat) : IO Nat := do
  let endAddress := address.toNat+bytes
  if !((context <= address && endAddress <= context.toNat+64) ||
      (framebuffer <= address && endAddress <= (framebuffer+stride*height).toNat)) then
    fail "review renderer private RAM span rejected"
  return address.toNat

private def setWord (bytes : ByteArray) (offset : Nat) (value : UInt64) : ByteArray :=
  (List.range 8).foldl (fun bytes i => bytes.set! (offset+i) ((value >>> (i.toUInt64*8)).toUInt8)) bytes

private def execute (memory : IO.Ref ByteArray) : Nat → Action → IO (UInt8 × UInt64)
  | 0, _ => fail "review renderer Action depth budget exhausted"
  | _+1, .done status value => pure (status,value)
  | fuel+1, .bind first next => do
    let (s,value) ← execute memory fuel first
    execute memory fuel (next s value)
  | fuel+1, .boundedFoldU64 budget step count initial a b c d next => do
    if count.toNat > budget || budget > 1024 then fail "review renderer fold budget exceeded"
    let mut s : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if s == 0 then
        let result ← execute memory fuel (step i.toUInt32 count value a b c d)
        s := result.1
        value := result.2
    execute memory fuel (next s value)
  | fuel+1, .platform op a b _ _ _ _ next => do
    if op == .virtualRead64 then
      let offset ← index a 8
      let value ← IO.ofExcept (Submission.word (← memory.get) offset)
      execute memory fuel (next 0 value)
    else if op == .virtualRead8 then
      let offset ← index a 1
      let value := (← memory.get)[offset]!.toUInt64
      execute memory fuel (next 0 value)
    else if op == .virtualWrite8 then
      let offset ← index a 1
      memory.modify (fun bytes => bytes.set! offset b.toUInt8)
      execute memory fuel (next 0 0)
    else fail "review renderer rejected unexpected mutation/device Action"
  | _, _ => fail "review renderer rejected unsupported Action"

private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def maximum (a b : UInt64) : UInt64 := if a < b then b else a

/-- The exact current Notebook contextStep mapping: raw x retains its sensor
range; raw y excludes the160-pixel toolbar before mapping to current paper.
No inferred points, smoothed handwriting, or hidden visibility changes. -/
private def segmentContext (bytes : ByteArray) (chunk : Submission.Chunk)
    (first last : Nat) : IO (Array UInt64) := do
  let w (offset : Nat) := IO.ofExcept (Submission.word bytes offset)
  let xRange ← w (chunk.offset+72)
  let yRange ← w (chunk.offset+80)
  let sourceHeight ← w (chunk.offset+104)
  let y (sample : Nat) := do
    let raw ← w (sample+24)
    return Ink.displayY (Ink.pageY raw yRange sourceHeight) height
  return #[Geometry.normalized (← w (first+16)) xRange, ← y first,
    Geometry.normalized (← w (last+16)) xRange, ← y last,
    ← w (first+32), ← w (last+32), ← w (chunk.offset+56), ← w (chunk.offset+88)]

private def paint (memory : IO.Ref ByteArray) (values : Array UInt64) (tiles : Nat) : IO (Nat × Nat) := do
  memory.modify fun bytes => (List.range 8).foldl
    (fun bytes i => setWord bytes (context.toNat+i*8) values[i]!) bytes
  let radius := (values[6]!+511)/512
  let px0 := Geometry.pixel values[0]! width
  let py0 := Geometry.pixel values[1]! height
  let px1 := Geometry.pixel values[2]! width
  let py1 := Geometry.pixel values[3]! height
  let left := minimum px0 px1
  let top := minimum py0 py1
  let x0 := (if radius < left then left-radius else 0)/32*32
  let y0 := (if radius < top then top-radius else 0)/32*32
  let x1 := minimum width (maximum px0 px1+radius+1)
  let y1 := minimum height (maximum py0 py1+radius+1)
  let columns := (x1-x0+31)/32
  let rows := (y1-y0+31)/32
  let count := (columns*rows).toNat
  if tiles+count > maximumTiles then fail "review render resource failure:8192-tile limit; original immutable artifact retained"
  let mut changed := 0
  for i in [:count] do
    let x := x0+(i.toUInt64%columns)*32
    let y := y0+(i.toUInt64/columns)*32
    let (status,value) ← execute memory 128
      (Rasterizer.segmentSurface context framebuffer x y width height)
    if status != 0 then fail s!"maintained ink rasterizer rejected preview: status{status}"
    changed := changed+value.toNat
  return (tiles+count,changed)

/-- Canonical1650×2200 Gray4 ink layer, with all raw chunks independently
validated before rendering. Invisible chunks remain in the artifact and are
omitted here exactly as the notebook omits them. No school state is mutated. -/
def render (bytes : ByteArray) : IO Json := do
  let envelope ← IO.ofExcept (Submission.decode bytes)
  let memory ← IO.mkRef (ByteArray.mk (Array.replicate (framebuffer+stride*height).toNat 255))
  let mut tiles := 0
  let mut changed := 0
  let mut segments := 0
  for chunk in envelope.chunks do
    if chunk.visible then
      for i in [:chunk.samples] do
        let sample := chunk.offset+128+i*72
        let flags ← IO.ofExcept (Submission.word bytes (sample+40))
        if flags &&& 1 != 0 then
          let previous := if i == 0 then sample else sample-72
          let values ← segmentContext bytes chunk previous sample
          let result ← paint memory values tiles
          tiles := result.1
          changed := changed+result.2
          segments := segments+1
  let pixels := (← memory.get).extract framebuffer.toNat (framebuffer+stride*height).toNat
  let digit (n : Nat) := Char.ofNat (if n < 10 then 48+n else 87+n)
  let encoded := String.ofList (pixels.data.toList.flatMap (fun byte =>
    [digit (byte.toNat/16),digit (byte.toNat%16)]))
  return Json.mkObj [("schema",toJson "lemma-school-review-ink/1"),("format",toJson "gray4-high-nibble-first"),
    ("width",toJson width.toNat),("height",toJson height.toNat),("stride",toJson stride.toNat),
    ("gray4Hex",toJson encoded),("tiles",toJson tiles),("segments",toJson segments),("changedPixels",toJson changed),
    ("documentRevision",toJson envelope.documentRevision),("page",toJson envelope.page),
    ("scope",toJson "hosted Lean preview of validated immutable ink using actual guest Rasterizer.segmentSurface; original prompt/typed work separate; no guest execution, recognition or assessment")]

end Lemma.School.ReviewRender
