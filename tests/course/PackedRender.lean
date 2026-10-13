import Lemma.Courses.Arithmetic
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate

/-! Exact compatibility against the original public scalar pixel function.
This host comparison is separate from actual RV64 course/controller execution.
The exporter consumes the real maintained render Action from the environment. -/
namespace CoursePackedRender
open Lemma.Courses.Arithmetic

def referenceWord (x y goal values state : UInt64) : UInt64 :=
  (List.range 8).foldl (fun word i =>
    let position := x + i.toUInt64 * 2
    word ||| (((panelPixel position y goal values state <<< 4) |||
      panelPixel (position + 1) y goal values state) <<< (i.toUInt64 * 8))) 0

def check : IO Unit := do
  let mut words : Nat := 0
  for goal in (#[(1 : UInt64),2,3]) do
    for outcome in [:8] do
      let n : UInt64 := if outcome % 2 = 0 then 0 else 99
      let values := n ||| ((6 : UInt64) <<< 7) ||| ((1 : UInt64) <<< 14) ||| ((2 : UInt64) <<< 21) ||| ((1 : UInt64) <<< 28)
      let mode := outcome.toUInt64 % 5
      let review := (outcome.toUInt64 % 3) ||| ((outcome.toUInt64 % 8) <<< 3) |||
        (mode <<< 6) ||| ((outcome.toUInt64 % 2) <<< 9)
      let state := outcome.toUInt64 ||| ((outcome.toUInt64 % 2) <<< 3) |||
        ((94 : UInt64) <<< 9) ||| ((8 : UInt64) <<< 16) ||| (review <<< 24)
      for y in [:160] do
        for c in [:24] do
          let x := c.toUInt64 * 16
          let expected := referenceWord x y.toUInt64 goal values state
          if panelWord x y.toUInt64 goal values state != expected then
            throw <| IO.userError s!"course word changed pixel order at {x},{y},goal{goal},outcome{outcome}"
          words := words + 1
  for (x,y) in #[(15,0),(369,0),(384,0),(0,160),(0xffffffffffffffff,0)] do
    if panelWord x y 1 0 0 != 0xffffffffffffffff then
      throw <| IO.userError "invalid word geometry was admitted"
  IO.println s!"COURSE_PACKED_RENDER:PASS {words} words,{words*16} exact scalar pixels,5 invalid geometries"

end CoursePackedRender

open Lean Elab Command
run_cmd do
  let env ← getEnv
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_2
      #[``Lemma.Courses.Arithmetic.render] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_2 suite
      { preserveCalls := preserved, symbolPrefix := "lemma_course_render_" } with
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
    { sourceName := "genuine packed course renderer", declarations, functions := lowered.functions }
  match Lemma.Compiler.LLVM.validateModule module with
    | .ok _ => pure () | .error error => throwError error
  if let some output ← liftIO <| IO.getEnv "LEMMA_COURSE_RENDER_OUT" then
    let path := System.FilePath.mk output
    if ← liftIO path.pathExists then throwError "course export refuses an existing output directory"
    liftIO <| IO.FS.createDirAll path
    liftIO <| IO.FS.writeFile (path / "program.ll") module.render
    liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  logInfo m!"COURSE_RENDER_GENUINE_LLVM:{suite.scalarFunctions.size}:{suite.actionFunctions.size}:{lowered.functions.size}"

def main : IO Unit := CoursePackedRender.check
