import Lemma.Core0.Bounded
import Lemma.Core0.IR

/-!
Independent executable semantics for checked Core0.

The model evaluates the typed Core0 tree directly with mathematical `Nat` values
reduced modulo 2^width.  It does not invoke the source Lean declaration and does not
share code with the LLVM lowering.  Finite differential tests are evidence, not a
compiler-correctness proof.
-/

namespace Lemma.Core0

open Lean

structure Scalar where
  ty : Ty
  value : Nat
  deriving BEq, Inhabited, Repr

namespace Scalar

def modulus (ty : Ty) : Nat :=
  2 ^ ty.width

def normalize (ty : Ty) (value : Nat) : Nat :=
  value % modulus ty

def make (ty : Ty) (value : Nat) : Option Scalar :=
  if ty.isInteger then some { ty, value := normalize ty value } else none

def u8 (value : Nat) : Scalar := { ty := .u8, value := normalize .u8 value }

def u32 (value : Nat) : Scalar := { ty := .u32, value := normalize .u32 value }

def u64 (value : Nat) : Scalar := { ty := .u64, value := normalize .u64 value }

end Scalar

inductive Value where
  | bool (value : Bool)
  | scalar (value : Scalar)
  deriving BEq, Inhabited, Repr

def Value.type : Value → Ty
  | .bool _ => .bool
  | .scalar value => value.ty

inductive EvalDiagnosticCode where
  | unknownFunction
  | arityMismatch
  | typeMismatch
  | invalidCheckedIR
  | fuelExhausted
  deriving BEq, DecidableEq, Inhabited, Repr

namespace EvalDiagnosticCode

def render : EvalDiagnosticCode → String
  | .unknownFunction => "unknown-function"
  | .arityMismatch => "arity-mismatch"
  | .typeMismatch => "type-mismatch"
  | .invalidCheckedIR => "invalid-checked-ir"
  | .fuelExhausted => "fuel-exhausted"

end EvalDiagnosticCode

structure EvalDiagnostic where
  code : EvalDiagnosticCode
  message : String
  callStack : List Name
  deriving Inhabited, Repr

def EvalDiagnostic.render (diag : EvalDiagnostic) : String :=
  let stack := String.intercalate " -> " (diag.callStack.reverse.map Name.toString)
  s!"Core0 reference[{diag.code.render}]: {diag.message}\n  call stack: {stack}"

private abbrev Locals := List (Nat × Value)

private def lookupLocal? (locals : Locals) (id : Nat) : Option Value :=
  (locals.find? (fun entry => entry.1 == id)).map (·.2)

private def evalFail (stack : List Name) (code : EvalDiagnosticCode)
    (message : String) : Except EvalDiagnostic α :=
  throw { code, message, callStack := stack }

private def expectType (stack : List Name) (expected : Ty) (value : Value) :
    Except EvalDiagnostic Unit := do
  unless value.type == expected do
    evalFail stack .typeMismatch s!"expected {expected.render}, got {value.type.render}"

private def expectScalar (stack : List Name) (expected : Ty) (value : Value) :
    Except EvalDiagnostic Scalar := do
  expectType stack expected value
  match value with
  | .scalar scalar => pure scalar
  | .bool _ => evalFail stack .invalidCheckedIR "integer operation received Bool"

private def expectBool (stack : List Name) (value : Value) :
    Except EvalDiagnostic Bool := do
  expectType stack .bool value
  match value with
  | .bool boolean => pure boolean
  | .scalar _ => evalFail stack .invalidCheckedIR "condition received an integer"

private def evalBin (stack : List Name) (op : BinOp) (ty : Ty)
    (lhs rhs : Value) : Except EvalDiagnostic Value := do
  unless ty.isInteger do
    evalFail stack .invalidCheckedIR s!"{op.render} cannot operate on Bool"
  let lhs ← expectScalar stack ty lhs
  let rhs ← expectScalar stack ty rhs
  let modulus := Scalar.modulus ty
  let result := match op with
    | .add => lhs.value + rhs.value
    | .sub => lhs.value + modulus - rhs.value
    | .mul => lhs.value * rhs.value
    | .band => Nat.land lhs.value rhs.value
    | .bor => Nat.lor lhs.value rhs.value
    | .bxor => Nat.xor lhs.value rhs.value
    | .shl => lhs.value * 2 ^ (rhs.value % ty.width)
    | .lshr => lhs.value / 2 ^ (rhs.value % ty.width)
    | .udiv => if rhs.value == 0 then 0 else lhs.value / rhs.value
    | .urem => if rhs.value == 0 then lhs.value else lhs.value % rhs.value
  pure (.scalar { ty, value := result % modulus })

private def evalUnary (stack : List Name) (op : UnaryOp) (ty : Ty)
    (value : Value) : Except EvalDiagnostic Value := do
  unless ty.isInteger do
    evalFail stack .invalidCheckedIR s!"{op.render} cannot operate on Bool"
  let value ← expectScalar stack ty value
  let result := match op with
    | .complement => Nat.xor value.value (Scalar.modulus ty - 1)
  pure (.scalar { ty, value := Scalar.normalize ty result })

