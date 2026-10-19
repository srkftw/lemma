import Lemma.Compiler.Test.DeviceExport

namespace Lemma.Compiler.SchoolWorkerExport
open Lean Elab Command
open Lemma.Compiler

def abi : Json := Json.mkObj [
  ("schema", toJson "lemma-school-worker/v1"), ("profile", toJson "core0-v0.5"),
  ("numericProfile", toJson "school-linear-q10-v1"),
  ("ready", toJson "LEMMA_SCHOOL/1\nREADY\n"),
  ("requestMagic", toJson "LMQ8"), ("responseMagic", toJson "LMS8"),
  ("maximumPayload", toJson (72 : Nat)), ("maximumRequests", toJson (64 : Nat)),
  ("requestWords", toJson #["generation", "fence", "model", "weight0", "weight1", "bias", "feature0", "feature1", "presenceMask"]),
  ("responseWords", toJson #["generation", "fence", "model", "scoreQ20"]),
  ("weightMagnitudeBound", toJson (8192 : Nat)), ("featureMagnitudeBound", toJson (1024 : Nat)),
  ("accumulationMagnitudeBound", toJson (25165824 : Nat)),
  ("missingness", toJson "presenceMask must equal 3; otherwise status31 and explainable fallback"),
  ("rounding", toJson "host quantization rounds half away from zero; target exact signed Q20 accumulation"),
  ("authority", toJson "echoed generation/fence/model are validated by durable school authority")]

def exportFiles (env : Environment) (directory : System.FilePath) : IO Unit := do
  let suite ← IO.ofExcept <| (Lemma.Core0.checkAndLowerActionSuiteV05 env #[`Lemma.School.Worker.entry]).mapError (·.render)
  unless suite.roots.size == 1 && suite.roots[0]!.signature.args.isEmpty do
    throw <| IO.userError "school worker requires its single zero-argument Action root"
  unless suite.usedDeviceOps.size == 4 &&
      Lemma.Core0.Device.opCatalog.all (fun spec => suite.usedDeviceOps.contains spec.op) do
    throw <| IO.userError "school worker must use exactly the four core0-v0.5 UART operations"
  let preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← IO.ofExcept <| lowerActionSuiteV05 suite { preserveCalls }
  let some root := lowered.roots[0]? | throw <| IO.userError "missing school worker root"
  let layout := Lemma.Machine.deviceLayout
  let llvm : LLVM.Module := {
    sourceName := "Lemma school-linear-worker-v1",
    declarations := Lemma.Machine.DeviceHarness.declarations,
    functions := lowered.functions ++ Lemma.Machine.DeviceHarness.functions layout root }
  IO.ofExcept <| LLVM.validateModule llvm
  let base ← IO.ofExcept <| Lemma.Compiler.Test.DeviceExport.renderManifest suite lowered layout
    { suiteId := 8, sourceSeed := 0, runtimeSeed := 0 }
  let base ← IO.ofExcept <| Json.parse base
  let object ← IO.ofExcept <| base.getObj?
  let fields := object.toList.filter (fun (key, _) => !["artifact_category", "test_abi", "suite_id", "source_seed", "runtime_seed"].contains key)
  let manifest := Json.mkObj (fields ++ [("artifact_category", toJson "school-worker"),
    ("worker_contract", abi)])
  IO.FS.createDirAll directory
  for (name, content) in #[
      ("program.ll", llvm.render), ("startup.S", Lemma.Machine.Primitives.renderStartup),
      ("link.ld", ← IO.ofExcept layout.linkerScript), ("layout.json", ← IO.ofExcept layout.machineManifestJson),
      ("device-contract.json", ← IO.ofExcept layout.deviceContractJson),
      ("worker-manifest.json", manifest.pretty ++ "\n"),
      ("worker-abi.json", abi.pretty ++ "\n"),
      ("worker-normalized.txt", Lemma.Compiler.Test.DeviceExport.renderNormalized suite),
      ("symbols.txt", lowered.renderSymbolManifest)] do
    IO.FS.writeFile (directory / name) content

syntax (name := schoolWorkerExport) "#school_worker_export" : command
elab_rules : command
  | `(#school_worker_export) => do
    let some output ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
      | throwError "LEMMA_CORE0_OUT is required"
    liftIO <| exportFiles (← getEnv) output
    logInfo "exported school-linear-worker-v1 from genuinely elaborated Lean"
end Lemma.Compiler.SchoolWorkerExport
