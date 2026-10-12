import Lemma.Kernel.Memory.Frames
import Lemma.Compiler.CFGLower

/-! Host-only independent request/partial-write reference for the maintained
zero callback. It also genuinely elaborates and lowers Frames.zero. No fixture
or host executor enters any target image. The private callback alias refers to
the actual imported declaration; its body is never copied into an observation. -/
open Lean Elab Command
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith "Frames.zeroStep"
  unless candidates.length = 1 do throwError "expected exactly one maintained zeroStep"
  let n := mkIdent candidates.head!.1
  elabCommand (← `(def $(mkIdent `observedZeroStep) (i count : UInt32)
      (acc frame a b c : UInt64) : Lemma.Core0.Memory.Action := $n i count acc frame a b c))

namespace ZeroLocal
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
-- Independent historical source form, including eighth-write result value.
def reference (i : UInt32) (_count : UInt32) (acc frame _ _ _ : UInt64) : Action :=
  let start := frame + i.toUInt64 * 64
  .bind (Access.write64 (start + 0) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 8) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 16) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 24) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 32) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 40) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 48) 0) fun s _ =>
  if Frames.failed s = true then .done s 0 else
  .bind (Access.write64 (start + 56) 0) fun s _ => .done s acc

structure Request where
  op : Lemma.Core0.Execution.Op
  address : UInt64
  value : UInt64
  status : UInt8
  deriving BEq
structure State where
  requests : Array Request := #[]
  writes : Nat := 0
  failAt : Nat := 8
  failure : UInt8 := 7

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message

-- Exact fixed kernel physical-region priority, independently stated.
def boundary (address : UInt64) : UInt8 :=
  if address % 8 = 0 then
    if 0x80200000 ≤ address && address ≤ 0x802ffff8 then 5 else
    if 0x80400000 ≤ address && address ≤ 0x804ffff8 then 0 else
    if 0x80500000 ≤ address && address ≤ 0x8050fff8 then 0 else
    if 0x80600000 ≤ address && address ≤ 0x806ffff8 then 5 else
    if 0x82000000 ≤ address && address ≤ 0x83fffff8 then 0 else
    if 0x87e00000 ≤ address && address ≤ 0x87fffff8 then 5 else 7
  else 8

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .platform op address value _ _ _ _ next =>
    let old ← state.get
    let mut s := boundary address
    let mut v : UInt64 := 0
    if op = .physicalRead64 then
      require (address = Frames.configuration) "unexpected zeroing read"
      if s = 0 then v := 8192
    else
      require (op = .physicalWrite64 && value = 0) "unexpected zeroing write"
      if s = 0 && old.writes = old.failAt then s := old.failure
    state.set {old with
      requests := old.requests.push (⟨op,address,value,s⟩ : Request)
      writes := old.writes + (if op = .physicalWrite64 && s = 0 then 1 else 0)}
    execute state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "zeroing fold exceeded checked bound"
    let mut result := (0,initial)
    for i in [:count.toNat] do
      if result.1 = 0 then result ← execute state (step i.toUInt32 count result.2 a b c d)
    execute state (next result.1 result.2)
  | _ => throw <| IO.userError "unexpected zeroing action"

def compare (first second : Action) (failAt : Nat) (failure : UInt8) : IO State := do
  let a ← IO.mkRef ({failAt,failure} : State)
  let b ← IO.mkRef ({failAt,failure} : State)
  let ra ← execute a first
  let rb ← execute b second
  require (ra = rb && (← a.get).requests == (← b.get).requests &&
    (← a.get).writes = (← b.get).writes) "zeroing changed status/value/request or successful write prefix"
  pure (← b.get)

def referencePage (frame : UInt64) : Action :=
  if Frames.frameAddressValid frame = false then .done Frames.invalidFrame 0 else
  .bind Frames.runtimeCount fun s count =>
  if Frames.failed s = true then .done s 0 else
  if Frames.pool + count * Frames.bytes ≤ frame then .done Frames.invalidFrame 0 else
  .boundedFoldU64 64 reference 64 0 frame 0 0 0 fun s v => .done s v

run_cmd do
  liftIO do
    let addresses : Array UInt64 := #[0,0x801ffff8,0x80200000,0x802fffc0,0x802ffff8,
      0x803ffff8,0x80400000,0x804fffc0,0x804ffff8,0x80500000,0x8050ffc0,0x8050fff8,
      0x80600000,0x806fffc0,0x806ffff8,0x81ffffc0,0x81fffff8,0x82000000,0x82000001,
      0x83ffffc0,0x83ffffc8,0x83fffff8,0x84000000,0x87e00000,0x87ffffc0,0x87fffff8,
      0xffffffffffffffc0,0xfffffffffffffff8,0xffffffffffffffff]
    for address in addresses do
      for index in #[0,1,63,64,0xffffffff] do
        for failure in #[1,7,255] do
          for position in [:9] do
            discard <| compare (reference index 64 19 address 31 37 41)
              (observedZeroStep index 64 19 address 31 37 41) position failure
    -- Exhaustive callback status domain at each admitted fault position.
    for status in [:256] do
      for position in [:9] do
        discard <| compare (reference 17 64 19 0x82000000 31 37 41)
          (observedZeroStep 17 64 19 0x82000000 31 37 41) position status.toUInt8
    -- One property ranges over every full-page first-error position.
    for position in [:513] do
      let actual ← compare (referencePage 0x83fff000) (Frames.zero 0x83fff000) position 7
      require (actual.writes = min position 512) "page zero changed successful prefix"
      for i in [:actual.writes] do
        let some row := actual.requests[i+1]? | throw <| IO.userError "missing actual page write"
        require (row.address = 0x83fff000+i.toUInt64*8 && row.value = 0 && row.status = 0)
          "page zero omitted/reordered/corrupted a checked store"
    IO.println "ZERO_LOCAL:PASS independent boundaries/wrap/all statuses/all512 fault positions and ordered checked zero stores"

open Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_4 #[`Lemma.Kernel.Memory.Frames.zero] with
    | .ok s => pure s | .error e => throwError e.render
  let lowered ← match lowerActionSuiteExecution .kernel_v0_4 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineLiteralConstants := true, inlinePrimitiveWrappers := true, symbolPrefix := "zero_" } with
    | .ok s => pure s | .error e => throwError e
  let module : LLVM.Module := { sourceName := "maintained locally bounded zeroing", functions := lowered.functions }
  match LLVM.validateModule module with
    | .ok () => pure () | .error e => throwError e
  let some directory ← liftIO <| IO.getEnv "LEMMA_ZERO_LOCAL_OUT" | throwError "fresh output required"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite zeroing fixture"
  liftIO <| IO.FS.createDirAll path
  liftIO <| IO.FS.writeFile (path / "program.ll") module.render
  liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  logInfo "ZERO_LOCAL_COMPILE:PASS maintained genuine checked LLVM"
end ZeroLocal
