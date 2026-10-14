import Lemma.Platform.LemmaSim.NotebookKernel
import Lemma.Compiler.CFGLower

/-! Ordinary maintained declarations checked under the unchanged Kernel4
profile. This emits complete real CFG-derived LLVM bodies, never a manually
constructed demonstration AST. Object/relocation and whole-image execution
remain independently recorded obligations. -/
open Lean Elab Command
open Lemma.Core0 Lemma.Compiler
run_cmd do
  let env ← getEnv
  let some output ← liftIO <| IO.getEnv "LEMMA_SURFACE_BORROW_OUT"
    | throwError "LEMMA_SURFACE_BORROW_OUT must select an unused output"
  let path := System.FilePath.mk output
  if ← liftIO path.pathExists then throwError "refusing retained output overwrite"
  liftIO <| IO.FS.createDirAll path
  let groups := #[("bulk", #[`Lemma.Platform.LemmaSim.DeviceService.surfaceV2,
      `Lemma.Platform.LemmaSim.DeviceService.surfaceV2At,
      `Lemma.Kernel.Memory.AddressSpace.lookup,`Lemma.Kernel.Memory.AddressSpace.lookupAt,
      `Lemma.Kernel.Task.capture]),
    ("dispatch", #[`Lemma.Platform.LemmaSim.NotebookKernel.dispatchBulk])]
  for (label,roots) in groups do
    let suite ← match checkAndLowerActionSuiteForProfile env .kernel_v0_4 roots with
      | .ok suite => pure suite | .error error => throwError error.render
    let lowered ← match lowerActionSuiteExecution .kernel_v0_4 suite {
        preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
        inlineLiteralConstants := true
        inlinePrimitiveWrappers := true
        symbolPrefix := "surface_borrow_" } with
      | .ok result => pure result | .error error => throwError error
    let mut declarations : Array LLVM.Declaration := #[]
    for spec in suite.usedExecutionOps do
      if let some name := spec.primitiveSymbol? then
        declarations := declarations.push {
          name := name
          returnType := if spec.resultKind == .checked then .checkedResult else .i64
          parameters := spec.machineArguments.map llvmTy}
    if !suite.usedDeviceOps.isEmpty || suite.usedExecutionOps.any (·.operation.isDevice) then
      declarations := declarations.push {name := "core0_io_fence",returnType := .void,parameters := #[]}
    let module : LLVM.Module := {
      sourceName := "genuine same-Action checked Surface bulk " ++ label
      functions := lowered.functions
      declarations := declarations}
    match LLVM.validateModule module with
      | .ok () => pure () | .error error => throwError error
    liftIO <| IO.FS.writeFile (path / (label ++ ".ll")) module.render
    liftIO <| IO.FS.writeFile (path / (label ++ "-symbols.txt")) lowered.renderSymbolManifest
    let mut functions : Array Json := #[]
    for f in suite.scalarFunctions do
      let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
        | throwError "missing genuine scalar symbol"
      functions := functions.push <| Json.mkObj [("source",.str f.name.toString),
        ("symbol",.str symbol.llvm),("args",.arr <| f.signature.args.map (Json.str ∘ Ty.render)),("effects",.arr #[])]
    for f in suite.actionFunctions do
      let some symbol := lowered.symbols.find? (fun row => row.source == f.name)
        | throwError "missing genuine Action symbol"
      let effects := if f.effects == .empty then #[] else
        (String.ofList (f.effects.render.toList.drop 1 |>.reverse.drop 1 |>.reverse)).splitOn "," |>.toArray.map Json.str
      functions := functions.push <| Json.mkObj [("source",.str f.name.toString),
        ("symbol",.str symbol.llvm),("args",.arr <| f.signature.args.map (Json.str ∘ Ty.render)),("effects",.arr effects)]
    liftIO <| IO.FS.writeFile (path / (label ++ "-unit.json")) <|
      (Json.mkObj [("role",.str "kernel"),("profile",.str "core0-kernel-v0.4"),
        ("functions",.arr functions),("primitive_declarations",.arr <| declarations.map fun d => .str d.name)]).pretty
    logInfo m!"SURFACE_BULK_BORROW_LOWER:PASS {label} genuine Kernel4 checked LLVM {lowered.functions.size}functions"
  for profile in #[Profile.kernel_v0_1,Profile.kernel_v0_2,Profile.user_v0_1,Profile.user_v0_7] do
    match checkAndLowerActionSuiteForProfile env profile #[`Lemma.Platform.LemmaSim.DeviceService.surfaceV2At] with
      | .error _ => pure () | .ok _ => throwError "ungranted profile admitted physical/device borrow"
  logInfo "SURFACE_BULK_BORROW_PROFILE_NEGATIVES:PASS no profile broadening"
