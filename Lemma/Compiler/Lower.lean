import Lemma.Core0
import Lemma.Compiler.LLVMIR

/-!
Total lowering from the checked Core0 tree to the project's structured LLVM IR.
There is no fallback node: adding a Core0 constructor requires adding and reviewing
its semantics and LLVM rule here.
-/

namespace Lemma.Compiler

structure Symbol where
  source : Lean.Name
  llvm : String
  deriving Repr, BEq

structure LoweredApplication where
  functions : Array LLVM.Function
  symbols : Array Symbol
  rootSymbol : String
  deriving Repr

private def llvmTy : Lemma.Core0.Ty → LLVM.Ty
  | .bool => .i1
  | .u8 => .i8
  | .u32 => .i32
  | .u64 => .i64

private def llvmBinOp : Lemma.Core0.BinOp → LLVM.BinOp
  | .add => .add
  | .sub => .sub
  | .mul => .mul
  | .band => .and
  | .bor => .or
  | .bxor => .xor

private def llvmCmpOp : Lemma.Core0.CmpOp → LLVM.Predicate
  | .eq => .eq
  | .ult => .ult
  | .ule => .ule

private def normalizeLiteral (ty : Lemma.Core0.Ty) (value : Nat) : Nat :=
  value % (2 ^ ty.width)

private structure LowerState where
  nextValue : Nat := 0
  instructions : Array LLVM.Instruction := #[]
  locals : List (Nat × LLVM.Operand) := []

private abbrev LowerM := StateT LowerState (Except String)

private def fresh (stem : String) : LowerM String := do
  let state ← get
  set { state with nextValue := state.nextValue + 1 }
  pure s!"{stem}{state.nextValue}"

private def emit (instruction : LLVM.Instruction) : LowerM Unit :=
  modify fun state => { state with instructions := state.instructions.push instruction }

private def lookupLocal (id : Nat) : LowerM LLVM.Operand := do
  let state ← get
  match state.locals.find? (fun entry => entry.1 == id) with
  | some entry => pure entry.2
  | none => throw s!"checked Core0 IR refers to unknown local %{id}"

private def lookupSymbol (symbols : Array Symbol) (name : Lean.Name) : Except String String :=
  match symbols.find? (fun symbol => symbol.source == name) with
  | some symbol => pure symbol.llvm
  | none => throw s!"checked Core0 call has no symbol mapping for `{name}`"

private def withLocal (id : Nat) (value : LLVM.Operand) (action : LowerM α) : LowerM α := do
  let before ← get
  set { before with locals := (id, value) :: before.locals }
  let result ← action
  modify fun after => { after with locals := before.locals }
  pure result

private def lowerExpr (symbols : Array Symbol) : Lemma.Core0.Expr → LowerM LLVM.Operand
  | .var id _ => lookupLocal id
  | .lit ty value => pure (.int (llvmTy ty) (normalizeLiteral ty value))
  | .boolLit value => pure (.int .i1 (if value then 1 else 0))
  | .letE id _ _ value body => do
      let value ← lowerExpr symbols value
      withLocal id value (lowerExpr symbols body)
  | .bin op ty lhs rhs => do
      let lhs ← lowerExpr symbols lhs
      let rhs ← lowerExpr symbols rhs
      let result ← fresh "bin"
      emit (.bin result (llvmBinOp op) (llvmTy ty) lhs rhs)
      pure (.local result)
  | .cmp op operandTy lhs rhs => do
      let lhs ← lowerExpr symbols lhs
      let rhs ← lowerExpr symbols rhs
      let result ← fresh "cmp"
      emit (.icmp result (llvmCmpOp op) (llvmTy operandTy) lhs rhs)
      pure (.local result)
  | .ite resultTy condition thenBranch elseBranch => do
      -- Core0 v0.1 is pure, first-order, total, and recursion-free.  Eagerly
      -- computing both scalar branches before `select` is therefore equivalent
      -- to Lean's conditional while avoiding an effect-sensitive CFG rule.
      let condition ← lowerExpr symbols condition
      let thenValue ← lowerExpr symbols thenBranch
      let elseValue ← lowerExpr symbols elseBranch
      let result ← fresh "select"
      emit (.select result condition (llvmTy resultTy) thenValue elseValue)
      pure (.local result)
  | .call callee resultTy args => do
      let symbol ← match lookupSymbol symbols callee with
        | .ok symbol => pure symbol
        | .error message => throw message
      let some functionSymbol := symbols.find? (fun candidate => candidate.source == callee)
        | throw s!"missing checked function `{callee}`"
      let _ := functionSymbol
      let mut lowered : Array (LLVM.Ty × LLVM.Operand) := #[]
      -- The frontend already checked the callee signature.  Recover it from
      -- expression nodes so each operand remains typed in emitted LLVM.
      for arg in args do
        lowered := lowered.push (llvmTy arg.type, ← lowerExpr symbols arg)
      let result ← fresh "call"
      emit (.call (some result) (llvmTy resultTy) symbol lowered)
      pure (.local result)
  | .cast op sourceTy targetTy value => do
      let value ← lowerExpr symbols value
      let result ← fresh "cast"
      match op with
      | .zext => emit (.zext result (llvmTy sourceTy) value (llvmTy targetTy))
      | .trunc => emit (.trunc result (llvmTy sourceTy) value (llvmTy targetTy))
      pure (.local result)

private def lowerFunction (symbols : Array Symbol) (root : Lean.Name)
    (function : Lemma.Core0.Function) : Except String LLVM.Function := do
  let parameters := function.params.mapIdx fun index param =>
    ({ ty := llvmTy param.ty, name := s!"arg{index}" } : LLVM.Parameter)
  let locals := function.params.mapIdx (fun index param =>
    (param.id, LLVM.Operand.local s!"arg{index}")) |>.toList
  let initial : LowerState := { locals }
  let (result, state) ← lowerExpr symbols function.body |>.run initial
  let symbol ← lookupSymbol symbols function.name
  pure {
    name := symbol
    returnType := llvmTy function.signature.result
    parameters
    linkage := if function.name == root then none else some "internal"
    attributes := #["nounwind"]
    blocks := #[{
      label := "entry"
      instructions := state.instructions.push (.ret (llvmTy function.signature.result) result)
    }]
  }

def lowerApplication (program : Lemma.Core0.Program) : Except String LoweredApplication := do
  unless !program.functions.isEmpty do
    throw "checked Core0 program has an empty function corpus"
  let symbols := program.functions.mapIdx fun index function =>
    ({ source := function.name, llvm := s!"core0_user_{index}" } : Symbol)
  let mut functions := #[]
  for function in program.functions do
    functions := functions.push (← lowerFunction symbols program.root function)
  let rootSymbol ← lookupSymbol symbols program.root
  pure { functions, symbols, rootSymbol }

def LoweredApplication.renderSymbolManifest (lowered : LoweredApplication) : String :=
  String.join <| lowered.symbols.toList.map fun symbol =>
    s!"source={symbol.source};llvm={symbol.llvm}\n"

end Lemma.Compiler
