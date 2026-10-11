import Lemma.Documents.Ink
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Host-only literal header inputs for the actual guest codec. This interpreter
permits only checked user-word reads/writes, preserves failure statuses, and
never supplies pixels or reconstructs documents for the running guest. -/
namespace InkHeadersFixture
open Lemma.Core0.Memory
open Lemma.Documents

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  reads : Array UInt64 := #[]
  writes : Array (UInt64 × UInt64) := #[]
  rejectedRead : Option UInt64 := none
  rejectedWrite : Option UInt64 := none

def base : UInt64 := 0x318000

def initial (count : UInt64 := 1) (lifecycle : UInt64 := 1)
    (width : UInt64 := 1650) (height : UInt64 := 2200) : State := Id.run do
  let mut s : State := {}
  for (offset,value) in #[(0,0x314b4e49414d454c),(8,1),(16,3),(24,17),(32,99),
      (40,0),(48,count),(56,512),(64,1),(72,65535),(80,65535),(88,4095),
      (96,width),(104,height),(112,lifecycle),(120,0)] do
    s := {s with words := s.words.insert (base+offset) value}
  return s

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .platform op a b _ _ _ _ next =>
    if a % 8 ≠ 0 then throw <| IO.userError "unaligned header word"
    match op with
    | .virtualRead64 =>
      state.modify fun s => {s with reads := s.reads.push a}
      let s ← state.get
      if s.rejectedRead = some a then execute state (next 13 0) else
      let some value := s.words[a]? | throw <| IO.userError "header validation read beyond the128-byte preview"
      execute state (next 0 value)
    | .virtualWrite64 =>
      state.modify fun s => {s with writes := s.writes.push (a,b)}
      let s ← state.get
      if s.rejectedWrite = some a then execute state (next 13 0) else
      state.set {s with words := s.words.insert a b}
      execute state (next 0 0)
    | _ => throw <| IO.userError "header codec attempted unrelated memory/device/syscall effects"
  | _ => throw <| IO.userError "header codec attempted an unexpected Action"

def validation : IO Unit := do
  let mut accepted := 0
  for (width,height) in #[(1650,2200),(1404,1872),(1,162),(4096,4096)] do
    for lifecycle in #[1,3,4,6] do
      for count in #[1,384] do
        let initial := initial count lifecycle width height
        let state ← IO.mkRef initial
        let result ← execute state (Ink.validateChunkHeader base 17 99)
        let final ← state.get
        if result ≠ (0,128+count*72) || final.reads ≠ (List.range 16).toArray.map (fun i => base+i.toUInt64*8) ||
            !final.writes.isEmpty then
          throw <| IO.userError "valid literal header changed bytes/read beyond preview/returned wrong bounded length"
        for i in [:16] do
          let address := base+i.toUInt64*8
          if final.words[address]? ≠ initial.words[address]? then
            throw <| IO.userError "read-only header validation changed a literal word"
        accepted := accepted+1
  -- Literal field mutations must fail even when a surrounding store record has
  -- a valid checksum. Nothing here invokes the store's parser as its oracle.
  let mutations : Array (UInt64 × UInt64) := #[(0,0),(8,0),(8,2),(16,1),(24,0),(24,18),
    (32,0),(32,100),(40,1),(48,0),(48,385),(56,255),(56,8193),(64,0),(64,2),
    (72,0),(72,65536),(80,0),(80,65536),(88,65536),(96,0),(96,4097),(104,0),
    (104,161),(104,4097),(112,0),(112,2),(112,5),(112,7),(112,8),(120,1)]
  for (offset,value) in mutations do
    let initial := initial
    let initial := {initial with words := initial.words.insert (base+offset) value}
    let state ← IO.mkRef initial
    if (← execute state (Ink.validateChunkHeader base 17 99)) ≠ (234,0) ||
        !(← state.get).writes.isEmpty || (← state.get).reads.size ≠ offset.toNat/8+1 then
      throw <| IO.userError s!"malformed field at{offset} was accepted or progressed beyond its rejection"
  for (page,stroke) in #[(0,99),(65,99),(17,0)] do
    let state ← IO.mkRef (initial)
    if (← execute state (Ink.validateChunkHeader base page stroke)) ≠ (234,0) ||
        !(← state.get).reads.isEmpty || !(← state.get).writes.isEmpty then
      throw <| IO.userError "invalid index identity accessed the record"
  -- Non-pressure input is represented honestly; brush/raw/geometry boundary
  -- values retain the existing v1 accepted semantics.
  for (offset,value) in #[(56,256),(56,8192),(72,1),(80,1),(88,0),(88,65535)] do
    let initial := initial
    let state ← IO.mkRef {initial with words := initial.words.insert (base+offset) value}
    if (← execute state (Ink.validateChunkHeader base 17 99)) ≠ (0,200) then
      throw <| IO.userError "valid boundary/non-pressure header was rejected"
  for i in [:16] do
    let state ← IO.mkRef {initial with rejectedRead := some (base+i.toUInt64*8)}
    if (← execute state (Ink.validateChunkHeader base 17 99)) ≠ (13,0) ||
        (← state.get).reads.size ≠ i+1 || !(← state.get).writes.isEmpty then
      throw <| IO.userError "checked header read failure was swallowed or continued"
  IO.println s!"INK_HEADERS:PASS {accepted} valid geometry/count/lifecycle headers,31 literal malformed fields, identity/non-pressure boundaries and16 read failures"

