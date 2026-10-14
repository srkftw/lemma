import Lemma.Courses.PackageReference
import Lemma.Courses.PackageTarget

/-! Host-only finite RAM observes the actual imported guest Actions. It supplies
opaque bytes and selected read failures only. Independent Python/zlib observes
the published format separately; genuine LLVM export has a separate artifact. -/
namespace CoursePackageTests
open Lemma.Core0.Memory
open Lemma.Courses

structure Reads where
  base : UInt64 := 0x40000
  bytes : ByteArray
  failCall : Option Nat := none
  calls : Array (UInt64 × UInt64) := #[]

private def read (state : Reads) (address width : UInt64) : Except String UInt64 := do
  if address < state.base || state.bytes.size.toUInt64 < width ||
      state.bytes.size.toUInt64 - width < address - state.base then
    throw "decoder read outside its exact private package buffer"
  let offset := (address - state.base).toNat
  return (List.range width.toNat).foldl
    (fun value i => value ||| (state.bytes[offset+i]!.toUInt64 <<< (i.toUInt64 * 8))) 0

partial def run (state : IO.Ref Reads) : Action → IO (UInt8 × UInt64)
  | .done s value => pure (s,value)
  | .bind first next => do
      let (s,value) ← run state first
      run state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if count.toNat > budget then throw <| IO.userError "decoder exceeded its declared fold budget"
      let mut status : UInt8 := 0
      let mut value := initial
      for i in [:count.toNat] do
        if status = 0 then
          let (s,result) ← run state (step i.toUInt32 count value a b c d)
          status := s
          value := result
      run state (next status value)
  | .platform operation address _ _ _ _ _ next => do
      let width ← match operation with
        | .virtualRead8 => pure 1
        | .virtualRead64 => pure 8
        | _ => throw <| IO.userError "decoder acquired a write, syscall or hidden device operation"
      let before ← state.get
      state.modify fun s => {s with calls := s.calls.push (address,width)}
      if before.failCall == some before.calls.size then run state (next 33 0) else
      let value ← match read before address width with
        | .ok value => pure value | .error message => throw <| IO.userError message
      run state (next 0 value)
  | _ => throw <| IO.userError "decoder acquired undeclared Action syntax"

private def word (bytes : ByteArray) (offset : Nat) : UInt64 :=
  (List.range 8).foldl (fun value i => value ||| (bytes[offset+i]!.toUInt64 <<< (i.toUInt64 * 8))) 0

private def putWord (bytes : ByteArray) (offset : Nat) (value : UInt64) : ByteArray :=
  (List.range 8).foldl (fun output i => output.set! (offset+i) ((value >>> (i.toUInt64*8)).toUInt8)) bytes

/-- Independently spelled UInt32 reference, also bound to four known answers. -/
private def referenceCRC (bytes : ByteArray) : UInt32 := Id.run do
  let mut state : UInt32 := 0xffffffff
  for byte in bytes.data do
    state := state ^^^ byte.toUInt32
    for _ in [:8] do
      state := if state &&& 1 = 0 then state >>> 1 else (state >>> 1) ^^^ 0xedb88320
  return state ^^^ 0xffffffff

private def rechecksum (bytes : ByteArray) : ByteArray :=
  let cleared := putWord (putWord bytes 80 0) 88 0
  let crc := (referenceCRC cleared).toUInt64
  putWord (putWord cleared 80 crc) 88 (crc ^^^ 0xffffffff)

private def expect (image : ByteArray) (action : Action) (result : UInt8 × UInt64) : IO Reads := do
  let state ← IO.mkRef {bytes := image : Reads}
  let actual ← run state action
  if actual != result then throw <| IO.userError s!"decoder returned {actual}, expected {result}"
  let observed ← state.get
  if observed.bytes != image then throw <| IO.userError "observational decoder changed package bytes"
  return observed

