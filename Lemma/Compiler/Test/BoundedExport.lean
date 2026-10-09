import Lean
import Lemma.Compiler.CFGLower
import Lemma.Compiler.Export
import Lemma.Compiler.Test.ScalarABI
import Lemma.Machine.ScalarHarness

/-! Fixed, test-only exporter for the `core0-v0.3` bounded-loop suite. -/

namespace Lemma.Compiler.Test.BoundedExport

open Lean Elab Command
open Lemma.Compiler
open Lemma.Compiler.Test.ScalarABI

private def quoted (value : String) : String :=
  "\"" ++ Lemma.Compiler.Format.escapeJson value ++ "\""

private def jsonArray (values : List String) : String :=
  "[" ++ String.intercalate "," values ++ "]"

private def renderSignature (signature : Lemma.Core0.Signature) : String :=
  let args := signature.args.toList.map (fun ty => quoted ty.render)
  "{\"args\":" ++ jsonArray args ++ ",\"result\":" ++ quoted signature.result.render ++ "}"

private def extensionName : Option LLVM.ABIExtension → String
  | none => "none"
  | some extension => extension.render

private def parseEnvNat (name : String) : IO Nat := do
  let some text ← IO.getEnv name
    | throw <| IO.userError s!"{name} must be set for the bounded-suite exporter"
  let some value := text.toNat?
    | throw <| IO.userError s!"{name} must be a decimal natural number"
  unless value < 2 ^ 64 do throw <| IO.userError s!"{name} exceeds UInt64"
  pure value

private def renderPrimitive (stableId : String) : String :=
  let candidates := Lemma.Core0.primitiveAllowlistV03.toList.filter
    (fun spec => spec.stableId == stableId)
  let identities := candidates.map (quoted ∘ (·.leanDecl.toString))
  let signature := candidates.head?.map (renderSignature ∘ (·.signature)) |>.getD "null"
  "{" ++
    "\"stable_id\":" ++ quoted stableId ++ "," ++
    "\"lean_identities\":" ++ jsonArray identities ++ "," ++
    "\"signature\":" ++ signature ++ "," ++
    "\"effect\":\"pure\"}"

private def renderIteration (site : Lemma.Core0.IterationUse) : String :=
  let spec := Lemma.Core0.boundedFoldU32Spec
  "{" ++
    "\"stable_id\":" ++ quoted site.stableId ++ "," ++
    "\"source_identity\":" ++ quoted spec.leanDecl.toString ++ "," ++
    "\"static_budget\":" ++ toString site.budget ++ "," ++
    "\"static_budget_type\":\"Nat\"," ++
    "\"static_budget_form\":\"canonical-standard-Nat-literal\"," ++
    "\"callback\":" ++ quoted site.callback.toString ++ "," ++
    "\"runtime_signature\":" ++ renderSignature spec.runtimeSignature ++ "," ++
    "\"callback_signature\":" ++ renderSignature spec.callbackSignature ++ "," ++
    "\"maximum_budget\":" ++ toString spec.maximumBudget ++ "," ++
    "\"counter\":{\"type\":\"u32\",\"order\":\"ascending-zero-based\"}," ++
    "\"accumulator\":\"u32\"," ++
    "\"outcome\":{\"type\":\"u64\",\"success\":\"zero-extended-u32\"," ++
      "\"exhaustion_tag\":\"0x8000000000000000\"," ++
      "\"exhaustion_payload\":\"initial-u32\",\"exhaustion_reserved_bits\":\"bits32-through62-zero\"," ++
      "\"callbacks_on_exhaustion\":0}," ++
    "\"effect\":\"pure\"}"