def finishing : IO Unit := do
  for lifecycle in #[1,3,4,6] do
    for count in #[1,384] do
      let state ← IO.mkRef (initial)
      if (← execute state (Ink.finishChunk base count lifecycle)) ≠ (0,128+count*72) ||
          (← state.get).writes ≠ #[(base+48,count),(base+112,lifecycle)] ||
          !(← state.get).reads.isEmpty then
        throw <| IO.userError "valid finished chunk did not publish exactly count/lifecycle"
  for lifecycle in #[0,2,5,7,8,0xffffffffffffffff] do
    let state ← IO.mkRef (initial)
    if (← execute state (Ink.finishChunk base 1 lifecycle)) ≠ (234,0) ||
        !(← state.get).writes.isEmpty then
      throw <| IO.userError "invalid lifecycle partially published a chunk"
  for (count,status) in #[(0,234),(385,235)] do
    let state ← IO.mkRef (initial)
    if (← execute state (Ink.finishChunk base count 1)).1.toUInt64 ≠ status ||
        !(← state.get).writes.isEmpty then
      throw <| IO.userError "chunk count failure changed bytes/status semantics"
  for offset in #[48,112] do
    let state ← IO.mkRef {initial with rejectedWrite := some (base+offset)}
    if (← execute state (Ink.finishChunk base 1 3)).1 ≠ 13 ||
        (← state.get).writes.size ≠ (if offset=48 then 1 else 2) then
      throw <| IO.userError "finishChunk continued after a checked write failure"
  IO.println "INK_FINISH:PASS unchanged v1 bytes for1/3/4/6, malformed origins/no partial invalid writes, count/status and checked-write boundaries"

end InkHeadersFixture
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  liftIO InkHeadersFixture.validation
  liftIO InkHeadersFixture.finishing
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[`Lemma.Documents.Ink.validateChunkHeader, `Lemma.Documents.Ink.finishChunk] with
    | .ok result => pure result
    | .error diagnostic => throwError diagnostic.render
  let result ← match lowerActionSuiteExecution .user_v0_1 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "ink_header_probe_" } with
    | .ok result => pure result
    | .error diagnostic => throwError diagnostic
  let module : LLVM.Module := {sourceName := "genuine guest ink header v1", functions := result.functions}
  match LLVM.validateModule module with
  | .ok () => pure ()
  | .error error => throwError error
  if let some directory ← liftIO <| IO.getEnv "LEMMA_INK_HEADER_PROBE_OUT" then
    let path := System.FilePath.mk directory
    if ← liftIO path.pathExists then throwError "refusing to overwrite retained ink header probe"
    liftIO <| IO.FS.createDirAll path
    liftIO <| IO.FS.writeFile (path / "program.ll") module.render
    liftIO <| IO.FS.writeFile (path / "symbols.txt") result.renderSymbolManifest
  logInfo "INK_HEADER_COMPILE:PASS genuine production Actions elaborated/checked/lowered; RV64 execution separate"
