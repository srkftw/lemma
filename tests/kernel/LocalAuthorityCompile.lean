import Lemma.Kernel.Task
import Lemma.Ink.Surface
import Lemma.Platform.LemmaSim.DeviceService
import Lemma.Compiler.CFGLower

/-! Genuine elaboration and checked lowering of the maintained hot paths.
These diagnostic LLVM modules do not replace full audited guest artifacts. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  let env ← getEnv
  let some directory ← liftIO <| IO.getEnv "LEMMA_LOCAL_PROBE_OUT"
    | throwError "LEMMA_LOCAL_PROBE_OUT must name a fresh output directory"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite retained probe"
  liftIO <| IO.FS.createDirAll path
  for (label,profile,roots) in #[
      ("allocation", Profile.kernel_v0_3, #[`Lemma.Kernel.Syscall.allocate,`Lemma.Kernel.Task.table]),
      ("capability", Profile.kernel_v0_3, #[`Lemma.Kernel.Capability.managed, `Lemma.Kernel.Capability.requireActive]),
      ("transfer", Profile.kernel_v0_3, #[`Lemma.Platform.LemmaSim.DeviceService.surface, `Lemma.Kernel.Task.capture]),
      ("surface", Profile.user_v0_1, #[`Lemma.Ink.Surface.background])] do
    let suite ← match checkAndLowerActionSuiteForProfile env profile roots with
      | .ok suite => pure suite
      | .error error => throwError error.render
    let lowered ← match lowerActionSuiteExecution profile suite {
        preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
        symbolPrefix := "local_probe_" } with
      | .ok result => pure result
      | .error error => throwError error
    let mut declarations : Array LLVM.Declaration := #[]
    for spec in suite.usedExecutionOps do
      if let some name := spec.primitiveSymbol? then
        declarations := declarations.push {
          name := name
          returnType := if spec.resultKind == .checked then .checkedResult else .i64
          parameters := spec.machineArguments.map llvmTy }
    if !suite.usedDeviceOps.isEmpty || suite.usedExecutionOps.any (·.operation.isDevice) then
      declarations := declarations.push { name := "core0_io_fence", returnType := .void, parameters := #[] }
    let module : LLVM.Module := {
      sourceName := "checked maintained " ++ label
      functions := lowered.functions
      declarations := declarations }
    match LLVM.validateModule module with
    | .ok () => pure ()
    | .error error => throwError error
    liftIO <| IO.FS.writeFile (path / (label ++ ".ll")) module.render
    liftIO <| IO.FS.writeFile (path / (label ++ "-symbols.txt")) lowered.renderSymbolManifest
    let mut functions : Array Json := #[]
    for f in suite.scalarFunctions do
      let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
        | throwError "missing scalar symbol"
      functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
        ("symbol", .str symbol.llvm), ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))),
        ("effects", .arr #[])]
    for f in suite.actionFunctions do
      let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
        | throwError "missing action symbol"
      let effects := if f.effects == .empty then #[] else
        (String.ofList (f.effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)).splitOn "," |>.toArray.map Json.str
      functions := functions.push <| Json.mkObj [("source", .str f.name.toString),
        ("symbol", .str symbol.llvm), ("args", .arr (f.signature.args.map (Json.str ∘ Ty.render))),
        ("effects", .arr effects)]
    liftIO <| IO.FS.writeFile (path / (label ++ "-unit.json"))
      (Json.mkObj [("role",.str (if label == "surface" then "user" else "kernel")),("functions",.arr functions)]).pretty
    logInfo m!"LOCAL_AUTHORITY_COMPILE:PASS {label} genuine checked LLVM lowering; full guest audit separate"
