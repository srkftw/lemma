import Lemma.Ink.Rasterizer
import Lemma.Compiler.CFGLower

/-! Host-only artifact probe over genuinely elaborated production ink declarations.
No manufactured target AST and no host implementation enters the RV64 object. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler

run_cmd do
  let env ← getEnv
  let some directory ← liftIO <| IO.getEnv "LEMMA_INK_PROBE_OUT"
    | throwError "LEMMA_INK_PROBE_OUT must name a fresh artifact directory"
  let path := System.FilePath.mk directory
  liftIO <| IO.FS.createDirAll path
  let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_1
      #[`Lemma.Ink.Rasterizer.segment, `Lemma.Ink.Rasterizer.clearTile] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  let lowered ← match lowerActionSuiteExecution .user_v0_1 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      symbolPrefix := "ink_probe_" } with
    | .ok result => pure result
    | .error error => throwError error
  let module : LLVM.Module := { sourceName := "Lemma guest ink v1", functions := lowered.functions }
  match LLVM.validateModule module with
  | .ok () => pure ()
  | .error error => throwError error
  liftIO <| IO.FS.writeFile (path / "program.ll") module.render
  liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  liftIO <| IO.FS.writeFile (path / "source-declarations.txt")
    (String.intercalate "\n" ((suite.scalarFunctions.map (·.name.toString) ++
      suite.actionFunctions.map (·.name.toString)).toList) ++ "\n")
  logInfo m!"INK_COMPILE: real user-profile source checked and LLVM emitted; execution separate"
