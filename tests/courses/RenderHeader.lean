import Lemma.Courses.PackageRender
import Lemma.Courses.Package

namespace CourseHeaderRenderTests
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

private def observe (before : Model) (action : Action) : IO ((UInt8 × UInt64) × Model) := do
  let state ← IO.mkRef {before with reads := #[], writes := #[]}
  let result ← run state action
  return (result, ← state.get)

private def require (value : Bool) (message : String) : IO Unit := do
  unless value do throw <| IO.userError message

def check : IO Unit := do
  let some first ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE" | throw <| IO.userError "real published edition1 required"
  let some second ← IO.getEnv "LEMMA_COURSE_AUTHOR_PACKAGE_FILE" | throw <| IO.userError "real published edition2 required"
  let editions : Array (String × UInt64 × Array UInt64) := #[(first,1,#[0x79a7,0x4927,0x4927,0x7b6f]),
      (second,2,#[0x79a7,0x7492,0x7b6f,0x7b6f])]
  for (file,edition,goldens) in editions do
    let image ← IO.FS.readBinFile file
    require (readBytes image 24 8 == 1 && readBytes image 32 8 == edition) "published identity/edition differs"
    let before : Model := {package := image}
    for field in [:4] do
      let descriptor := readBytes image (96+field.toUInt64*8) 8
      let start := descriptor &&& 0xffffffff
      let length := descriptor >>> 32
      let (result,prepared) ← observe before (PackageRender.prepareHeader source image.size.toUInt64 field.toUInt64 0 cache)
      require (result == (0,length) && prepared.package == image && prepared.framebuffer == before.framebuffer) "header preparation changed source/display/length"
      require (readBytes prepared.glyphs 0 8 == goldens[field]!) "independent literal first glyph/edition anchor differs"
      require ((prepared.reads.filter (fun row => row == (source+start,1))).size == 3) "actual selected header byte read scope differs"
      let (bad,rejected) ← observe before (PackageRender.prepareHeader source image.size.toUInt64 field.toUInt64 (length+1) cache)
      require (bad == (244,0) && rejected.writes.isEmpty) "header position rejection altered cache"
    for action in #[PackageRender.prepareHeader source image.size.toUInt64 4 0 cache,
        PackageRender.prepareHeader source image.size.toUInt64 0 0 source] do
      let (bad,rejected) ← observe before action
      require (bad.1 != 0 && rejected.reads.isEmpty && rejected.writes.isEmpty) "field/source alias admission consumed bytes"
    let corrupt := {before with package := image.set! (image.size-1) 0}
    let (bad,rejected) ← observe corrupt (PackageRender.renderHeaderSelected source image.size.toUInt64 1 0 cache width height)
    require (bad == (243,0) && rejected.writes.isEmpty && rejected.framebuffer == before.framebuffer) "header CRC failure reached presentation"
    for action in #[PackageRender.renderHeaderSelected source image.size.toUInt64 1 0 Lemma.Ink.Surface.framebuffer width height,
        PackageRender.renderHeaderSelected Lemma.Ink.Surface.framebuffer image.size.toUInt64 1 0 cache width height] do
      let (bad,rejected) ← observe before action
      require (bad == (240,0) && rejected.reads.isEmpty && rejected.writes.isEmpty) "header framebuffer alias reached validation/output"
    let descriptor := readBytes image 104 8
    let length := descriptor >>> 32
    let (good,rendered) ← observe before (PackageRender.renderHeaderSelected source image.size.toUInt64 1 0 cache width height)
    require (good == (0,length) && rendered.package == image) "real header connected framebuffer operation failed"
    -- Independent scalar pixels of the first known glyph, and a point in the
    -- untouched canonical typed-goal region. Full renderer pixels are already
    -- separately qualified; this check binds the new header selector to them.
    for y in [:20] do
      for x in [:12] do
        let offset := (320+y)*(width.toNat/2)+(24+x)/2
        let pixel := if x%2 == 0 then rendered.framebuffer[offset]!.toUInt64 >>> 4 else rendered.framebuffer[offset]!.toUInt64 &&& 15
        let expected := if x < 9 && y < 15 then if ((goldens[1]! >>> (14-(y/3*3+x/3)).toUInt64) &&& 1) == 1 then 0 else 15 else 15
        require (pixel == expected) "independent header glyph pixels differ"
    require (rendered.framebuffer[160*(width.toNat/2)+12]! == 0xaa) "header presentation overwrote the canonical typed-goal panel"
  IO.println "COURSE_HEADER_RENDER:PASS actual two published editions, four exact anchors, independent glyph/pixel/goal-region and indexed/position/CRC/alias guards; component only"
end CourseHeaderRenderTests

def main : IO Unit := CourseHeaderRenderTests.check
