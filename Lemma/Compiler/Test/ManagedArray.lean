import Lean
import Lean.Compiler.Main
import Lemma.Core0.ManagedBytesIR
import Lemma.Core0.ManagedArrayIR
import Lemma.Core0.Frontend
import Lemma.Compiler.CFGLower
import Lemma.Core0.MemoryModel
import Lemma.Mathematics.ManagedArraySubmission

namespace Lemma.Compiler.Test.ManagedArray
@[noinline] def make (capacity a b : UInt64) : Array UInt64 :=
  (Array.emptyWithCapacity capacity.toNat).push a |>.push b
@[noinline] def read (xs : Array UInt64) (index : UInt64) : UInt64 :=
  if index = 0 then xs[index.toNat]! else xs[index.toNat]! + 1
@[noinline] def changed (xs : Array UInt64) (index value : UInt64) : Array UInt64 :=
  xs.set! index.toNat value
@[noinline] def length (xs : Array UInt64) : UInt64 := xs.size.toUInt64
@[noinline] def entry (a b : UInt64) : UInt64 :=
  let xs := make 2 a b
  let next := changed xs 0 b
  read xs 0 + read next 0
@[noinline] def full64 (a b : UInt64) : UInt64 :=
  let xs := make 2 a b
  read xs 0 ^^^ read xs 1
@[noinline] def ownedGet (a b : UInt64) : UInt64 :=
  let xs := make 2 a b
  if a = b then xs[0]! else xs[1]!
@[noinline] def sizeEntry (a b : UInt64) : UInt64 := length (make 2 a b)
@[noinline] def badIndex (a b : UInt64) : UInt64 := read (make 2 a b) 6
@[noinline] def oobSet (a b : UInt64) : UInt64 :=
  let xs := changed (make 2 a b) 6 0xffffffffffffffff
  read xs 0
@[noinline] def staticArray (a b : UInt64) : UInt64 := #[a,b].size.toUInt64
@[noinline] def wrongElement (a b : UInt64) : UInt64 :=
  let xs : Array UInt8 := (Array.emptyWithCapacity 2).push a.toUInt8 |>.push b.toUInt8
  xs.size.toUInt64
@[noinline] def collisionSource (a b : UInt64) : UInt64 := entry a b

def actionEntry (a b : UInt64) : Lemma.Core0.Memory.Action :=
  .managedArray2 entry a b fun status value => .done status value

def productionEntry (a b : UInt64) : Lemma.Core0.Memory.Action :=
  .managedArray2 Lemma.Mathematics.ManagedArraySubmission.compareFiveSix a b fun status value => .done status value

def full64Entry (a b : UInt64) : Lemma.Core0.Memory.Action :=
  .managedArray2 full64 a b fun status value => .done status value

def dynamicEntry (function : UInt64 → UInt64 → UInt64) (a b : UInt64) : Lemma.Core0.Memory.Action :=
  .managedArray2 function a b fun status value => .done status value
end Lemma.Compiler.Test.ManagedArray

/-- Quarantined negative source: a real declaration may not impersonate a
compiler-generated Array function, even with a matching scalar Action ABI. -/
def Lemma.Compiler.Test.ManagedArray.collisionSource.__lemma_managed_array_v05.Lemma.Compiler.Test.ManagedArray.collisionSource
    (a b : UInt64) : Lemma.Core0.Memory.Action := .done 0 (a+b)

def Lemma.Compiler.Test.ManagedArray.collisionEntry (a b : UInt64) : Lemma.Core0.Memory.Action :=
  Lemma.Compiler.Test.ManagedArray.collisionSource.__lemma_managed_array_v05.Lemma.Compiler.Test.ManagedArray.collisionSource a b

