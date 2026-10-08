import Lemma.Compiler.Lower
import Lemma.Compiler.LLVMValidate
import Lemma.Core0.ScalarLemmas

/-!
Structured `core0-v0.2` lowering.

This module is intentionally parallel to the historical single-block lowering in
`Lower.lean`.  Task 001 and the Gate 2 `core0-v0.1` suite retain their byte-stable
eager-select path; the new profile uses explicit branches and phi merge values.
-/

namespace Lemma.Compiler

private structure CFGState where
  nextValue : Nat := 0
  nextBlock : Nat := 0
  currentLabel : String := "entry"
  currentInstructions : Array LLVM.Instruction := #[]
  blocks : Array LLVM.Block := #[]
  locals : List (Nat × LLVM.Operand) := []

private abbrev CFGM := StateT CFGState (Except String)

private def freshValue (stem : String) : CFGM String := do
  let state ← get
  set { state with nextValue := state.nextValue + 1 }
  pure s!"{stem}{state.nextValue}"

private def freshBlock (stem : String) : CFGM String := do
  let state ← get
  set { state with nextBlock := state.nextBlock + 1 }
  pure s!"{stem}.{state.nextBlock}"

private def emit (instruction : LLVM.Instruction) : CFGM Unit :=
  modify fun state => {
    state with currentInstructions := state.currentInstructions.push instruction
  }