private def isV02OnlyBin : BinOp → Bool
  | .shl | .lshr | .udiv | .urem => true
  | _ => false

private def evalCmp (stack : List Name) (op : CmpOp) (ty : Ty)
    (lhs rhs : Value) : Except EvalDiagnostic Value := do
  expectType stack ty lhs
  expectType stack ty rhs
  let result ← match op, lhs, rhs with
    | .eq, .bool a, .bool b => pure (a == b)
    | .eq, .scalar a, .scalar b => pure (a.value == b.value)
    | .ult, .scalar a, .scalar b => pure (a.value < b.value)
    | .ule, .scalar a, .scalar b => pure (a.value ≤ b.value)
    | _, _, _ => evalFail stack .invalidCheckedIR s!"{op.render} is invalid for {ty.render}"
  pure (.bool result)

mutual

  private def evalExpr (fuel : Nat) (program : Program) (stack : List Name)
      (locals : Locals) (expr : Expr) : Except EvalDiagnostic Value := do
    let fuel + 1 := fuel
      | evalFail stack .fuelExhausted "expression/call limit exhausted"
    match expr with
    | .var id ty =>
        let some value := lookupLocal? locals id
          | evalFail stack .invalidCheckedIR s!"unknown local %{id}"
        expectType stack ty value
        pure value
    | .lit ty value =>
        unless ty.isInteger do
          evalFail stack .invalidCheckedIR "integer literal was tagged Bool"
        pure (.scalar { ty, value := Scalar.normalize ty value })
    | .boolLit value => pure (.bool value)
    | .letE id _ ty value body =>
        let value ← evalExpr fuel program stack locals value
        expectType stack ty value
        evalExpr fuel program stack ((id, value) :: locals) body
    | .bin op ty lhs rhs =>
        if program.contractVersion == Profile.v0_1.contractVersion && isV02OnlyBin op then
          evalFail stack .invalidCheckedIR
            s!"{op.render} is not available in {Profile.v0_1.contractVersion}"
        let lhs ← evalExpr fuel program stack locals lhs
        let rhs ← evalExpr fuel program stack locals rhs
        evalBin stack op ty lhs rhs
    | .unary op ty value =>
        if program.contractVersion == Profile.v0_1.contractVersion then
          evalFail stack .invalidCheckedIR
            s!"{op.render} is not available in {Profile.v0_1.contractVersion}"
        let value ← evalExpr fuel program stack locals value
        evalUnary stack op ty value
    | .cmp op ty lhs rhs =>
        let lhs ← evalExpr fuel program stack locals lhs
        let rhs ← evalExpr fuel program stack locals rhs
        evalCmp stack op ty lhs rhs
    | .ite resultTy condition thenBranch elseBranch =>
        let condition ← evalExpr fuel program stack locals condition >>= expectBool stack
        let value ← if condition then
          evalExpr fuel program stack locals thenBranch
        else
          evalExpr fuel program stack locals elseBranch
        expectType stack resultTy value
        pure value
    | .call callee resultTy args =>
        let mut values : Array Value := #[]
        for arg in args do
          values := values.push (← evalExpr fuel program stack locals arg)
        let result ← evalFunction fuel program stack callee values
        expectType stack resultTy result
        pure result
    | .cast op sourceTy targetTy value =>
        unless sourceTy.isInteger && targetTy.isInteger do
          evalFail stack .invalidCheckedIR "conversion involved Bool"
        let value ← evalExpr fuel program stack locals value
        let source ← expectScalar stack sourceTy value
        unless (op == .zext && sourceTy.width < targetTy.width) ||
            (op == .trunc && targetTy.width < sourceTy.width) do
          evalFail stack .invalidCheckedIR "conversion direction disagrees with its type widths"
        pure (.scalar { ty := targetTy, value := Scalar.normalize targetTy source.value })
    | .boundedFoldU32 budget callback count initial =>
        unless program.contractVersion == Profile.v0_3.contractVersion ||
            program.contractVersion == Profile.v0_4.contractVersion ||
            program.contractVersion == Profile.v0_5.contractVersion ||
            program.contractVersion == Profile.v0_6.contractVersion ||
            program.contractVersion == Profile.v0_7.contractVersion ||
            program.contractVersion == Profile.firmware_v0_1.contractVersion ||
            program.contractVersion == Profile.firmware_v0_2.contractVersion ||
            program.contractVersion == Profile.counter_su_v0_1.contractVersion ||
            program.contractVersion == Profile.kernel_v0_1.contractVersion ||
            program.contractVersion == Profile.kernel_v0_2.contractVersion ||
            program.contractVersion == Profile.kernel_v0_3.contractVersion ||
            program.contractVersion == Profile.kernel_v0_4.contractVersion ||
            program.contractVersion == Profile.kernel_v0_5.contractVersion ||
            program.contractVersion == Profile.kernel_v0_6.contractVersion ||
            program.contractVersion == Profile.kernel_v0_7.contractVersion ||
            program.contractVersion == Profile.kernel_v0_8.contractVersion ||
            program.contractVersion == Profile.kernel_v0_9.contractVersion ||
            program.contractVersion == Profile.user_v0_1.contractVersion ||
            program.contractVersion == Profile.user_v0_2.contractVersion ||
            program.contractVersion == Profile.user_v0_3.contractVersion ||
            program.contractVersion == Profile.user_v0_4.contractVersion ||
            program.contractVersion == Profile.user_v0_5.contractVersion ||
            program.contractVersion == Profile.user_v0_6.contractVersion ||
            program.contractVersion == Profile.user_v0_7.contractVersion ||
            program.contractVersion == Profile.boot_v0_1.contractVersion ||
            program.contractVersion == Profile.boot_v0_2.contractVersion do
          evalFail stack .invalidCheckedIR
            s!"bounded iteration is not available in {program.contractVersion}"
        unless budget ≤ Lemma.Core0.Bounded.maximumBudget do
          evalFail stack .invalidCheckedIR
            s!"bounded-fold budget {budget} exceeds maximum {Lemma.Core0.Bounded.maximumBudget}"
        let site : IterationUse := {
          stableId := boundedFoldU32StableId
          budget
          callback
        }
        unless program.usedIterations.contains site do
          evalFail stack .invalidCheckedIR
            "bounded-fold expression is missing its checked iteration metadata"
        let some ownerName := stack.head?
          | evalFail stack .invalidCheckedIR
              "bounded-fold expression has no owning checked function"
        let some ownerFunction := program.findFunction? ownerName
          | evalFail stack .invalidCheckedIR
              s!"bounded-fold owner `{ownerName}` is absent"
        unless ownerFunction.dependencies.contains callback do
          evalFail stack .invalidCheckedIR
            s!"bounded-fold callback `{callback}` is missing from its owner's dependency closure"
        let countRaw ← evalExpr fuel program stack locals count
        let countValue ← expectScalar stack .u32 countRaw
        let initialRaw ← evalExpr fuel program stack locals initial
        let initialValue ← expectScalar stack .u32 initialRaw
        let some callbackFunction := program.findFunction? callback
          | evalFail stack .unknownFunction
              s!"checked bounded-fold callback `{callback}` is absent"
        let expectedCallback : Signature := { args := #[.u32, .u32], result := .u32 }
        unless callbackFunction.signature == expectedCallback do
          evalFail stack .invalidCheckedIR
            s!"bounded-fold callback `{callback}` does not have signature (u32,u32)->u32"
        if countValue.value ≤ budget then
          let mut accumulator := initialValue
          for index in [:countValue.value] do
            let result ← evalFunction fuel program stack callback
              #[.scalar (.u32 index), .scalar accumulator]
            accumulator ← expectScalar stack .u32 result
          pure (.scalar (.u64 accumulator.value))
        else
          let tagged := Nat.lor Lemma.Core0.Bounded.exhaustionTag.toNat initialValue.value
          pure (.scalar (.u64 tagged))

  private def evalFunction (fuel : Nat) (program : Program) (stack : List Name)
      (name : Name) (args : Array Value) : Except EvalDiagnostic Value := do
    let fuel + 1 := fuel
      | evalFail (name :: stack) .fuelExhausted "function-call limit exhausted"
    let some function := program.findFunction? name
      | evalFail (name :: stack) .unknownFunction s!"checked program has no function `{name}`"
    unless args.size == function.params.size do
      evalFail (name :: stack) .arityMismatch
        s!"`{name}` expected {function.params.size} arguments, got {args.size}"
    let mut locals : Locals := []
    for h : index in [:args.size] do
      let param := function.params[index]!
      let value := match args[index] with
        | .bool boolean => Value.bool boolean
        | .scalar scalar => Value.scalar {
            scalar with value := Scalar.normalize scalar.ty scalar.value
          }
      expectType (name :: stack) param.ty value
      locals := (param.id, value) :: locals
    let result ← evalExpr fuel program (name :: stack) locals function.body
    expectType (name :: stack) function.signature.result result
    pure result

end

/-- Evaluate a checked root with Bool/integer values. -/
def evalProgram (program : Program) (args : Array Value) : Except EvalDiagnostic Value :=
  match Profile.ofContractVersion? program.contractVersion with
  | none => .error {
      code := .invalidCheckedIR
      message := s!"unsupported Core0 contract `{program.contractVersion}`"
      callStack := [program.root]
    }
  | some _ => evalFunction 65536 program [] program.root args

/-- Scalar-only convenience entry point used by the differential target harness. -/
def evalProgramScalars (program : Program) (args : Array Scalar) :
    Except EvalDiagnostic Scalar :=
  let values := args.map Value.scalar
  match evalProgram program values with
  | .error diag => .error diag
  | .ok (.scalar scalar) => .ok scalar
  | .ok (.bool _) => .error {
      code := .typeMismatch
      message := "scalar evaluator entry point was used with a Bool-returning root"
      callStack := [program.root]
    }

end Lemma.Core0
