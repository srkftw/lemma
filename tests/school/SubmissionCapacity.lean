import Lemma.School.Submission

/-! Private preparation: genuine retained guest-Action workspace bytes are
unchanged; only declared raw ink stimulus/index records are expanded. This is
hosted parser evidence, distinct from target queue/Store execution. -/
open Lean Lemma.School.Submission

private def setWord (bytes : ByteArray) (offset : Nat) (value : UInt64) : ByteArray :=
  (List.range 8).foldl (fun bytes i => bytes.set! (offset+i) ((value >>> (i.toUInt64*8)).toUInt8)) bytes
private def w (bytes : ByteArray) (offset : Nat) : IO UInt64 := IO.ofExcept (word bytes offset)
private def require (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw (IO.userError message)

private def expanded (base : ByteArray) (count samples wireVersion : Nat) : IO ByteArray := do
  let _ ← IO.ofExcept (decode base)
  let originalChunk := 3968+(← w base 248).toNat
  let header := base.extract originalChunk (originalChunk+128)
  let indexBytes := 128+count*24+count*16
  let mut index := ByteArray.mk (Array.replicate indexBytes 0)
  for (offset,value) in #[(0,Lemma.Documents.Ink.magic),(8,2),(16,2),(24,1),
      (32,count.toUInt64),(40,count.toUInt64),(48,count.toUInt64)] do
    index := setWord index offset value
  let mut raw := ByteArray.empty
  for i in [:count] do
    let visible := i%3 != 0
    index := setWord index (128+i*24) (0x10001+i.toUInt64)
    index := setWord index (136+i*24) (42+i.toUInt64)
    index := setWord index (144+i*24) (if visible then 1 else 0)
    index := setWord index (128+count*24+i*16) (if visible then 1 else 2)
    index := setWord index (136+count*24+i*16) (42+i.toUInt64)
    let n := if samples == 0 then 1+i%2 else samples
    let mut chunk := setWord (setWord header 32 (42+i.toUInt64)) 48 n.toUInt64
    for j in [:n] do
      let mut sample := ByteArray.mk (Array.replicate 72 0)
      for (offset,value) in #[(0,0x1000000000000000+i.toUInt64*384+j.toUInt64),
          (8,0x0800000000000000+i.toUInt64*1000+j.toUInt64),
          (16,((i*1739+j*27)%65536).toUInt64),(24,((20000+i*113+j*17)%65536).toUInt64),
          (32,32768),(40,1)] do sample := setWord sample offset value
      chunk := chunk++sample
    raw := raw++chunk
  let mut result := base.extract 0 3968 ++ index ++ raw
  result := setWord result 8 wireVersion.toUInt64
  result := setWord result 16 result.size.toUInt64
  result := setWord result 248 indexBytes.toUInt64
  return result

private def accepted (name : String) (bytes : ByteArray) (count wireVersion : Nat) : IO Json := do
  let value ← IO.ofExcept (decode bytes)
  require (value.chunks.size == count && value.wireVersion == wireVersion) s!"{name}: count/version changed"
  require (value.chunks.any (fun chunk => !chunk.visible) && value.chunks.any (fun chunk => chunk.visible))
    s!"{name}: original invisible/visible records lost"
  for i in [:count] do
    let some chunk := value.chunks[i]? | throw (IO.userError "validated chunk absent")
    require ((← w bytes (chunk.offset+128)) == 0x1000000000000000+i.toUInt64*384)
      s!"{name}: full-width sequence changed"
    require ((← w bytes (chunk.offset+136)) == 0x0800000000000000+i.toUInt64*1000)
      s!"{name}: full-width timestamp changed"
    require (chunk.object == 0x10001+i && chunk.stroke == 42+i) s!"{name}: order/identity changed"
  return Json.mkObj [("case",toJson name),("result",toJson "PASS"),("bytes",toJson bytes.size),
    ("chunks",toJson count),("wireVersion",toJson wireVersion),("CRC32",toJson (crc32 bytes)),
    ("rawLengths",toJson (value.chunks.map (·.bytes)))]

private def rejected (name : String) (bytes : ByteArray) : IO Json := do
  match decode bytes with
  | .ok _ => throw (IO.userError s!"{name}: invalid artifact accepted")
  | .error reason => return Json.mkObj [("case",toJson name),("result",toJson "PASS"),("rejected",toJson reason)]

def main (args : List String) : IO UInt32 := do
  match args with
  | [input,output] =>
    let base ← IO.FS.readBinFile input
    let legacy ← IO.ofExcept (decode base)
    require (legacy.wireVersion == 1 && legacy.chunks.size == 1) "legacy source fixture differs"
    let directory := System.FilePath.mk output
    IO.FS.createDirAll directory
    let work32 ← expanded base 32 0 2
    let work512 ← expanded base 512 1 2
    let work9 ← expanded base 9 384 2
    let work10 ← expanded base 10 384 2
    let mut rows : Array Json := #[]
    rows := rows.push (← accepted "32-strokes-odd-chunk-boundaries" work32 32 2)
    rows := rows.push (← accepted "512-short-strokes-complete-index" work512 512 2)
    rows := rows.push (← accepted "nine-full-chunks-under-byte-limit" work9 9 2)
    rows := rows.push (← rejected "ten-full-chunks-over-byte-limit" work10)
    rows := rows.push (← rejected "v1-cannot-advertise32" (setWord work32 8 1))
    rows := rows.push (← rejected "unknown-envelope-version" (setWord work32 8 3))
    rows := rows.push (← rejected "truncated-raw-body" (setWord (work32.extract 0 (work32.size-8)) 16 (work32.size-8).toUInt64))
    rows := rows.push (← rejected "duplicate-original-raw-object" (setWord work32 (3968+128+24) 0x10001))
    let eight ← expanded base 8 0 1
    let nine ← expanded base 9 0 1
    rows := rows.push (← accepted "original-v1-eight-chunk-bound" eight 8 1)
    rows := rows.push (← rejected "original-v1-ninth-chunk-reject" nine)
    require ((← w work32 248) == 1408) "32-stroke packed index differs"
    require ((← w work512 248)+3968 == 24576) "512-stroke metadata does not exactly fit24KiB"
    IO.FS.writeBinFile (directory/"v1-original.bin") base
    IO.FS.writeBinFile (directory/"v2-32-strokes.bin") work32
    IO.FS.writeBinFile (directory/"v2-512-strokes.bin") work512
    IO.FS.writeBinFile (directory/"v2-nine-full.bin") work9
    IO.FS.writeBinFile (directory/"v2-over-limit.bin") work10
    IO.FS.writeFile (directory/"results.json") (toJson rows).pretty
    IO.println (Json.mkObj [("result",toJson "PASS"),("checks",toJson rows.size),
      ("scope",toJson "private hosted v1/v2 decoder; genuine retained guest-Action workspace plus explicit raw-stimulus records; target queue/Store/retry/cold-restore separate")]).compress
    return 0
  | _ => return 2
