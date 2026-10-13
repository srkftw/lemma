import Lean.Compiler.Main
import Lemma.Core0.Frontend
import Lemma.Compiler.CFGLower
import Lemma.Mathematics.ManagedResult

namespace Lemma.Compiler.Test.ManagedSums
open Lemma.Core0.Memory

def ordinary (lhs rhs : UInt64) : Action :=
  .managedSums2 Lemma.Mathematics.ManagedResult.compareFiveSix lhs rhs fun status value =>
    .done status value

def dynamic (function : UInt64 → UInt64 → UInt64) (lhs rhs : UInt64) : Action :=
  .managedSums2 function lhs rhs fun status value => .done status value

inductive Nullary where
  | one | two
@[noinline] def nullary (lhs rhs : UInt64) : UInt64 :=
  let result := if lhs = rhs then Nullary.one else Nullary.two
  match result with | .one => lhs | .two => rhs

inductive Recursive where
  | end (value : UInt64)
  | next (value : UInt64) (tail : Recursive)
inductive ReferenceField where
  | scalar (value : UInt64)
  | reference (value : String)
inductive TooMany where
  | a (value : UInt64) | b (value : UInt64) | c (value : UInt64)
  | d (value : UInt64) | e (value : UInt64) | f (value : UInt64)
  | g (value : UInt64) | h (value : UInt64) | i (value : UInt64)
inductive Boundary where
  | a (v0 v1 v2 v3 v4 v5 v6 : UInt64)
  | b (value : UInt64) | c (value : UInt64) | d (value : UInt64)
  | e (value : UInt64) | f (value : UInt64) | g (value : UInt64) | h (value : UInt64)

open Lean Elab Command
run_elab do
  Compiler.compile #[``Lemma.Mathematics.ManagedResult.compareFiveSix, ``nullary]
  let env ← getEnv
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_3 #[``ordinary] with
    | .ok value => pure value
    | .error error => throwError error.render
  unless suite.actionFunctions.any (fun f => (Lemma.Core0.ManagedSumsIR.generatedSource? f.name).isSome) do
    throwError "ordinary sum source was not genuinely lowered"
  unless suite.usedExecutionOps.all (·.operation.admits .user_v0_3) do
    throwError "sum closure exceeded inherited User authority"
  for profile in #[Lemma.Core0.Profile.user_v0_1, .user_v0_2, .kernel_v0_5, .kernel_v0_6, .boot_v0_1] do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env profile #[``ordinary] with
    | .ok _ => throwError m!"historical profile {profile.contractVersion} silently admitted sum bridge"
    | .error error => unless error.code == .unsupportedPrimitive do throwError error.render
  match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_3 #[``dynamic] with
  | .ok _ => throwError "runtime-selected sum function escaped source closure"
  | .error _ => pure ()
  match Lemma.Core0.ManagedSumsIR.buildProgram env ``nullary with
  | .ok _ => throwError "nullary/tagged sum escaped explicit payload layout"
  | .error _ => pure ()
  for typeName in #[``Recursive, ``ReferenceField, ``TooMany, ``Nullary] do
    match Lemma.Core0.ManagedSumsIR.deriveShape env typeName 1 with
    | .ok _ => throwError m!"unsupported source sum layout admitted: {typeName}"
    | .error _ => pure ()
  let boundary ← match Lemma.Core0.ManagedSumsIR.deriveShape env ``Boundary 1 with
    | .ok shape => pure shape
    | .error error => throwError error
  unless boundary.constructors.size == 8 && boundary.constructors[0]!.bytes == 64 &&
      boundary.constructors[7]!.tag == 7 && boundary.constructors[7]!.bytes == 16 do
    throwError "actual elaborated eight-constructor/seven-scalar-field boundary differs"
  let program ← match Lemma.Core0.ManagedSumsIR.buildProgram env ``Lemma.Mathematics.ManagedResult.compareFiveSix with
    | .ok value => pure value
    | .error error => throwError error
  unless program.shapes.size == 1 && program.shapes[0]!.constructors.size == 2 &&
      program.shapes[0]!.constructors[0]!.bytes == 24 && program.shapes[0]!.constructors[1]!.bytes == 16 &&
      program.sourceNames.size == 3 do throwError "genuine sum constructor/type/call closure differs"
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_3 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "managed_sum_fixture_"} with
    | .ok value => pure value
    | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map Lemma.Compiler.llvmTy} : Lemma.Compiler.LLVM.Declaration)
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "genuine managed sums source qualification; target execution separate"
    declarations, functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
  | .error error => throwError error
  | .ok _ => pure ()
  let some out ← IO.getEnv "LEMMA_MANAGED_SUM_OUT" | throwError "LEMMA_MANAGED_SUM_OUT must name an unused fixture directory"
  unless !(← System.FilePath.pathExists out) do throwError "sum fixture output already exists"
  IO.FS.createDirAll out
  IO.FS.writeFile (System.FilePath.mk out / "program.ll") module.render
  IO.FS.writeFile (System.FilePath.mk out / "symbols.txt") lowered.renderSymbolManifest
  let ir ← program.sourceNames.mapM fun name => do
    let some declaration := Lean.IR.findEnvDecl env name | throwError "missing real IR after checked closure"
    pure <| Json.mkObj [("source", .str name.toString),
      ("genuine_ir", .str (Lean.IR.formatDecl declaration).pretty)]
  IO.FS.writeFile (System.FilePath.mk out / "genuine-ir.json") ((Json.arr ir).pretty ++ "\n")
  IO.FS.writeFile (System.FilePath.mk out / "catalog.json") ((Json.mkObj [
    ("contract_version", .str "lemma-managed-sums-v1"),
    ("profile", .str Lemma.Core0.Profile.user_v0_3.contractVersion),
    ("compiler_revision", .str "5045d0056413266e57c625dcd7c365b10e377c52"),
    ("entry", .str program.root.toString),
    ("allocator", .str "lemma-owned-arena-v1"),
    ("shapes", Json.arr (program.shapes.map fun shape => Json.mkObj [
      ("source", .str shape.typeName.toString), ("id", toJson shape.id),
      ("constructors", Json.arr (shape.constructors.map fun ctor => Json.mkObj [
        ("source", .str ctor.constructor.toString), ("tag", toJson ctor.tag), ("bytes", toJson ctor.bytes)]))])),
    ("functions", Json.arr ir)]).pretty ++ "\n")
  logInfo "MANAGED_SUMS:PASS genuine constructors/cases/projections/release->checked LLVM; User3 only; isolated RV64 separate"

end Lemma.Compiler.Test.ManagedSums
