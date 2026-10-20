import Lemma.School.Submission

/-! Structural/admission fault fixture executing actual maintained guest
workspace Actions in bounded test RAM. It is not a target execution receipt. -/
open Lean Lemma.Core0.Memory Lemma.Documents Lemma.Courses

private def setWord (bytes : ByteArray) (offset : Nat) (value : UInt64) : ByteArray :=
  (List.range 8).foldl (fun bytes i => bytes.set! (offset+i) ((value >>> (i.toUInt64*8)).toUInt8)) bytes
private def readWord (bytes : ByteArray) (offset : Nat) : IO UInt64 :=
  IO.ofExcept (Lemma.School.Submission.word bytes offset)
private partial def run (memory : IO.Ref ByteArray) : Action → IO (UInt8 × UInt64)
  | .done status value => pure (status,value)
  | .bind first next => do
    let (s,value) ← run memory first
    run memory (next s value)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if count.toNat > budget || budget > 65536 then throw (IO.userError "fixture fold budget")
    let mut s : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if s == 0 then
        let result ← run memory (step i.toUInt32 count value a b c d)
        s := result.1
        value := result.2
    run memory (next s value)
  | .platform op a b _ _ _ _ next => do
    let bytes ← memory.get
    let width := if op == .virtualRead64 || op == .virtualWrite64 then 8 else 1
    if a.toNat+width > bytes.size then throw (IO.userError "fixture address bound")
    if op == .virtualRead64 then run memory (next 0 (← readWord bytes a.toNat))
    else if op == .virtualWrite64 then
      memory.set (setWord bytes a.toNat b)
      run memory (next 0 0)
    else if op == .virtualRead8 then run memory (next 0 bytes[a.toNat]!.toUInt64)
    else if op == .virtualWrite8 then
      memory.set (bytes.set! a.toNat b.toUInt8)
      run memory (next 0 0)
    else throw (IO.userError "fixture unexpected device operation")
  | _ => throw (IO.userError "fixture unexpected Action")
private def ok (memory : IO.Ref ByteArray) (action : Action) : IO UInt64 := do
  let (status,value) ← run memory action
  if status != 0 then throw (IO.userError s!"guest fixture Action rejected{status}")
  return value

private def build (package context : ByteArray) (kind node : Nat)
    (remote : ByteArray := ByteArray.empty) (edit : Bool := false) : IO ByteArray := do
  if context.size != 104 then throw (IO.userError "fixture context must be104bytes")
  let memory ← IO.mkRef (ByteArray.mk (Array.replicate 131072 0))
  let doc : UInt64 := 0x10000
  let workspace : UInt64 := 0x11000
  let page : UInt64 := 0x12000
  let packed : UInt64 := 0x18000
  let source : UInt64 := 0x19000
  let scratch : UInt64 := 0x1f000
  memory.modify fun bytes => (List.range package.size).foldl (fun bytes i => bytes.set! (source.toNat+i) package[i]!) bytes
  let _ ← ok memory (MathematicsClosure.create doc 1 1)
  for (offset,value) in #[(48,2),(120,2),(56,0),(64,1),(72,1),(80,2),(88,1)] do
    memory.modify fun bytes => setWord bytes (doc.toNat+offset) value
  let _ ← ok memory (MathematicsClosure.completeExecution doc 1 2 1 11 8)
  if remote.size % 64 != 0 || remote.size > 128 then
    throw (IO.userError "fixture remote groups must be complete and bounded")
  for group in [:remote.size / 64] do
    memory.modify fun bytes => (List.range 64).foldl (fun bytes i =>
      bytes.set! (scratch.toNat+i) remote[group*64+i]!) bytes
    let _ ← ok memory (Mathematics.appendRemote doc scratch)
    pure ()
  if edit then
    let _ ← ok memory (Mathematics.edit doc 80 1)
    pure ()
  let _ ← ok memory (PackageWorkspace.create workspace doc 1 1)
  if kind == 1 then
    let _ ← ok memory (PackageWorkspace.captureSelection workspace source package.size.toUInt64 3 scratch)
    pure ()
  let _ ← ok memory (PackageWorkspace.validate workspace 1 1)
  let _ ← ok memory (Ink.emptyPage page 1)
  let chunk : UInt64 := 0x1e000
  let _ ← ok memory (Ink.chunk chunk 1 42 1024 65535)
  for (offset,value) in #[(72,65535),(80,65535),(96,1280),(104,1024)] do
    memory.modify fun bytes => setWord bytes (chunk.toNat+offset) value
  let chunkBytes ← ok memory (Ink.finishChunk chunk 1 1)
  let _ ← ok memory (Ink.addEntry page 0x10001 42)
  let _ ← ok memory (Ink.addEdit page 2 42)
  let _ ← ok memory (Ink.visibility page 42 0)
  let packedBytes ← ok memory (Ink.encodePage page packed)
  let bytes ← memory.get
  let mut output := ByteArray.mk (Array.replicate 256 0)
  output := output ++ bytes.extract workspace.toNat (workspace+PackageWorkspace.bytes).toNat
  output := output ++ bytes.extract packed.toNat (packed+packedBytes).toNat
  output := output ++ bytes.extract chunk.toNat (chunk+chunkBytes).toNat
  let w := readWord context
  for (offset,value) in #[(0,Lemma.School.Submission.magic),(8,1),(16,output.size.toUInt64),
      (24,0x5351000000000012),(32,17),(40,1),(48,1),(56,← readWord bytes (doc.toNat+40)),(64,← w 88),(72,← w 96),
      (80,node.toUInt64),(88,← readWord package 80),(96,← w 72),
      (104,kind.toUInt64),(112,120),(120,← readWord bytes (doc.toNat+96)),(232,256),(240,3712),(248,packedBytes)] do
    output := setWord output offset value
  for i in [:context.size] do output := output.set! (128+i) context[i]!
  return output

def main (args : List String) : IO UInt32 := do
  match args with
  | [package,context,output,kind,node,remote,edit] =>
    let bytes ← build (← IO.FS.readBinFile package) (← IO.FS.readBinFile context)
      (kind.toNat?.getD 2) (node.toNat?.getD 4) (← IO.FS.readBinFile remote) (edit == "edit")
    let decoded ← IO.ofExcept (Lemma.School.Submission.decode bytes)
    IO.FS.writeBinFile output bytes
    IO.println (toJson decoded).compress
    return 0
  | [package,context,output,kind,node] =>
    let bytes ← build (← IO.FS.readBinFile package) (← IO.FS.readBinFile context) (kind.toNat?.getD 1) (node.toNat?.getD 4)
    let decoded ← IO.ofExcept (Lemma.School.Submission.decode bytes)
    IO.FS.writeBinFile output bytes
    IO.println (toJson decoded).compress
    return 0
  | [artifact] =>
    match Lemma.School.Submission.decode (← IO.FS.readBinFile artifact) with
    | .ok value => IO.println (toJson value).compress; return 0
    | .error message => IO.eprintln message; return 1
  | _ => return 2
