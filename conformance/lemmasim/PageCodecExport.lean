import Lemma.Documents.Ink
import Lemma.Compiler.CFGLower
import Lemma.Compiler.LLVMValidate
import Lemma.Core0.Frontend

/-! Host-only closure/export check through actual elaborated declarations. -/
open Lean Elab Command
elab "#page_codec_export" : command => do
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``Lemma.Documents.Ink.encodePage, ``Lemma.Documents.Ink.decodePage,
        ``Lemma.Documents.Ink.pageRecordBytes, ``Lemma.Documents.Ink.encodedPageBytes] with
    | .ok suite => pure suite
    | .error error => throwError error.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_1 suite {
      preserveCalls := preserved, symbolPrefix := "lemma_page_" } with
    | .ok lowered => pure lowered
    | .error error => throwError error
  let some output ← liftIO <| IO.getEnv "LEMMA_PAGE_OUT"
    | throwError "LEMMA_PAGE_OUT must name an unused output directory"
  let directory := System.FilePath.mk output
  if ← liftIO directory.pathExists then throwError "page export refuses existing output"
  liftIO <| IO.FS.createDirAll directory
  let mut declarations : Array Lemma.Compiler.LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map Lemma.Compiler.llvmTy }
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "Lemma.Documents.Ink", declarations, functions := lowered.functions }
  match Lemma.Compiler.LLVM.validateModule module with
    | .ok _ => pure ()
    | .error error => throwError error
  liftIO <| IO.FS.writeFile (directory / "program.ll") module.render
  liftIO <| IO.FS.writeFile (directory / "symbols.txt") lowered.renderSymbolManifest
  logInfo m!"PAGE_REAL_CORE0:{suite.scalarFunctions.size}:{suite.actionFunctions.size}:{lowered.functions.size}"
#page_codec_export
