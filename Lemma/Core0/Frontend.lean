import Lean
import Lean.Compiler.ExternAttr
import Lean.Compiler.ImplementedByAttr
import Lean.Compiler.InitAttr
import Lemma.Core0.IR

/-!
Genuine Lean-environment frontend for Core0 v0.1.

The checker reads `ConstantInfo` types and bodies installed by Lean's elaborator.  It
does not accept a surface-syntax AST or a separately constructed demonstration tree.
Every atomic operation is selected by exact declaration identity, scalar type, and
(for notation) the exact standard typeclass instance expression.
-/

namespace Lemma.Core0

open Lean

inductive DiagnosticCode where
  | unknownDeclaration
  | unsupportedDeclaration
  | unsafeDeclaration
  | polymorphicDeclaration
  | unsupportedType
  | unsupportedBinder
  | unsupportedExpression
  | unsupportedPrimitive
  | invalidPrimitiveInstance
  | arityMismatch
  | typeMismatch
  | recursiveDependency
  | invalidSuite
  | internal
  deriving BEq, DecidableEq, Inhabited, Repr

namespace DiagnosticCode

def render : DiagnosticCode → String
  | .unknownDeclaration => "unknown-declaration"
  | .unsupportedDeclaration => "unsupported-declaration"
  | .unsafeDeclaration => "unsafe-declaration"
  | .polymorphicDeclaration => "polymorphic-declaration"
  | .unsupportedType => "unsupported-type"
  | .unsupportedBinder => "unsupported-binder"
  | .unsupportedExpression => "unsupported-expression"
  | .unsupportedPrimitive => "unsupported-primitive"
  | .invalidPrimitiveInstance => "invalid-primitive-instance"
  | .arityMismatch => "arity-mismatch"
  | .typeMismatch => "type-mismatch"
  | .recursiveDependency => "recursive-dependency"
  | .invalidSuite => "invalid-suite"
  | .internal => "internal"

end DiagnosticCode

structure Diagnostic where
  code : DiagnosticCode
  root : Name
  declaration : Name
  /-- Root-to-failure declaration path, including an operation name when useful. -/
  path : List Name
  message : String
  /-- Best-effort declaration range from Lean's elaboration environment. -/
  position? : Option String := none
  deriving Inhabited, Repr

def Diagnostic.render (diag : Diagnostic) : String :=
  let path := String.intercalate " -> " (diag.path.map Name.toString)
  let pos := diag.position?.map (fun p => s!" at {diag.declaration}:{p}") |>.getD ""
  s!"Core0[{diag.code.render}]{pos}: {diag.message}\n  dependency path: {path}"

private def typeExpr? : Lean.Expr → Option Ty
  | .mdata _ e => typeExpr? e
  | .const n _ =>
      if n == ``Bool then some .bool
      else if n == ``UInt8 then some .u8
      else if n == ``UInt32 then some .u32
      else if n == ``UInt64 then some .u64
      else none
  | _ => none

private def directBinName (ty : Ty) (op : BinOp) : Name :=
  match ty, op with
  | .u8, .add => ``UInt8.add
  | .u8, .sub => ``UInt8.sub
  | .u8, .mul => ``UInt8.mul
  | .u8, .band => ``UInt8.land
  | .u8, .bor => ``UInt8.lor
  | .u8, .bxor => ``UInt8.xor
  | .u32, .add => ``UInt32.add
  | .u32, .sub => ``UInt32.sub
  | .u32, .mul => ``UInt32.mul
  | .u32, .band => ``UInt32.land
  | .u32, .bor => ``UInt32.lor
  | .u32, .bxor => ``UInt32.xor
  | .u64, .add => ``UInt64.add
  | .u64, .sub => ``UInt64.sub
  | .u64, .mul => ``UInt64.mul
  | .u64, .band => ``UInt64.land
  | .u64, .bor => ``UInt64.lor
  | .u64, .bxor => ``UInt64.xor
  | .bool, _ => .anonymous

private def directCmpName (ty : Ty) (op : CmpOp) : Name :=
  match ty, op with
  | _, .eq => ``Eq
  | .u8, .ult => ``UInt8.lt
  | .u8, .ule => ``UInt8.le
  | .u32, .ult => ``UInt32.lt
  | .u32, .ule => ``UInt32.le
  | .u64, .ult => ``UInt64.lt
  | .u64, .ule => ``UInt64.le
  | .bool, _ => .anonymous