private def renderManifest (suite : Lemma.Core0.CheckedSuite) (lowered : LoweredSuite)
    (config : Configuration) : String :=
  let roots := lowered.roots.toList.map fun root =>
    let extensions := root.signature.args.toList.map
      (quoted ∘ extensionName ∘ rv64LP64Extension)
    "{" ++
      "\"root_id\":" ++ toString root.id ++ "," ++
      "\"source\":" ++ quoted root.source.toString ++ "," ++
      "\"llvm\":" ++ quoted root.llvm ++ "," ++
      "\"signature\":" ++ renderSignature root.signature ++ "," ++
      "\"return_extension\":" ++ quoted (extensionName (rv64LP64Extension root.signature.result)) ++ "," ++
      "\"parameter_extensions\":" ++ jsonArray extensions ++ "}"
  let functions := suite.functions.toList.map fun function =>
    let symbol := lowered.symbols.find? (fun candidate => candidate.source == function.name)
      |>.map (·.llvm) |>.getD "<missing>"
    let dependencies := function.dependencies.toList.map (quoted ∘ Name.toString)
    let extensions := function.signature.args.toList.map
      (quoted ∘ extensionName ∘ rv64LP64Extension)
    "{" ++
      "\"source\":" ++ quoted function.name.toString ++ "," ++
      "\"llvm\":" ++ quoted symbol ++ "," ++
      "\"signature\":" ++ renderSignature function.signature ++ "," ++
      "\"dependencies\":" ++ jsonArray dependencies ++ "," ++
      "\"body\":" ++ quoted function.body.renderNormalized ++ "," ++
      "\"return_extension\":" ++ quoted (extensionName (rv64LP64Extension function.signature.result)) ++ "," ++
      "\"parameter_extensions\":" ++ jsonArray extensions ++ "," ++
      "\"noinline\":true}"
  let primitives := suite.usedPrimitives.toList.map renderPrimitive
  let iterations := suite.usedIterations.toList.map renderIteration
  String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"artifact_category\": \"test-loop-suite\",",
    "  \"contract_version\": " ++ quoted suite.contractVersion ++ ",",
    "  \"test_abi\": " ++ quoted name ++ ",",
    "  \"suite_id\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.suiteId) ++ ",",
    "  \"source_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.sourceSeed) ++ ",",
    "  \"runtime_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.runtimeSeed) ++ ",",
    "  \"loop_contract\": {\"source_identity\":\"Lemma.Core0.Bounded.boundedFoldU32\"," ++
      "\"stable_id\":\"u32.bounded-fold\",\"validator\":\"Lemma.Compiler.LLVM.validateModule\"," ++
      "\"static_budget_type\":\"Nat\",\"static_budget_form\":\"canonical-standard-Nat-literal\"," ++
      "\"runtime_count\":\"u32\",\"counter\":{\"type\":\"u32\",\"order\":\"ascending-zero-based\"}," ++
      "\"accumulator\":\"u32\",\"maximum_budget\":256," ++
      "\"outcome\":{\"type\":\"u64\",\"success\":\"zero-extended-u32\"," ++
        "\"exhaustion_tag\":\"0x8000000000000000\",\"exhaustion_payload\":\"initial-u32\"," ++
        "\"exhaustion_reserved_bits\":\"bits32-through62-zero\"," ++
        "\"callbacks_on_exhaustion\":0},\"effect\":\"pure\"},",
    "  \"roots\": " ++ jsonArray roots ++ ",",
    "  \"functions\": " ++ jsonArray functions ++ ",",
    "  \"used_primitives\": " ++ jsonArray primitives ++ ",",
    "  \"iterations\": " ++ jsonArray iterations ++ ",",
    "  \"machine_primitives\": [",
    "    {\"identity\":\"startup\",\"effect\":\"machine-state\",\"implementation\":\"Lemma.Machine.Primitives.startup\"},",
    "    {\"identity\":\"io-fence\",\"effect\":\"ordered-mmio\",\"implementation\":\"Lemma.Machine.Primitives.ioFence\"},",
    "    {\"identity\":\"uart16550\",\"effect\":\"bounded-ordered-mmio\",\"implementation\":\"Lemma.Machine.Harness.uartPutc/uartDrain\"},",
    "    {\"identity\":\"typed-runtime-input\",\"effect\":\"fixed-memory-read\",\"implementation\":\"Lemma.Machine.ScalarHarness.main\"},",
    "    {\"identity\":\"sifive-test\",\"effect\":\"vm-termination-mmio\",\"implementation\":\"Lemma.Machine.Harness.exitSuccess/exitFailure\"}",
    "  ]",
    "}", ""
  ]

private def renderNormalized (suite : Lemma.Core0.CheckedSuite) : String :=
  let roots := suite.roots.toList.map fun root =>
    s!"root={root.id};source={root.source};signature={renderSignature root.signature}\n"
  let functions := suite.functions.toList.map fun function =>
    s!"function={function.name};signature={renderSignature function.signature};" ++
      s!"body={function.body.renderNormalized}\n"
  let primitives := suite.usedPrimitives.toList.map (s!"primitive={·}\n")
  let iterations := suite.usedIterations.toList.map fun site =>
    s!"iteration={site.stableId};budget={site.budget};callback={site.callback}\n"
  "contract=" ++ suite.contractVersion ++ "\n" ++ String.join roots ++
    String.join functions ++ String.join primitives ++ String.join iterations

