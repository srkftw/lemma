import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.Format
import Lemma.Compiler.Test.MemoryABI
import Lemma.Machine.MemoryHarness
import Lemma.Machine.MemoryLayout
import Lemma.Machine.Primitives

/-! Fixed test exporter for the genuine `core0-v0.4` checked-memory suite. -/

namespace Lemma.Compiler.Test.MemoryExport

open Lean Elab Command
open Lemma.Compiler
open Lemma.Compiler.Test.MemoryABI

private def quoted (value : String) : String :=
  "\"" ++ Lemma.Compiler.Format.escapeJson value ++ "\""

private def jsonArray (values : List String) : String :=
  "[" ++ String.intercalate "," values ++ "]"

private def renderScalarSignature (signature : Lemma.Core0.Signature) : String :=
  let args := signature.args.toList.map (quoted ∘ Lemma.Core0.Ty.render)
  "{\"args\":" ++ jsonArray args ++
    ",\"result\":" ++ quoted signature.result.render ++ "}"

private def renderActionSignature (signature : Lemma.Core0.ActionSignature) : String :=
  let args := signature.args.toList.map (quoted ∘ Lemma.Core0.Ty.render)
  "{\"args\":" ++ jsonArray args ++ "}"

private def effectNames (effects : Lemma.Core0.EffectSet) : List String :=
  (if effects.checkedAccess then ["checked-access"] else []) ++
  (if effects.ramRead then ["fixed-ram-read"] else []) ++
  (if effects.ramWrite then ["fixed-ram-write"] else [])

private def renderEffects (effects : Lemma.Core0.EffectSet) : String :=
  jsonArray (effectNames effects |>.map quoted)

private def extensionName : Option LLVM.ABIExtension → String
  | none => "none"
  | some extension => extension.render

private def renderPrimitive (stableId : String) : String :=
  let candidates := Lemma.Core0.primitiveAllowlistV04.toList.filter
    (fun spec => spec.stableId == stableId)
  let leanIdentities := candidates.map (quoted ∘ (fun spec => spec.leanDecl.toString))
  let signature := candidates.head?.map (renderScalarSignature ∘ (fun spec => spec.signature))
    |>.getD "null"
  "{" ++
    "\"stable_id\":" ++ quoted stableId ++ "," ++
    "\"lean_identities\":" ++ jsonArray leanIdentities ++ "," ++
    "\"signature\":" ++ signature ++ "," ++
    "\"effect\":\"pure\"}"

private def memorySourceIdentity (use : Lemma.Core0.MemoryOpUse) : String :=
  if use.range then
    match use.access with
    | .read => "Lemma.Core0.Memory.Action.checkReadRange"
    | .write => "Lemma.Core0.Memory.Action.checkWriteRange"
  else
    let constructor := match use.access with
      | .read => "load"
      | .write => "store"
    let suffix := use.width?.map Lemma.Core0.Memory.Width.render |>.getD "?"
    "Lemma.Core0.Memory.Action." ++ constructor ++ suffix

private def renderMemoryUse (use : Lemma.Core0.MemoryOpUse) : String :=
  let effect := if use.range then "checked-access" else match use.access with
    | .read => "fixed-ram-read"
    | .write => "fixed-ram-write"
  let access := use.access.render
  let width := use.width?.map (toString ∘ Lemma.Core0.Memory.Width.bits) |>.getD "null"
  "{" ++
    "\"stable_id\":" ++ quoted use.stableId ++ "," ++
    "\"source_identity\":" ++ quoted (memorySourceIdentity use) ++ "," ++
    "\"access\":" ++ quoted access ++ "," ++
    "\"width\":" ++ width ++ "," ++
    "\"range\":" ++ toString use.range ++ "," ++
    "\"effect\":" ++ quoted effect ++ "}"

