import Lemma.Courses.PackageRender
import Lemma.Courses.Package

namespace CourseRenderTests
open Lemma.Core0.Memory
open Lemma.Courses

def source : UInt64 := 0x40000
def cache : UInt64 := 0x48000
def width : UInt64 := 1650
def height : UInt64 := 640

structure Model where
  package : ByteArray
  glyphs : ByteArray := ByteArray.mk (Array.replicate 4096 0xa5)
  framebuffer : ByteArray := ByteArray.mk (Array.replicate 528000 0xaa)
  reads : Array (UInt64 × UInt64) := #[]
  writes : Array (UInt64 × UInt64) := #[]
  readFault : UInt64 := 0
  writeFault : UInt64 := 0

private def inRange (address count base size : UInt64) : Bool :=
  address ≥ base && count ≤ size && address - base ≤ size - count

private def readBytes (data : ByteArray) (offset count : UInt64) : UInt64 :=
  (List.range count.toNat).foldl (fun value i =>
    value ||| (data[offset.toNat+i]!.toUInt64 <<< (i.toUInt64*8))) 0

private def read (m : Model) (address count : UInt64) : Except String UInt64 := do
  if inRange address count source m.package.size.toUInt64 then
    return readBytes m.package (address-source) count
  else if inRange address count cache 4096 then return readBytes m.glyphs (address-cache) count
  else if inRange address count Lemma.Ink.Surface.framebuffer m.framebuffer.size.toUInt64 then
    return readBytes m.framebuffer (address-Lemma.Ink.Surface.framebuffer) count
  else throw "course render read outside independent owned ranges"

private def writeBytes (data : ByteArray) (offset count value : UInt64) : ByteArray :=
  (List.range count.toNat).foldl (fun data i =>
    data.set! (offset.toNat+i) ((value >>> (i.toUInt64*8)).toUInt8)) data

private def write (m : Model) (address count value : UInt64) : Except String Model := do
  if inRange address count cache 4096 then
    return {m with glyphs := writeBytes m.glyphs (address-cache) count value}
  else if inRange address count Lemma.Ink.Surface.framebuffer m.framebuffer.size.toUInt64 then
    return {m with framebuffer := writeBytes m.framebuffer (address-Lemma.Ink.Surface.framebuffer) count value}
  else throw "course render write escaped cache/framebuffer or altered package"

partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
      let (s,v) ← run state first
      run state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "course render exceeded declared fold"
      let mut status : UInt8 := 0
      let mut value := initial
      for i in [:count.toNat] do
        if status == 0 then
          let (s,v) ← run state (step i.toUInt32 count value a b c d)
          status := s
          value := v
      run state (next status value)
  | .platform operation a b _ _ _ _ next => do
      let m ← state.get
      match operation with
      | .virtualRead8 | .virtualRead64 =>
          let count := if operation == .virtualRead8 then 1 else 8
          state.set {m with reads := m.reads.push (a,count)}
          if m.readFault == a then run state (next 71 0) else
          run state (next 0 (← IO.ofExcept <| read m a count))
      | .virtualWrite8 | .virtualWrite64 =>
          let count := if operation == .virtualWrite8 then 1 else 8
          state.set {m with writes := m.writes.push (a,count)}
          if m.writeFault == a then run state (next 72 0) else
          let changed ← IO.ofExcept <| write (← state.get) a count b
          state.set changed
          run state (next 0 0)
      | _ => throw <| IO.userError "course render acquired syscall/device authority"
  | _ => throw <| IO.userError "course render acquired undeclared Action"

private def encode (text : String) : IO ByteArray := do
  IO.ofExcept <| (Package.encode {
    identity := 1, edition := 1, title := "TEST", sourceAnchor := "original:test",
    editionAnchor := "edition:1", rightsAnchor := "original fixture",
    nodes := #[{kind := .explanation, title := "TITLE", body := text, sourceAnchor := "original:node"}]
  }).mapError Package.Error.render

private def checkCache (m : Model) (expected : Array (Nat × UInt64)) : IO Unit := do
  for i in [:512] do
    let wanted := (expected.find? (fun entry => entry.1 == i)).map (·.2) |>.getD 0
    if readBytes m.glyphs (i.toUInt64*8) 8 != wanted then
      throw <| IO.userError s!"independent glyph/cell expectation differs at {i}"

