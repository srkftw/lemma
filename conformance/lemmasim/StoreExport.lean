import Lemma.Services.Store.Engine
import Lemma.Compiler.CFGLower
import Lemma.Core0.Frontend

/-! Host-only genuine elaboration/Core0/LLVM closure probe. This does not append
a kernel startup, create target ASTs, or claim a linked guest execution. -/
open Lean Elab Command
elab "#store_export" : command => do
  let env ← getEnv
  let names := #[``Lemma.Services.Store.Engine.mountStart, ``Lemma.Services.Store.Engine.formatStart,
    ``Lemma.Services.Store.Engine.appendStart, ``Lemma.Services.Store.Engine.checkpointStart,
    ``Lemma.Services.Store.Engine.lookup, ``Lemma.Services.Store.Engine.enumerate,
    ``Lemma.Services.Store.Engine.readStart, ``Lemma.Services.Store.Engine.complete]
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_1 names with
    | .ok suite => pure suite
    | .error error => throwError error.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_1 suite {
      preserveCalls := preserved, symbolPrefix := "lemma_store_" } with
    | .ok lowered => pure lowered
    | .error error => throwError error
  let some output ← liftIO <| IO.getEnv "LEMMA_STORE_OUT"
    | throwError "LEMMA_STORE_OUT must name an unused output directory"
  let directory := System.FilePath.mk output
  if ← liftIO directory.pathExists then throwError "store export refuses an existing output directory"
  liftIO <| IO.FS.createDirAll directory
  liftIO <| IO.FS.writeFile (directory / "program.ll") (Lemma.Compiler.LLVM.Module.render {
    sourceName := "Lemma.Services.Store.Engine", functions := lowered.functions })
  liftIO <| IO.FS.writeFile (directory / "symbols.txt") lowered.renderSymbolManifest
  let roots := suite.roots.map fun root => root.source.toString
  liftIO <| IO.FS.writeFile (directory / "roots.txt") (String.intercalate "\n" roots.toList ++ "\n")
  logInfo m!"STORE_REAL_CORE0:{suite.scalarFunctions.size}:{suite.actionFunctions.size}:{lowered.functions.size}"
#store_export
