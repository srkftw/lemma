import Lean
import Lemma.Documents.Ink

/-! Host-only focused execution of the actual page codec Action declarations.
This supplies owned virtual memory effects; it is not live notebook recovery,
rasterization, or RV64 execution evidence. -/
namespace PageCodecProbe
open Lemma.Core0.Memory
open Lemma.Documents

private def resident : UInt64 := 0x1000
private def serialized : UInt64 := 0x7000
private def restored : UInt64 := 0xd000

private def readWord (bytes : Array UInt8) (address : UInt64) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:8] do
    value := value ||| (bytes[address.toNat + i]!.toUInt64 <<< UInt64.ofNat (8 * i))
  return value

private def writeWord (bytes : Array UInt8) (address value : UInt64) : Array UInt8 := Id.run do
  let mut output := bytes
  for i in [:8] do
    output := output.set! (address.toNat + i) ((value >>> UInt64.ofNat (8 * i)).toUInt8)
  return output

private partial def run (memory : IO.Ref (Array UInt8)) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status, value)
  | .bind first next => do
      let (status, value) ← run memory first
      run memory (next status value)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next => do
      if budget < count.toNat then run memory (next 9 initial) else
      let mut value := initial
      let mut status : UInt8 := 0
      for i in [:count.toNat] do
        if status = 0 then
          let (s, v) ← run memory (step (UInt32.ofNat i) count value c0 c1 c2 c3)
          status := s
          value := v
      run memory (next status value)
  | .platform operation a b _ _ _ _ next => do
      if a.toNat > 0x20000 - 8 then throw <| IO.userError "page probe memory bounds" else
      match operation with
      | .virtualRead64 => run memory (next 0 (readWord (← memory.get) a))
      | .virtualWrite64 =>
          memory.modify fun bytes => writeWord bytes a b
          run memory (next 0 0)
      | _ => throw <| IO.userError "page probe rejects non-word memory effect"
  | _ => throw <| IO.userError "page probe rejects unsupported Action"

private def require (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message

private def action (memory : IO.Ref (Array UInt8)) (program : Action) : IO UInt64 := do
  let (status, value) ← run memory program
  require (status == 0) s!"actual page Action failed status {status}"
  return value

private def get (memory : IO.Ref (Array UInt8)) (address : UInt64) : IO UInt64 :=
  return readWord (← memory.get) address

private def put (memory : IO.Ref (Array UInt8)) (address value : UInt64) : IO Unit :=
  memory.modify fun bytes => writeWord bytes address value

private def rejectPreserving (memory : IO.Ref (Array UInt8)) (program : Action) : IO Unit := do
  let before := (← memory.get).extract restored.toNat (restored + Ink.pageBytes).toNat
  let (status, _) ← run memory program
  require (status == Ink.malformed) s!"malformed page accepted: {status}"
  require ((← memory.get).extract restored.toNat (restored + Ink.pageBytes).toNat == before)
    "malformed page partially replaced resident content"

private def artifact (memory : IO.Ref (Array UInt8)) (directory name : String) (start bytes : UInt64) : IO Unit := do
  IO.FS.writeBinFile (System.FilePath.mk directory / name)
    (ByteArray.mk ((← memory.get).extract start.toNat (start + bytes).toNat))

private def stopStep (_ _ : UInt32) (_ _ _ _ _ : UInt64) : Action := .done 10 77

def main (arguments : List String) : IO UInt32 := do
  let directory := arguments.headD "build/lemmasim/page-codec-probe"
  let path := System.FilePath.mk directory
  if ← path.pathExists then throw <| IO.userError "page probe refuses existing output"
  IO.FS.createDirAll path
  let memory ← IO.mkRef (Array.replicate 0x20000 (255 : UInt8))
  let stop : Action := .boundedFoldU64 1 stopStep 1 0 0 0 0 0 fun s value => .done s value
  require ((← run memory stop) == (10, 77)) "probe changed compiled fold stop semantics"
  let _ ← action memory (Ink.emptyPage resident 16)
  require ((← action memory (Ink.encodePage resident serialized)) == 128) "empty packed extent"
  artifact memory directory "empty-page-v2.bin" serialized 128
  let _ ← action memory (Ink.addEntry resident 65537 7)
  let _ ← action memory (Ink.addEdit resident 1 7)
  require ((← action memory (Ink.encodePage resident serialized)) == 168) "first stroke packed extent"
  require ((← get memory (serialized + 8)) == 2) "writer did not identify v2"
  require ((← get memory (serialized + 152)) == 1) "packed edit offset"
  artifact memory directory "one-stroke-page-v2.bin" serialized 168
  let _ ← action memory (Ink.addEntry resident 65538 8)
  let _ ← action memory (Ink.addEdit resident 1 8)
  let _ ← action memory (Ink.undo resident)
  let bytes ← action memory (Ink.encodePage resident serialized)
  require (bytes == 208) "two stroke packed extent"
  require ((← action memory (Ink.pageRecordBytes serialized)) == bytes) "version-selected extent"
  let _ ← action memory (Ink.decodePage serialized restored 16 bytes)
  require ((← get memory (restored + 8)) == 1) "resident version changed"
  require ((← get memory (restored + 48)) == 1) "undo cursor lost"
  require ((← get memory (Ink.entry restored 1 + 16)) == 0) "undo visibility lost"
  require ((← get memory (Ink.entry restored 2)) == 0) "unused entries not cleared"
  require ((← get memory (Ink.edit restored 2)) == 0) "unused redo suffix not cleared"
  let _ ← action memory (Ink.redo restored)
  require ((← get memory (Ink.entry restored 1 + 16)) == 1) "redo after decode failed"
  let _ ← action memory (Ink.undo restored)
  artifact memory directory "two-stroke-undo-page-v2.bin" serialized bytes
  artifact memory directory "two-stroke-undo-resident.bin" restored Ink.pageBytes
  rejectPreserving memory (Ink.decodePage serialized restored 16 (bytes - 8))
  rejectPreserving memory (Ink.decodePage serialized restored 17 bytes)
  put memory (serialized + 8) 3
  rejectPreserving memory (Ink.decodePage serialized restored 16 bytes)
  put memory (serialized + 8) 2
  put memory (serialized + 56) 1
  rejectPreserving memory (Ink.decodePage serialized restored 16 bytes)
  put memory (serialized + 56) 0
  put memory (serialized + 176) 0
  rejectPreserving memory (Ink.decodePage serialized restored 16 bytes)
  put memory (serialized + 176) 1
  put memory (serialized + 32) 513
  rejectPreserving memory (Ink.decodePage serialized restored 16 bytes)
  put memory (serialized + 32) 2
  require ((← action memory (Ink.pageRecordBytes resident)) == Ink.pageBytes) "legacy extent lost"
  let _ ← action memory (Ink.decodePage resident restored 16 Ink.pageBytes)
  require ((← memory.get).extract resident.toNat (resident + Ink.pageBytes).toNat ==
    (← memory.get).extract restored.toNat (restored + Ink.pageBytes).toNat) "legacy v1 copy changed"
  artifact memory directory "legacy-page-v1.bin" resident Ink.pageBytes
  IO.FS.writeFile (path / "result.json")
    "{\"status\":\"PASS\",\"scope\":\"actual Lean Action codec, host virtual-memory effects; not RV64 execution\",\"empty_bytes\":128,\"one_stroke_bytes\":168,\"two_stroke_bytes\":208,\"rejected_malformed_boundaries\":6}\n"
  return 0
end PageCodecProbe

def main (arguments : List String) : IO UInt32 := PageCodecProbe.main arguments
