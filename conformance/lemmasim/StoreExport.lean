import Lemma.Services.Store.Engine
import Lemma.Services.Store.Server
import Lemma.Services.Store.Client
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Core0.Frontend

/-! Host-only genuine elaboration/Core0/LLVM closure probe. This does not append
a kernel startup, create target ASTs, or claim a linked guest execution. -/
open Lean Elab Command
elab "#store_export" : command => do
  let env ← getEnv
  let mode ← liftIO <| IO.getEnv "LEMMA_STORE_EXPORT_MODE"
  let library := #[``Lemma.Services.Store.Engine.mountStart, ``Lemma.Services.Store.Engine.formatStart,
    ``Lemma.Services.Store.Engine.appendStart, ``Lemma.Services.Store.Engine.checkpointStart,
    ``Lemma.Services.Store.Engine.lookup, ``Lemma.Services.Store.Engine.enumerate,
    ``Lemma.Services.Store.Engine.readStart, ``Lemma.Services.Store.Engine.complete]
  let names ← match mode with
    | none | some "library" => pure library
    | some "daemon" => pure #[``Lemma.Services.Store.Server.main]
    | some "client" => pure #[``Lemma.Services.Store.Client.beginCall,
        ``Lemma.Services.Store.Client.waitCall, ``Lemma.Services.Store.Client.pollCall,
        ``Lemma.Services.Store.Client.call]
    | some _ => throwError "LEMMA_STORE_EXPORT_MODE must be library, daemon, or client"
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
  let mut declarations : Array Lemma.Compiler.LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map Lemma.Compiler.llvmTy }
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "Lemma.Services.Store", declarations, functions := lowered.functions }
  match Lemma.Compiler.LLVM.validateModule module with
    | .ok _ => pure ()
    | .error error => throwError error
  liftIO <| IO.FS.writeFile (directory / "program.ll") module.render
  liftIO <| IO.FS.writeFile (directory / "symbols.txt") lowered.renderSymbolManifest
  let roots := suite.roots.map fun root => root.source.toString
  liftIO <| IO.FS.writeFile (directory / "roots.txt") (String.intercalate "\n" roots.toList ++ "\n")
  logInfo m!"STORE_REAL_CORE0:{suite.scalarFunctions.size}:{suite.actionFunctions.size}:{lowered.functions.size}"
#store_export
