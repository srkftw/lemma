import Lean.Compiler.Main
import Lemma.Core0.Frontend
import Lemma.Compiler.CFGLower
import Lemma.Mathematics.ManagedSubmission

/-! Host-only genuine source/lowering qualification. No target success is
certified by this fixture; actual isolated RV64 execution is a separate check. -/
namespace Lemma.Compiler.Test.ManagedRecords
open Lemma.Core0.Memory

def entry (lhs rhs : UInt64) : Action :=
  .managed2 Lemma.Mathematics.ManagedRational.compareFiveSix lhs rhs fun status value => .done status value

def dynamic (function : UInt64 → UInt64 → UInt64) (lhs rhs : UInt64) : Action :=
  .managed2 function lhs rhs fun status value => .done status value

structure NonScalar where
  flag : Bool

@[noinline] def nonScalarMake (n d : UInt64) : NonScalar := ⟨n = d⟩
@[noinline] def nonScalar (n d : UInt64) : UInt64 := if (nonScalarMake n d).flag then 1 else 0

open Lean Elab Command
run_elab do
  Lean.Compiler.compile #[``Lemma.Mathematics.ManagedRational.compareFiveSix, ``nonScalar]
  let env ← getEnv
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_2 #[``entry] with
    | .ok value => pure value
    | .error error => throwError error.render
  unless suite.actionFunctions.any (fun f => (Lemma.Core0.ManagedIR.generatedSource? f.name).isSome) do
    throwError "ordinary managed source was not genuinely lowered"
  unless suite.usedExecutionOps.all (·.operation.admits .user_v0_2) do
    throwError "managed closure exceeded inherited User authority"
  for profile in #[Lemma.Core0.Profile.v0_1, .v0_2, .v0_3, .v0_4, .v0_5, .v0_6, .v0_7,
      .firmware_v0_1, .firmware_v0_2, .kernel_v0_1, .kernel_v0_2, .kernel_v0_3, .kernel_v0_4, .kernel_v0_5, .user_v0_1] do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env profile #[``entry] with
    | .ok _ => throwError m!"legacy profile {profile.contractVersion} silently admitted managed bridge"
    | .error _ => pure ()
  match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_2 #[``dynamic] with
  | .ok _ => throwError "runtime-selected managed function escaped closure checking"
  | .error _ => pure ()
  match Lemma.Core0.ManagedIR.buildProgram env ``nonScalar with
  | .ok _ => throwError "Bool-field structure escaped scalar object layout"
  | .error _ => pure ()
  let program ← match Lemma.Core0.ManagedIR.buildProgram env ``Lemma.Mathematics.ManagedRational.compareFiveSix with
    | .ok value => pure value
    | .error error => throwError error
  unless program.shapes.size == 1 && program.shapes[0]!.bytes == 24 && program.sourceNames.size == 3 do
    throwError "genuine ordinary structure/call closure differs"
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_2 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "managed_record_fixture_"} with
    | .ok value => pure value
    | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name, returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map Lemma.Compiler.llvmTy} : Lemma.Compiler.LLVM.Declaration)
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "genuine managed records source qualification; target execution separate"
    declarations, functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
  | .error error => throwError error
  | .ok _ => pure ()
  let some out ← IO.getEnv "LEMMA_MANAGED_OUT" | throwError "LEMMA_MANAGED_OUT must name an unused fixture output directory"
  unless !(← System.FilePath.pathExists out) do throwError "managed fixture output already exists"
  IO.FS.createDirAll out
  IO.FS.writeFile (System.FilePath.mk out / "program.ll") module.render
  IO.FS.writeFile (System.FilePath.mk out / "symbols.txt") lowered.renderSymbolManifest
  let ir ← program.sourceNames.mapM fun name => do
    let some declaration := Lean.IR.findEnvDecl env name | throwError "missing genuine IR after checked closure"
    pure <| Json.mkObj [("source", .str name.toString),
      ("genuine_ir", .str (Lean.IR.formatDecl declaration).pretty)]
  IO.FS.writeFile (System.FilePath.mk out / "genuine-ir.json") ((Json.arr ir).pretty ++ "\n")
  logInfo m!"PASS genuine managed structure IR -> checked LLVM; legacy/dynamic/layout rejection; actual guest execution separate"

end Lemma.Compiler.Test.ManagedRecords
