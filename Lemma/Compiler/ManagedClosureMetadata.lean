import Lemma.Compiler.CFGLower
import Lemma.Mathematics.ManagedClosureSubmissionAction
import Lemma.Mathematics.ExecutionIdentityV6
import Lemma.Services.Arithmetic.ProtocolV9

/-! Source-derived closure metadata for the explicitly selected isolated math
successor. The caller owns deployment selection; this module closes the actual
ordinary PAP/adapter/dispatcher and named execution authority. -/
namespace Lemma.Compiler.ManagedClosureMetadata
open Lean Lemma.Core0

private def symbol (lowered : LoweredActionSuite) (source : Name) : Except String String := do
  let some row := lowered.symbols.find? (·.source == source) | throw "Missing checked closure symbol"
  pure row.llvm

private def renderType : ManagedClosureIR.ValueTy → String
  | .scalar => "UInt64"
  | .closure => "UInt64 → UInt64"
  | _ => "<unadmitted ordinary source type>"

private def signature (env : Environment) (source : Name) : Except String String := do
  let (parameters,result) ← ManagedClosureIR.signature env source
  pure <| String.intercalate " → " ((parameters.toList.map fun t =>
    if t == .closure then "(UInt64 → UInt64)" else renderType t) ++ [renderType result])

def managedClosureFields (env : Environment) (isArithmetic : Bool)
    (suite : CheckedActionSuite) (lowered : LoweredActionSuite) : Except String (List (String × Json)) := do
  let mut entries : Array Name := #[]
  for function in suite.actionFunctions do
    if let some (root,_) := ManagedClosureIR.generatedSource? function.name then
      unless entries.contains root do entries := entries.push root
  if suite.contractVersion != Profile.user_v0_7.contractVersion then
    unless entries.isEmpty do throw "Closure metadata crossed its explicit User7 profile"
    return []
  unless isArithmetic && entries == #[`Lemma.Mathematics.ManagedClosureSubmission.compareFiveSix] do
    throw "User7 math closure metadata requires its exact isolated ordinary entry"
  let program ← ManagedClosureIR.buildProgram env entries[0]!
  let mut functions : Array Json := #[]
  for source in program.sourceNames do
    let some declaration := Lean.IR.findEnvDecl env source | throw "Missing genuine closure source IR"
    let generated := ManagedClosureIR.genName program.root source
    let some checked := suite.actionFunctions.find? (·.name == generated)
      | throw "Genuine closure source missing from checked unit"
    functions := functions.push <| Json.mkObj [
      ("source",.str source.toString),("source_signature",.str (← signature env source)),
      ("generated_source",.str generated.toString),("symbol",.str (← symbol lowered generated)),
      ("genuine_ir",.str (Lean.IR.formatDecl declaration).pretty),
      ("checked_action",.str checked.body.renderNormalized)]
  let mut adapters : Array Json := #[]
  for target in program.targets do
    let some declaration := Lean.IR.findEnvDecl env target.adapter | throw "Missing genuine scalar boxed adapter IR"
    adapters := adapters.push <| Json.mkObj [
      ("adapter",.str target.adapter.toString),("owner",.str target.source.toString),
      ("owner_signature",.str (← signature env target.source)),("captures",toJson target.captures),
      ("genuine_ir",.str (Lean.IR.formatDecl declaration).pretty)]
  let dispatcher := ManagedClosureIR.dispatchName program.root
  let some checked := suite.actionFunctions.find? (·.name == dispatcher)
    | throw "Checked finite closure dispatcher absent"
  return [("managed_closure",Json.mkObj [
    ("contract_version",.str "lemma-managed-closure-v1"),
    ("compiler_revision",.str "5045d0056413266e57c625dcd7c365b10e377c52"),
    ("allocator",.str "lemma-owned-arena-v1"),("entry",.str program.root.toString),
    ("maximum_captures",toJson (4 : Nat)),("maximum_targets",toJson (8 : Nat)),
    ("slots",toJson (31 : Nat)),("payload_bytes",toJson (64 : Nat)),
    ("cookie",toJson Lemma.User.Runtime.ManagedClosure.cookie),
    ("initializer_policy",.str "reject static/persistent boxes and closures"),
    ("lifetime",.str "real owned scalar boxes; generational parent/environment; retain/release/reclamation"),
    ("functions",.arr functions),("adapters",.arr adapters),
    ("dispatcher",Json.mkObj [("source",.str dispatcher.toString),("symbol",.str (← symbol lowered dispatcher)),
      ("checked_action",.str checked.body.renderNormalized)])])]