def check : IO Unit := do
  let some filename ← IO.getEnv "LEMMA_COURSE_PACKAGE_FILE"
    | throw <| IO.userError "LEMMA_COURSE_PACKAGE_FILE must identify real Lean publisher output"
  let image ← IO.FS.readBinFile filename
  let original ← match Package.encode PackageReference.arithmetic with
    | .ok bytes => pure bytes | .error error => throw <| IO.userError error.render
  if image != original then throw <| IO.userError "publisher bytes differ from the typed source declaration"
  for (input, expected) in #[("",0), ("123456789",0xcbf43926), ("abc",0x352441c2), ("hello",0x3610a686)] do
    if referenceCRC input.toUTF8 != expected then throw <| IO.userError "independent CRC known answer differs"
  let base : UInt64 := 0x40000
  let length := image.size.toUInt64
  let normal ← expect image (PackageTarget.validate base length) (0,8)
  if normal.calls.isEmpty then throw <| IO.userError "decoder did not read any real package bytes"
  for (ordinal,goal) in #[(0,0),(2,1),(5,2),(6,3)] do
    let _ ← expect image (PackageTarget.select base length ordinal) (0,base+128+ordinal*192)
    let _ ← expect image (PackageTarget.goal base length ordinal) (0,goal)
  let _ ← expect image (PackageTarget.select base length 8) (244,0)
  let _ ← expect image (PackageTarget.character base length 2 0 0) (0,89)
  let noReads ← expect image (PackageTarget.character base length 2 8 0) (241,0)
  if !noReads.calls.isEmpty then throw <| IO.userError "invalid text role read package bytes"
  for (address,bytes,status) in #[(base,127,240),(base,32769,242),(base+1,length,240),
      (0xfffffffffffffff8,length,240)] do
    let noReads ← expect image (PackageTarget.validate address bytes) (status,0)
    if !noReads.calls.isEmpty then throw <| IO.userError "argument error performed a read"
  let exercise : Nat := 128 + 2*192
  let mut rejected : Nat := 0
  for (offset,value,status) in #[(8,2,241),(40,17,242),(56,136,240),(72,16385,242),
      (exercise+16,4,241),(exercise+24,2,241),(exercise+32,2,240),(exercise+40,1,241),
      (exercise+48,4,240),(exercise+56,4,240),(exercise+80,1,240)] do
    let changed := rechecksum (putWord image offset value)
    let _ ← expect changed (PackageTarget.validate base length) (status,0)
    rejected := rejected + 1
  let damaged := image.set! (image.size-1) (image[image.size-1]! ^^^ 1)
  let _ ← expect damaged (PackageTarget.validate base length) (243,0)
  let alias := rechecksum (putWord image 96 (word image 96 - 1))
  let _ ← expect alias (PackageTarget.validate base length) (240,0)
  let firstText := (word image 96 &&& 0xffffffff).toNat
  let nonASCII := rechecksum (image.set! firstText 128)
  let _ ← expect nonASCII (PackageTarget.validate base length) (241,0)
  for call in #[0,1,11,12,100,normal.calls.size/2,normal.calls.size-1] do
    let state ← IO.mkRef {bytes := image,failCall := some call : Reads}
    let result ← run state (PackageTarget.validate base length)
    let observed ← state.get
    if result != (33,0) || observed.calls.size != call+1 ||
        observed.calls != normal.calls.extract 0 (call+1) then
      throw <| IO.userError "read error lost its status or changed/continued the read prefix"
  for invalid in #[{PackageReference.arithmetic with identity := 0},
      {PackageReference.arithmetic with nodes := #[]},
      {PackageReference.arithmetic with title := "unsupported lambda: λ"},
      {PackageReference.arithmetic with nodes := Array.replicate 17 PackageReference.arithmetic.nodes[0]!},
      {PackageReference.arithmetic with nodes := #[{PackageReference.arithmetic.nodes[0]! with logicalPrerequisites := #[0]}]}] do
    if (Package.encode invalid).isOk then throw <| IO.userError "authoring accepted an invalid/resource/unsupported declaration"
  IO.println s!"COURSE_PACKAGE_ACTIONS:PASS {image.size} real bytes,8 nodes,{rejected} valid-CRC shape failures,3 corruption/text failures,7 exact read-fault prefixes,4 argument guards,5 typed-authoring rejections; no writes"

end CoursePackageTests

def main : IO Unit := CoursePackageTests.check
