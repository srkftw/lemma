import Lean
import Lemma.Core0
import Lemma.Compiler.Format
import Lemma.Compiler.Lower
import Lemma.Machine.Harness
import Lemma.Machine.Layout
import Lemma.Machine.Primitives

/-!
Elaboration commands joining the checked Core0 frontend to structured LLVM and
the structured machine-primitive generator.  `#core0_export` runs only after the
named ordinary Lean declaration has entered the current `Environment`.
-/

namespace Lemma.Compiler.Export

open Lean Elab Command

private def quoted (value : String) : String :=
  "\"" ++ Format.escapeJson value ++ "\""

private def jsonArray (values : List String) : String :=
  "[" ++ String.intercalate "," values ++ "]"

private def renderSignature (signature : Lemma.Core0.Signature) : String :=
  let args := signature.args.toList.map (fun ty => quoted ty.render)
  "{\"args\":" ++ jsonArray args ++ ",\"result\":" ++ quoted signature.result.render ++ "}"

private def renderCore0Manifest (program : Lemma.Core0.Program) (lowered : LoweredApplication) : String :=
  let functions := program.functions.toList.map fun function =>
    let symbol := lowered.symbols.find? (fun candidate => candidate.source == function.name)
      |>.map (·.llvm) |>.getD "<missing>"
    let dependencies := function.dependencies.toList.map (quoted ∘ Name.toString)
    "{" ++
      "\"source\":" ++ quoted function.name.toString ++ "," ++
      "\"llvm\":" ++ quoted symbol ++ "," ++
      "\"signature\":" ++ renderSignature function.signature ++ "," ++
      "\"dependencies\":" ++ jsonArray dependencies ++ "," ++
      "\"body\":" ++ quoted function.body.renderNormalized ++
    "}"
  let primitives := program.usedPrimitives.toList.map fun stableId =>
    let candidates := Lemma.Core0.primitiveAllowlist.toList.filter (fun spec => spec.stableId == stableId)
    let identities := candidates.map (quoted ∘ (·.leanDecl.toString))
    let signature := candidates.head?.map (renderSignature ∘ (·.signature)) |>.getD "null"
    "{" ++
      "\"stable_id\":" ++ quoted stableId ++ "," ++
      "\"lean_identities\":" ++ jsonArray identities ++ "," ++
      "\"signature\":" ++ signature ++ "," ++
      "\"effect\":\"pure\"}"
  String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"contract_version\": " ++ quoted program.contractVersion ++ ",",
    "  \"root\": " ++ quoted program.root.toString ++ ",",
    "  \"root_llvm\": " ++ quoted lowered.rootSymbol ++ ",",
    "  \"root_abi\": {\"args\":[\"u64\",\"u64\",\"u64\"],\"result\":\"u64\"},",
    "  \"functions\": " ++ jsonArray functions ++ ",",
    "  \"used_primitives\": " ++ jsonArray primitives ++ ",",
    "  \"machine_primitives\": [",
    "    {\"identity\":\"startup\",\"effect\":\"machine-state\",\"implementation\":\"Lemma.Machine.Primitives.startup\"},",
    "    {\"identity\":\"io-fence\",\"effect\":\"ordered-mmio\",\"implementation\":\"Lemma.Machine.Primitives.ioFence\"},",
    "    {\"identity\":\"uart16550\",\"effect\":\"bounded-ordered-mmio\",\"implementation\":\"Lemma.Machine.Harness.uartPutc/uartDrain\"},",
    "    {\"identity\":\"runtime-input\",\"effect\":\"fixed-memory-read\",\"implementation\":\"Lemma.Machine.Harness.main\"},",
    "    {\"identity\":\"sifive-test\",\"effect\":\"vm-termination-mmio\",\"implementation\":\"Lemma.Machine.Harness.exitSuccess/exitFailure\"}",
    "  ]",
    "}", ""
  ]

/-- Check the fixed Task 001 harness ABI. Additive test profiles use separate exporters. -/
def checkLegacyTargetRoot (program : Lemma.Core0.Program) : Except String Unit := do
  let some root := program.findFunction? program.root
    | throw "checked Core0 program does not contain its root"
  unless root.signature.args == #[Lemma.Core0.Ty.u64, .u64, .u64] &&
      root.signature.result == Lemma.Core0.Ty.u64 do
    throw "freestanding harness root must have type UInt64 -> UInt64 -> UInt64 -> UInt64"

