import Lean.Compiler.Main
import Lemma.Core0.Frontend
import Lemma.Compiler.CFGLower
import Lemma.Mathematics.ManagedByteSubmission

/-! Genuine source/IR/LLVM qualification. The output is a component object,
not an isolated guest image or a mathematical evidence authority. -/
namespace Lemma.Compiler.Test.ManagedBytes
open Lemma.Core0.Memory

@[noinline] def make (capacity a b : UInt64) : ByteArray :=
  (ByteArray.emptyWithCapacity capacity.toNat).push a.toUInt8 |>.push b.toUInt8 |>.push 42
@[noinline] def size (bytes : ByteArray) : UInt64 := bytes.size.toUInt64
@[noinline] def read (bytes : ByteArray) (index : UInt64) : UInt64 := (bytes.get! index.toNat).toUInt64
@[noinline] def write (bytes : ByteArray) (index value : UInt64) : ByteArray := bytes.set! index.toNat value.toUInt8
@[noinline] def alias (capacity a b : UInt64) : UInt64 :=
  let bytes := make capacity a b
  let next := bytes.push 7
  size bytes + size next
@[noinline] def alias2 (a b : UInt64) : UInt64 := alias 3 a b
@[noinline] def mutate2 (a b : UInt64) : UInt64 :=
  let bytes := make 3 a b
  let next := write bytes 0 255
  size next * 256 + read next 0
@[noinline] def staticPayload (a b : UInt64) : UInt64 :=
  let bytes := (ByteArray.emptyWithCapacity 2).push a.toUInt8 |>.push b.toUInt8
  size bytes
@[noinline] def genericArray (a b : UInt64) : UInt64 :=
  let bytes := #[a, b]
  bytes.size.toUInt64
@[noinline] def scalarOnly (a b : UInt64) : UInt64 := a + b
@[noinline] def booleanSource (a b : UInt64) : Bool := a = b
@[noinline] def booleanCaller (a b : UInt64) : UInt64 :=
  let bytes := make 3 a b
  if booleanSource a b then size bytes else size bytes + 1

def entry (lhs rhs : UInt64) : Action :=
  .managedBytes2 Lemma.Mathematics.ManagedByteSubmission.compareFiveSix lhs rhs fun s v => .done s v

def aliasEntry (lhs rhs : UInt64) : Action :=
  .managedBytes2 alias2 lhs rhs fun s v => .done s v

def mutateEntry (lhs rhs : UInt64) : Action :=
  .managedBytes2 mutate2 lhs rhs fun s v => .done s v

def dynamic (function : UInt64 → UInt64 → UInt64) (lhs rhs : UInt64) : Action :=
  .managedBytes2 function lhs rhs fun s v => .done s v

open Lean Elab Command

/-- Mutates only real compiler output for rejection tests. It never supplies
source behavior to the maintained lowering path. -/
partial def corrupt (which : Nat) (body : IR.FnBody) : IR.FnBody × Nat :=
  match body with
  | .vdecl x ty expression next =>
    let (next,count) := corrupt which next
    match expression with
    | .fap name args =>
      if which == 4 && name == ``ByteArray.push then
        (.vdecl x ty (.fap ``IO.println args) next,count+1)
      else (.vdecl x ty expression next,count)
    | _ => (.vdecl x ty expression next,count)
  | .inc x n conditional persistent next =>
    let (next,count) := corrupt which next
    if which == 1 then (.inc x 2 conditional persistent next,count+1) else
    if which == 2 then (.inc x n true persistent next,count+1) else
    (.inc x n conditional persistent next,count)
  | .dec x n conditional persistent next =>
    let (next,count) := corrupt which next
    if which == 3 then (.dec x n conditional true next,count+1) else
    (.dec x n conditional persistent next,count)
  | .case name source ty alternatives =>
    let changed : Array (IR.Alt × Nat) := alternatives.map fun alternative =>
      match alternative with
      | .ctor info branch => let (branch,count) := corrupt which branch; (.ctor info branch,count)
      | .default branch => let (branch,count) := corrupt which branch; (.default branch,count)
    (.case name source ty (changed.map (·.1)),changed.foldl (fun n e => n+e.2) 0)
  | _ => (body,0)