open Lean Elab Command
/-- Negative-only transforms of real compiler output. They do not supply
source behavior to the admitted grammar or target lowering. -/
partial def corruptArray (which : Nat) (body : IR.FnBody) : IR.FnBody × Nat :=
  match body with
  | .vdecl x ty expression next =>
    let (next,count) := corruptArray which next
    match expression with
    | .box .uint64 source =>
      if which == 1 then (.vdecl x ty (.box .uint32 source) next,count+1)
      else (.vdecl x ty expression next,count)
    | .fap name args =>
      if which == 2 && name == ``Array.push then
        (.vdecl x ty (.fap name (args.set! 0 args[1]!)) next,count+1)
      else if which == 4 && name.getPrefix == ``Lemma.Compiler.Test.ManagedArray.read then
        (.vdecl x ty expression (.inc x 1 false false next),count+1)
      else if which == 6 && name == ``Array.push then
        (.vdecl x ty (.fap ``IO.println args) next,count+1)
      else (.vdecl x ty expression next,count)
    | .unbox source =>
      if which == 5 then (.vdecl x ty expression (.dec source 1 false false next),count+1)
      else (.vdecl x ty expression next,count)
    | .lit (.num 0) =>
      if which == 3 then (.vdecl x ty (.lit (.num 1)) next,count+1)
      else (.vdecl x ty expression next,count)
    | _ => (.vdecl x ty expression next,count)
  | .inc x n c p next => let (next,count) := corruptArray which next; (.inc x n c p next,count)
  | .dec x n c p next => let (next,count) := corruptArray which next; (.dec x n c p next,count)
  | .case name source ty alternatives =>
    let changed : Array (IR.Alt × Nat) := alternatives.map fun alternative =>
      match alternative with
      | .ctor info branch => let (branch,count) := corruptArray which branch; (.ctor info branch,count)
      | .default branch => let (branch,count) := corruptArray which branch; (.default branch,count)
    (.case name source ty (changed.map (·.1)),changed.foldl (fun count row => count+row.2) 0)
  | _ => (body,0)
