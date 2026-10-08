import Lean
import Lemma.Compiler.Format
import Lemma.Core0.Frontend
import Lemma.Core0.Semantics

/-! Typed checked-model entry point fixed to `core0-v0.3`. -/

namespace Lemma.Compiler.Test.BoundedEval

open Lean Elab Command

private def parseDecimal (stx : Syntax) (what : String) : CommandElabM Nat := do
  let some text := stx.isStrLit?
    | throwErrorAt stx s!"{what} must be a string literal"
  let some value := text.toNat?
    | throwErrorAt stx s!"{what} is not a decimal natural number"
  pure value

private def valueFor (stx : Syntax) (ty : Lemma.Core0.Ty) : CommandElabM Lemma.Core0.Value := do
  let value ← parseDecimal stx s!"typed {ty.render} argument"
  match ty with
  | .bool =>
      if value == 0 then pure (.bool false)
      else if value == 1 then pure (.bool true)
      else throwErrorAt stx "typed Bool argument must be exactly 0 or 1"
  | .u8 =>
      unless value < 2 ^ 8 do throwErrorAt stx "typed UInt8 argument is outside 0..255"
      pure (.scalar (.u8 value))
  | .u32 =>
      unless value < 2 ^ 32 do
        throwErrorAt stx "typed UInt32 argument is outside 0..4294967295"
      pure (.scalar (.u32 value))
  | .u64 =>
      unless value < 2 ^ 64 do throwErrorAt stx "typed UInt64 argument exceeds 64 bits"
      pure (.scalar (.u64 value))

private def transportValue : Lemma.Core0.Value → Nat
  | .bool false => 0
  | .bool true => 1
  | .scalar scalar => scalar.value

private def typeTag : Lemma.Core0.Value → String
  | .bool _ => "bool"
  | .scalar scalar => scalar.ty.render

syntax (name := core0EvalTypedV03) "#core0_eval_typed_v03 " ident str str* : command

elab_rules : command
  | `(#core0_eval_typed_v03 $decl:ident $caseId:str $args:str*) => do
      let name ← resolveGlobalConstNoOverload decl
      let env ← getEnv
      let program ← match Lemma.Core0.checkAndLowerForProfile env .v0_3 name with
        | .ok program => pure program
        | .error diagnostic => throwErrorAt decl diagnostic.render
      unless program.contractVersion == Lemma.Core0.Profile.v0_3.contractVersion do
        throwErrorAt decl "v0.3 evaluator received a mismatched checked profile"
      let some root := program.findFunction? name
        | throwErrorAt decl "checked Core0 program does not contain its typed root"
      unless args.size == root.signature.args.size do
        throwErrorAt decl
          s!"typed evaluator expected {root.signature.args.size} arguments, got {args.size}"
      let id ← parseDecimal caseId "typed evaluator case ID"
      unless id < 2 ^ 64 do throwErrorAt caseId "typed evaluator case ID exceeds 64 bits"
      let mut values : Array Lemma.Core0.Value := #[]
      for h : index in [:args.size] do
        values := values.push (← valueFor args[index] root.signature.args[index]!)
      match Lemma.Core0.evalProgram program values with
      | .error diagnostic => throwErrorAt decl diagnostic.render
      | .ok result =>
          unless result.type == root.signature.result do
            throwErrorAt decl "checked Core0 model returned the wrong typed result"
          logInfoAt decl m!"CORE0_TYPED_REFERENCE:{Format.hexFixed 16 id}:{typeTag result}:{Format.hexFixed 16 (transportValue result)}"

end Lemma.Compiler.Test.BoundedEval
