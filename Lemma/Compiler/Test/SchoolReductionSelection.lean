import Lemma.Compiler.CourseInstallExport
import Lemma.Compiler.KernelExport
import Lean.Compiler.Main
import Lemma.Services.Arithmetic.ServerV9

/-! Host-only exact dependency admission checks, never a target proof. -/
namespace Lemma.Compiler.Test.SchoolReductionSelection
open Lean Elab Command
open Lemma.Compiler.CourseInstallExport
open Lemma.Compiler.KernelExport Lemma.Compiler.DeploymentCatalog

run_cmd do
  for source in #["Lemma.Services.Arithmetic.ReductionV1.maximumMagnitude",
      "Lemma.Services.Arithmetic.ReductionV1.requiredBudget",
      "Lemma.Services.Arithmetic.ReductionV1.gcdStep",
      "Lemma.Services.Arithmetic.ReductionV1.calculate",
      "Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity"] do
    unless submissionReductionDependency true source && !submissionReductionDependency false source do
      throwError "local numerical validation escaped its exact submission-only scope"
  for source in #["Lemma.Services.Arithmetic.ServerV9.main", "Lemma.Services.Arithmetic.ServerV9.step",
      "Lemma.Services.Arithmetic.ClientV9.beginCall", "Lemma.Services.Arithmetic.ClientV9.pollCall",
      "Lemma.Services.Arithmetic.ProtocolV9.request", "Lemma.Services.Arithmetic.ProtocolV9.reply",
      "Lemma.Services.Arithmetic.ProtocolV9.evaluate", "Lemma.Services.Arithmetic.ReductionV1.other",
      "Lemma.Services.Arithmetic.ReductionV1.calculate.extra", "Lemma.Services.Arithmetic.ReductionV1"] do
    unless !submissionReductionDependency true source && !submissionReductionDependency false source do
      throwError "a sibling RPC/executable namespace entered numerical transcript validation"
  for configuration in #["lemmasim-silicon-school-notebook", "lemmasim-silicon-school24-notebook"] do
    let image ← match imageFor configuration "arithmetic" with
      | .ok image => pure image
      | .error error => throwError error
    unless schoolArithmeticBorrowedModuleImport configuration "user" "Lemma.Services.Arithmetic.ServerV7" (some image) &&
        schoolArithmeticBorrowedSource configuration "user" "Lemma.Services.Arithmetic.ServerV7.processCopied" (some image) do
      throwError "exact older copied engine import/source was refused"
    let successor := isSchool24Configuration configuration
    unless schoolArithmeticBorrowedModuleImport configuration "user" "Lemma.Services.Arithmetic.ServerV8" (some image) == successor &&
        schoolArithmeticBorrowedSource configuration "user" "Lemma.Services.Arithmetic.ServerV8.processCopied" (some image) == successor do
      throwError "V8 copied engine escaped its exact V9 consumer"
    for source in #["Lemma.Services.Arithmetic.ServerV7.main", "Lemma.Services.Arithmetic.ServerV7.step",
        "Lemma.Services.Arithmetic.ServerV7.processCopied.extra", "Lemma.Services.Arithmetic.ServerV8.main",
        "Lemma.Services.Arithmetic.ServerV8.step", "Lemma.Services.Arithmetic.ServerV8.processCopied.extra"] do
      unless !schoolArithmeticBorrowedSource configuration "user" source (some image) &&
          !schoolArithmeticBorrowedModuleImport configuration "user" source (some image) do
        throwError "module import granted a sibling executable or unknown helper"
    for role in #["kernel", "firmware", "course"] do
      unless !schoolArithmeticBorrowedModuleImport configuration role "Lemma.Services.Arithmetic.ServerV7" (some image) &&
          !schoolArithmeticBorrowedSource configuration role "Lemma.Services.Arithmetic.ServerV7.processCopied" (some image) do
        throwError "copied engine borrowing crossed its isolated role"
    for forged in #[{image with id := 2}, {image with key := "notebook"},
        {image with moduleName := `Lemma.Services.Arithmetic.ServerV7},
        {image with root := `Lemma.Services.Arithmetic.ServerV7.main}] do
      unless !schoolArithmeticBorrowedModuleImport configuration "user" "Lemma.Services.Arithmetic.ServerV7" (some forged) &&
          !schoolArithmeticBorrowedSource configuration "user" "Lemma.Services.Arithmetic.ServerV7.processCopied" (some forged) do
        throwError "forged image acquired copied engine borrowing"
  logInfo "PASS: exact pure local-tool submission validation dependency admission"

