import Lemma.Services.Store.Format
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate

/-! Host effect observer of the real Lean checksum declaration. It supplies
bytes and read failures, never a journal or target implementation. The same
elaborated declaration is independently exported through checked LLVM lowering.
Whole-image RV64 execution has a separate receipt. -/
namespace StoreChecksumWords
open Lemma.Core0.Memory

structure Reads where
  base : UInt64
  bytes : ByteArray
  failAt : Option UInt64 := none
  calls : Array (UInt64 × UInt64) := #[]

def read (state : Reads) (address width : UInt64) : Except String UInt64 := do
  if address < state.base || state.bytes.size.toUInt64 < width ||
      state.bytes.size.toUInt64 - width < address - state.base then
    throw "checksum touched outside the declared backing span"
  let offset := (address - state.base).toNat
  let mut word : UInt64 := 0
  for i in [:width.toNat] do
    word := word ||| (state.bytes[offset + i]!.toUInt64 <<< (i.toUInt64 * 8))
  return word

partial def run (state : IO.Ref Reads) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
      let (s,v) ← run state first
      run state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if count.toNat > budget then throw <| IO.userError "invalid bounded checksum loop"
      let mut status : UInt8 := 0
      let mut result := initial
      for i in [:count.toNat] do
        if status = 0 then
          let (s,v) ← run state (step i.toUInt32 count result a b c d)
          status := s
          result := v
      run state (next status result)
  | .platform op a _ _ _ _ _ next => do
      let width ← match op with
        | .virtualRead8 => pure 1
        | .virtualRead64 => pure 8
        | _ => throw <| IO.userError "checksum acquired an unexpected effect"
      let observed ← state.get
      state.modify fun s => {s with calls := s.calls.push (a,width)}
      if observed.failAt.any (fun bad => a ≤ bad && bad - a < width) then
        run state (next 17 0)
      else
        let value ← match read observed a width with
          | .ok value => pure value
          | .error error => throw <| IO.userError error
        run state (next 0 value)
  | _ => throw <| IO.userError "checksum acquired an unexpected Action"

def reference (bytes : ByteArray) (initial : UInt64) : UInt64 :=
  bytes.data.foldl (fun h b => (h ^^^ b.toUInt64) * 1099511628211) initial

def payload (length : Nat) : ByteArray :=
  ByteArray.mk <| (List.range length).toArray.map fun i => ((i * 37 + 19) % 256).toUInt8

def check : IO Unit := do
  let initial : UInt64 := 0xcbf29ce484222325
  -- Fixed independent FNV-1a vectors also catch a changed byte order/prime.
  for (text,expected) in #[ ("",0xcbf29ce484222325), ("a",0xaf63dc4c8601ec8c),
      ("foobar",0x85944171f73967e8), ("12345678",0x173932c41a90a42d) ] do
    if reference text.toUTF8 initial != expected then throw <| IO.userError "reference known-answer mismatch"
  let mut cases := 0
  for base in #[0x20000,0x20003] do
    for length in #[0,1,7,8,9,511,512,2496,32768] do
      let bytes := payload length
      for seed in #[initial,0,0xffffffffffffffff] do
        let state ← IO.mkRef {base,bytes}
        let actual ← run state (Lemma.Services.Store.Format.checksum base length.toUInt64 seed)
        if actual != (0,reference bytes seed) then throw <| IO.userError "real checksum differs from independent byte fold"
        let calls := (← state.get).calls
        let width := if (base ||| length.toUInt64) &&& 7 = 0 then 8 else 1
        if calls.size.toUInt64 != length.toUInt64 / width ||
            calls.any (fun p => p.2 != width) then throw <| IO.userError "read batching or zero-length behavior differs"
        cases := cases + 1
  for bad in #[0,1,7,8,15,511] do
    let state ← IO.mkRef {base:=0x20000,bytes:=payload 512,failAt:=some (0x20000+bad)}
    let actual ← run state (Lemma.Services.Store.Format.checksum 0x20000 512 initial)
    if actual != (17,0) || (← state.get).calls.size != bad.toNat / 8 + 1 then
      throw <| IO.userError "failed word read lost status or continued reading"
  for (address,length) in #[(0x20000,32769),(0xfffffffffffffff8,16)] do
    let state ← IO.mkRef {base:=address,bytes:=ByteArray.empty}
    let actual ← run state (Lemma.Services.Store.Format.checksum address length initial)
    if actual != (220,0) || !(← state.get).calls.isEmpty then
      throw <| IO.userError "invalid bounds touched memory or changed error precedence"
  IO.println s!"STORE_CHECKSUM_WORDS:PASS {cases} byte-reference cases,4 knownanswers,6 readfaults,2 bounds; effects only declared reads"

end StoreChecksumWords

open Lean Elab Command
run_cmd do
  let env ← getEnv
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_1
      #[``Lemma.Services.Store.Format.checksum] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_1 suite
      { preserveCalls := preserved, symbolPrefix := "lemma_checksum_" } with
    | .ok lowered => pure lowered
    | .error error => throwError error
  let mut declarations : Array Lemma.Compiler.LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name := name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map Lemma.Compiler.llvmTy }
  let module : Lemma.Compiler.LLVM.Module :=
    { sourceName := "genuine Store checksum", declarations, functions := lowered.functions }
  match Lemma.Compiler.LLVM.validateModule module with
    | .ok _ => pure () | .error error => throwError error
  if let some output ← liftIO <| IO.getEnv "LEMMA_CHECKSUM_WORDS_OUT" then
    let path := System.FilePath.mk output
    if ← liftIO path.pathExists then throwError "checksum export refuses an existing output directory"
    liftIO <| IO.FS.createDirAll path
    liftIO <| IO.FS.writeFile (path / "program.ll") module.render
    liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  logInfo m!"STORE_CHECKSUM_GENUINE_LLVM:{suite.scalarFunctions.size}:{suite.actionFunctions.size}:{lowered.functions.size}"

def main : IO Unit := StoreChecksumWords.check