private def renderABI (config : Configuration) : String :=
  String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"contract_version\": \"core0-v0.3\",",
    "  \"name\": " ++ quoted name ++ ",",
    "  \"byte_order\": \"little-endian\",",
    "  \"magic_bytes\": \"4c454d4d41303032\",",
    "  \"magic_word\": \"0x323030414d4d454c\",",
    "  \"version\": 1,",
    "  \"header_bytes\": 128,",
    "  \"record_bytes\": 136,",
    "  \"maximum_arguments\": 16,",
    "  \"maximum_cases\": 29,",
    "  \"tags\": {\"bool\":1,\"u8\":2,\"u32\":3,\"u64\":4},",
    "  \"header_words\": [\"magic\",\"version\",\"header_bytes\",\"record_bytes\",\"suite_id\",\"batch_id\",\"root_id\",\"case_count\",\"argument_count\",\"result_tag\",\"argument_tags_0_7\",\"argument_tags_8_15\",\"source_seed\",\"runtime_seed\",\"reserved_zero\",\"reserved_zero\"],",
    "  \"record_layout\": \"case_id:u64,arguments:16xu64; unused slots zero\",",
    "  \"transport_rules\": \"Bool=0/1; UInt8<=255; UInt32<=4294967295; UInt64 unrestricted; reject before truncation; zero-extend narrow results to u64\",",
    "  \"output_protocol\": {\"banner\":\"LEMMA_SCALAR/1\\n\",\"batch\":\"BATCH:<suite16>:<batch16>:<root16>:<count16>\\n\",\"result\":\"RESULT:<case16>:<tag16>:<value16>\\n\",\"end\":\"END:<batch16>:<count16>\\n\",\"hex\":\"lowercase fixed-width\"},",
    "  \"suite_id\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.suiteId) ++ ",",
    "  \"source_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.sourceSeed) ++ ",",
    "  \"runtime_seed\": " ++ quoted (Lemma.Compiler.Format.hexFixed 16 config.runtimeSeed) ++
    "}", ""
  ]

private def exportSuite (env : Environment) (names : Array Name)
    (outputDir : System.FilePath) : IO Unit := do
  let config : Configuration := {
    suiteId := ← parseEnvNat "LEMMA_SCALAR_SUITE_ID"
    sourceSeed := ← parseEnvNat "LEMMA_SCALAR_SOURCE_SEED"
    runtimeSeed := ← parseEnvNat "LEMMA_SCALAR_RUNTIME_SEED"
  }
  match config.validate with
  | .error message => throw <| IO.userError message
  | .ok () => pure ()
  let suite ← match Lemma.Core0.checkAndLowerSuiteForProfile env .v0_3 names with
    | .ok suite => pure suite
    | .error diagnostic => throw <| IO.userError diagnostic.render
  unless !suite.usedIterations.isEmpty do
    throw <| IO.userError "bounded suite did not contain a checked iteration site"
  for root in suite.roots do
    unless root.signature.args.size ≤ maxArguments do
      throw <| IO.userError
        (s!"typed bounded suite root `{root.source}` has {root.signature.args.size} arguments; " ++
          s!"the {name} maximum is {maxArguments}")
  let preserveCalls := suite.functions.map (·.name)
  let lowered ← match lowerSuiteV03 suite { preserveCalls } with
    | .ok lowered => pure lowered
    | .error message => throw <| IO.userError s!"bounded suite LLVM lowering failed: {message}"
  let layout := Lemma.Machine.core0Layout
  let linkScript ← match layout.linkerScript with
    | .ok script => pure script
    | .error message => throw <| IO.userError message
  let layoutManifest ← match layout.manifestJson with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let llvmModule : LLVM.Module := {
    sourceName := "Lemma Gate 4 bounded iteration suite"
    declarations := Lemma.Machine.ScalarHarness.declarations
    functions := lowered.functions ++
      Lemma.Machine.ScalarHarness.functions layout config lowered.roots
  }
  match LLVM.validateModule llvmModule with
  | .ok () => pure ()
  | .error message => throw <| IO.userError message
  IO.FS.createDirAll outputDir
  IO.FS.writeFile (outputDir / "program.ll") llvmModule.render
  IO.FS.writeFile (outputDir / "startup.S") Lemma.Machine.Primitives.renderStartup
  IO.FS.writeFile (outputDir / "link.ld") linkScript
  IO.FS.writeFile (outputDir / "layout.json") layoutManifest
  IO.FS.writeFile (outputDir / "bounded-suite-manifest.json")
    (renderManifest suite lowered config)
  IO.FS.writeFile (outputDir / "bounded-suite-normalized.txt") (renderNormalized suite)
  IO.FS.writeFile (outputDir / "scalar-test-abi.json") (renderABI config)
  IO.FS.writeFile (outputDir / "symbols.txt") lowered.renderSymbolManifest

syntax (name := core0ExportBoundedSuite)
  "#core0_export_bounded_suite " "[" ident,* "]" : command

elab_rules : command
  | `(#core0_export_bounded_suite [$decls:ident,*]) => do
      let mut names : Array Name := #[]
      for declaration in decls.getElems do
        names := names.push (← resolveGlobalConstNoOverload declaration)
      let output? ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
      let some output := output?
        | throwError "LEMMA_CORE0_OUT must name the generated-artifact directory"
      let env ← getEnv
      liftIO <| exportSuite env names (System.FilePath.mk output)
      logInfo m!"Core0 exported bounded v0.3 suite with {names.size} roots to {output}"

end Lemma.Compiler.Test.BoundedExport