/- Genuine frontend suites, not hand-authored target ASTs or emitted digests. -/
run_elab do
  Compiler.compile #[``Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix]
  let env ← getEnv
  for (root, parameterized, reduction, version) in #[
      (``Lemma.Services.Arithmetic.ServerV7.main, false, false, "lemma-arithmetic-execution-identity-v6"),
      (``Lemma.Services.Arithmetic.ServerV8.main, true, false, "lemma-arithmetic-execution-identity-v7"),
      (``Lemma.Services.Arithmetic.ServerV9.main, true, true, "lemma-arithmetic-execution-identity-v8")] do
    let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_7 #[root] with
      | .ok suite => pure suite | .error error => throwError error.render
    let fields ← IO.ofExcept <| Lemma.Compiler.ManagedClosureMetadata.executionFields true true "user" suite parameterized reduction
    let payload ← IO.ofExcept <| (Json.mkObj fields).getObjVal? "arithmetic_closure_execution_identity"
    unless (payload.getObjValAs? String "contract_version").toOption == some version do
      throwError "Genuine arithmetic suite received another whole implementation identity"
    if parameterized then
      let checker ← IO.ofExcept <| payload.getObjVal? "parameterized"
      unless (checker.getObjValAs? Nat "checker_id").toOption == some 0x0002000000000001 do
        throwError "Copied parameterized checking acquired another wire identity"
    if reduction then
      let implementation ← IO.ofExcept <| payload.getObjVal? "implementation"
      unless (implementation.getObjValAs? Nat "id").toOption == some 0x0009000100000001 do
        throwError "Whole ServerV9 retained another implementation identity"
      let advisory ← IO.ofExcept <| payload.getObjVal? "local_reduction"
      for (key, expected) in #[("version",(1 : Nat)),("request_bytes",144),("reply_bytes",176),
          ("service_id",0x0001000052444331),("gcd_steps",32),("maximum_magnitude",1000000),("required_budget",34)] do
        unless (advisory.getObjValAs? Nat key).toOption == some expected do
          throwError "Genuine local reduction metadata differs at {key}"
    else if (payload.getObjVal? "local_reduction").toOption.isSome then
      throwError "Historical implementation acquired local reduction metadata"
    for (wrongParameterized, wrongReduction) in #[(false,false),(false,true),(true,false),(true,true)] do
      if wrongParameterized != parameterized || wrongReduction != reduction then
        match Lemma.Compiler.ManagedClosureMetadata.executionFields true true "user" suite wrongParameterized wrongReduction with
        | .error _ => pure ()
        | .ok _ => throwError "Arithmetic implementation selection accepted a different genuine entry"
    match Lemma.Compiler.ManagedClosureMetadata.executionFields true true "kernel" suite parameterized reduction with
    | .error _ => pure ()
    | .ok _ => throwError "Arithmetic execution identity crossed its isolated user role"
  let mixed ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_7
      #[``Lemma.Services.Arithmetic.ServerV8.main, ``Lemma.Services.Arithmetic.ServerV9.main] with
    | .ok suite => pure suite | .error error => throwError error.render
  match Lemma.Compiler.ManagedClosureMetadata.executionFields true true "user" mixed true true with
  | .error _ => pure ()
  | .ok _ => throwError "Mixed V8/V9 whole entries acquired local reduction authority"
  let noLegacy ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_7
      #[``Lemma.Services.Arithmetic.ProtocolV9.reply] with
    | .ok suite => pure suite | .error error => throwError error.render
  match Lemma.Compiler.ManagedClosureMetadata.executionFields true true "user" noLegacy false true with
  | .error _ => pure ()
  | .ok _ => throwError "Invalid local selector disappeared through the no-Protocol7 early return"
  logInfo "PASS: genuine V7/V8/V9 execution identities preserve checker wire identity and reject crossed/mixed selectors"

end Lemma.Compiler.Test.SchoolReductionSelection