private def finishBlock (terminator : LLVM.Instruction) : CFGM String := do
  let state ← get
  let label := state.currentLabel
  let block : LLVM.Block := {
    label
    instructions := state.currentInstructions.push terminator
  }
  set { state with blocks := state.blocks.push block, currentInstructions := #[] }
  pure label

private def startBlock (label : String) : CFGM Unit := do
  let state ← get
  unless state.currentInstructions.isEmpty do
    throw s!"cannot start CFG block `{label}` before sealing `{state.currentLabel}`"
  set { state with currentLabel := label }

private def lookupLocal (id : Nat) : CFGM LLVM.Operand := do
  let state ← get
  match state.locals.find? (fun entry => entry.1 == id) with
  | some entry => pure entry.2
  | none => throw s!"checked Core0 IR refers to unknown local %{id}"

private def withLocal (id : Nat) (value : LLVM.Operand) (action : CFGM α) : CFGM α := do
  let before ← get
  set { before with locals := (id, value) :: before.locals }
  let result ← action
  modify fun after => { after with locals := before.locals }
  pure result

private def lookupSymbol (symbols : Array Symbol) (name : Lean.Name) : Except String String :=
  match symbols.find? (fun symbol => symbol.source == name) with
  | some symbol => pure symbol.llvm
  | none => throw s!"checked Core0 call has no symbol mapping for `{name}`"

private def lookupFunction (functions : Array Lemma.Core0.Function) (name : Lean.Name) :
    Except String Lemma.Core0.Function :=
  match functions.find? (fun function => function.name == name) with
  | some function => pure function
  | none => throw s!"checked Core0 call has no function definition for `{name}`"

private def ordinaryBinOp : Lemma.Core0.BinOp → Option LLVM.BinOp
  | .add => some .add
  | .sub => some .sub
  | .mul => some .mul
  | .band => some .and
  | .bor => some .or
  | .bxor => some .xor
  | _ => none

private def llvmCmpOp : Lemma.Core0.CmpOp → LLVM.Predicate
  | .eq => .eq
  | .ult => .ult
  | .ule => .ule

private def normalizeLiteral (ty : Lemma.Core0.Ty) (value : Nat) : Nat :=
  value % (2 ^ ty.width)

private def widthMask (ty : Lemma.Core0.Ty) : Nat :=
  2 ^ ty.width - 1

private def lowerExprCFG (functions : Array Lemma.Core0.Function)
      (symbols : Array Symbol) : Lemma.Core0.Expr → CFGM LLVM.Operand
    | .var id _ => lookupLocal id
    | .lit ty value => pure (.int (llvmTy ty) (normalizeLiteral ty value))
    | .boolLit value => pure (.int .i1 (if value then 1 else 0))
    | .letE id _ _ value body => do
        let value ← lowerExprCFG functions symbols value
        withLocal id value (lowerExprCFG functions symbols body)
    | .bin op ty lhs rhs => do
        if op == .udiv || op == .urem then
          let lhs ← lowerExprCFG functions symbols lhs
          let rhs ← lowerExprCFG functions symbols rhs
          let isZero ← freshValue "divisor.zero"
          emit (.icmp isZero .eq (llvmTy ty) rhs (.int (llvmTy ty) 0))
          let zeroLabel ← freshBlock "div.zero"
          let nonzeroLabel ← freshBlock "div.nonzero"
          let mergeLabel ← freshBlock "div.merge"
          let _ ← finishBlock (.branch (.local isZero) zeroLabel nonzeroLabel)

          startBlock zeroLabel
          let zeroValue := if op == .udiv then .int (llvmTy ty) 0 else lhs
          let zeroExit ← finishBlock (.jump mergeLabel)

          startBlock nonzeroLabel
          let result ← freshValue (if op == .udiv then "udiv" else "urem")
          emit (.bin result (if op == .udiv then .udiv else .urem)
            (llvmTy ty) lhs rhs)
          let nonzeroExit ← finishBlock (.jump mergeLabel)

          startBlock mergeLabel
          let merged ← freshValue "div.result"
          emit (.phi merged (llvmTy ty)
            #[(zeroValue, zeroExit), (.local result, nonzeroExit)])
          pure (.local merged)
        else if op == .shl || op == .lshr then
          let lhs ← lowerExprCFG functions symbols lhs
          let rhs ← lowerExprCFG functions symbols rhs
          let count ← freshValue "shift.count"
          emit (.bin count .and (llvmTy ty) rhs
            (.int (llvmTy ty) (Lemma.Core0.ScalarLemmas.shiftCountMask ty)))
          let result ← freshValue (if op == .shl then "shl" else "lshr")
          emit (.bin result (if op == .shl then .shl else .lshr)
            (llvmTy ty) lhs (.local count))
          pure (.local result)
        else
          let some llvmOp := ordinaryBinOp op
            | throw s!"unsupported checked binary operation `{op.render}`"
          let lhs ← lowerExprCFG functions symbols lhs
          let rhs ← lowerExprCFG functions symbols rhs
          let result ← freshValue "bin"
          emit (.bin result llvmOp (llvmTy ty) lhs rhs)
          pure (.local result)
    | .unary .complement ty value => do
        let value ← lowerExprCFG functions symbols value
        let result ← freshValue "complement"
        emit (.bin result .xor (llvmTy ty) value (.int (llvmTy ty) (widthMask ty)))
        pure (.local result)
    | .cmp op operandTy lhs rhs => do
        let lhs ← lowerExprCFG functions symbols lhs
        let rhs ← lowerExprCFG functions symbols rhs
        let result ← freshValue "cmp"
        emit (.icmp result (llvmCmpOp op) (llvmTy operandTy) lhs rhs)
        pure (.local result)
    | .ite resultTy condition thenBranch elseBranch => do
        let condition ← lowerExprCFG functions symbols condition
        let thenLabel ← freshBlock "if.then"
        let elseLabel ← freshBlock "if.else"
        let mergeLabel ← freshBlock "if.merge"
        let _ ← finishBlock (.branch condition thenLabel elseLabel)

        startBlock thenLabel
        let thenValue ← lowerExprCFG functions symbols thenBranch
        let thenExit ← finishBlock (.jump mergeLabel)

        startBlock elseLabel
        let elseValue ← lowerExprCFG functions symbols elseBranch
        let elseExit ← finishBlock (.jump mergeLabel)

        startBlock mergeLabel
        let result ← freshValue "if.result"
        emit (.phi result (llvmTy resultTy)
          #[(thenValue, thenExit), (elseValue, elseExit)])
        pure (.local result)
    | .call callee resultTy args => do
        let symbol ← match lookupSymbol symbols callee with
          | .ok symbol => pure symbol
          | .error message => throw message
        let calleeFunction ← match lookupFunction functions callee with
          | .ok function => pure function
          | .error message => throw message
        unless calleeFunction.signature.result == resultTy do
          throw s!"checked call result for `{callee}` disagrees with its function signature"
        unless args.length == calleeFunction.signature.args.size do
          throw s!"checked call arity for `{callee}` disagrees with its function signature"
        let mut lowered : Array LLVM.ABIArgument := #[]
        let mut index := 0
        for argument in args do
          let expected := calleeFunction.signature.args[index]!
          unless argument.type == expected do
            throw s!"checked call argument #{index} for `{callee}` disagrees with its function signature"
          lowered := lowered.push {
            ty := llvmTy expected
            value := ← lowerExprCFG functions symbols argument
            extension := rv64LP64Extension expected
          }
          index := index + 1
        let result ← freshValue "call"
        emit (.abiCall (some result) (llvmTy resultTy)
          (rv64LP64Extension resultTy) symbol lowered)
        pure (.local result)
    | .cast op sourceTy targetTy value => do
        let value ← lowerExprCFG functions symbols value
        let result ← freshValue "cast"
        match op with
        | .zext => emit (.zext result (llvmTy sourceTy) value (llvmTy targetTy))
        | .trunc => emit (.trunc result (llvmTy sourceTy) value (llvmTy targetTy))
        pure (.local result)

private def lowerFunctionV02 (suite : Lemma.Core0.CheckedSuite)
    (symbols : Array Symbol) (options : SuiteLowerOptions)
    (function : Lemma.Core0.Function) : Except String LLVM.Function := do
  let parameters := function.params.mapIdx fun index param =>
    ({ ty := llvmTy param.ty, name := s!"arg{index}" } : LLVM.Parameter)
  let parameterExtensions := function.params.map fun param => rv64LP64Extension param.ty
  let locals := function.params.mapIdx (fun index param =>
    (param.id, LLVM.Operand.local s!"arg{index}")) |>.toList
  let initial : CFGState := { locals }
  let (result, state) ← lowerExprCFG suite.functions symbols function.body |>.run initial
  let finalState ← match finishBlock (.ret (llvmTy function.signature.result) result) |>.run state with
    | .ok (_, state) => pure state
    | .error message => throw message
  let symbol ← lookupSymbol symbols function.name
  let isRoot := suite.roots.any fun root => root.source == function.name
  let isPreserved := options.preserveCalls.contains function.name
  let attributes :=
    if isPreserved then
      #["nounwind", "noinline", "\"disable-tail-calls\"=\"true\""]
    else #["nounwind"]
  let lowered : LLVM.Function := {
    name := symbol
    returnType := llvmTy function.signature.result
    returnExtension := rv64LP64Extension function.signature.result
    parameters
    parameterExtensions
    linkage := if isRoot || isPreserved then none else some "internal"
    attributes
    blocks := finalState.blocks
  }
  LLVM.validateFunction lowered
  pure lowered

/-- Lower a checked `core0-v0.2` suite through explicit, validated CFGs. -/
def lowerSuiteV02 (suite : Lemma.Core0.CheckedSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredSuite := do
  unless suite.contractVersion == Lemma.Core0.Profile.v0_2.contractVersion do
    throw s!"structured lowering requires `{Lemma.Core0.Profile.v0_2.contractVersion}`, got `{suite.contractVersion}`"
  unless !suite.roots.isEmpty do throw "checked Core0 suite has no declared roots"
  unless !suite.functions.isEmpty do throw "checked Core0 suite has an empty function corpus"
  let mut seenFunctions : Array Lean.Name := #[]
  for function in suite.functions do
    if seenFunctions.contains function.name then
      throw s!"checked suite contains duplicate function `{function.name}`"
    unless function.params.size == function.signature.args.size do
      throw s!"checked suite function `{function.name}` has inconsistent parameter arity"
    for h : index in [:function.params.size] do
      unless function.params[index].ty == function.signature.args[index]! do
        throw s!"checked suite function `{function.name}` has an inconsistent parameter type"
    unless function.body.type == function.signature.result do
      throw s!"checked suite function `{function.name}` has an inconsistent result type"
    let missing := function.dependencies.filter fun dependency =>
      !seenFunctions.contains dependency
    unless missing.isEmpty do
      throw s!"checked suite function `{function.name}` is not dependency-first"
    seenFunctions := seenFunctions.push function.name
  let mut seenRoots : Array Lean.Name := #[]
  for h : index in [:suite.roots.size] do
    let root := suite.roots[index]
    unless root.id == index + 1 do
      throw s!"checked suite root `{root.source}` has non-canonical id {root.id}"
    if seenRoots.contains root.source then
      throw s!"checked suite contains duplicate root `{root.source}`"
    seenRoots := seenRoots.push root.source
    let function ← lookupFunction suite.functions root.source
    unless function.signature == root.signature do
      throw s!"checked suite root `{root.source}` has an inconsistent signature"
  let mut seenPreserved : Array Lean.Name := #[]
  for name in options.preserveCalls do
    if seenPreserved.contains name then
      throw s!"preserved-call set contains duplicate declaration `{name}`"
    seenPreserved := seenPreserved.push name
    let _ ← lookupFunction suite.functions name
  let symbols := suite.functions.mapIdx fun index function =>
    ({ source := function.name, llvm := s!"core0_user_{index}" } : Symbol)
  let mut functions := #[]
  for function in suite.functions do
    functions := functions.push (← lowerFunctionV02 suite symbols options function)
  let mut roots := #[]
  for root in suite.roots do
    roots := roots.push {
      id := root.id
      source := root.source
      llvm := ← lookupSymbol symbols root.source
      signature := root.signature
    }
  pure { functions, symbols, roots }

end Lemma.Compiler
