import Lean
import Lemma.Compiler.CFGLower
import Lemma.Kernel.Memory.Access

namespace Lemma.Compiler.ClosedInlineFixture
open Lemma.Core0.Memory

def literal : UInt64 := 123
def computed (word : UInt64) : UInt64 := word + 1
def read (address : UInt64) : Action :=
  .platform .physicalRead64 address 0 0 0 0 0 fun s v => .done s v
def reordered (address value : UInt64) : Action :=
  .platform .physicalWrite64 value address 0 0 0 0 fun s v => .done s v
def erasedError (address : UInt64) : Action :=
  .platform .physicalRead64 address 0 0 0 0 0 fun _ v => .done 0 v
def changedValue (address : UInt64) : Action :=
  .platform .physicalRead64 address 0 0 0 0 0 fun s v => .done s (v + 1)
def device (address : UInt64) : Action :=
  .platform .deviceRead64 address 0 0 0 0 0 fun s v => .done s v
def main (address : UInt64) : Action :=
  .bind (read address) fun s v =>
  if s = 0 then .bind (Lemma.Kernel.Memory.Access.write64 address literal) fun t _ =>
    .done t (computed v)
  else .done s v

end Lemma.Compiler.ClosedInlineFixture
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
  let names := #[`Lemma.Compiler.ClosedInlineFixture.main,
    `Lemma.Compiler.ClosedInlineFixture.reordered, `Lemma.Compiler.ClosedInlineFixture.erasedError,
    `Lemma.Compiler.ClosedInlineFixture.changedValue, `Lemma.Compiler.ClosedInlineFixture.device]
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_4 names with
    | .ok s => pure s | .error e => throwError e.render
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let old ← match lowerActionSuiteExecution .kernel_v0_4 suite { preserveCalls := preserved } with
    | .ok s => pure s | .error e => throwError e
  let off ← match lowerActionSuiteExecution .kernel_v0_4 suite {
      preserveCalls := preserved, inlineLiteralConstants := false, inlinePrimitiveWrappers := false } with
    | .ok s => pure s | .error e => throwError e
  unless old.functions == off.functions && old.inlineLiterals.isEmpty && old.inlineWrappers.isEmpty do
    throwError "default-off changed historical bodies/catalog"
  let on ← match lowerActionSuiteExecution .kernel_v0_4 suite {
      preserveCalls := preserved, inlineLiteralConstants := true, inlinePrimitiveWrappers := true } with
    | .ok s => pure s | .error e => throwError e
  let some literal := on.inlineLiterals[0]? | throwError "literal row missing"
  unless on.inlineLiterals.map (·.source) == #[`Lemma.Compiler.ClosedInlineFixture.literal] &&
      literal.value == 123 && literal.ty == .u64 do
    throwError "literal optimization admitted nonliteral/signature"
  unless on.inlineWrappers.map (·.source) == #[`Lemma.Compiler.ClosedInlineFixture.read,
      `Lemma.Kernel.Memory.Access.write64] do
    throwError "primitive optimization admitted reordered/error-erasing/value-changing/device policy"
  for f in on.functions do
    let eligible := on.inlineLiterals.any (·.symbol == f.name) || on.inlineWrappers.any (·.symbol == f.name)
    unless f.attributes.contains "alwaysinline" == eligible &&
        f.attributes.contains "noinline" == !eligible do
      throwError "inline catalog/function attributes differ"
    let some previous := old.functions.find? (·.name == f.name) | throwError "body missing"
    unless f.blocks == previous.blocks && f.parameters == previous.parameters &&
        f.returnType == previous.returnType && f.returnExtension == previous.returnExtension &&
        f.parameterExtensions == previous.parameterExtensions && f.linkage == previous.linkage do
      throwError "inline selection changed checked access or scalar body"
  logInfo "CLOSED_INLINE:PASS genuine source eligibility, unchanged checked bodies/ABI and historical default"