private def renderActionIteration (site : Lemma.Core0.ActionIterationUse) : String :=
  "{" ++
    "\"stable_id\":" ++ quoted site.stableId ++ "," ++
    "\"source_identity\":\"Lemma.Core0.Memory.Action.boundedFoldU64\"," ++
    "\"static_budget\":" ++ toString site.budget ++ "," ++
    "\"callback\":" ++ quoted site.callback.toString ++ "," ++
    "\"maximum_budget\":256," ++
    "\"counter\":{\"type\":\"u32\",\"order\":\"ascending-zero-based\"}," ++
    "\"accumulator\":\"u64\"," ++
    "\"contexts\":4," ++
    "\"outcome\":\"checked-result-v1\"," ++
    "\"exhaustion\":{\"status\":9,\"value\":\"initial\",\"callbacks\":0}}"

private def renderManifest (suite : Lemma.Core0.CheckedActionSuite)
    (lowered : LoweredActionSuite) (layout : Lemma.Machine.MemoryLayout)
    (config : Configuration) : Except String String := do
  let memoryContract ← layout.memoryContractJson
  let roots := lowered.roots.toList.map fun root =>
    "{" ++
      "\"root_id\":" ++ toString root.id ++ "," ++
      "\"source\":" ++ quoted root.source.toString ++ "," ++
      "\"llvm\":" ++ quoted root.llvm ++ "," ++
      "\"signature\":" ++ renderActionSignature root.signature ++ "}"
  let scalarFunctions := suite.scalarFunctions.toList.map fun function =>
    let symbol := lowered.symbols.find? (fun candidate => candidate.source == function.name)
      |>.map (fun candidate => candidate.llvm) |>.getD "<missing>"
    "{" ++
      "\"source\":" ++ quoted function.name.toString ++ "," ++
      "\"llvm\":" ++ quoted symbol ++ "," ++
      "\"signature\":" ++ renderScalarSignature function.signature ++ "," ++
      "\"dependencies\":" ++ jsonArray
        (function.dependencies.toList.map (quoted ∘ Name.toString)) ++ "," ++
      "\"body\":" ++ quoted function.body.renderNormalized ++ "," ++
      "\"noinline\":true}"
  let actionFunctions := suite.actionFunctions.toList.map fun function =>
    let symbol := lowered.symbols.find? (fun candidate => candidate.source == function.name)
      |>.map (fun candidate => candidate.llvm) |>.getD "<missing>"
    "{" ++
      "\"source\":" ++ quoted function.name.toString ++ "," ++
      "\"llvm\":" ++ quoted symbol ++ "," ++
      "\"signature\":" ++ renderActionSignature function.signature ++ "," ++
      "\"scalar_dependencies\":" ++ jsonArray
        (function.scalarDependencies.toList.map (quoted ∘ Name.toString)) ++ "," ++
      "\"action_dependencies\":" ++ jsonArray
        (function.actionDependencies.toList.map (quoted ∘ Name.toString)) ++ "," ++
      "\"direct_effects\":" ++ renderEffects function.directEffects ++ "," ++
      "\"transitive_effects\":" ++ renderEffects function.effects ++ "," ++
      "\"body\":" ++ quoted function.body.renderNormalized ++ "," ++
      "\"noinline\":true}"
  let memoryUses := suite.usedMemoryOps.qsort (fun left right => left.stableId < right.stableId)
  let primitives := suite.usedPrimitives.toList.map renderPrimitive
  let iterations := suite.usedActionIterations.toList.map renderActionIteration
  pure <| String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"artifact_category\": \"test-memory-suite\",",
    "  \"contract_version\": \"core0-v0.4\",",
    "  \"test_abi\": \"lemma-memory-test-v1\",",
    "  \"suite_id\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.suiteId) ++ ",",
    "  \"source_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.sourceSeed) ++ ",",
    "  \"runtime_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.runtimeSeed) ++ ",",
    "  \"checked_result\": {\"logical_status\":\"u8\",\"logical_value\":\"u64\"," ++
      "\"llvm\":\"{ i64, i64 }\",\"rv64\":\"a0=status-zero-extended,a1=value\"," ++
      "\"status_high_bits_zero\":true},",
    "  \"memory_contract\": " ++ memoryContract ++ ",",
    "  \"roots\": " ++ jsonArray roots ++ ",",
    "  \"scalar_functions\": " ++ jsonArray scalarFunctions ++ ",",
    "  \"action_functions\": " ++ jsonArray actionFunctions ++ ",",
    "  \"used_primitives\": " ++ jsonArray primitives ++ ",",
    "  \"used_memory_ops\": " ++ jsonArray
      (memoryUses.toList.map renderMemoryUse) ++ ",",
    "  \"action_iterations\": " ++ jsonArray iterations ++ ",",
    "  \"machine_primitives\": [",
    "    {\"identity\":\"startup\",\"effect\":\"machine-state\",\"implementation\":\"Lemma.Machine.Primitives.startup\"},",
    "    {\"identity\":\"io-fence\",\"effect\":\"ordered-mmio\",\"implementation\":\"Lemma.Machine.Primitives.ioFence\"},",
    "    {\"identity\":\"uart16550\",\"effect\":\"bounded-ordered-mmio\",\"implementation\":\"Lemma.Machine.Harness.uartPutc/uartDrain\"},",
    "    {\"identity\":\"memory-test-dispatch\",\"effect\":\"fixed-input-read/canary-observation\",\"implementation\":\"Lemma.Machine.MemoryHarness.main\"},",
    "    {\"identity\":\"sifive-test\",\"effect\":\"vm-termination-mmio\",\"implementation\":\"Lemma.Machine.Harness.exitSuccess/exitFailure\"}",
    "  ]",
    "}", ""
  ]

