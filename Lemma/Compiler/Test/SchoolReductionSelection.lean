import Lemma.Compiler.CourseInstallExport
import Lemma.Compiler.KernelExport

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

end Lemma.Compiler.Test.SchoolReductionSelection