def executionFields (selectedDeployment isArithmetic : Bool) (role : String)
    (suite : CheckedActionSuite) (parameterized : Bool := false)
    (localReduction : Bool := false) : Except String (List (String × Json)) := do
  if localReduction && !isArithmetic then throw "Local reduction identity escaped its Arithmetic role"
  if localReduction && !parameterized then throw "Local reduction requires its preserved parameterized checker"
  if !isArithmetic then return []
  let hasV7 := suite.actionFunctions.any fun function =>
    ((Lean.privateToUserName? function.name).getD function.name).toString.startsWith
      "Lemma.Services.Arithmetic.ProtocolV7."
  if !hasV7 then
    if parameterized then throw "Parameterized Arithmetic omitted its preserved Protocol7 implementation" else return []
  let hasV8 := suite.actionFunctions.any (·.name == `Lemma.Services.Arithmetic.ServerV8.main)
  let hasV9 := suite.actionFunctions.any (·.name == `Lemma.Services.Arithmetic.ServerV9.main)
  unless (!localReduction || parameterized) && hasV8 == (parameterized && !localReduction) && hasV9 == localReduction do
    throw "Parameterized Arithmetic source escaped its exact implementation identity"
  if parameterized then
    unless suite.actionFunctions.any (·.name == `Lemma.Services.Arithmetic.ProtocolV8.reply) &&
        suite.actionFunctions.any (·.name == `Lemma.Multimodal.Parameterized.evaluate) do
      throw "Parameterized Arithmetic omitted its genuinely elaborated packet/checker path"
  if localReduction then
    unless #[`Lemma.Services.Arithmetic.ServerV9.processCopied,
        `Lemma.Services.Arithmetic.ServerV9.step,
        `Lemma.Services.Arithmetic.ServerV8.processCopied,
        `Lemma.Services.Arithmetic.ServerV7.processCopied,
        `Lemma.Services.Arithmetic.ProtocolV9.evaluate,
        `Lemma.Services.Arithmetic.ProtocolV9.reply,
        `Lemma.Services.Arithmetic.ReductionV1.calculate].all
          (fun source => suite.actionFunctions.any fun function =>
            ((Lean.privateToUserName? function.name).getD function.name) == source) &&
        suite.scalarFunctions.any (·.name == `Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity) do
      throw "Local reduction omitted its exact service and delegated checking path"
  unless selectedDeployment && role == "user" && suite.contractVersion == Profile.user_v0_7.contractVersion &&
      suite.actionFunctions.any (·.name == `Lemma.Services.Arithmetic.ProtocolV7.reply) &&
      suite.actionFunctions.any (·.name == `Lemma.Services.Arithmetic.ProtocolV7.validateRequest) do
    throw "Closure execution identity escaped its exact Protocol7 isolated deployment"
  return [("arithmetic_closure_execution_identity",Json.mkObj ([
    ("contract_version",.str (if localReduction then "lemma-arithmetic-execution-identity-v8" else if parameterized then "lemma-arithmetic-execution-identity-v7" else "lemma-arithmetic-execution-identity-v6")),
    ("implementation",Json.mkObj [("name",.str (if localReduction then "lemma-isolated-arithmetic-local-reduction-closure-v1" else if parameterized then
      "lemma-isolated-arithmetic-parameterized-closure-v1" else "lemma-isolated-arithmetic-closure-v1")),
      ("id",toJson (if localReduction then (0x0009000100000001 : Nat) else if parameterized then (0x0008000100000001 : Nat) else Lemma.Mathematics.ExecutionIdentityV6.implementation.toNat))]),
    ("lowering",Json.mkObj [("name",.str "core0-user-v0.7/lemma-managed-closure-v1"),
      ("id",toJson Lemma.Mathematics.ExecutionIdentityV6.lowering.toNat)]),
    ("runtime",Json.mkObj [("name",.str "lemma-owned-arena-closure-graph-v1"),
      ("id",toJson Lemma.Mathematics.ExecutionIdentityV6.runtime.toNat)]),
    ("resources",Json.mkObj [("name",.str "lemma-arithmetic-closure-resource-v1"),
      ("id",toJson Lemma.Mathematics.ExecutionIdentityV6.resources.toNat),
      ("heap_objects",toJson (31 : Nat)),("maximum_captures",toJson (4 : Nat)),
      ("maximum_targets",toJson (8 : Nat)),("ordinary_peak_objects",toJson (9 : Nat)),
      ("semantic_budgets",.arr #[toJson (0 : Nat),toJson (8 : Nat)]),
      ("deadline_ticks",toJson (10000000 : Nat))])] ++
    (if parameterized then [("parameterized",Json.mkObj [
      ("version",toJson (2 : Nat)),("request_bytes",toJson (192 : Nat)),
      ("reply_bytes",toJson (192 : Nat)),("checker_id",toJson (0x0002000000000001 : Nat))])] else []) ++
    (if localReduction then [("local_reduction",Json.mkObj [
      ("version",toJson (1 : Nat)),
      ("request_bytes",toJson Lemma.Services.Arithmetic.ProtocolV9.requestBytes.toNat),
      ("reply_bytes",toJson Lemma.Services.Arithmetic.ProtocolV9.replyBytes.toNat),
      ("service_id",toJson Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity.toNat),
      ("gcd_steps",toJson (32 : Nat)),
      ("maximum_magnitude",toJson Lemma.Services.Arithmetic.ReductionV1.maximumMagnitude.toNat),
      ("required_budget",toJson Lemma.Services.Arithmetic.ReductionV1.requiredBudget.toNat)])] else [])))]
end Lemma.Compiler.ManagedClosureMetadata