/-- Run genuine frontend checking and ordinary structured lowering for the legacy harness. -/
def prepareLegacyApplication (env : Environment) (name : Name) :
    IO (Lemma.Core0.Program × LoweredApplication) := do
  let program ← match Lemma.Core0.checkAndLower env name with
    | .ok program => pure program
    | .error diagnostic => throw <| IO.userError diagnostic.render
  match checkLegacyTargetRoot program with
  | .error message => throw <| IO.userError message
  | .ok () => pure ()
  let lowered ← match lowerApplication program with
    | .ok lowered => pure lowered
    | .error message => throw <| IO.userError s!"Core0 LLVM lowering failed: {message}"
  pure (program, lowered)

/-- Emit the common legacy harness artifacts from an already checked/lowered application. -/
def writeLegacyArtifacts (name : Name) (outputDir : System.FilePath)
    (program : Lemma.Core0.Program) (lowered : LoweredApplication) : IO Unit := do
  let layout := Lemma.Machine.core0Layout
  let linkScript ← match layout.linkerScript with
    | .ok script => pure script
    | .error message => throw <| IO.userError message
  let layoutManifest ← match layout.manifestJson with
    | .ok manifest => pure manifest
    | .error message => throw <| IO.userError message
  let module : LLVM.Module := {
    sourceName := name.toString
    declarations := Lemma.Machine.Harness.declarations
    functions := lowered.functions ++ Lemma.Machine.Harness.functions layout lowered.rootSymbol
  }
  IO.FS.createDirAll outputDir
  IO.FS.writeFile (outputDir / "program.ll") module.render
  IO.FS.writeFile (outputDir / "startup.S") Lemma.Machine.Primitives.renderStartup
  IO.FS.writeFile (outputDir / "link.ld") linkScript
  IO.FS.writeFile (outputDir / "layout.json") layoutManifest
  IO.FS.writeFile (outputDir / "core0-manifest.json") (renderCore0Manifest program lowered)
  IO.FS.writeFile (outputDir / "core0-normalized.txt") program.renderManifest
  IO.FS.writeFile (outputDir / "symbols.txt") lowered.renderSymbolManifest

private def exportProgram (env : Environment) (name : Name) (outputDir : System.FilePath) : IO Unit := do
  let (program, lowered) ← prepareLegacyApplication env name
  writeLegacyArtifacts name outputDir program lowered

syntax (name := core0Export) "#core0_export " ident : command

elab_rules : command
  | `(#core0_export $decl:ident) => do
      let name ← resolveGlobalConstNoOverload decl
      let output? ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
      let some output := output?
        | throwErrorAt decl "LEMMA_CORE0_OUT must name the generated-artifact directory"
      let env ← getEnv
      liftIO <| exportProgram env name (System.FilePath.mk output)
      logInfoAt decl m!"Core0 exported `{name}` to {output}"

private def parseNatArgument (stx : Syntax) : CommandElabM Nat := do
  let some text := stx.isStrLit?
    | throwErrorAt stx "Core0 evaluator arguments must be string literals"
  let some value := text.toNat?
    | throwErrorAt stx "Core0 evaluator argument is not a decimal natural number"
  unless value < 2 ^ 64 do
    throwErrorAt stx "Core0 evaluator argument exceeds UInt64"
  pure value

syntax (name := core0Eval) "#core0_eval " ident str str str : command

elab_rules : command
  | `(#core0_eval $decl:ident $a:str $b:str $c:str) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      let program ← match Lemma.Core0.checkAndLower env name with
        | .ok program => pure program
        | .error diagnostic => throwErrorAt decl diagnostic.render
      let args := #[← parseNatArgument a, ← parseNatArgument b, ← parseNatArgument c]
      let scalars := args.map Lemma.Core0.Scalar.u64
      match Lemma.Core0.evalProgramScalars program scalars with
      | .error diagnostic => throwErrorAt decl diagnostic.render
      | .ok result =>
          unless result.ty == .u64 do
            throwErrorAt decl "Core0 reference root did not return UInt64"
          logInfoAt decl m!"CORE0_REFERENCE:{Format.hexFixed 16 result.value}"

end Lemma.Compiler.Export