private def castName (source target : Ty) : Name :=
  match source, target with
  | .u8, .u32 => ``UInt8.toUInt32
  | .u8, .u64 => ``UInt8.toUInt64
  | .u32, .u8 => ``UInt32.toUInt8
  | .u32, .u64 => ``UInt32.toUInt64
  | .u64, .u8 => ``UInt64.toUInt8
  | .u64, .u32 => ``UInt64.toUInt32
  | _, _ => .anonymous

private def singletonSig (input output : Ty) : Signature :=
  { args := #[input], result := output }

private def binarySig (input output : Ty) : Signature :=
  { args := #[input, input], result := output }

/-- The atomic target operations in Core0 v0.1, with exact Lean identities/signatures. -/
def primitiveAllowlist : Array PrimitiveSpec := Id.run do
  let mut specs := #[]
  for ty in #[Ty.u8, Ty.u32, Ty.u64] do
    for op in #[BinOp.add, .sub, .mul, .band, .bor, .bxor] do
      specs := specs.push {
        stableId := s!"{ty.render}.{op.render}"
        leanDecl := directBinName ty op
        signature := binarySig ty ty
      }
    for op in #[CmpOp.ult, .ule] do
      specs := specs.push {
        stableId := s!"{ty.render}.{op.render}"
        leanDecl := directCmpName ty op
        signature := binarySig ty .bool
      }
    specs := specs.push {
      stableId := s!"{ty.render}.eq"
      leanDecl := ``Eq
      signature := binarySig ty .bool
    }
  specs := specs.push {
    stableId := "bool.eq", leanDecl := ``Eq, signature := binarySig .bool .bool
  }
  for pair in #[(Ty.u8, Ty.u32), (.u8, .u64), (.u32, .u8), (.u32, .u64), (.u64, .u8), (.u64, .u32)] do
    let (source, target) := pair
    let op := if source.width < target.width then "zext" else "trunc"
    specs := specs.push {
      stableId := s!"{source.render}.to-{target.render}.{op}"
      leanDecl := castName source target
      signature := singletonSig source target
    }
  return specs

private def stripMData : Lean.Expr → Lean.Expr
  | .mdata _ e => stripMData e
  | e => e

private def constName? (e : Lean.Expr) : Option Name :=
  match stripMData e with
  | .const name _ => some name
  | _ => none

private def appView? (e : Lean.Expr) : Option (Name × Array Lean.Expr) :=
  let e := stripMData e
  match e.getAppFn with
  | .const name _ => some (name, e.getAppArgs)
  | _ => none

private def sameExpr (a b : Lean.Expr) : Bool :=
  stripMData a == stripMData b

private def sourcePosition? (env : Environment) (decl : Name) : Option String :=
  let ranges? :=
    declRangeExt.find? (level := .server) env decl <|>
      declRangeExt.find? (level := .exported) env decl
  ranges?.map fun ranges =>
    let p := ranges.selectionRange.pos
    s!"{p.line}:{p.column}"

private structure LowerContext where
  env : Environment
  root : Name
  declaration : Name
  path : List Name
  locals : Array Param

private structure LowerState where
  nextVar : Nat
  dependencies : Array Name := #[]
  usedPrimitives : Array String := #[]

private abbrev LowerM := StateT LowerState (Except Diagnostic)

private def mkDiagnostic (ctx : LowerContext) (code : DiagnosticCode)
    (message : String) (path := ctx.path) : Diagnostic :=
  {
    code
    root := ctx.root
    declaration := ctx.declaration
    path
    message
    position? := sourcePosition? ctx.env ctx.declaration
  }

private def fail (ctx : LowerContext) (code : DiagnosticCode) (message : String)
    (path := ctx.path) : LowerM α :=
  throw (mkDiagnostic ctx code message path)

private def markPrimitive (stableId : String) : LowerM Unit := do
  let state ← get
  unless state.usedPrimitives.contains stableId do
    set { state with usedPrimitives := state.usedPrimitives.push stableId }

private def addDependency (name : Name) : LowerM Unit := do
  let state ← get
  unless state.dependencies.contains name do
    set { state with dependencies := state.dependencies.push name }

private def localForBVar? (locals : Array Param) (index : Nat) : Option Param :=
  if index < locals.size then
    locals[locals.size - 1 - index]?
  else
    none

private def ensureType (ctx : LowerContext) (expected : Ty) (actual : Expr) : LowerM Unit :=
  unless actual.type == expected do
    fail ctx .typeMismatch s!"expected {expected.render}, got {actual.type.render}"

private def expectedArithmeticInstance (ty : Ty) (op : BinOp) : Option (Name × Name) :=
  match op, ty with
  | .add, .u8 => some (``instHAdd, ``instAddUInt8)
  | .add, .u32 => some (``instHAdd, ``instAddUInt32)
  | .add, .u64 => some (``instHAdd, ``instAddUInt64)
  | .sub, .u8 => some (``instHSub, ``instSubUInt8)
  | .sub, .u32 => some (``instHSub, ``instSubUInt32)
  | .sub, .u64 => some (``instHSub, ``instSubUInt64)
  | .mul, .u8 => some (``instHMul, ``instMulUInt8)
  | .mul, .u32 => some (``instHMul, ``instMulUInt32)
  | .mul, .u64 => some (``instHMul, ``instMulUInt64)
  | .band, .u8 => some (``instHAndOfAndOp, ``instAndOpUInt8)
  | .band, .u32 => some (``instHAndOfAndOp, ``instAndOpUInt32)
  | .band, .u64 => some (``instHAndOfAndOp, ``instAndOpUInt64)
  | .bor, .u8 => some (``instHOrOfOrOp, ``instOrOpUInt8)
  | .bor, .u32 => some (``instHOrOfOrOp, ``instOrOpUInt32)
  | .bor, .u64 => some (``instHOrOfOrOp, ``instOrOpUInt64)
  | .bxor, .u8 => some (``instHXorOfXorOp, ``instXorOpUInt8)
  | .bxor, .u32 => some (``instHXorOfXorOp, ``instXorOpUInt32)
  | .bxor, .u64 => some (``instHXorOfXorOp, ``instXorOpUInt64)
  | _, .bool => none

private def wrapperBinOp? (name : Name) : Option BinOp :=
  if name == ``HAdd.hAdd then some .add
  else if name == ``HSub.hSub then some .sub
  else if name == ``HMul.hMul then some .mul
  else if name == ``HAnd.hAnd then some .band
  else if name == ``HOr.hOr then some .bor
  else if name == ``HXor.hXor then some .bxor
  else none

private def directBinOp? (name : Name) : Option (Ty × BinOp) := Id.run do
  for ty in #[Ty.u8, Ty.u32, Ty.u64] do
    for op in #[BinOp.add, .sub, .mul, .band, .bor, .bxor] do
      if name == directBinName ty op then return some (ty, op)
  return none

private def checkArithmeticInstance (ctx : LowerContext) (ty : Ty) (op : BinOp)
    (instanceExpr : Lean.Expr) : LowerM Unit := do
  let some (outerName, operationName) := expectedArithmeticInstance ty op
    | fail ctx .invalidPrimitiveInstance s!"no {op.render} instance is allowed for {ty.render}"
  let some (actualOuter, args) := appView? instanceExpr
    | fail ctx .invalidPrimitiveInstance s!"{ty.render}.{op.render} did not use the standard instance"
  unless actualOuter == outerName && args.size == 2 do
    fail ctx .invalidPrimitiveInstance s!"{ty.render}.{op.render} used a non-allowlisted instance"
  unless typeExpr? args[0]! == some ty && constName? args[1]! == some operationName do
    fail ctx .invalidPrimitiveInstance s!"{ty.render}.{op.render} used a non-allowlisted operation dictionary"

private def ofNatInstanceName : Ty → Name
  | .u8 => ``UInt8.instOfNat
  | .u32 => ``UInt32.instOfNat
  | .u64 => ``UInt64.instOfNat
  | .bool => .anonymous

private def ltInstanceName : Ty → Name
  | .u8 => ``instLTUInt8
  | .u32 => ``instLTUInt32
  | .u64 => ``instLTUInt64
  | .bool => .anonymous

private def leInstanceName : Ty → Name
  | .u8 => ``instLEUInt8
  | .u32 => ``instLEUInt32
  | .u64 => ``instLEUInt64
  | .bool => .anonymous

private def decLtName : Ty → Name
  | .u8 => ``UInt8.decLt
  | .u32 => ``UInt32.decLt
  | .u64 => ``UInt64.decLt
  | .bool => .anonymous

private def decLeName : Ty → Name
  | .u8 => ``UInt8.decLe
  | .u32 => ``UInt32.decLe
  | .u64 => ``UInt64.decLe
  | .bool => .anonymous

private def decEqName : Ty → Name
  | .bool => ``instDecidableEqBool
  | .u8 => ``instDecidableEqUInt8
  | .u32 => ``instDecidableEqUInt32
  | .u64 => ``instDecidableEqUInt64

private structure ExpectedDecider where
  name : Name
  lhs : Lean.Expr
  rhs : Lean.Expr

private def validateDecider (ctx : LowerContext) (expected : ExpectedDecider)
    (decider : Lean.Expr) : LowerM Unit := do
  let some (name, args) := appView? decider
    | fail ctx .invalidPrimitiveInstance "condition did not use a named standard Decidable instance"
  unless name == expected.name && args.size == 2 &&
      sameExpr args[0]! expected.lhs && sameExpr args[1]! expected.rhs do
    fail ctx .invalidPrimitiveInstance
      s!"condition used `{name}` instead of the exact allowlisted decider `{expected.name}`"

private def parseSignatureCore (ctx : LowerContext) (type : Lean.Expr) :
    Except Diagnostic (Signature × Array Name) := do
  let rec go (fuel : Nat) (type : Lean.Expr) (argTypes : Array Ty) (argNames : Array Name) := do
    let fuel + 1 := fuel
      | throw <| mkDiagnostic ctx .unsupportedType
          "function signature exceeds the Core0 limit of 1024 scalar parameters"
    match stripMData type with
    | .forallE name domain body binderInfo => do
        unless binderInfo == .default do
          throw <| mkDiagnostic ctx .unsupportedBinder
            s!"implicit, strict-implicit, and instance parameters are outside Core0 (`{name}`)"
        let some ty := typeExpr? domain
          | throw <| mkDiagnostic ctx .unsupportedType
              s!"parameter `{name}` is not Bool/UInt8/UInt32/UInt64"
        go fuel body (argTypes.push ty) (argNames.push name)
    | result => do
        let some resultTy := typeExpr? result
          | throw <| mkDiagnostic ctx .unsupportedType
              "function result is not Bool/UInt8/UInt32/UInt64"
        pure ({ args := argTypes, result := resultTy }, argNames)
  go 1024 type #[] #[]

private def declarationSignature (ctx : LowerContext) (name : Name) :
    Except Diagnostic Signature := do
  let some info := ctx.env.find? name
    | throw <| mkDiagnostic ctx .unknownDeclaration s!"declaration `{name}` is not in the Lean environment"
        (ctx.path ++ [name])
  let (sig, _) ← parseSignatureCore { ctx with declaration := name } info.type
  pure sig

mutual

  private def lowerExpr (fuel : Nat) (ctx : LowerContext) (source : Lean.Expr) : LowerM Expr := do
    let fuel + 1 := fuel
      | fail ctx .internal "Core0 expression traversal fuel exhausted"
    match source with
    | .mdata _ inner => lowerExpr fuel ctx inner
    | .bvar index =>
        let some binding := localForBVar? ctx.locals index
          | fail ctx .internal s!"unbound de Bruijn variable #{index}"
        pure (.var binding.id binding.ty)
    | .letE name type value body nondep =>
        unless nondep do
          fail ctx .unsupportedExpression s!"dependent let binding `{name}` is outside Core0"
        let ty ← match typeExpr? type with
          | some ty => pure ty
          | none =>
              match stripMData value with
              | .lam _ _ _ _ =>
                  fail ctx .unsupportedExpression s!"let binding `{name}` creates a nested/capturing closure"
              | _ => fail ctx .unsupportedType s!"let binding `{name}` has a non-scalar/boxed type"
        let loweredValue ← lowerExpr fuel ctx value
        ensureType ctx ty loweredValue
        let state ← get
        let id := state.nextVar
        set { state with nextVar := id + 1 }
        let binder : Param := { id, name, ty }
        let loweredBody ← lowerExpr fuel { ctx with locals := ctx.locals.push binder } body
        pure (.letE id name ty loweredValue loweredBody)
    | .lam .. =>
        fail ctx .unsupportedExpression
          "nested/capturing closures are outside Core0; use a top-level first-order function"
    | .forallE .. =>
        fail ctx .unsupportedExpression "runtime dependent functions/types are outside Core0"
    | .proj typeName index _ =>
        fail ctx .unsupportedExpression
          s!"projection {typeName}.#{index} requires a boxed/aggregate representation"
    | .fvar .. => fail ctx .internal "unexpected free variable in an environment declaration"
    | .mvar .. => fail ctx .internal "unexpected metavariable in an elaborated declaration"
    | .sort .. => fail ctx .unsupportedExpression "a universe/type was used as a runtime value"
    | .lit .. => fail ctx .unsupportedExpression "only typed UInt literals are admitted"
    | .const name _ =>
        if name == ``Bool.true then pure (.boolLit true)
        else if name == ``Bool.false then pure (.boolLit false)
        else lowerApp fuel ctx source
    | .app .. => lowerApp fuel ctx source

  private def lowerPredicate (fuel : Nat) (ctx : LowerContext) (source : Lean.Expr) :
      LowerM (Expr × ExpectedDecider) := do
    let fuel + 1 := fuel
      | fail ctx .internal "Core0 predicate traversal fuel exhausted"
    let some (name, args) := appView? source
      | fail ctx .unsupportedExpression "condition is not an allowlisted scalar comparison"
    if name == ``LT.lt then
      unless args.size == 4 do fail ctx .arityMismatch "malformed LT.lt application"
      let some ty := typeExpr? args[0]!
        | fail ctx .unsupportedType "LT operand type is not a Core0 scalar"
      unless ty.isInteger do fail ctx .unsupportedPrimitive "ordering Bool is outside Core0"
      unless constName? args[1]! == some (ltInstanceName ty) do
        fail ctx .invalidPrimitiveInstance s!"{ty.render}.ult used a non-allowlisted LT instance"
      let lhs ← lowerExpr fuel ctx args[2]!
      let rhs ← lowerExpr fuel ctx args[3]!
      ensureType ctx ty lhs
      ensureType ctx ty rhs
      markPrimitive s!"{ty.render}.ult"
      pure (.cmp .ult ty lhs rhs, { name := decLtName ty, lhs := args[2]!, rhs := args[3]! })
    else if name == ``LE.le then
      unless args.size == 4 do fail ctx .arityMismatch "malformed LE.le application"
      let some ty := typeExpr? args[0]!
        | fail ctx .unsupportedType "LE operand type is not a Core0 scalar"
      unless ty.isInteger do fail ctx .unsupportedPrimitive "ordering Bool is outside Core0"
      unless constName? args[1]! == some (leInstanceName ty) do
        fail ctx .invalidPrimitiveInstance s!"{ty.render}.ule used a non-allowlisted LE instance"
      let lhs ← lowerExpr fuel ctx args[2]!
      let rhs ← lowerExpr fuel ctx args[3]!
      ensureType ctx ty lhs
      ensureType ctx ty rhs
      markPrimitive s!"{ty.render}.ule"
      pure (.cmp .ule ty lhs rhs, { name := decLeName ty, lhs := args[2]!, rhs := args[3]! })
    else if name == ``Eq then
      unless args.size == 3 do fail ctx .arityMismatch "malformed Eq application"
      let some ty := typeExpr? args[0]!
        | fail ctx .unsupportedType "equality operand type is not a Core0 scalar"
      let lhs ← lowerExpr fuel ctx args[1]!
      let rhs ← lowerExpr fuel ctx args[2]!
      ensureType ctx ty lhs
      ensureType ctx ty rhs
      markPrimitive s!"{ty.render}.eq"
      pure (.cmp .eq ty lhs rhs, { name := decEqName ty, lhs := args[1]!, rhs := args[2]! })
    else
      let mut matched : Option (Ty × CmpOp) := none
      for ty in #[Ty.u8, Ty.u32, Ty.u64] do
        for op in #[CmpOp.ult, .ule] do
          if name == directCmpName ty op then matched := some (ty, op)
      let some (ty, op) := matched
        | fail ctx .unsupportedPrimitive s!"condition operation `{name}` is not allowlisted"
            (ctx.path ++ [name])
      unless args.size == 2 do fail ctx .arityMismatch s!"malformed comparison `{name}`"
      let lhs ← lowerExpr fuel ctx args[0]!
      let rhs ← lowerExpr fuel ctx args[1]!
      ensureType ctx ty lhs
      ensureType ctx ty rhs
      markPrimitive s!"{ty.render}.{op.render}"
      let decName := if op == .ult then decLtName ty else decLeName ty
      pure (.cmp op ty lhs rhs, { name := decName, lhs := args[0]!, rhs := args[1]! })

  private def lowerApp (fuel : Nat) (ctx : LowerContext) (source : Lean.Expr) : LowerM Expr := do
    let fuel + 1 := fuel
      | fail ctx .internal "Core0 application traversal fuel exhausted"
    let some (name, args) := appView? source
      | fail ctx .unsupportedExpression
          "dynamic/higher-order application is outside Core0 (possible capturing closure)"

    if name == ``ite then
      unless args.size == 5 do fail ctx .arityMismatch "malformed ite application"
      let some resultTy := typeExpr? args[0]!
        | fail ctx .unsupportedType "ite result is not a Core0 scalar"
      let (condition, decider) ← lowerPredicate fuel ctx args[1]!
      validateDecider ctx decider args[2]!
      let thenBranch ← lowerExpr fuel ctx args[3]!
      let elseBranch ← lowerExpr fuel ctx args[4]!
      ensureType ctx resultTy thenBranch
      ensureType ctx resultTy elseBranch
      pure (.ite resultTy condition thenBranch elseBranch)

    else if name == ``Decidable.decide then
      unless args.size == 2 do fail ctx .arityMismatch "malformed Decidable.decide application"
      let (condition, decider) ← lowerPredicate fuel ctx args[0]!
      validateDecider ctx decider args[1]!
      pure condition

    else if name == ``OfNat.ofNat then
      unless args.size == 3 do fail ctx .arityMismatch "malformed OfNat.ofNat application"
      let some ty := typeExpr? args[0]!
        | fail ctx .unsupportedType "numeric literal does not have a Core0 type"
      unless ty.isInteger do fail ctx .unsupportedType "Bool numeric literals are outside Core0"
      let value ← match stripMData args[1]! with
        | .lit (.natVal value) => pure value
        | _ => fail ctx .unsupportedExpression "Core0 numeric literal is not a kernel Nat literal"
      let some (instName, instArgs) := appView? args[2]!
        | fail ctx .invalidPrimitiveInstance s!"{ty.render} literal has an unknown OfNat instance"
      unless instName == ofNatInstanceName ty && instArgs.size == 1 && sameExpr instArgs[0]! args[1]! do
        fail ctx .invalidPrimitiveInstance s!"{ty.render} literal used a non-allowlisted OfNat instance"
      pure (.lit ty value)

    else if let some op := wrapperBinOp? name then
      unless args.size == 6 do fail ctx .arityMismatch s!"malformed `{name}` application"
      let some ty := typeExpr? args[0]!
        | fail ctx .unsupportedType s!"`{name}` operand is not a Core0 integer"
      unless ty.isInteger && typeExpr? args[1]! == some ty && typeExpr? args[2]! == some ty do
        fail ctx .typeMismatch s!"`{name}` is not homogeneous on an admitted integer type"
      checkArithmeticInstance ctx ty op args[3]!
      let lhs ← lowerExpr fuel ctx args[4]!
      let rhs ← lowerExpr fuel ctx args[5]!
      ensureType ctx ty lhs
      ensureType ctx ty rhs
      markPrimitive s!"{ty.render}.{op.render}"
      pure (.bin op ty lhs rhs)

    else if let some (ty, op) := directBinOp? name then
      unless args.size == 2 do fail ctx .arityMismatch s!"malformed `{name}` application"
      let lhs ← lowerExpr fuel ctx args[0]!
      let rhs ← lowerExpr fuel ctx args[1]!
      ensureType ctx ty lhs
      ensureType ctx ty rhs
      markPrimitive s!"{ty.render}.{op.render}"
      pure (.bin op ty lhs rhs)

    else
      let mut cast? : Option (Ty × Ty) := none
      for pair in #[(Ty.u8, Ty.u32), (.u8, .u64), (.u32, .u8), (.u32, .u64), (.u64, .u8), (.u64, .u32)] do
        if name == castName pair.1 pair.2 then cast? := some pair
      if let some (sourceTy, targetTy) := cast? then
        unless args.size == 1 do fail ctx .arityMismatch s!"malformed conversion `{name}`"
        let value ← lowerExpr fuel ctx args[0]!
        ensureType ctx sourceTy value
        let op := if sourceTy.width < targetTy.width then CastOp.zext else .trunc
        markPrimitive s!"{sourceTy.render}.to-{targetTy.render}.{op.render}"
        pure (.cast op sourceTy targetTy value)
      else
        lowerUserCall fuel ctx name args

  private def lowerUserCall (fuel : Nat) (ctx : LowerContext) (name : Name)
      (args : Array Lean.Expr) : LowerM Expr := do
    let fuel + 1 := fuel
      | fail ctx .internal "Core0 call traversal fuel exhausted"
    let forbidden :=
      name == ``HDiv.hDiv || name == ``HMod.hMod ||
      name == ``HShiftLeft.hShiftLeft || name == ``HShiftRight.hShiftRight ||
      name == ``Complement.complement || name == ``UInt8.complement ||
      name == ``UInt32.complement || name == ``UInt64.complement ||
      name == ``UInt8.div || name == ``UInt32.div || name == ``UInt64.div ||
      name == ``UInt8.mod || name == ``UInt32.mod || name == ``UInt64.mod ||
      name == ``UInt8.shiftLeft || name == ``UInt32.shiftLeft || name == ``UInt64.shiftLeft ||
      name == ``UInt8.shiftRight || name == ``UInt32.shiftRight || name == ``UInt64.shiftRight
    if forbidden then
      fail ctx .unsupportedPrimitive
        s!"division, remainder, shifts, and complement are deliberately unsupported (`{name}`)"
        (ctx.path ++ [name])
    let callCtx := { ctx with path := ctx.path ++ [name] }
    let sig ← match declarationSignature callCtx name with
      | .ok sig => pure sig
      | .error diag => throw diag
    unless args.size == sig.args.size do
      fail ctx .arityMismatch
        s!"call to `{name}` expected {sig.args.size} scalar arguments, got {args.size}"
        callCtx.path
    let mut loweredArgs : Array Expr := #[]
    for h : index in [:args.size] do
      let arg ← lowerExpr fuel ctx args[index]
      ensureType ctx sig.args[index]! arg
      loweredArgs := loweredArgs.push arg
    addDependency name
    pure (.call name sig.result loweredArgs.toList)

end

private def lowerFunction (env : Environment) (root : Name) (name : Name)
    (path : List Name) : Except Diagnostic (Function × Array String) := do
  let baseCtx : LowerContext := { env, root, declaration := name, path, locals := #[] }
  let some info := env.find? name
    | throw <| mkDiagnostic baseCtx .unknownDeclaration s!"declaration `{name}` is not in the Lean environment"
  if (getExternAttrData? env name).isSome then
    throw <| mkDiagnostic baseCtx .unsupportedDeclaration
      s!"declaration `{name}` has an arbitrary @[extern] implementation"
  if hasInitAttr env name || isIOUnitInitFn env name then
    throw <| mkDiagnostic baseCtx .unsupportedDeclaration
      s!"declaration `{name}` has a runtime initialization effect"
  if let some replacement := Compiler.getImplementedBy? env name then
    throw <| mkDiagnostic baseCtx .unsupportedDeclaration
      s!"declaration `{name}` has unchecked compiler replacement `{replacement}`"
  let value ← match info with
    | .defnInfo definition =>
        unless definition.levelParams.isEmpty do
          throw <| mkDiagnostic baseCtx .polymorphicDeclaration
            s!"`{name}` has universe parameters; Core0 is monomorphic"
        unless definition.safety == .safe do
          throw <| mkDiagnostic baseCtx .unsafeDeclaration
            s!"`{name}` is {repr definition.safety}; unsafe/partial declarations are outside Core0"
        pure definition.value
    | .opaqueInfo _ =>
        throw <| mkDiagnostic baseCtx .unsupportedDeclaration
          s!"opaque declaration `{name}` is not inspectable as Core0 target code (extern, initialize-generated, and partial definitions are rejected)"
    | .axiomInfo _ =>
        throw <| mkDiagnostic baseCtx .unsupportedDeclaration
          s!"axiom/extern declaration `{name}` has no accepted Core0 implementation"
    | .thmInfo _ =>
        throw <| mkDiagnostic baseCtx .unsupportedDeclaration
          s!"theorem `{name}` is proof data, not a Core0 runtime function"
    | _ =>
        throw <| mkDiagnostic baseCtx .unsupportedDeclaration
          s!"declaration kind for `{name}` is outside Core0"
  let (signature, typeNames) ← parseSignatureCore baseCtx info.type
  let mut body := stripMData value
  let mut params : Array Param := #[]
  for index in [:signature.args.size] do
    match stripMData body with
    | .lam valueName domain next binderInfo =>
        unless binderInfo == .default do
          throw <| mkDiagnostic baseCtx .unsupportedBinder
            s!"parameter #{index} of `{name}` is not an explicit binder"
        unless typeExpr? domain == some signature.args[index]! do
          throw <| mkDiagnostic baseCtx .typeMismatch
            s!"lambda binder #{index} of `{name}` differs from its declared signature"
        let typeName := typeNames[index]!
        let binderName := if valueName.isAnonymous then typeName else valueName
        params := params.push { id := index, name := binderName, ty := signature.args[index]! }
        body := next
    | _ =>
        throw <| mkDiagnostic baseCtx .arityMismatch
          s!"body of `{name}` has fewer lambdas than its signature"
  match stripMData body with
  | .lam .. =>
      throw <| mkDiagnostic baseCtx .unsupportedExpression
        s!"body of `{name}` returns a closure"
  | _ => pure ()
  let ctx := { baseCtx with locals := params }
  let initialState : LowerState := { nextVar := params.size }
  let (loweredBody, state) ← lowerExpr 65536 ctx body |>.run initialState
  unless loweredBody.type == signature.result do
    throw <| mkDiagnostic baseCtx .typeMismatch
      s!"body of `{name}` lowered to {loweredBody.type.render}, expected {signature.result.render}"
  pure ({ name, signature, params, body := loweredBody, dependencies := state.dependencies },
    state.usedPrimitives)

private inductive VisitTask where
  | enter (name : Name) (path : List Name)
  | exit (function : Function)

/--
Read a Lean-elaborated declaration and its transitive declaration bodies, reject all
operations outside Core0, and return dependency-first checked IR.
-/
def checkAndLower (env : Environment) (root : Name) : Except Diagnostic Program := do
  let mut stack : List VisitTask := [.enter root [root]]
  let mut visiting : List Name := []
  let mut done : List Name := []
  let mut functions : Array Function := #[]
  let mut usedPrimitives : Array String := #[]
  while !stack.isEmpty do
    match stack with
    | [] => pure ()
    | task :: rest =>
      stack := rest
      match task with
      | .enter name path =>
          if done.contains name then
            pure ()
          else if visiting.contains name then
            let ctx : LowerContext := { env, root, declaration := name, path, locals := #[] }
            throw <| mkDiagnostic ctx .recursiveDependency
              s!"recursive/cyclic dependency reaches `{name}`" path
          else
            let (function, used) ← lowerFunction env root name path
            visiting := name :: visiting
            for primitive in used do
              unless usedPrimitives.contains primitive do
                usedPrimitives := usedPrimitives.push primitive
            let exits := [.exit function]
            let entries := function.dependencies.toList.map fun dep =>
              .enter dep (path ++ [dep])
            stack := entries ++ exits ++ stack
      | .exit function =>
          visiting := visiting.filter (fun n => n != function.name)
          unless done.contains function.name do
            done := function.name :: done
            functions := functions.push function
  pure { root, functions, usedPrimitives }

/-- Check several genuine elaborated roots with the unchanged Core0 v0.1 frontend,
then form one deterministic, dependency-first corpus.  Shared declarations are keyed
by exact Lean identity and must lower identically from every root that reaches them. -/
def checkAndLowerSuite (env : Environment) (declaredRoots : Array Name) :
    Except Diagnostic CheckedSuite := do
  unless !declaredRoots.isEmpty do
    throw {
      code := .invalidSuite
      root := .anonymous
      declaration := .anonymous
      path := []
      message := "a checked suite must declare at least one root"
    }
  let mut seenRoots : Array Name := #[]
  let mut roots : Array CheckedRoot := #[]
  let mut functions : Array Function := #[]
  let mut usedPrimitives : Array String := #[]
  for root in declaredRoots do
    if seenRoots.contains root then
      throw {
        code := .invalidSuite
        root
        declaration := root
        path := [root]
        message := s!"checked suite declares duplicate root `{root}`"
      }
    seenRoots := seenRoots.push root
    let program ← checkAndLower env root
    unless program.contractVersion == "core0-v0.1" do
      throw {
        code := .invalidSuite
        root
        declaration := root
        path := [root]
        message := s!"checked suite root `{root}` used unsupported contract `{program.contractVersion}`"
      }
    let some rootFunction := program.findFunction? root
      | throw {
          code := .internal
          root
          declaration := root
          path := [root]
          message := s!"checked program omitted its root `{root}`"
        }
    roots := roots.push {
      id := roots.size + 1
      source := root
      signature := rootFunction.signature
    }
    for function in program.functions do
      match functions.find? (fun candidate => candidate.name == function.name) with
      | some existing =>
          unless existing == function do
            throw {
              code := .internal
              root
              declaration := function.name
              path := [root, function.name]
              message := s!"shared declaration `{function.name}` lowered inconsistently across suite roots"
            }
      | none =>
          let missing := function.dependencies.filter fun dependency =>
            !(functions.any fun candidate => candidate.name == dependency)
          unless missing.isEmpty do
            throw {
              code := .internal
              root
              declaration := function.name
              path := [root, function.name]
              message := s!"suite merge encountered non-topological dependencies in `{function.name}`"
            }
          functions := functions.push function
    for primitive in program.usedPrimitives do
      unless usedPrimitives.contains primitive do
        usedPrimitives := usedPrimitives.push primitive
  pure { roots, functions, usedPrimitives }

end Lemma.Core0
