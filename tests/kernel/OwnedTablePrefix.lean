import Lemma.Kernel.Memory.AddressSpace
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lean

/-! Host-only finite RAM oracle. The reference retains the previous pure-prefix
enumeration but calls the actual unchanged tableAt authority. All read/fault
prefixes and later-handle errors are compared, not just successful values. -/
open Lean Elab Command
run_cmd do
  for (suffix,aliasName) in [("AddressSpace.ownedTable",`observedOwnedTable),
      ("AddressSpace.tableAt",`observedTableAt)] do
    let rows := (← getEnv).constants.toList.filter (·.1.toString.endsWith suffix)
    unless rows.length = 1 do throwError "exact maintained table authority required"
    let n := mkIdent rows.head!.1
    elabCommand (← `(def $(mkIdent aliasName) (address table : UInt64) :
      Lemma.Core0.Memory.Action := $n address table))

namespace OwnedTablePrefix
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
private def descriptor : UInt64 := 0x82080000
structure State where
  amount : UInt64 := 14
  trace : Array UInt64 := #[]
  callbacks : Nat := 0
  failAt : Option Nat := none
  corruptAt : UInt64 := 0
  corruptValue : UInt64 := 0
  deriving Inhabited
private def value (s : State) (a : UInt64) : UInt64 :=
  if a = s.corruptAt then s.corruptValue else
  if a = descriptor+40 then s.amount else
  if a = descriptor+24 then 2 else
  if descriptor+128 ≤ a && a < descriptor+384 then
    8192+(a-descriptor-128)/8 else
  if a = Frames.configuration then 8192 else
  if Frames.records ≤ a && a < Frames.records+32*32 then
    if (a-Frames.records)%32 = 0 then 2 else
    if (a-Frames.records)%32 = 8 then 2 else
    if (a-Frames.records)%32 = 24 then 1 else 0
  else 0
partial def execute (cell : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute cell first
    execute cell (next s v)
  | .boundedFoldU64 bound step count acc a b c d next =>
    if count.toNat > bound then throw (IO.userError "unexpected fold limit")
    let mut result := (0,acc)
    for i in [:count.toNat] do
      if result.1 = 0 then
        cell.modify fun s => {s with callbacks := s.callbacks+1}
        result ← execute cell (step i.toUInt32 count result.2 a b c d)
    execute cell (next result.1 result.2)
  | .platform op address _ _ _ _ _ next =>
    if op != .physicalRead64 then throw (IO.userError "unexpected effect in table scan")
    let s ← cell.get
    if s.trace.size ≥ 256 then throw (IO.userError "finite read budget")
    cell.set {s with trace := s.trace.push address}
    execute cell (next (if s.failAt = some s.trace.size then 7 else 0) (value s address))
  | _ => throw (IO.userError "unexpected Action in table scan")
private def referenceStep (i _ : UInt32) (acc address wanted _ _ : UInt64) : Action :=
  if i < 8 then .done 0 acc else
  .bind (observedTableAt address i.toUInt64) fun s table =>
  if AddressSpace.failed s then .done s 0 else .done 0 (if table = wanted then 1 else acc)
private def reference (address table : UInt64) : Action :=
  .bind (Access.read64 (address+40)) fun s amount =>
  if AddressSpace.failed s then .done s 0 else
  if amount ≤ 32 then
  .boundedFoldU64 32 referenceStep amount.toUInt32 0 address table 0 0 fun s found =>
  if AddressSpace.failed s then .done s 0 else
  if found = 1 then .done 0 table else .done AddressSpace.invalidPte 0
  else .done AddressSpace.invalidDescriptor 0
private def compare (initial : State) (wanted : UInt64) (expected : UInt8) : IO Nat := do
  let a ← IO.mkRef initial;let b ← IO.mkRef initial
  let old ← execute a (reference descriptor wanted)
  let current ← execute b (observedOwnedTable descriptor wanted)
  let x ← a.get;let y ← b.get
  if old != current || x.trace != y.trace || current.1 != expected then
    throw (IO.userError s!"table status or complete ordered read/fault trace differs: {old}/{current}")
  pure y.trace.size
def check : IO Unit := do
  for amount in #[(0 : UInt64),8,9,14,32,33] do
    for index in #[(8 : UInt64),13,31,33] do
      let expected := if 32 < amount then AddressSpace.invalidDescriptor else
        if 8 ≤ index && index < amount then (0 : UInt8) else AddressSpace.invalidPte
      discard <| compare {amount} (Frames.pool+index*4096) expected
  let reads ← compare {} (Frames.pool+8*4096) 0
  if reads != 37 then throw (IO.userError "complete six-handle authority trace was omitted")
  for i in [:reads] do
    discard <| compare {failAt := some i} (Frames.pool+8*4096) 7
  for (address,v,expected) in #[(descriptor+24,0,Frames.invalidFrame),
      (descriptor+128+13*8,16384+13,Frames.notOwned),
      (Frames.records+13*32,1,Frames.notOwned),(Frames.records+13*32+8,3,Frames.purposeDenied),
      (Frames.records+13*32+24,2,Frames.notOwned)] do
    discard <| compare {corruptAt := address,corruptValue := v} (Frames.pool+8*4096) expected
  let a ← IO.mkRef ({} : State);let b ← IO.mkRef ({} : State)
  discard <| execute a (reference descriptor (Frames.pool+8*4096))
  discard <| execute b (observedOwnedTable descriptor (Frames.pool+8*4096))
  let old ← a.get;let current ← b.get
  if old.callbacks != 14 || current.callbacks != 6 then throw (IO.userError "pure prefix was not removed")
  IO.println s!"OWNED_TABLE_PREFIX:PASS 24 domains,{reads} exact fault prefixes,5 late authority corruptions; callbacks14→6,read trace={reads}"
end OwnedTablePrefix

run_cmd do
  let env ← getEnv
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .kernel_v0_3
      #[`observedOwnedTable] with
    | .ok suite => pure suite | .error error => throwError error.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .kernel_v0_3 suite
      {preserveCalls := preserved,symbolPrefix := "lemma_table_prefix_"} with
    | .ok lowered => pure lowered | .error error => throwError error
  let mut declarations : Array Lemma.Compiler.LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name := name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map Lemma.Compiler.llvmTy }
  let module : Lemma.Compiler.LLVM.Module :=
    {sourceName := "genuine maintained owned table scan",declarations,functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
  | .ok _ => pure () | .error error => throwError error
  if let some directory ← liftIO <| IO.getEnv "LEMMA_TABLE_PREFIX_OUT" then
    let p := System.FilePath.mk directory
    if ← liftIO p.pathExists then throwError "export requires unused output"
    liftIO <| IO.FS.createDirAll p
    liftIO <| IO.FS.writeFile (p/"program.ll") module.render
    liftIO <| IO.FS.writeFile (p/"symbols.txt") lowered.renderSymbolManifest
  logInfo m!"OWNED_TABLE_GENUINE_LLVM:{lowered.functions.size}"

def main : IO Unit := OwnedTablePrefix.check