run_elab do
  let root := ``Lemma.Mathematics.ManagedByteSubmission.compareFiveSix
  Compiler.compile #[root,``alias2,``mutate2,``staticPayload,``genericArray,``scalarOnly,``booleanCaller]
  let env ← getEnv
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_4 #[``entry,``aliasEntry,``mutateEntry] with
    | .ok value => pure value
    | .error error => throwError error.render
  unless suite.contractVersion == "core0-user-v0.4" && suite.actionFunctions.any
      (fun f => (Lemma.Core0.ManagedBytesIR.generatedSource? f.name).isSome) &&
      suite.usedExecutionOps.all (·.operation.admits .user_v0_4) do
    throwError "actual ByteArray profile/source/User effect closure differs"
  for profile in #[Lemma.Core0.Profile.v0_1,.v0_2,.v0_3,.v0_4,.v0_5,.v0_6,.v0_7,
      .user_v0_1,.user_v0_2,.user_v0_3,.firmware_v0_1,.firmware_v0_2,
      .kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,.kernel_v0_5,.kernel_v0_6,.kernel_v0_7,.boot_v0_1,.boot_v0_2] do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env profile #[``entry] with
    | .ok _ => throwError m!"unadmitted profile acquired ByteArray authority: {profile.contractVersion}"
    | .error error =>
      unless error.code == .unsupportedPrimitive ||
          (!profile.isExecution && error.code == .invalidSuite) do throwError error.render
  match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_4 #[``dynamic] with
    | .ok _ => throwError "dynamic ByteArray entry escaped closed ordinary source"
    | .error _ => pure ()
  for source in #[``staticPayload,``genericArray,``scalarOnly,``booleanCaller] do
    match Lemma.Core0.ManagedBytesIR.buildProgram env source with
    | .ok _ => throwError m!"unadmitted genuine source accepted: {source}"
    | .error _ => pure ()
  let program ← match Lemma.Core0.ManagedBytesIR.buildProgram env root with
    | .ok value => pure value
    | .error error => throwError error
  unless program.sourceNames.size == 5 do throwError "actual ordinary16-byte submission closure differs"
  let mut rejected : Array Json := #[]
  for which in [1,2,3,4] do
    let mut mutated := env
    let mut count := 0
    for name in #[``alias,``make] do
      let some (.fdecl owner params result body info) := IR.findEnvDecl env name
        | throwError "genuine mutation owner absent"
      let (body,changed) := corrupt which body
      count := count+changed
      mutated := IR.declMapExt.addEntry mutated (.fdecl owner params result body info)
    unless count>0 do throwError "actual ownership/foreign mutation anchor absent"
    match Lemma.Core0.ManagedBytesIR.buildProgram mutated ``alias2 with
      | .ok _ => throwError m!"actual compiler IR corruption accepted: {which}"
      | .error error => rejected := rejected.push <| Json.mkObj [("mutation",toJson which),("actual_changed_nodes",toJson count),("rejected",toJson error)]
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_4 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineUserWordWrappers := true, symbolPrefix := "managed_bytes_fixture_"} with
    | .ok value => pure value
    | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map Lemma.Compiler.llvmTy} : Lemma.Compiler.LLVM.Declaration)
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "genuine ordinary bounded ByteArray source; linked isolated execution separate"
    declarations, functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
    | .error error => throwError error
    | .ok _ => pure ()
  let some output ← IO.getEnv "LEMMA_MANAGED_BYTES_OUT" | throwError "LEMMA_MANAGED_BYTES_OUT must name an unused output directory"
  unless !(← System.FilePath.pathExists output) do throwError "ByteArray fixture output already exists"
  IO.FS.createDirAll output
  let ir ← program.sourceNames.mapM fun source => do
    let some declaration := IR.findEnvDecl env source | throwError "actual IR closure missing"
    pure <| Json.mkObj [("source",toJson source.toString),("genuine_ir",toJson (IR.formatDecl declaration).pretty)]
  IO.FS.writeFile (System.FilePath.mk output / "program.ll") module.render
  IO.FS.writeFile (System.FilePath.mk output / "symbols.txt") lowered.renderSymbolManifest
  IO.FS.writeFile (System.FilePath.mk output / "genuine-ir.json") ((Json.arr ir).pretty ++ "\n")
  IO.FS.writeFile (System.FilePath.mk output / "catalog.json") ((Json.mkObj [
    ("contract",toJson "lemma-managed-bytes-v1"),("profile",toJson suite.contractVersion),
    ("compiler_revision",toJson "5045d0056413266e57c625dcd7c365b10e377c52"),
    ("root",toJson root.toString),("maximum_payload",toJson (48 : Nat)),
    ("allocator",toJson "lemma-owned-arena-v1"),("slots",toJson (31 : Nat)),
    ("genuine_ir",Json.arr ir),("actual_ir_mutations",Json.arr rejected)]).pretty ++ "\n")
  logInfo "MANAGED_BYTES:PASS genuine source/ownership->checked LLVM; closed User4; linked isolated execution separate"
end Lemma.Compiler.Test.ManagedBytes