private def renderNormalized (suite : Lemma.Core0.CheckedActionSuite) : String :=
  let roots := suite.roots.toList.map fun root =>
    s!"root={root.id};source={root.source};signature={renderActionSignature root.signature}\n"
  let scalars := suite.scalarFunctions.toList.map fun function =>
    s!"scalar={function.name};body={function.body.renderNormalized}\n"
  let actions := suite.actionFunctions.toList.map fun function =>
    s!"action={function.name};direct={function.directEffects.render};" ++
      s!"transitive={function.effects.render};body={function.body.renderNormalized}\n"
  let operations := suite.usedMemoryOps.toList.map fun use =>
    s!"memory-op={use.stableId}\n"
  let iterations := suite.usedActionIterations.toList.map fun site =>
    s!"action-iteration={site.stableId};budget={site.budget};callback={site.callback}\n"
  "contract=core0-v0.4\n" ++ String.join roots ++ String.join scalars ++
    String.join actions ++ String.join operations ++ String.join iterations

private def renderABI (config : Configuration) : String :=
  String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"contract_version\": \"core0-v0.4\",",
    "  \"name\": \"lemma-memory-test-v1\",",
    "  \"result_tag\": \"checked-result-v1\",",
    "  \"physical_result_words\": [\"status:i64\",\"value:i64\"],",
    "  \"byte_order\": \"little-endian\",",
    "  \"magic_bytes\": \"4c454d4d41303035\",",
    "  \"magic_word\": \"0x353030414d4d454c\",",
    "  \"version\": 1,",
    "  \"header_bytes\": 128,",
    "  \"control_bytes\": 256,",
    "  \"maximum_arguments\": 16,",
    "  \"tags\": {\"bool\":1,\"u8\":2,\"u32\":3,\"u64\":4},",
    "  \"header_words\": [" ++ String.intercalate ","
      (headerFieldNames.toList.map quoted) ++ "],",
    "  \"argument_layout\": \"16xu64; unused slots zero\",",
    "  \"transport_rules\": \"Bool=0/1; UInt8<=255; UInt32<=4294967295; UInt64 unrestricted; reject before truncation\",",
    "  \"output_protocol\": {\"banner\":\"LEMMA_MEMORY/1\\n\"," ++
      "\"case\":\"CASE:<suite16>:<case16>:<root16>\\n\"," ++
      "\"outcome\":\"OUTCOME:<case16>:<status16>:<value16>\\n\"," ++
      "\"region\":\"REGION:<id2>:<length16>:<little-endian-i64-words>\\n\"," ++
      "\"canary\":\"CANARY:<id2>:<low16>:<high16>\\n\"," ++
      "\"end\":\"END:<case16>\\n\"},",
    "  \"suite_id\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.suiteId) ++ ",",
    "  \"source_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.sourceSeed) ++ ",",
    "  \"runtime_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.runtimeSeed),
    "}", ""
  ]

