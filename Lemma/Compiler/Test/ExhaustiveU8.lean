import Lean
import Lemma.Core0.Frontend
import Lemma.Core0.Semantics

/-!
Test-only exhaustive evaluation support for the Gate 2 UInt8 primitive anchors.

This module evaluates already checked `Core0.Program` values.  It deliberately
does not contain a source-language oracle: the independent source driver lives
under `examples/foundation` and invokes the original elaborated declarations.
The two byte streams are compared by the bounded host orchestrator.
-/

namespace Lemma.Compiler.Test.ExhaustiveU8

open Lean Elab Command

private structure RootSpec where
  label : String
  location : Syntax
  name : Name
  expectedResult : Lemma.Core0.Ty
  program : Lemma.Core0.Program

private def checkedRoot (env : Environment) (label : String) (location : Syntax)
    (name : Name) (expectedResult : Lemma.Core0.Ty) : CommandElabM RootSpec := do
  let program ← match Lemma.Core0.checkAndLower env name with
    | .ok program => pure program
    | .error diagnostic =>
        throwErrorAt location
          m!"exhaustive checked-model lowering failed for {label}: {diagnostic.render}"
  let some root := program.findFunction? name
    | throwErrorAt location
        m!"exhaustive checked-model program omitted root `{name}`"
  let expectedArgs : Array Lemma.Core0.Ty := #[.u8, .u8]
  unless root.signature.args == expectedArgs &&
      root.signature.result == expectedResult do
    throwErrorAt location
      m!"exhaustive checked-model root {label} has signature " ++
        m!"{root.signature.args.map Lemma.Core0.Ty.render} -> " ++
        m!"{root.signature.result.render}; expected #[u8, u8] -> " ++
        m!"{expectedResult.render}"
  pure { label, location, name, expectedResult, program }

private def transportResult (spec : RootSpec) (x y : Nat)
    (result : Lemma.Core0.Value) : CommandElabM UInt8 := do
  unless result.type == spec.expectedResult do
    throwErrorAt spec.location
      m!"exhaustive checked-model result type mismatch for {spec.label} " ++
        m!"at x={x}, y={y}: expected {spec.expectedResult.render}, " ++
        m!"got {result.type.render}"
  match result with
  | .bool value => pure value.toUInt8
  | .scalar scalar =>
      unless scalar.ty == .u8 && scalar.value < 256 do
        throwErrorAt spec.location
          m!"exhaustive checked-model produced a noncanonical UInt8 for " ++
            m!"{spec.label} at x={x}, y={y}: " ++
            m!"type={scalar.ty.render}, value={scalar.value}"
      pure scalar.value.toUInt8

private def evaluateRoot (spec : RootSpec) : CommandElabM ByteArray := do
  let mut output := ByteArray.empty
  for x in [:256] do
    for y in [:256] do
      let arguments : Array Lemma.Core0.Value := #[
        .scalar (.u8 x),
        .scalar (.u8 y)
      ]
      let result ← match Lemma.Core0.evalProgram spec.program arguments with
        | .ok result => pure result
        | .error diagnostic =>
            throwErrorAt spec.location
              m!"exhaustive checked-model evaluation failed for {spec.label} " ++
                m!"at x={x}, y={y}: {diagnostic.render}"
      output := output.push (← transportResult spec x y result)
  unless output.size == 65536 do
    throwErrorAt spec.location
      m!"exhaustive checked-model produced {output.size} results for " ++
        m!"{spec.label}, expected 65536"
  pure output

/-!
Write the five closed primitive result matrices in this exact order:
`u8Add`, `u8Sub`, `u8Lt`, `u8Le`, `u8Eq`.  Within each matrix, `x` is the
outer index and `y` the inner index, both spanning `0..255`.
-/
syntax (name := core0ExhaustiveU8Model)
  "#core0_exhaustive_u8_model " str ident ident ident ident ident : command

elab_rules : command
  | `(#core0_exhaustive_u8_model $output:str $add:ident $sub:ident
      $lt:ident $le:ident $eq:ident) => do
      let some outputText := output.raw.isStrLit?
        | throwErrorAt output "exhaustive checked-model output must be a string literal"
      if outputText.isEmpty then
        throwErrorAt output "exhaustive checked-model output path must not be empty"
      let env ← getEnv
      let addName ← resolveGlobalConstNoOverload add
      let subName ← resolveGlobalConstNoOverload sub
      let ltName ← resolveGlobalConstNoOverload lt
      let leName ← resolveGlobalConstNoOverload le
      let eqName ← resolveGlobalConstNoOverload eq
      let addSpec ← checkedRoot env "u8Add" add addName .u8
      let subSpec ← checkedRoot env "u8Sub" sub subName .u8
      let ltSpec ← checkedRoot env "u8Lt" lt ltName .bool
      let leSpec ← checkedRoot env "u8Le" le leName .bool
      let eqSpec ← checkedRoot env "u8Eq" eq eqName .bool
      let specs : Array RootSpec := #[addSpec, subSpec, ltSpec, leSpec, eqSpec]
      let mut outputBytes := ByteArray.empty
      for spec in specs do
        outputBytes := outputBytes ++ (← evaluateRoot spec)
      unless outputBytes.size == 327680 do
        throwErrorAt output
          m!"exhaustive checked-model produced {outputBytes.size} total results, " ++
            m!"expected 327680"
      liftIO <| IO.FS.writeBinFile outputText outputBytes
      logInfoAt output m!"CORE0_U8_EXHAUSTIVE_MODEL:5:327680"

end Lemma.Compiler.Test.ExhaustiveU8