run_elab do
  let root := ``Lemma.Compiler.Test.ManagedArray.entry
  let productionRoot := ``Lemma.Mathematics.ManagedArraySubmission.compareFiveSix
  Compiler.compile #[root,productionRoot,``Lemma.Compiler.Test.ManagedArray.collisionSource,``Lemma.Compiler.Test.ManagedArray.full64,``Lemma.Compiler.Test.ManagedArray.ownedGet,
    ``Lemma.Compiler.Test.ManagedArray.sizeEntry,``Lemma.Compiler.Test.ManagedArray.badIndex,
    ``Lemma.Compiler.Test.ManagedArray.oobSet,``Lemma.Compiler.Test.ManagedArray.staticArray,
    ``Lemma.Compiler.Test.ManagedArray.wrongElement]
  let env ← getEnv
  let program ← match Lemma.Core0.ManagedArrayIR.buildProgram env root with
    | .ok program => pure program
    | .error error => throwError error
  let productionProgram ← match Lemma.Core0.ManagedArrayIR.buildProgram env productionRoot with
    | .ok program => pure program
    | .error error => throwError "actual production ordinary Array source rejected: {error}"
  unless productionProgram.sourceNames.size == 4 && productionProgram.defaultInitializers ==
      #[`Lemma.Mathematics.ManagedArraySubmission.read._boxed_const_1] do
    throwError "actual production source/default closure differs"
  for root in #[``Lemma.Compiler.Test.ManagedArray.full64,``Lemma.Compiler.Test.ManagedArray.sizeEntry,
      ``Lemma.Compiler.Test.ManagedArray.badIndex,``Lemma.Compiler.Test.ManagedArray.oobSet] do
    match Lemma.Core0.ManagedArrayIR.buildProgram env root with
      | .ok _ => pure ()
      | .error error => throwError "genuine expected Array source rejected: {root}: {error}"
  unless program.defaultInitializers == #[`Lemma.Compiler.Test.ManagedArray.read._boxed_const_1] &&
      (env.find? program.defaultInitializers[0]!).isNone &&
      Lemma.Core0.ManagedArrayIR.defaultInitializer? env program.defaultInitializers[0]! == some 0 do
    throwError "genuine owner-bound full64 zero-box initializer differs"
  for root in #[``Lemma.Compiler.Test.ManagedArray.staticArray,``Lemma.Compiler.Test.ManagedArray.wrongElement,
      ``Lemma.Compiler.Test.ManagedArray.ownedGet] do
    match Lemma.Core0.ManagedArrayIR.buildProgram env root with
      | .ok _ => throwError "unadmitted generic/static source accepted: {root}"
      | .error _ => pure ()
  for root in #[root,``Lemma.Compiler.Test.ManagedArray.full64] do
    match Lemma.Core0.ManagedBytesIR.buildProgram env root with
      | .ok _ => throwError "legacy bytes grammar acquired ordinary Array authority"
      | .error _ => pure ()
  let mut rejections : Array Json := #[]
  for which in [1,2,3,4,5,6,7] do
    let owner := if which == 7 then root else
      if which == 3 then `Lemma.Compiler.Test.ManagedArray.read._boxed_const_1 else
      if which == 4 || which == 5 then ``Lemma.Compiler.Test.ManagedArray.read else ``Lemma.Compiler.Test.ManagedArray.make
    let some (.fdecl name params result body info) := IR.findEnvDecl env owner | throwError "actual mutation owner absent"
    let (body,changed) := if which == 7 then (body,1) else corruptArray which body
    let params := if which == 7 then params.set! 1 {params[1]! with x := params[0]!.x} else params
    unless changed>0 do throwError "actual Array IR rejection mutation anchor absent: {which}"
    let mutated := IR.declMapExt.addEntry env (.fdecl name params result body info)
    match Lemma.Core0.ManagedArrayIR.buildProgram mutated root with
      | .ok _ => throwError "actual compiler Array IR mutation accepted: {which}"
      | .error error => rejections := rejections.push <| Json.mkObj [
          ("mutation",toJson which),("changed_genuine_nodes",toJson changed),("rejected",toJson error)]
  let profiles := #[Lemma.Core0.Profile.v0_1,.v0_2,.v0_3,.v0_4,.v0_5,.v0_6,.v0_7,
    .firmware_v0_1,.firmware_v0_2,.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,
    .kernel_v0_5,.kernel_v0_6,.kernel_v0_7,.user_v0_1,.user_v0_2,.user_v0_3,.user_v0_4,.boot_v0_1,.boot_v0_2]
  for profile in profiles do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env profile #[``Lemma.Compiler.Test.ManagedArray.actionEntry] with
      | .ok _ => throwError "legacy profile acquired the Array bridge: {profile.contractVersion}"
      | .error error =>
        unless error.code == .unsupportedPrimitive || (!profile.isExecution && error.code == .invalidSuite) do
          throwError error.render
  match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_5 #[``Lemma.Compiler.Test.ManagedArray.dynamicEntry] with
    | .ok _ => throwError "dynamic Array function escaped closed source admission"
    | .error _ => pure ()
  match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_5 #[``Lemma.Compiler.Test.ManagedArray.collisionEntry] with
    | .ok _ => throwError "source declaration impersonated generated Array function"
    | .error _ => pure ()
  unless Lemma.Core0.Profile.ofContractVersion? "core0-user-v0.5" == some .user_v0_5 &&
      Lemma.Core0.Profile.user_v0_5.isUser && Lemma.Core0.Profile.user_v0_5.isExecution &&
      Lemma.Core0.Execution.Op.all.all (fun op => op.admits .user_v0_5 == op.admits .user_v0_4) &&
      Lemma.Core0.Execution.memoryRegions .user_v0_5 == Lemma.Core0.Execution.memoryRegions .user_v0_4 do
    throwError "User5 changed its inherited User privilege/memory boundary"
  match Lemma.Core0.Memory.Model.evaluateDefault ({regions := #[]} : Lemma.Core0.Memory.Model.State)
      (Lemma.Compiler.Test.ManagedArray.actionEntry 1 2) with
    | .ok _ => throwError "finite scalar host model executed managed Array policy"
    | .error error => unless error.code == .executionActionUnsupported do throwError error.message
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_5
      #[``Lemma.Compiler.Test.ManagedArray.actionEntry,``Lemma.Compiler.Test.ManagedArray.productionEntry,
        ``Lemma.Compiler.Test.ManagedArray.full64Entry] with
    | .ok value => pure value
    | .error error => throwError error.render
  unless suite.contractVersion == "core0-user-v0.5" && suite.actionFunctions.any
      (fun function => (Lemma.Core0.ManagedArrayIR.generatedSource? function.name).isSome) do
    throwError "actual User5/source-derived closure missing"
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_5 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineUserWordWrappers := true,symbolPrefix := "managed_array_component_"} with
    | .ok value => pure value
    | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map Lemma.Compiler.llvmTy} : Lemma.Compiler.LLVM.Declaration)
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "genuine ordinary Array UInt64 component; checked User5 bridge; isolated execution separate"
    declarations, functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
    | .error error => throwError error
    | .ok _ => pure ()
  let some output ← IO.getEnv "LEMMA_MANAGED_ARRAY_OUT" | throwError "LEMMA_MANAGED_ARRAY_OUT must name unused output"
  unless !(← System.FilePath.pathExists output) do throwError "Array component output already exists"
  IO.FS.createDirAll output
  let ir ← (program.sourceNames ++ program.defaultInitializers ++ productionProgram.sourceNames ++ productionProgram.defaultInitializers).mapM fun source => do
    let some declaration := IR.findEnvDecl env source | throwError "genuine complete Array IR absent"
    let owner := if program.defaultInitializers.contains source || productionProgram.defaultInitializers.contains source then source.getPrefix else source
    let some info := env.find? owner | throwError "ordinary Array/default owner absent"
    let sourceType ← PrettyPrinter.ppExpr info.type
    pure <| Json.mkObj [("source",toJson source.toString),
      ("owner_source",toJson owner.toString),("owner_source_signature",toJson sourceType.pretty),
      ("genuine_ir",toJson (IR.formatDecl declaration).pretty),
      ("compiler_derived_default",toJson (program.defaultInitializers.contains source || productionProgram.defaultInitializers.contains source))]
  IO.FS.writeFile (System.FilePath.mk output / "program.ll") module.render
  IO.FS.writeFile (System.FilePath.mk output / "symbols.txt") lowered.renderSymbolManifest
  IO.FS.writeFile (System.FilePath.mk output / "genuine-ir.json") (Json.arr ir).pretty
  IO.FS.writeFile (System.FilePath.mk output / "catalog.json") ((Json.mkObj [
    ("contract",toJson "lemma-managed-array-v1"),
    ("compiler_revision",toJson "5045d0056413266e57c625dcd7c365b10e377c52"),
    ("source_admission",toJson "genuine managedArray2 User5 bridge; all21 historical profiles reject"),
    ("source_profile",toJson suite.contractVersion),
    ("legacy_profiles_rejected",toJson profiles.size),
    ("production_root",toJson productionRoot.toString),
    ("root",toJson root.toString),("maximum_elements",toJson (6 : Nat)),
    ("element_bits",toJson (64 : Nat)),("slots",toJson (31 : Nat)),
    ("get_out_of_bounds",toJson "controlled-panic236; no default mathematical result"),
    ("set_out_of_bounds",toJson "controlled-panic236; consumed parent/child released, retained aliases survive"),
    ("actual_ir_rejections",Json.arr rejections),
    ("genuine_ir",Json.arr ir)]).pretty ++ "\n")
  logInfo "MANAGED_ARRAY_COMPONENT:PASS genuine source/full64 ownership->checked CFG/LLVM; real User5 bridge; all21 oldprofiles rejected; isolated execution separate"