private def parseEnvNat (name : String) : IO Nat := do
  let some text ← IO.getEnv name
    | throw <| IO.userError s!"{name} must be set for the memory-suite exporter"
  let some value := text.toNat?
    | throw <| IO.userError s!"{name} must be a decimal natural number"
  unless value < 2 ^ 64 do throw <| IO.userError s!"{name} exceeds UInt64"
  pure value

private def exportSuite (env : Environment) (names : Array Name)
    (outputDir : System.FilePath) : IO Unit := do
  unless names.size == 26 do
    throw <| IO.userError s!"the fixed Gate 5 suite requires 26 roots, got {names.size}"
  let config : Configuration := {
    suiteId := ← parseEnvNat "LEMMA_MEMORY_SUITE_ID"
    sourceSeed := ← parseEnvNat "LEMMA_MEMORY_SOURCE_SEED"
    runtimeSeed := ← parseEnvNat "LEMMA_MEMORY_RUNTIME_SEED"
  }
  match config.validate with
  | .ok () => pure ()
  | .error message => throw <| IO.userError message
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteV04 env names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  unless suite.roots.size == 26 && suite.usedMemoryOps.size == 8 &&
      suite.usedActionIterations.size == 5 do
    throw <| IO.userError
      (s!"memory suite closure differs: roots={suite.roots.size}, " ++
        s!"ops={suite.usedMemoryOps.size}, folds={suite.usedActionIterations.size}")
  for root in suite.roots do
    match validateSignature root.signature.args with
    | .ok () => pure ()
    | .error message => throw <| IO.userError message
  let preserveCalls := suite.scalarFunctions.map (fun function => function.name) ++
    suite.actionFunctions.map (fun function => function.name)
  let lowered ← match lowerActionSuiteV04 suite { preserveCalls } with
    | .ok lowered => pure lowered
    | .error message => throw <| IO.userError s!"memory suite LLVM lowering failed: {message}"
  let layout := Lemma.Machine.memoryLayout
  let linkScript ← match layout.linkerScript with
    | .ok script => pure script
    | .error message => throw <| IO.userError message
  let machineLayout ← match layout.machine.manifestJson with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let fixtureLayout ← match layout.fixtureContractJson with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let manifest ← match renderManifest suite lowered layout config with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let llvmModule : LLVM.Module := {
    sourceName := "Lemma Gate 5 checked fixed-memory suite"
    declarations := Lemma.Machine.MemoryHarness.declarations
    functions := lowered.functions ++
      Lemma.Machine.MemoryHarness.functions layout config lowered.roots
  }
  match LLVM.validateModule llvmModule with
  | .ok () => pure ()
  | .error message => throw <| IO.userError message
  IO.FS.createDirAll outputDir
  IO.FS.writeFile (outputDir / "program.ll") llvmModule.render
  IO.FS.writeFile (outputDir / "startup.S") Lemma.Machine.Primitives.renderStartup
  IO.FS.writeFile (outputDir / "link.ld") linkScript
  IO.FS.writeFile (outputDir / "layout.json") machineLayout
  IO.FS.writeFile (outputDir / "memory-fixtures.json") fixtureLayout
  IO.FS.writeFile (outputDir / "memory-suite-manifest.json") manifest
  IO.FS.writeFile (outputDir / "memory-suite-normalized.txt") (renderNormalized suite)
  IO.FS.writeFile (outputDir / "memory-test-abi.json") (renderABI config)
  IO.FS.writeFile (outputDir / "symbols.txt") lowered.renderSymbolManifest

syntax (name := core0ExportMemorySuite)
  "#core0_export_memory_suite " "[" ident,* "]" : command

elab_rules : command
  | `(#core0_export_memory_suite [$decls:ident,*]) => do
      let mut names : Array Name := #[]
      for declaration in decls.getElems do
        names := names.push (← resolveGlobalConstNoOverload declaration)
      let some output ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
        | throwError "LEMMA_CORE0_OUT must name the generated-artifact directory"
      let env ← getEnv
      liftIO <| exportSuite env names (System.FilePath.mk output)
      logInfo m!"Core0 exported checked-memory v0.4 suite with {names.size} roots to {output}"

end Lemma.Compiler.Test.MemoryExport