private def observe (before : Model) (action : Action) : IO ((UInt8 × UInt64) × Model) := do
  let state ← IO.mkRef {before with reads := #[], writes := #[]}
  let result ← run state action
  return (result, ← state.get)

def check : IO Unit := do
  let image ← encode "a\nB! jz?$"
  let before : Model := {package := image}
  let (result,prepared) ← observe before (PackageRender.prepare source image.size.toUInt64 0 1 0 cache)
  if result != (0,9) || prepared.package != image || prepared.framebuffer != before.framebuffer then
    throw <| IO.userError "actual preparation altered source/display or lost raw text position"
  checkCache prepared #[(0,0x2bed),(32,0x6bae),(33,0x2482),(35,0x124e),(36,0x72a7),(37,0x7282),(38,0x7b6f)]
  let descriptor := readBytes image (128+120) 8
  let body := source + (descriptor &&& 0xffffffff)
  if (prepared.reads.filter (fun item => item == (body,1))).size != 3 then
    throw <| IO.userError "body was not read once for CRC, once for text validity and once for layout"
  let (result,page) ← observe before (PackageRender.prepare source image.size.toUInt64 0 1 2 cache)
  if result != (0,9) then throw <| IO.userError "explicit raw-offset page differs"
  checkCache page #[(0,0x6bae),(1,0x2482),(3,0x124e),(4,0x72a7),(5,0x7282),(6,0x7b6f)]
  let long ← encode (String.join (List.replicate 256 "a\n"))
  let (result,paged) ← observe {package := long} (PackageRender.prepare source long.size.toUInt64 0 1 0 cache)
  if result != (0,32) then throw <| IO.userError "row-bound pagination hid unrepresented bytes"
  checkCache paged ((Array.range 16).map fun i => (i*32,0x2bed))
  for (action,status) in #[(PackageRender.prepare source image.size.toUInt64 0 8 0 cache,241),
      (PackageRender.prepare source image.size.toUInt64 1 1 0 cache,244),
      (PackageRender.prepare source image.size.toUInt64 0 1 10 cache,244),
      (PackageRender.prepare source image.size.toUInt64 0 1 0 source,240)] do
    let (result,rejected) ← observe before action
    if result != (status,0) || !rejected.writes.isEmpty || rejected.glyphs != before.glyphs then
      throw <| IO.userError "invalid render argument altered unpublished cache"
  let corrupt := {before with package := image.set! (image.size-1) 0}
  let (result,rejected) ← observe corrupt (PackageRender.prepare source image.size.toUInt64 0 1 0 cache)
  if result != (243,0) || !rejected.writes.isEmpty then throw <| IO.userError "CRC failure started output"
  let (result,rejected) ← observe {before with readFault := body} (PackageRender.prepare source image.size.toUInt64 0 1 0 cache)
  if result != (71,0) || !rejected.writes.isEmpty then throw <| IO.userError "source fault lost its real status/prefix"
  let (result,rejected) ← observe {before with writeFault := cache+8} (PackageRender.prepare source image.size.toUInt64 0 1 0 cache)
  if result != (72,0) || rejected.writes.size != 2 || readBytes rejected.glyphs 0 8 != 0 ||
      readBytes rejected.glyphs 8 8 != 0xa5a5a5a5a5a5a5a5 then
    throw <| IO.userError "cache fault changed ordered partial effects"
  let (result,rendered) ← observe prepared (PackageRender.render cache width height)
  if result != (0,0) || rendered.package != image || rendered.glyphs != prepared.glyphs then
    throw <| IO.userError "actual Gray4 renderer lost source/cache or failed"
  for y in [:height.toNat] do
    for x in [:width.toNat] do
      let offset := y*(width.toNat/2)+x/2
      let observed := if x%2 == 0 then rendered.framebuffer[offset]!.toUInt64 >>> 4 else rendered.framebuffer[offset]!.toUInt64 &&& 15
      let expected := if 24 ≤ x && x < 408 && 320 ≤ y && y < 640 then
        let px := x-24; let py := y-320
        let cell := py/20*32+px/12
        let pattern := readBytes prepared.glyphs (cell.toUInt64*8) 8
        if px%12 < 9 && py%20 < 15 && ((pattern >>> (14-(py%20/3*3+px%12/3)).toUInt64) &&& 1) == 1 then 0 else 15
      else 10
      if observed != expected then throw <| IO.userError s!"independent scalar Gray4 pixel differs at {x}/{y}"
  for action in #[PackageRender.render cache 415 height, PackageRender.render cache width 639,
      PackageRender.render Lemma.Ink.Surface.framebuffer width height] do
    let (result,rejected) ← observe prepared action
    if result.1 == 0 || !rejected.writes.isEmpty then throw <| IO.userError "renderer admission allowed alias/short geometry"
  let (result,connected) ← observe before
    (PackageRender.renderSelected source image.size.toUInt64 0 1 0 cache width height)
  if result != (0,9) || connected.package != image || connected.glyphs != prepared.glyphs ||
      connected.framebuffer != rendered.framebuffer then
    throw <| IO.userError "same-Action connected renderer changed actual package/pagination/pixels"
  for (address,bytes,output,status) in #[(source,image.size.toUInt64,Lemma.Ink.Surface.framebuffer,240),
      (Lemma.Ink.Surface.framebuffer,image.size.toUInt64,cache,240)] do
    let (result,rejected) ← observe before
      (PackageRender.renderSelected address bytes 0 1 0 output width height)
    if result != (status,0) || !rejected.writes.isEmpty || !rejected.reads.isEmpty then
      throw <| IO.userError "connected source/cache/framebuffer alias consumed a validation or write"
  let (result,rejected) ← observe corrupt
    (PackageRender.renderSelected source image.size.toUInt64 0 1 0 cache width height)
  if result != (243,0) || rejected.framebuffer != before.framebuffer || !rejected.writes.isEmpty then
    throw <| IO.userError "connected CRC failure published partial display/cache"
  IO.println "COURSE_RENDER_ACTIONS:PASS actual immutable package text, explicit pagination, independent glyph/cell and528000-byte Gray4 oracle,CRC/authority/fault/partial-effect guards; component only"

end CourseRenderTests

def main : IO Unit := CourseRenderTests.check
