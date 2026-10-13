import Lemma.Compiler.Lower
import Lemma.Compiler.LLVMValidate
import Lemma.Core0.ActionIR
import Lemma.Core0.Bounded
import Lemma.Core0.ScalarLemmas
import Lemma.Core0.Trap
import Lemma.Core0.Timer

/-!
Structured `core0-v0.2` through `core0-v0.7` lowering.

This module is intentionally parallel to the historical single-block lowering in
`Lower.lean`.  Task 001 and the Gate 2 `core0-v0.1` suite retain their byte-stable
eager-select path.  The additive structured profiles use explicit branches and phi
merge values; v0.3 additionally lowers checked bounded folds to real CFG backedges,
v0.4 adds checked fixed-region Actions, v0.5 adds closed ordered UART sites,
v0.6 adds closed synchronous-trap primitive calls, and v0.7 adds the seven
closed timer/interrupt machine calls.
-/

namespace Lemma.Compiler

private structure CFGState where
  nextValue : Nat := 0
  nextBlock : Nat := 0
  nextMemorySite : Nat := 0
  nextDeviceSite : Nat := 0
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

private def freshMemorySite : CFGM Nat := do
  let state ← get
  set { state with nextMemorySite := state.nextMemorySite + 1 }
  pure state.nextMemorySite

private def freshDeviceSite : CFGM Nat := do
  let state ← get
  set { state with nextDeviceSite := state.nextDeviceSite + 1 }
  pure state.nextDeviceSite

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

private def lowerExprCFG (profile : Lemma.Core0.Profile)
      (functions : Array Lemma.Core0.Function)
      (symbols : Array Symbol) : Lemma.Core0.Expr → CFGM LLVM.Operand
    | .var id _ => lookupLocal id
    | .lit ty value => pure (.int (llvmTy ty) (normalizeLiteral ty value))
    | .boolLit value => pure (.int .i1 (if value then 1 else 0))
    | .letE id _ _ value body => do
        let value ← lowerExprCFG profile functions symbols value
        withLocal id value (lowerExprCFG profile functions symbols body)
    | .bin op ty lhs rhs => do
        if op == .udiv || op == .urem then
          let lhs ← lowerExprCFG profile functions symbols lhs
          let rhs ← lowerExprCFG profile functions symbols rhs
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
          let lhs ← lowerExprCFG profile functions symbols lhs
          let rhs ← lowerExprCFG profile functions symbols rhs
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
          let lhs ← lowerExprCFG profile functions symbols lhs
          let rhs ← lowerExprCFG profile functions symbols rhs
          let result ← freshValue "bin"
          emit (.bin result llvmOp (llvmTy ty) lhs rhs)
          pure (.local result)
    | .unary .complement ty value => do
        let value ← lowerExprCFG profile functions symbols value
        let result ← freshValue "complement"
        emit (.bin result .xor (llvmTy ty) value (.int (llvmTy ty) (widthMask ty)))
        pure (.local result)
    | .cmp op operandTy lhs rhs => do
        let lhs ← lowerExprCFG profile functions symbols lhs
        let rhs ← lowerExprCFG profile functions symbols rhs
        let result ← freshValue "cmp"
        emit (.icmp result (llvmCmpOp op) (llvmTy operandTy) lhs rhs)
        pure (.local result)
    | .ite resultTy condition thenBranch elseBranch => do
        let condition ← lowerExprCFG profile functions symbols condition
        let thenLabel ← freshBlock "if.then"
        let elseLabel ← freshBlock "if.else"
        let mergeLabel ← freshBlock "if.merge"
        let _ ← finishBlock (.branch condition thenLabel elseLabel)

        startBlock thenLabel
        let thenValue ← lowerExprCFG profile functions symbols thenBranch
        let thenExit ← finishBlock (.jump mergeLabel)

        startBlock elseLabel
        let elseValue ← lowerExprCFG profile functions symbols elseBranch
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
            value := ← lowerExprCFG profile functions symbols argument
            extension := rv64LP64Extension expected
          }
          index := index + 1
        let result ← freshValue "call"
        emit (.abiCall (some result) (llvmTy resultTy)
          (rv64LP64Extension resultTy) symbol lowered)
        pure (.local result)
    | .boundedFoldU32 budget callback count initial => do
        unless profile == .v0_3 || profile == .v0_4 || profile == .v0_5 ||
            profile == .v0_6 || profile == .v0_7 || profile.isExecution do
          throw s!"bounded iteration requires `{Lemma.Core0.Profile.v0_3.contractVersion}` or later"
        unless budget ≤ Lemma.Core0.Bounded.maximumBudget do
          throw s!"bounded iteration budget {budget} is outside 0..{Lemma.Core0.Bounded.maximumBudget}"
        unless count.type == .u32 && initial.type == .u32 do
          throw "bounded iteration runtime count and initial accumulator must both have type u32"
        let callbackFunction ← match lookupFunction functions callback with
          | .ok function => pure function
          | .error message => throw message
        let callbackSignature : Lemma.Core0.Signature := {
          args := #[.u32, .u32]
          result := .u32
        }
        unless callbackFunction.signature == callbackSignature do
          throw s!"bounded iteration callback `{callback}` must have signature (u32,u32)->u32"
        let callbackSymbol ← match lookupSymbol symbols callback with
          | .ok symbol => pure symbol
          | .error message => throw message

        let count ← lowerExprCFG profile functions symbols count
        let initial ← lowerExprCFG profile functions symbols initial
        let withinBudget ← freshValue "loop.within-budget"
        let exhaustedInitial ← freshValue "loop.exhausted-initial"
        let exhaustedTag ← freshValue "loop.exhausted-tag"
        let index ← freshValue "loop.index"
        let accumulator ← freshValue "loop.accumulator"
        let continueLoop ← freshValue "loop.continue"
        let nextAccumulator ← freshValue "loop.next-accumulator"
        let nextIndex ← freshValue "loop.next-index"
        let loopValue ← freshValue "loop.value"
        let result ← freshValue "loop.result"

        let preheaderLabel ← freshBlock "loop.preheader"
        let exhaustedLabel ← freshBlock "loop.exhausted"
        let headerLabel ← freshBlock "loop.header"
        let bodyLabel ← freshBlock "loop.body"
        let doneLabel ← freshBlock "loop.done"
        let outcomeLabel ← freshBlock "loop.outcome"

        emit (.icmp withinBudget .ule .i32 count (.int .i32 budget))
        let _ ← finishBlock (.branch (.local withinBudget) preheaderLabel exhaustedLabel)

        startBlock preheaderLabel
        let preheaderExit ← finishBlock (.jump headerLabel)

        startBlock exhaustedLabel
        emit (.zext exhaustedInitial .i32 initial .i64)
        emit (.bin exhaustedTag .or .i64 (.local exhaustedInitial)
          (.int .i64 (2 ^ 63)))
        let exhaustedExit ← finishBlock (.jump outcomeLabel)

        startBlock headerLabel
        emit (.phi index .i32
          #[(.int .i32 0, preheaderExit), (.local nextIndex, bodyLabel)])
        emit (.phi accumulator .i32
          #[(initial, preheaderExit), (.local nextAccumulator, bodyLabel)])
        emit (.icmp continueLoop .ult .i32 (.local index) count)
        let _ ← finishBlock (.branch (.local continueLoop) bodyLabel doneLabel)

        startBlock bodyLabel
        emit (.abiCall (some nextAccumulator) .i32 (rv64LP64Extension .u32)
          callbackSymbol #[
            { ty := .i32, value := .local index, extension := rv64LP64Extension .u32 },
            { ty := .i32, value := .local accumulator, extension := rv64LP64Extension .u32 }
          ])
        emit (.bin nextIndex .add .i32 (.local index) (.int .i32 1))
        let bodyExit ← finishBlock (.jump headerLabel)
        unless bodyExit == bodyLabel do
          throw "internal bounded-iteration latch label mismatch"

        startBlock doneLabel
        emit (.zext loopValue .i32 (.local accumulator) .i64)
        let doneExit ← finishBlock (.jump outcomeLabel)

        startBlock outcomeLabel
        emit (.phi result .i64
          #[(.local loopValue, doneExit), (.local exhaustedTag, exhaustedExit)])
        pure (.local result)
    | .cast op sourceTy targetTy value => do
        let value ← lowerExprCFG profile functions symbols value
        let result ← freshValue "cast"
        match op with
        | .zext => emit (.zext result (llvmTy sourceTy) value (llvmTy targetTy))
        | .trunc => emit (.trunc result (llvmTy sourceTy) value (llvmTy targetTy))
        pure (.local result)

private def lowerFunctionStructured (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedSuite)
    (symbols : Array Symbol) (options : SuiteLowerOptions)
    (function : Lemma.Core0.Function) : Except String LLVM.Function := do
  let parameters := function.params.mapIdx fun index param =>
    ({ ty := llvmTy param.ty, name := s!"arg{index}" } : LLVM.Parameter)
  let parameterExtensions := function.params.map fun param => rv64LP64Extension param.ty
  let locals := function.params.mapIdx (fun index param =>
    (param.id, LLVM.Operand.local s!"arg{index}")) |>.toList
  let initial : CFGState := { locals }
  let (result, state) ←
    lowerExprCFG profile suite.functions symbols function.body |>.run initial
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

private def lowerStructuredSuiteForProfile (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredSuite := do
  validateSymbolPrefix options.symbolPrefix
  unless suite.contractVersion == profile.contractVersion do
    throw s!"structured lowering requires `{profile.contractVersion}`, got `{suite.contractVersion}`"
  if profile != .v0_3 && !suite.usedIterations.isEmpty then
    throw s!"bounded-iteration metadata requires `{Lemma.Core0.Profile.v0_3.contractVersion}`"
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
    ({ source := function.name, llvm := s!"{options.symbolPrefix}core0_user_{index}" } : Symbol)
  let mut functions := #[]
  for function in suite.functions do
    functions := functions.push
      (← lowerFunctionStructured profile suite symbols options function)
  let mut roots := #[]
  for root in suite.roots do
    roots := roots.push {
      id := root.id
      source := root.source
      llvm := ← lookupSymbol symbols root.source
      signature := root.signature
    }
  pure { functions, symbols, roots }

/-- Lower a checked `core0-v0.2` suite through explicit, validated CFGs. -/
def lowerSuiteV02 (suite : Lemma.Core0.CheckedSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredSuite :=
  lowerStructuredSuiteForProfile .v0_2 suite options

/-- Lower a checked `core0-v0.3` suite, including bounded folds as genuine loops. -/
def lowerSuiteV03 (suite : Lemma.Core0.CheckedSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredSuite :=
  lowerStructuredSuiteForProfile .v0_3 suite options

/-! ## Checked fixed-region, device, trap, and timer Actions (`core0-v0.4`--`core0-v0.7`)

The Action path deliberately has a fixed two-word result and accepts only scalar
parameters.  It shares the structured scalar expression lowerer above, but keeps
effectful control flow in separate entry points so no historical scalar profile
can acquire memory or device effects by accident. -/

structure LoweredActionRoot where
  id : Nat
  source : Lean.Name
  llvm : String
  signature : Lemma.Core0.ActionSignature
  deriving Repr, BEq

/-- A literal catalog describes the checked source body, not an optimizer guess. -/
structure ClosedLiteral where
  source : Lean.Name
  symbol : String
  ty : Lemma.Core0.Ty
  value : Nat
  deriving Repr, BEq

/-- No foreign implementation is introduced: the complete existing checked
physical-memory lowering remains in this function before selective inlining. -/
structure CheckedPrimitiveWrapper where
  source : Lean.Name
  symbol : String
  operation : Lemma.Core0.Execution.Op
  effects : Lemma.Core0.EffectSet
  deriving Repr, BEq

private def closedLiteral? (function : Lemma.Core0.Function) :
    Option (Lemma.Core0.Ty × Nat) :=
  if !function.params.isEmpty || !function.signature.args.isEmpty ||
      !function.dependencies.isEmpty then none else
  match function.body with
  | .lit ty value =>
      if ty != .bool && ty == function.signature.result then some (ty, value % (2 ^ ty.width)) else none
  | _ => none

private def checkedPrimitiveWrapper? (function : Lemma.Core0.ActionFunction) :
    Option Lemma.Core0.Execution.Op := do
  let .platform operation arguments status value (.done returnedStatus returnedValue) := function.body
    | none
  unless operation.isPhysical && operation.widthBytes?.isSome && arguments.size == 6 &&
      function.params.size == operation.argumentCount &&
      function.signature.args == Array.replicate operation.argumentCount .u64 &&
      function.scalarDependencies.isEmpty && function.actionDependencies.isEmpty &&
      function.directEffects == Lemma.Core0.executionEffects operation &&
      function.effects == Lemma.Core0.executionEffects operation &&
      status.ty == .u8 && value.ty == .u64 && status.id != value.id &&
      returnedStatus == .var status.id .u8 && returnedValue == .var value.id .u64 do none
  for index in [:arguments.size] do
    if index < operation.argumentCount then
      let param := function.params[index]!
      unless param.ty == .u64 && param.id != status.id && param.id != value.id &&
          arguments[index]! == .var param.id .u64 do none
    else
      unless arguments[index]! == .lit .u64 0 do none
  some operation

/-- This successor admits no byte access or policy body, and is enabled only
under User-v0.2 by the suite entry below. -/
private def checkedUserWordWrapper? (function : Lemma.Core0.ActionFunction) :
    Option Lemma.Core0.Execution.Op := do
  let .platform operation arguments status value (.done returnedStatus returnedValue) := function.body
    | none
  unless (operation == .virtualRead64 || operation == .virtualWrite64) && arguments.size == 6 &&
      function.params.size == operation.argumentCount &&
      function.signature.args == Array.replicate operation.argumentCount .u64 &&
      function.scalarDependencies.isEmpty && function.actionDependencies.isEmpty &&
      function.directEffects == Lemma.Core0.executionEffects operation &&
      function.effects == Lemma.Core0.executionEffects operation &&
      status.ty == .u8 && value.ty == .u64 && status.id != value.id &&
      returnedStatus == .var status.id .u8 && returnedValue == .var value.id .u64 do none
  for index in [:arguments.size] do
    if index < operation.argumentCount then
      let param := function.params[index]!
      unless param.ty == .u64 && param.id != status.id && param.id != value.id &&
          arguments[index]! == .var param.id .u64 do none
    else
      unless arguments[index]! == .lit .u64 0 do none
  some operation

structure LoweredActionSuite where
  functions : Array LLVM.Function
  symbols : Array Symbol
  roots : Array LoweredActionRoot
  inlineLiterals : Array ClosedLiteral := #[]
  inlineWrappers : Array CheckedPrimitiveWrapper := #[]
  inlineUserWrappers : Array CheckedPrimitiveWrapper := #[]
  deriving Repr

def LoweredActionSuite.renderSymbolManifest (lowered : LoweredActionSuite) : String :=
  String.join <| lowered.symbols.toList.map fun symbol =>
    s!"source={symbol.source};llvm={symbol.llvm}\n"

private structure ActionOutcome where
  status : LLVM.Operand
  value : LLVM.Operand

private inductive CheckedMemoryRequest where
  | load (width : Lemma.Core0.Memory.Width)
  | store (width : Lemma.Core0.Memory.Width) (value : LLVM.Operand)
  | range (access : Lemma.Core0.MemoryAccess) (length : LLVM.Operand)

private def CheckedMemoryRequest.access : CheckedMemoryRequest → Lemma.Core0.MemoryAccess
  | .load _ => .read
  | .store _ _ => .write
  | .range access _ => access

private def CheckedMemoryRequest.width? : CheckedMemoryRequest →
    Option Lemma.Core0.Memory.Width
  | .load width | .store width _ => some width
  | .range _ _ => none

private def memoryLLVMType : Lemma.Core0.Memory.Width → LLVM.Ty
  | .w8 => .i8
  | .w32 => .i32
  | .w64 => .i64

private def permissionAllows (permission : Lemma.Core0.Memory.Permission)
    (access : Lemma.Core0.MemoryAccess) : Bool :=
  match permission, access with
  | .readWrite, _ => true
  | .readOnly, .read => true
  | _, _ => false

private def regionClassCode : Lemma.Core0.Memory.RegionKind → Nat
  | .ordinary => 0
  | .reserved => 1
  | .device => 2

private def statusOperand (status : UInt8) : LLVM.Operand :=
  .int .i8 status.toNat

private def boolOperand (value : Bool) : LLVM.Operand :=
  .int .i1 (if value then 1 else 0)

private def expectedDeviceSpec (op : Lemma.Core0.Device.Op) :
    Lemma.Core0.Device.OpSpec :=
  match op with
  | .uartReadStatus => {
      op
      base := Lemma.Core0.Device.UART.base
      offset := Lemma.Core0.Device.UART.lsrOffset
      widthBytes := 1
      access := .read
      fixedWriteValue? := none
      fenceBefore := true
      fenceAfter := true
      sideEffect := .observeLineStatus
    }
  | .uartReadByte => {
      op
      base := Lemma.Core0.Device.UART.base
      offset := Lemma.Core0.Device.UART.rbrThrOffset
      widthBytes := 1
      access := .read
      fixedWriteValue? := none
      fenceBefore := true
      fenceAfter := true
      sideEffect := .consumeReceiveByte
    }
  | .uartWriteByte => {
      op
      base := Lemma.Core0.Device.UART.base
      offset := Lemma.Core0.Device.UART.rbrThrOffset
      widthBytes := 1
      access := .write
      fixedWriteValue? := none
      fenceBefore := true
      fenceAfter := true
      sideEffect := .transmitByte
    }
  | .uartEnableAndResetFifo => {
      op
      base := Lemma.Core0.Device.UART.base
      offset := Lemma.Core0.Device.UART.fcrOffset
      widthBytes := 1
      access := .write
      fixedWriteValue? := some Lemma.Core0.Device.UART.fcrEnableAndReset
      fenceBefore := true
      fenceAfter := true
      sideEffect := .enableAndResetFifos
    }
  | .uartEnableAndResetFifo14 => {
      op
      base := Lemma.Core0.Device.UART.base
      offset := Lemma.Core0.Device.UART.fcrOffset
      widthBytes := 1
      access := .write
      fixedWriteValue? := some 0xc7
      fenceBefore := true
      fenceAfter := true
      sideEffect := .enableAndResetFifos
    }

private def deviceCatalogMatchesBackend : Bool :=
  Lemma.Core0.Device.opCatalog == #[
    expectedDeviceSpec .uartReadStatus,
    expectedDeviceSpec .uartReadByte,
    expectedDeviceSpec .uartWriteByte,
    expectedDeviceSpec .uartEnableAndResetFifo
  ]

private def kernelDeviceCatalogMatchesBackend : Bool :=
  Lemma.Core0.Device.kernelOpCatalog == Lemma.Core0.Device.opCatalog.push
    (expectedDeviceSpec .uartEnableAndResetFifo14)

private def expectedTrapSpec (op : Lemma.Core0.Trap.Op) :
    Lemma.Core0.Trap.OpSpec := {
  op
  llvmSymbol := op.llvmSymbol
  arguments := #[]
  result := .u64
  disposition := match op with
    | .ecall | .breakpoint => .resume
    | .unexpectedEcall | .illegalInstruction => .fatal
}

private def trapCatalogMatchesBackend : Bool :=
  Lemma.Core0.Trap.opCatalog == #[
    expectedTrapSpec .ecall,
    expectedTrapSpec .breakpoint,
    expectedTrapSpec .unexpectedEcall,
    expectedTrapSpec .illegalInstruction
  ]

private def expectedTimerSpec (op : Lemma.Core0.Timer.Op) :
    Lemma.Core0.Timer.OpSpec :=
  let base : Lemma.Core0.Timer.OpSpec := {
    op
    sourceIdentity := op.sourceIdentity
    llvmSymbol := op.llvmSymbol
    sourceArguments := #[]
    machineArguments := #[]
    result := .u64
    resultMeaning := .zero
    stateOperation := .readMachineTime
  }
  match op with
  | .readTime => { base with
      resultMeaning := .time
      stateOperation := .readMachineTime
      mmio? := some {
        address := Lemma.Core0.Timer.MachineTimer.timeAddress
        widthBytes := 8
        access := .read
        fenceBefore := true
        fenceAfter := true
      }
    }
  | .setCompare => { base with
      sourceArguments := #[.u64]
      machineArguments := #[.u64]
      stateOperation := .writeMachineCompare
      mmio? := some {
        address := Lemma.Core0.Timer.MachineTimer.compareAddress
        widthBytes := 8
        access := .write
        fenceBefore := true
        fenceAfter := true
      }
    }
  | .readPending => { base with
      resultMeaning := .pendingBit
      stateOperation := .readMIPMTIP
    }
  | .irqSaveDisable => { base with
      resultMeaning := .previousGlobalMIE
      stateOperation := .saveDisableMstatusMIE
    }
  | .irqRestore => { base with
      sourceArguments := #[.bool]
      machineArguments := #[.u64]
      canonicalBoolArgument := true
      stateOperation := .restoreMstatusMIE
    }
  | .setInterrupt => { base with
      sourceArguments := #[.bool]
      machineArguments := #[.u64]
      canonicalBoolArgument := true
      stateOperation := .setMieMTIE
    }
  | .probe => { base with
      resultMeaning := .probeMask
      requiresGlobalMIEDisabled := true
      stateOperation := .quarantinedProbe
    }

private def timerCatalogMatchesBackend : Bool :=
  Lemma.Core0.Timer.opCatalog == #[
    expectedTimerSpec .readTime,
    expectedTimerSpec .setCompare,
    expectedTimerSpec .readPending,
    expectedTimerSpec .irqSaveDisable,
    expectedTimerSpec .irqRestore,
    expectedTimerSpec .setInterrupt,
    expectedTimerSpec .probe
  ]

private def pushDeviceOp (operations : Array Lemma.Core0.Device.Op)
    (operation : Lemma.Core0.Device.Op) : Array Lemma.Core0.Device.Op :=
  if operations.contains operation then operations else operations.push operation

private def collectDeviceOps (operations : Array Lemma.Core0.Device.Op) :
    Lemma.Core0.ActionExpr → Array Lemma.Core0.Device.Op
  | .done .. | .call .. | .loop .. => operations
  | .bind first _ _ next =>
      collectDeviceOps (collectDeviceOps operations first) next
  | .load _ _ _ _ _ next | .store _ _ _ _ _ next |
      .checkRange _ _ _ _ _ next =>
      collectDeviceOps operations next
  | .ite _ thenBranch elseBranch =>
      collectDeviceOps (collectDeviceOps operations thenBranch) elseBranch
  | .boundedFoldU64 _ _ _ _ _ _ _ _ _ _ next =>
      collectDeviceOps operations next
  | .uartReadStatus _ _ next =>
      collectDeviceOps (pushDeviceOp operations .uartReadStatus) next
  | .uartReadByte _ _ next =>
      collectDeviceOps (pushDeviceOp operations .uartReadByte) next
  | .uartWriteByte _ _ next =>
      collectDeviceOps (pushDeviceOp operations .uartWriteByte) next
  | .uartEnableAndResetFifo _ next =>
      collectDeviceOps (pushDeviceOp operations .uartEnableAndResetFifo) next
  | .uartEnableAndResetFifo14 _ next =>
      collectDeviceOps (pushDeviceOp operations .uartEnableAndResetFifo14) next
  | .trap _ _ _ next =>
      collectDeviceOps operations next
  | .timer _ _ _ _ next =>
      collectDeviceOps operations next
  | .platform _ _ _ _ next =>
      collectDeviceOps operations next
termination_by action => sizeOf action

private def pushTrapOp (operations : Array Lemma.Core0.Trap.Op)
    (operation : Lemma.Core0.Trap.Op) : Array Lemma.Core0.Trap.Op :=
  if operations.contains operation then operations else operations.push operation

private def collectTrapOps (operations : Array Lemma.Core0.Trap.Op) :
    Lemma.Core0.ActionExpr → Array Lemma.Core0.Trap.Op
  | .done .. | .call .. | .loop .. => operations
  | .bind first _ _ next =>
      collectTrapOps (collectTrapOps operations first) next
  | .load _ _ _ _ _ next | .store _ _ _ _ _ next |
      .checkRange _ _ _ _ _ next =>
      collectTrapOps operations next
  | .ite _ thenBranch elseBranch =>
      collectTrapOps (collectTrapOps operations thenBranch) elseBranch
  | .boundedFoldU64 _ _ _ _ _ _ _ _ _ _ next =>
      collectTrapOps operations next
  | .uartReadStatus _ _ next | .uartReadByte _ _ next |
      .uartWriteByte _ _ next | .uartEnableAndResetFifo _ next | .uartEnableAndResetFifo14 _ next =>
      collectTrapOps operations next
  | .trap operation _ _ next =>
      collectTrapOps (pushTrapOp operations operation) next
  | .timer _ _ _ _ next =>
      collectTrapOps operations next
  | .platform _ _ _ _ next =>
      collectTrapOps operations next
termination_by action => sizeOf action

private def pushTimerOp (operations : Array Lemma.Core0.Timer.Op)
    (operation : Lemma.Core0.Timer.Op) : Array Lemma.Core0.Timer.Op :=
  if operations.contains operation then operations else operations.push operation

private def collectTimerOps (operations : Array Lemma.Core0.Timer.Op) :
    Lemma.Core0.ActionExpr → Array Lemma.Core0.Timer.Op
  | .done .. | .call .. | .loop .. => operations
  | .bind first _ _ next =>
      collectTimerOps (collectTimerOps operations first) next
  | .load _ _ _ _ _ next | .store _ _ _ _ _ next |
      .checkRange _ _ _ _ _ next =>
      collectTimerOps operations next
  | .ite _ thenBranch elseBranch =>
      collectTimerOps (collectTimerOps operations thenBranch) elseBranch
  | .boundedFoldU64 _ _ _ _ _ _ _ _ _ _ next =>
      collectTimerOps operations next
  | .uartReadStatus _ _ next | .uartReadByte _ _ next |
      .uartWriteByte _ _ next | .uartEnableAndResetFifo _ next | .uartEnableAndResetFifo14 _ next |
      .trap _ _ _ next =>
      collectTimerOps operations next
  | .timer operation _ _ _ next =>
      collectTimerOps (pushTimerOp operations operation) next
  | .platform _ _ _ _ next =>
      collectTimerOps operations next
termination_by action => sizeOf action

private def collectExecutionOps (operations : Array Lemma.Core0.Execution.OpSpec) :
    Lemma.Core0.ActionExpr → Array Lemma.Core0.Execution.OpSpec
  | .done .. | .call .. | .loop .. => operations
  | .bind first _ _ next => collectExecutionOps (collectExecutionOps operations first) next
  | .ite _ left right => collectExecutionOps (collectExecutionOps operations left) right
  | .load _ _ _ _ _ next | .store _ _ _ _ _ next | .checkRange _ _ _ _ _ next |
      .boundedFoldU64 _ _ _ _ _ _ _ _ _ _ next | .uartReadStatus _ _ next |
      .uartReadByte _ _ next | .uartWriteByte _ _ next | .uartEnableAndResetFifo _ next | .uartEnableAndResetFifo14 _ next |
      .trap _ _ _ next | .timer _ _ _ _ next => collectExecutionOps operations next
  | .platform operation _ _ _ next =>
      let spec := Lemma.Core0.Execution.specification operation
      collectExecutionOps (if operations.contains spec then operations else operations.push spec) next
termination_by action => sizeOf action

private def collectActionLoops (uses : Array Lemma.Core0.ActionLoopUse) :
    Lemma.Core0.ActionExpr → Array Lemma.Core0.ActionLoopUse
  | .done .. | .call .. => uses
  | .loop callback =>
      let use : Lemma.Core0.ActionLoopUse := { callback }
      if uses.contains use then uses else uses.push use
  | .bind first _ _ next => collectActionLoops (collectActionLoops uses first) next
  | .ite _ left right => collectActionLoops (collectActionLoops uses left) right
  | .load _ _ _ _ _ next | .store _ _ _ _ _ next | .checkRange _ _ _ _ _ next |
      .boundedFoldU64 _ _ _ _ _ _ _ _ _ _ next | .uartReadStatus _ _ next |
      .uartReadByte _ _ next | .uartWriteByte _ _ next | .uartEnableAndResetFifo _ next | .uartEnableAndResetFifo14 _ next |
      .trap _ _ _ next | .timer _ _ _ _ next | .platform _ _ _ _ next =>
      collectActionLoops uses next
termination_by action => sizeOf action

private def timerEffects : Lemma.Core0.Timer.Op → Lemma.Core0.EffectSet
  | .readTime => .timerRead
  | .setCompare => .timerWrite
  | .readPending => .timerInterrupt
  | .irqSaveDisable | .irqRestore => .interrupt
  | .setInterrupt | .probe => .timerInterrupt

/-- Recompute the complete set of effects performed directly by an Action body.
Calls and bounded-fold callbacks contribute through `actionDependencies`; their
continuations remain direct syntax in the caller. -/
private def directActionEffects : Lemma.Core0.ActionExpr → Lemma.Core0.EffectSet
  | .done .. | .call .. => .empty
  | .loop _ => { mayDiverge := true }
  | .bind first _ _ next =>
      directActionEffects first ∪ directActionEffects next
  | .load _ _ _ _ _ next =>
      Lemma.Core0.EffectSet.read ∪ directActionEffects next
  | .store _ _ _ _ _ next =>
      Lemma.Core0.EffectSet.write ∪ directActionEffects next
  | .checkRange _ _ _ _ _ next =>
      Lemma.Core0.EffectSet.check ∪ directActionEffects next
  | .ite _ thenBranch elseBranch =>
      directActionEffects thenBranch ∪ directActionEffects elseBranch
  | .boundedFoldU64 _ _ _ _ _ _ _ _ _ _ next =>
      directActionEffects next
  | .uartReadStatus _ _ next | .uartReadByte _ _ next =>
      Lemma.Core0.EffectSet.deviceRead ∪ directActionEffects next
  | .uartWriteByte _ _ next | .uartEnableAndResetFifo _ next | .uartEnableAndResetFifo14 _ next =>
      Lemma.Core0.EffectSet.deviceWrite ∪ directActionEffects next
  | .trap _ _ _ next =>
      Lemma.Core0.EffectSet.trap ∪ directActionEffects next
  | .timer operation _ _ _ next =>
      timerEffects operation ∪ directActionEffects next
  | .platform operation _ _ _ next =>
      Lemma.Core0.executionEffects operation ∪ directActionEffects next
termination_by action => sizeOf action

private def lookupActionFunction (functions : Array Lemma.Core0.ActionFunction)
    (name : Lean.Name) : Except String Lemma.Core0.ActionFunction :=
  match functions.find? (fun function => function.name == name) with
  | some function => pure function
  | none => throw s!"checked Core0 Action call has no function definition for `{name}`"

/-- Lower one checked ordinary-RAM operation.  Region lookup is an explicit ID
dispatch.  The selected metadata then passes, in order, through class, permission,
width, subtraction-safe bounds, and alignment guards.  Only the final success
block constructs a pointer or performs a volatile target access. -/
private def lowerCheckedMemory (request : CheckedMemoryRequest)
    (region offset : LLVM.Operand) : CFGM ActionOutcome := do
  let site ← freshMemorySite
  let memPrefix := s!"mem.{site}."
  let metadataLabel ← freshBlock (memPrefix ++ "metadata")
  let outcomeLabel ← freshBlock (memPrefix ++ "outcome")

  let mut baseIncoming : Array (LLVM.Operand × String) := #[]
  let mut lengthIncoming : Array (LLVM.Operand × String) := #[]
  let mut classIncoming : Array (LLVM.Operand × String) := #[]
  let mut permissionIncoming : Array (LLVM.Operand × String) := #[]
  let mut widthIncoming : Array (LLVM.Operand × String) := #[]
  let mut statusIncoming : Array (LLVM.Operand × String) := #[]
  let mut valueIncoming : Array (LLVM.Operand × String) := #[]

  -- Runtime identifiers carry no authority.  Every known identifier reaches a
  -- metadata edge; all other bytes take the recoverable unknown-region edge.
  for staticRegion in Lemma.Core0.Memory.regionTable do
    let caseLabel ← freshBlock
      (memPrefix ++ "region." ++ toString staticRegion.id.toNat)
    let nextLabel ← freshBlock (memPrefix ++ "lookup.next")
    let known ← freshValue (memPrefix ++ "region-known.")
    emit (.icmp known .eq .i8 region (.int .i8 staticRegion.id.toNat))
    let _ ← finishBlock (.branch (.local known) caseLabel nextLabel)

    startBlock caseLabel
    let caseExit ← finishBlock (.jump metadataLabel)
    baseIncoming := baseIncoming.push
      (.int .i64 staticRegion.base.toNat, caseExit)
    lengthIncoming := lengthIncoming.push
      (.int .i64 staticRegion.length, caseExit)
    classIncoming := classIncoming.push
      (.int .i8 (regionClassCode staticRegion.kind), caseExit)
    permissionIncoming := permissionIncoming.push
      (boolOperand (permissionAllows staticRegion.permission request.access), caseExit)
    let widthAllowed := match request.width? with
      | none => true
      | some width => staticRegion.widths.contains width
    widthIncoming := widthIncoming.push (boolOperand widthAllowed, caseExit)
    startBlock nextLabel

  let unknownExit ← finishBlock (.jump outcomeLabel)
  statusIncoming := statusIncoming.push
    (statusOperand Lemma.Core0.Memory.Status.unknownRegion, unknownExit)
  valueIncoming := valueIncoming.push (.int .i64 0, unknownExit)

  startBlock metadataLabel
  let baseName ← freshValue (memPrefix ++ "base.")
  let lengthName ← freshValue (memPrefix ++ "length.")
  let className ← freshValue (memPrefix ++ "class.")
  let permissionName ← freshValue (memPrefix ++ "permission-ok.")
  let widthName ← freshValue (memPrefix ++ "width-ok.")
  emit (.phi baseName .i64 baseIncoming)
  emit (.phi lengthName .i64 lengthIncoming)
  emit (.phi className .i8 classIncoming)
  emit (.phi permissionName .i1 permissionIncoming)
  emit (.phi widthName .i1 widthIncoming)
  let classOk ← freshValue (memPrefix ++ "class-ok.")
  emit (.icmp classOk .eq .i8 (.local className) (.int .i8 0))
  let permissionLabel ← freshBlock (memPrefix ++ "permission")
  let classDeniedLabel ← freshBlock (memPrefix ++ "class-denied")
  let _ ← finishBlock (.branch (.local classOk) permissionLabel classDeniedLabel)

  -- Class failure is split so reserved and device denials remain distinct.
  startBlock classDeniedLabel
  let isReserved ← freshValue (memPrefix ++ "class-is-reserved.")
  emit (.icmp isReserved .eq .i8 (.local className) (.int .i8 1))
  let reservedLabel ← freshBlock (memPrefix ++ "reserved")
  let deviceLabel ← freshBlock (memPrefix ++ "device")
  let _ ← finishBlock (.branch (.local isReserved) reservedLabel deviceLabel)

  startBlock reservedLabel
  let reservedExit ← finishBlock (.jump outcomeLabel)
  statusIncoming := statusIncoming.push
    (statusOperand Lemma.Core0.Memory.Status.reservedRegion, reservedExit)
  valueIncoming := valueIncoming.push (.int .i64 0, reservedExit)

  startBlock deviceLabel
  let deviceExit ← finishBlock (.jump outcomeLabel)
  statusIncoming := statusIncoming.push
    (statusOperand Lemma.Core0.Memory.Status.deviceRegion, deviceExit)
  valueIncoming := valueIncoming.push (.int .i64 0, deviceExit)

  startBlock permissionLabel
  let widthLabel ← freshBlock (memPrefix ++ "width")
  let permissionDeniedLabel ← freshBlock (memPrefix ++ "permission-denied")
  let _ ← finishBlock
    (.branch (.local permissionName) widthLabel permissionDeniedLabel)

  startBlock permissionDeniedLabel
  let permissionExit ← finishBlock (.jump outcomeLabel)
  let permissionStatus := match request.access with
    | .read => Lemma.Core0.Memory.Status.readDenied
    | .write => Lemma.Core0.Memory.Status.writeDenied
  statusIncoming := statusIncoming.push (statusOperand permissionStatus, permissionExit)
  valueIncoming := valueIncoming.push (.int .i64 0, permissionExit)

  startBlock widthLabel
  let lengthGuardLabel ← freshBlock (memPrefix ++ "length-guard")
  let widthDeniedLabel ← freshBlock (memPrefix ++ "width-denied")
  let _ ← finishBlock (.branch (.local widthName) lengthGuardLabel widthDeniedLabel)

  startBlock widthDeniedLabel
  let widthExit ← finishBlock (.jump outcomeLabel)
  statusIncoming := statusIncoming.push
    (statusOperand Lemma.Core0.Memory.Status.widthDenied, widthExit)
  valueIncoming := valueIncoming.push (.int .i64 0, widthExit)

  startBlock lengthGuardLabel
  let requestedLength : LLVM.Operand := match request with
    | .load width | .store width _ => .int .i64 width.bytes
    | .range _ length => length
  let lengthOk ← freshValue (memPrefix ++ "length-ok.")
  emit (.icmp lengthOk .ule .i64 requestedLength (.local lengthName))
  let subtractLabel ← freshBlock (memPrefix ++ "subtract")
  let boundsDeniedByLength ← freshBlock (memPrefix ++ "bounds-length-denied")
  let _ ← finishBlock (.branch (.local lengthOk) subtractLabel boundsDeniedByLength)

  startBlock boundsDeniedByLength
  let lengthDeniedExit ← finishBlock (.jump outcomeLabel)
  statusIncoming := statusIncoming.push
    (statusOperand Lemma.Core0.Memory.Status.outOfBounds, lengthDeniedExit)
  valueIncoming := valueIncoming.push (.int .i64 0, lengthDeniedExit)

  startBlock subtractLabel
  let remaining ← freshValue (memPrefix ++ "remaining.")
  emit (.bin remaining .sub .i64 (.local lengthName) requestedLength)
  let offsetOk ← freshValue (memPrefix ++ "offset-ok.")
  emit (.icmp offsetOk .ule .i64 offset (.local remaining))
  let inBoundsLabel ← freshBlock (memPrefix ++ "in-bounds")
  let boundsDeniedByOffset ← freshBlock (memPrefix ++ "bounds-offset-denied")
  let _ ← finishBlock (.branch (.local offsetOk) inBoundsLabel boundsDeniedByOffset)

  startBlock boundsDeniedByOffset
  let offsetDeniedExit ← finishBlock (.jump outcomeLabel)
  statusIncoming := statusIncoming.push
    (statusOperand Lemma.Core0.Memory.Status.outOfBounds, offsetDeniedExit)
  valueIncoming := valueIncoming.push (.int .i64 0, offsetDeniedExit)

  startBlock inBoundsLabel
  match request with
  | .range _ _ =>
      -- A range preflight observes no bytes and constructs no address.
      let successExit ← finishBlock (.jump outcomeLabel)
      statusIncoming := statusIncoming.push
        (statusOperand Lemma.Core0.Memory.Status.ok, successExit)
      valueIncoming := valueIncoming.push (.int .i64 0, successExit)
  | .load width | .store width _ =>
      let alignmentMask ← freshValue (memPrefix ++ "alignment-mask.")
      emit (.bin alignmentMask .and .i64 offset (.int .i64 (width.bytes - 1)))
      let alignmentOk ← freshValue (memPrefix ++ "alignment-ok.")
      emit (.icmp alignmentOk .eq .i64 (.local alignmentMask) (.int .i64 0))
      let accessLabel ← freshBlock (memPrefix ++ "access")
      let alignmentDeniedLabel ← freshBlock (memPrefix ++ "alignment-denied")
      let _ ← finishBlock
        (.branch (.local alignmentOk) accessLabel alignmentDeniedLabel)

      startBlock alignmentDeniedLabel
      let alignmentDeniedExit ← finishBlock (.jump outcomeLabel)
      statusIncoming := statusIncoming.push
        (statusOperand Lemma.Core0.Memory.Status.misaligned, alignmentDeniedExit)
      valueIncoming := valueIncoming.push (.int .i64 0, alignmentDeniedExit)

      startBlock accessLabel
      let address ← freshValue (memPrefix ++ "address.")
      emit (.bin address .add .i64 (.local baseName) offset)
      let pointer ← freshValue (memPrefix ++ "pointer.")
      emit (.intToPtr pointer (.local address))
      let successValue ← match request with
        | .load width => do
            let loaded ← freshValue (memPrefix ++ "loaded.")
            emit (.load loaded (memoryLLVMType width) (.local pointer) width.bytes true)
            match width with
            | .w8 =>
                let extended ← freshValue (memPrefix ++ "loaded-u64.")
                emit (.zext extended .i8 (.local loaded) .i64)
                pure (.local extended)
            | .w32 =>
                let extended ← freshValue (memPrefix ++ "loaded-u64.")
                emit (.zext extended .i32 (.local loaded) .i64)
                pure (.local extended)
            | .w64 => pure (.local loaded)
        | .store width value => do
            emit (.store (memoryLLVMType width) value (.local pointer) width.bytes true)
            pure (.int .i64 0)
        | .range .. => throw "internal checked-memory request changed after range split"
      let successExit ← finishBlock (.jump outcomeLabel)
      statusIncoming := statusIncoming.push
        (statusOperand Lemma.Core0.Memory.Status.ok, successExit)
      valueIncoming := valueIncoming.push (successValue, successExit)

  startBlock outcomeLabel
  let statusName ← freshValue (memPrefix ++ "status.")
  let valueName ← freshValue (memPrefix ++ "value.")
  emit (.phi statusName .i8 statusIncoming)
  emit (.phi valueName .i64 valueIncoming)
  pure { status := .local statusName, value := .local valueName }

/-- Checked execution RAM access. The success block is the sole pointer
construction/access path. Half-open interval limits are subtraction checked;
no speculative wrapped address addition is used. -/
private def lowerExecutionMemory (profile : Lemma.Core0.Profile)
    (operation : Lemma.Core0.Execution.Op) (arguments : Array LLVM.Operand) :
    CFGM ActionOutcome := do
  let some width := operation.widthBytes?
    | throw "execution memory operation omitted its width"
  unless width == 1 || width == 8 || (operation.isDevice && width == 4) do
    throw "unsupported execution access width"
  let some address := arguments[0]?
    | throw "execution memory operation omitted its address"
  let writeValue := arguments[1]?.getD (.int .i64 0)
  let site ← freshMemorySite
  let stem := s!"execution.mem.{site}."
  let outcomeLabel ← freshBlock (stem ++ "outcome")
  let lookupLabel ← freshBlock (stem ++ "lookup")
  let misalignedLabel ← freshBlock (stem ++ "misaligned")
  let alignmentMask ← freshValue (stem ++ "alignment-mask.")
  let aligned ← freshValue (stem ++ "aligned.")
  emit (.bin alignmentMask .and .i64 address (.int .i64 (width - 1)))
  emit (.icmp aligned .eq .i64 (.local alignmentMask) (.int .i64 0))
  let _ ← finishBlock (.branch (.local aligned) lookupLabel misalignedLabel)
  startBlock misalignedLabel
  let misalignedExit ← finishBlock (.jump outcomeLabel)
  let mut statuses : Array (LLVM.Operand × String) := #[
    (statusOperand Lemma.Core0.Memory.Status.misaligned, misalignedExit)]
  let mut values : Array (LLVM.Operand × String) := #[(.int .i64 0, misalignedExit)]
  startBlock lookupLabel
  if operation.isWrite && (width == 1 || width == 4) then
    let byteOk ← freshValue (stem ++ "byte-valid.")
    let byteValidLabel ← freshBlock (stem ++ "byte-valid")
    let invalidByteLabel ← freshBlock (stem ++ "invalid-byte")
    emit (.icmp byteOk .ule .i64 writeValue (.int .i64 (if width == 1 then 255 else 0xffffffff)))
    let _ ← finishBlock (.branch (.local byteOk) byteValidLabel invalidByteLabel)
    startBlock invalidByteLabel
    let invalidByteExit ← finishBlock (.jump outcomeLabel)
    statuses := statuses.push (statusOperand Lemma.Core0.Memory.Status.invalidLength, invalidByteExit)
    values := values.push (.int .i64 0, invalidByteExit)
    startBlock byteValidLabel
  let regions := if operation.isDevice then Lemma.Core0.Execution.deviceRegionsFor profile operation
    else Lemma.Core0.Execution.memoryRegions profile
  for region in regions do
    unless region.start < region.stop && width ≤ region.stop - region.start do
      throw "execution memory authority interval is shorter than the access width"
    let checkUpperLabel ← freshBlock (stem ++ "upper")
    let accessLabel ← freshBlock (stem ++ "access")
    let nextLabel ← freshBlock (stem ++ "next")
    let aboveStart ← freshValue (stem ++ "above-start.")
    emit (.icmp aboveStart .uge .i64 address (.int .i64 region.start))
    let _ ← finishBlock (.branch (.local aboveStart) checkUpperLabel nextLabel)
    startBlock checkUpperLabel
    let belowLimit ← freshValue (stem ++ "below-limit.")
    emit (.icmp belowLimit .ule .i64 address (.int .i64 (region.stop - width)))
    let _ ← finishBlock (.branch (.local belowLimit) accessLabel nextLabel)
    startBlock accessLabel
    if operation.isWrite && !region.writable then
      let deniedExit ← finishBlock (.jump outcomeLabel)
      statuses := statuses.push (statusOperand Lemma.Core0.Memory.Status.writeDenied, deniedExit)
      values := values.push (.int .i64 0, deniedExit)
    else
      let pointer ← freshValue (stem ++ "pointer.")
      emit (.intToPtr pointer address)
      let llvmType := if width == 1 then LLVM.Ty.i8 else if width == 4 then .i32 else .i64
      if operation.isDevice then emit (.call none .void "core0_io_fence" #[])
      let value ← if operation.isWrite then do
        let stored ← if width == 1 || width == 4 then do
          let byte ← freshValue (stem ++ "stored-byte.")
          emit (.trunc byte .i64 writeValue llvmType)
          pure (LLVM.Operand.local byte)
        else pure writeValue
        emit (.store llvmType stored (.local pointer) width true)
        pure (LLVM.Operand.int .i64 0)
      else do
        let loaded ← freshValue (stem ++ "loaded.")
        emit (.load loaded llvmType (.local pointer) width true)
        if width == 1 || width == 4 then do
          let word ← freshValue (stem ++ "loaded-word.")
          emit (.zext word llvmType (.local loaded) .i64)
          pure (LLVM.Operand.local word)
        else pure (.local loaded)
      if operation.isDevice then emit (.call none .void "core0_io_fence" #[])
      let accessExit ← finishBlock (.jump outcomeLabel)
      statuses := statuses.push (statusOperand Lemma.Core0.Memory.Status.ok, accessExit)
      values := values.push (value, accessExit)
    startBlock nextLabel
  let deniedExit ← finishBlock (.jump outcomeLabel)
  statuses := statuses.push (statusOperand Lemma.Core0.Memory.Status.outOfBounds, deniedExit)
  values := values.push (.int .i64 0, deniedExit)
  startBlock outcomeLabel
  let status ← freshValue (stem ++ "status.")
  let value ← freshValue (stem ++ "value.")
  emit (.phi status .i8 statuses)
  emit (.phi value .i64 values)
  pure { status := .local status, value := .local value }

private def lowerExecutionCall (operation : Lemma.Core0.Execution.Op)
    (arguments : Array LLVM.Operand) : CFGM ActionOutcome := do
  let spec := Lemma.Core0.Execution.specification operation
  let some symbol := spec.primitiveSymbol?
    | throw "execution machine call has no closed primitive symbol"
  let machineArguments := (arguments.extract 0 spec.meaningfulArguments).map fun value =>
    ({ ty := LLVM.Ty.i64, value } : LLVM.ABIArgument)
  let result ← freshValue "execution.result."
  if spec.resultKind == .checked then
    emit (.abiCall (some result) .checkedResult none symbol machineArguments)
    let statusWord ← freshValue "execution.status-word."
    let status ← freshValue "execution.status."
    let value ← freshValue "execution.value."
    emit (.extractResultStatus statusWord (.local result))
    emit (.trunc status .i64 (.local statusWord) .i8)
    emit (.extractResultValue value (.local result))
    pure { status := .local status, value := .local value }
  else
    emit (.abiCall (some result) .i64 none symbol machineArguments)
    pure { status := statusOperand Lemma.Core0.Memory.Status.ok, value := .local result }

private def lowerActionExpr (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedActionSuite)
    (symbols : Array Symbol) : Lemma.Core0.ActionExpr → CFGM ActionOutcome
  | .done status value => do
      unless status.type == .u8 && value.type == .u64 do
        throw "checked Action.done must contain (u8,u64)"
      pure {
        status := ← lowerExprCFG profile suite.scalarFunctions symbols status
        value := ← lowerExprCFG profile suite.scalarFunctions symbols value
      }
  | .bind first status value next => do
      unless status.ty == .u8 && value.ty == .u64 do
        throw "checked Action.bind must bind (u8,u64)"
      let outcome ← lowerActionExpr profile suite symbols first
      withLocal status.id outcome.status do
        withLocal value.id outcome.value do
          lowerActionExpr profile suite symbols next
  | .load width region offset status value next => do
      if profile.isExecution then
        throw "production profiles reject diagnostic fixed-region RAM constructors"
      unless region.type == .u8 && offset.type == .u64 &&
          status.ty == .u8 && value.ty == .u64 do
        throw "checked Action load has an inconsistent type"
      let region ← lowerExprCFG profile suite.scalarFunctions symbols region
      let offset ← lowerExprCFG profile suite.scalarFunctions symbols offset
      let outcome ← lowerCheckedMemory (.load width) region offset
      withLocal status.id outcome.status do
        withLocal value.id outcome.value do
          lowerActionExpr profile suite symbols next
  | .store width region offset value status next => do
      if profile.isExecution then
        throw "production profiles reject diagnostic fixed-region RAM constructors"
      let expected := match width with
        | .w8 => Lemma.Core0.Ty.u8
        | .w32 => Lemma.Core0.Ty.u32
        | .w64 => Lemma.Core0.Ty.u64
      unless region.type == .u8 && offset.type == .u64 && value.type == expected &&
          status.ty == .u8 do
        throw "checked Action store has an inconsistent type"
      let region ← lowerExprCFG profile suite.scalarFunctions symbols region
      let offset ← lowerExprCFG profile suite.scalarFunctions symbols offset
      let value ← lowerExprCFG profile suite.scalarFunctions symbols value
      let outcome ← lowerCheckedMemory (.store width value) region offset
      withLocal status.id outcome.status do
        lowerActionExpr profile suite symbols next
  | .checkRange access region offset length status next => do
      if profile.isExecution then
        throw "production profiles reject diagnostic fixed-region RAM constructors"
      unless region.type == .u8 && offset.type == .u64 && length.type == .u64 &&
          status.ty == .u8 do
        throw "checked Action range preflight has an inconsistent type"
      let region ← lowerExprCFG profile suite.scalarFunctions symbols region
      let offset ← lowerExprCFG profile suite.scalarFunctions symbols offset
      let length ← lowerExprCFG profile suite.scalarFunctions symbols length
      let outcome ← lowerCheckedMemory (.range access length) region offset
      withLocal status.id outcome.status do
        lowerActionExpr profile suite symbols next
  | .ite condition thenBranch elseBranch => do
      unless condition.type == .bool do
        throw "checked Action conditional requires a Bool condition"
      let condition ← lowerExprCFG profile suite.scalarFunctions symbols condition
      let thenLabel ← freshBlock "action.if.then"
      let elseLabel ← freshBlock "action.if.else"
      let mergeLabel ← freshBlock "action.if.merge"
      let _ ← finishBlock (.branch condition thenLabel elseLabel)

      startBlock thenLabel
      let thenOutcome ← lowerActionExpr profile suite symbols thenBranch
      let thenExit ← finishBlock (.jump mergeLabel)

      startBlock elseLabel
      let elseOutcome ← lowerActionExpr profile suite symbols elseBranch
      let elseExit ← finishBlock (.jump mergeLabel)

      startBlock mergeLabel
      let statusName ← freshValue "action.if.status"
      let valueName ← freshValue "action.if.value"
      emit (.phi statusName .i8
        #[(thenOutcome.status, thenExit), (elseOutcome.status, elseExit)])
      emit (.phi valueName .i64
        #[(thenOutcome.value, thenExit), (elseOutcome.value, elseExit)])
      pure { status := .local statusName, value := .local valueName }
  | .call callee args => do
      let function ← match lookupActionFunction suite.actionFunctions callee with
        | .ok function => pure function
        | .error message => throw message
      unless args.length == function.signature.args.size do
        throw s!"checked Action call arity for `{callee}` disagrees with its signature"
      let symbol ← match lookupSymbol symbols callee with
        | .ok symbol => pure symbol
        | .error message => throw message
      let mut arguments : Array LLVM.ABIArgument := #[]
      let mut index := 0
      for argument in args do
        let expected := function.signature.args[index]!
        unless argument.type == expected do
          throw s!"checked Action call argument #{index} for `{callee}` has the wrong type"
        arguments := arguments.push {
          ty := llvmTy expected
          value := ← lowerExprCFG profile suite.scalarFunctions symbols argument
          extension := rv64LP64Extension expected
        }
        index := index + 1
      let aggregate ← freshValue "action.call.result"
      emit (.abiCall (some aggregate) .checkedResult none symbol arguments)
      let statusWord ← freshValue "action.call.status-word"
      let status ← freshValue "action.call.status"
      let value ← freshValue "action.call.value"
      emit (.extractResultStatus statusWord (.local aggregate))
      emit (.trunc status .i64 (.local statusWord) .i8)
      emit (.extractResultValue value (.local aggregate))
      pure { status := .local status, value := .local value }
  | .loop callback => do
      unless profile.isKernel || profile.isUser do
        throw "checked Action.loop requires a kernel/user execution profile"
      let function ← match lookupActionFunction suite.actionFunctions callback with
        | .ok function => pure function
        | .error message => throw message
      unless function.signature.args.isEmpty do
        throw s!"checked Action.loop callback `{callback}` has the wrong signature"
      let symbol ← match lookupSymbol symbols callback with
        | .ok symbol => pure symbol
        | .error message => throw message
      let repeatLabel ← freshBlock "action.loop.repeat"
      let failureLabel ← freshBlock "action.loop.failure"
      let _ ← finishBlock (.jump repeatLabel)
      startBlock repeatLabel
      let aggregate ← freshValue "action.loop.result"
      emit (.abiCall (some aggregate) .checkedResult none symbol #[])
      let statusWord ← freshValue "action.loop.status-word"
      let status ← freshValue "action.loop.status"
      let value ← freshValue "action.loop.value"
      emit (.extractResultStatus statusWord (.local aggregate))
      emit (.trunc status .i64 (.local statusWord) .i8)
      emit (.extractResultValue value (.local aggregate))
      let succeeded ← freshValue "action.loop.succeeded"
      emit (.icmp succeeded .eq .i8 (.local status) (.int .i8 0))
      let _ ← finishBlock (.branch (.local succeeded) repeatLabel failureLabel)
      startBlock failureLabel
      pure { status := .local status, value := .local value }
  | .boundedFoldU64 budget callback count initial ctx0 ctx1 ctx2 ctx3 status value next => do
      let maximumBudget := if profile == .v0_5 || profile == .v0_6 ||
          profile == .v0_7 || profile.isExecution then
        Lemma.Core0.Memory.maximumBudgetV05
      else
        Lemma.Core0.Memory.maximumBudgetV04
      unless budget ≤ maximumBudget do
        throw s!"checked Action fold budget {budget} exceeds {maximumBudget}"
      unless count.type == .u32 && initial.type == .u64 && ctx0.type == .u64 &&
          ctx1.type == .u64 && ctx2.type == .u64 && ctx3.type == .u64 &&
          status.ty == .u8 && value.ty == .u64 do
        throw "checked Action fold has an inconsistent type"
      let callbackFunction ← match lookupActionFunction suite.actionFunctions callback with
        | .ok function => pure function
        | .error message => throw message
      let callbackArgs : Array Lemma.Core0.Ty :=
        #[.u32, .u32, .u64, .u64, .u64, .u64, .u64]
      unless callbackFunction.signature.args == callbackArgs do
        throw s!"checked Action fold callback `{callback}` has the wrong signature"
      let callbackSymbol ← match lookupSymbol symbols callback with
        | .ok symbol => pure symbol
        | .error message => throw message

      let count ← lowerExprCFG profile suite.scalarFunctions symbols count
      let initial ← lowerExprCFG profile suite.scalarFunctions symbols initial
      let ctx0 ← lowerExprCFG profile suite.scalarFunctions symbols ctx0
      let ctx1 ← lowerExprCFG profile suite.scalarFunctions symbols ctx1
      let ctx2 ← lowerExprCFG profile suite.scalarFunctions symbols ctx2
      let ctx3 ← lowerExprCFG profile suite.scalarFunctions symbols ctx3

      let withinBudget ← freshValue "action.fold.within-budget"
      let indexName ← freshValue "action.fold.index"
      let accumulatorName ← freshValue "action.fold.accumulator"
      let continueLoop ← freshValue "action.fold.continue"
      let callbackAggregate ← freshValue "action.fold.callback-result"
      let callbackStatusWord ← freshValue "action.fold.callback-status-word"
      let callbackStatus ← freshValue "action.fold.callback-status"
      let callbackValue ← freshValue "action.fold.callback-value"
      let callbackOk ← freshValue "action.fold.callback-ok"
      let nextIndex ← freshValue "action.fold.next-index"
      let resultStatus ← freshValue "action.fold.status"
      let resultValue ← freshValue "action.fold.value"

      let preheaderLabel ← freshBlock "action.fold.preheader"
      let exhaustedLabel ← freshBlock "action.fold.exhausted"
      let headerLabel ← freshBlock "action.fold.header"
      let bodyLabel ← freshBlock "action.fold.body"
      let continueLabel ← freshBlock "action.fold.latch"
      let stoppedLabel ← freshBlock "action.fold.stopped"
      let doneLabel ← freshBlock "action.fold.done"
      let outcomeLabel ← freshBlock "action.fold.outcome"

      emit (.icmp withinBudget .ule .i32 count (.int .i32 budget))
      let _ ← finishBlock (.branch (.local withinBudget) preheaderLabel exhaustedLabel)

      startBlock exhaustedLabel
      let exhaustedExit ← finishBlock (.jump outcomeLabel)

      startBlock preheaderLabel
      let preheaderExit ← finishBlock (.jump headerLabel)

      startBlock headerLabel
      emit (.phi indexName .i32
        #[(.int .i32 0, preheaderExit), (.local nextIndex, continueLabel)])
      emit (.phi accumulatorName .i64
        #[(initial, preheaderExit), (.local callbackValue, continueLabel)])
      emit (.icmp continueLoop .ult .i32 (.local indexName) count)
      let _ ← finishBlock (.branch (.local continueLoop) bodyLabel doneLabel)

      startBlock bodyLabel
      emit (.abiCall (some callbackAggregate) .checkedResult none callbackSymbol #[
        { ty := .i32, value := .local indexName,
          extension := rv64LP64Extension .u32 },
        { ty := .i32, value := count,
          extension := rv64LP64Extension .u32 },
        { ty := .i64, value := .local accumulatorName, extension := none },
        { ty := .i64, value := ctx0, extension := none },
        { ty := .i64, value := ctx1, extension := none },
        { ty := .i64, value := ctx2, extension := none },
        { ty := .i64, value := ctx3, extension := none }
      ])
      emit (.extractResultStatus callbackStatusWord (.local callbackAggregate))
      emit (.trunc callbackStatus .i64 (.local callbackStatusWord) .i8)
      emit (.extractResultValue callbackValue (.local callbackAggregate))
      emit (.icmp callbackOk .eq .i8 (.local callbackStatus) (.int .i8 0))
      let _ ← finishBlock (.branch (.local callbackOk) continueLabel stoppedLabel)

      startBlock continueLabel
      emit (.bin nextIndex .add .i32 (.local indexName) (.int .i32 1))
      let continueExit ← finishBlock (.jump headerLabel)
      unless continueExit == continueLabel do
        throw "internal Action-fold latch label mismatch"

      startBlock stoppedLabel
      let stoppedExit ← finishBlock (.jump outcomeLabel)

      startBlock doneLabel
      let doneExit ← finishBlock (.jump outcomeLabel)

      startBlock outcomeLabel
      emit (.phi resultStatus .i8 #[
        (statusOperand Lemma.Core0.Memory.Status.budgetExceeded, exhaustedExit),
        (.local callbackStatus, stoppedExit),
        (statusOperand Lemma.Core0.Memory.Status.ok, doneExit)
      ])
      emit (.phi resultValue .i64 #[
        (initial, exhaustedExit),
        (.local callbackValue, stoppedExit),
        (.local accumulatorName, doneExit)
      ])
      withLocal status.id (.local resultStatus) do
        withLocal value.id (.local resultValue) do
          lowerActionExpr profile suite symbols next
  | .uartReadStatus status value next => do
      unless profile == .v0_5 || profile == .v0_6 || profile == .v0_7 ||
          profile.isFirmware || profile.isKernel || profile.isBoot do
        throw s!"UART status reads require `{Lemma.Core0.Profile.v0_5.contractVersion}`"
      unless status.ty == .u8 && value.ty == .u64 do
        throw "checked UART status read has an inconsistent continuation type"
      let site ← freshDeviceSite
      let byte ← freshValue "uart.lsr.byte."
      let word ← freshValue "uart.lsr.word."
      emit (.uartRead8 byte site .lsr)
      emit (.zext word .i8 (.local byte) .i64)
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        withLocal value.id (.local word) do
          lowerActionExpr profile suite symbols next
  | .uartReadByte status value next => do
      unless profile == .v0_5 || profile == .v0_6 || profile == .v0_7 ||
          profile.isFirmware || profile.isKernel || profile.isBoot do
        throw s!"UART byte reads require `{Lemma.Core0.Profile.v0_5.contractVersion}`"
      unless status.ty == .u8 && value.ty == .u64 do
        throw "checked UART byte read has an inconsistent continuation type"
      let site ← freshDeviceSite
      let byte ← freshValue "uart.rbr.byte."
      let word ← freshValue "uart.rbr.word."
      emit (.uartRead8 byte site .rbr)
      emit (.zext word .i8 (.local byte) .i64)
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        withLocal value.id (.local word) do
          lowerActionExpr profile suite symbols next
  | .uartWriteByte value status next => do
      unless profile == .v0_5 || profile == .v0_6 || profile == .v0_7 ||
          profile.isFirmware || profile.isKernel || profile.isBoot do
        throw s!"UART byte writes require `{Lemma.Core0.Profile.v0_5.contractVersion}`"
      unless value.type == .u8 && status.ty == .u8 do
        throw "checked UART byte write has an inconsistent type"
      let value ← lowerExprCFG profile suite.scalarFunctions symbols value
      let site ← freshDeviceSite
      emit (.uartWrite8 site value)
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        lowerActionExpr profile suite symbols next
  | .uartEnableAndResetFifo status next => do
      unless profile == .v0_5 || profile == .v0_6 || profile == .v0_7 ||
          profile.isFirmware || profile.isKernel || profile.isBoot do
        throw s!"UART FIFO control requires `{Lemma.Core0.Profile.v0_5.contractVersion}`"
      unless status.ty == .u8 do
        throw "checked UART FIFO control has an inconsistent continuation type"
      let site ← freshDeviceSite
      emit (.uartEnableAndResetFifo site)
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        lowerActionExpr profile suite symbols next
  | .uartEnableAndResetFifo14 status next => do
      unless profile == .kernel_v0_2 || profile == .kernel_v0_3 || profile == .kernel_v0_4 || profile == .kernel_v0_5 || profile == .kernel_v0_6 || profile == .kernel_v0_7 do
        throw "UART FIFO trigger14 requires core0-kernel-v0.2"
      unless status.ty == .u8 do
        throw "checked kernel FIFO control has an inconsistent continuation type"
      let site ← freshDeviceSite
      emit (.uartEnableAndResetFifo14 site)
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        lowerActionExpr profile suite symbols next
  | .trap operation status value next => do
      unless profile == .v0_6 || profile == .v0_7 do
        throw s!"synchronous trap operations require `{Lemma.Core0.Profile.v0_6.contractVersion}`"
      unless status.ty == .u8 && value.ty == .u64 do
        throw "checked synchronous trap has an inconsistent continuation type"
      let mask ← freshValue "trap.context-mask."
      emit (.abiCall (some mask) .i64 none operation.llvmSymbol #[])
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        withLocal value.id (.local mask) do
          lowerActionExpr profile suite symbols next
  | .timer operation argument? status value next => do
      unless profile == .v0_7 do
        throw s!"timer/interrupt operations require `{Lemma.Core0.Profile.v0_7.contractVersion}`"
      unless status.ty == .u8 && value.ty == .u64 do
        throw "checked timer operation has an inconsistent continuation type"
      let some spec := Lemma.Core0.Timer.findSpec? operation
        | throw s!"checked timer operation `{operation.stableId}` is absent from its catalog"
      let mut arguments : Array LLVM.ABIArgument := #[]
      match spec.sourceArguments, spec.machineArguments, argument? with
      | sourceArgs, machineArgs, none =>
          unless sourceArgs.isEmpty && machineArgs.isEmpty do
            throw s!"checked timer operation `{operation.stableId}` omitted its argument"
      | sourceArgs, machineArgs, some argument =>
          let some sourceTy := sourceArgs[0]?
            | throw s!"checked timer operation `{operation.stableId}` has a spurious argument"
          let some machineTy := machineArgs[0]?
            | throw s!"timer ABI for `{operation.stableId}` omitted its machine argument"
          unless sourceArgs.size == 1 && machineArgs.size == 1 &&
              argument.type == sourceTy do
            throw s!"checked timer operation `{operation.stableId}` has an inconsistent argument"
          let lowered ← lowerExprCFG profile suite.scalarFunctions symbols argument
          let abiValue ← if sourceTy == .bool && machineTy == .u64 &&
              spec.canonicalBoolArgument then do
            let canonical ← freshValue "timer.bool-u64."
            emit (.zext canonical .i1 lowered .i64)
            pure (.local canonical)
          else if sourceTy == .u64 && machineTy == .u64 &&
              !spec.canonicalBoolArgument then
            pure lowered
          else
            throw s!"timer ABI for `{operation.stableId}` is outside the closed lowering"
          arguments := arguments.push { ty := .i64, value := abiValue, extension := none }
      let primitiveResult ← freshValue "timer.result."
      emit (.abiCall (some primitiveResult) .i64 none operation.llvmSymbol arguments)
      let logicalValue := if spec.resultMeaning == .zero then
        LLVM.Operand.int .i64 0
      else
        .local primitiveResult
      withLocal status.id (statusOperand Lemma.Core0.Memory.Status.ok) do
        withLocal value.id logicalValue do
          lowerActionExpr profile suite symbols next
  | .platform operation arguments status value next => do
      unless operation.admits profile do
        throw s!"execution operation `{operation.stableId}` is denied by `{profile.contractVersion}`"
      unless arguments.size == 6 && status.ty == .u8 && value.ty == .u64 do
        throw "checked execution operation has an inconsistent signature"
      let mut loweredArguments : Array LLVM.Operand := #[]
      for index in [:arguments.size] do
        let argument := arguments[index]!
        unless argument.type == .u64 do throw "execution argument must have type u64"
        if index ≥ operation.argumentCount then
          unless argument == .lit .u64 0 do
            throw "unused execution operand must be literal zero"
        loweredArguments := loweredArguments.push
          (← lowerExprCFG profile suite.scalarFunctions symbols argument)
      let outcome ← if operation.widthBytes?.isSome then
        lowerExecutionMemory profile operation loweredArguments
      else if operation == .forwardSupervisor then do
        let some enabled := loweredArguments[0]?
          | throw "supervisor forwarding omitted its canonical Boolean"
        let valid ← freshValue "execution.forward.canonical."
        let callLabel ← freshBlock "execution.forward.call"
        let deniedLabel ← freshBlock "execution.forward.denied"
        let mergeLabel ← freshBlock "execution.forward.outcome"
        emit (.icmp valid .ule .i64 enabled (.int .i64 1))
        let _ ← finishBlock (.branch (.local valid) callLabel deniedLabel)
        startBlock deniedLabel
        let deniedExit ← finishBlock (.jump mergeLabel)
        startBlock callLabel
        let called ← lowerExecutionCall operation loweredArguments
        let calledExit ← finishBlock (.jump mergeLabel)
        startBlock mergeLabel
        let status ← freshValue "execution.forward.status."
        let value ← freshValue "execution.forward.value."
        emit (.phi status .i8 #[(statusOperand Lemma.Core0.Memory.Status.invalidLength, deniedExit),
          (called.status, calledExit)])
        emit (.phi value .i64 #[(.int .i64 0, deniedExit), (called.value, calledExit)])
        pure { status := .local status, value := .local value }
      else lowerExecutionCall operation loweredArguments
      withLocal status.id outcome.status do
        withLocal value.id outcome.value do
          lowerActionExpr profile suite symbols next
termination_by action => sizeOf action

private def lowerScalarActionFunction (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedActionSuite)
    (symbols : Array Symbol) (options : SuiteLowerOptions)
    (function : Lemma.Core0.Function) : Except String LLVM.Function := do
  let parameters := function.params.mapIdx fun index param =>
    ({ ty := llvmTy param.ty, name := s!"arg{index}" } : LLVM.Parameter)
  let parameterExtensions := function.params.map fun param => rv64LP64Extension param.ty
  let locals := function.params.mapIdx (fun index param =>
    (param.id, LLVM.Operand.local s!"arg{index}")) |>.toList
  let initial : CFGState := { locals }
  let (result, state) ←
    lowerExprCFG profile suite.scalarFunctions symbols function.body |>.run initial
  let finalState ← match
      finishBlock (.ret (llvmTy function.signature.result) result) |>.run state with
    | .ok (_, state) => pure state
    | .error message => throw message
  let symbol ← lookupSymbol symbols function.name
  let isPreserved := options.preserveCalls.contains function.name
  let lowered : LLVM.Function := {
    name := symbol
    returnType := llvmTy function.signature.result
    returnExtension := rv64LP64Extension function.signature.result
    parameters
    parameterExtensions
    linkage := if isPreserved then none else some "internal"
    attributes := if options.inlineLiteralConstants && (closedLiteral? function).isSome then
      #["nounwind", "alwaysinline"]
    else if isPreserved then
      #["nounwind", "noinline", "\"disable-tail-calls\"=\"true\""]
    else #["nounwind"]
    blocks := finalState.blocks
  }
  LLVM.validateFunction lowered
  pure lowered

private def lowerActionFunction (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedActionSuite)
    (symbols : Array Symbol) (options : SuiteLowerOptions)
    (firstDeviceSite : Nat) (function : Lemma.Core0.ActionFunction) :
    Except String (LLVM.Function × Nat) := do
  let parameters := function.params.mapIdx fun index param =>
    ({ ty := llvmTy param.ty, name := s!"arg{index}" } : LLVM.Parameter)
  let parameterExtensions := function.params.map fun param => rv64LP64Extension param.ty
  let locals := function.params.mapIdx (fun index param =>
    (param.id, LLVM.Operand.local s!"arg{index}")) |>.toList
  let initial : CFGState := { locals, nextDeviceSite := firstDeviceSite }
  let (outcome, state) ←
    lowerActionExpr profile suite symbols function.body |>.run initial
  -- Run the final sequence as one stateful action so fresh-name state is retained.
  let finalize : CFGM Unit := do
    let statusWord ← freshValue "action.result.status-word"
    let partialResult ← freshValue "action.result.partial"
    let completeResult ← freshValue "action.result.complete"
    emit (.zext statusWord .i8 outcome.status .i64)
    emit (.insertResultStatus partialResult (.local statusWord))
    emit (.insertResultValue completeResult (.local partialResult) outcome.value)
    let _ ← finishBlock (.ret .checkedResult (.local completeResult))
    pure ()
  let (_, finalState) ← finalize.run state
  let symbol ← lookupSymbol symbols function.name
  let isRoot := suite.roots.any fun root => root.source == function.name
  let isPreserved := options.preserveCalls.contains function.name
  let lowered : LLVM.Function := {
    name := symbol
    returnType := .checkedResult
    returnExtension := none
    parameters
    parameterExtensions
    linkage := if isRoot || isPreserved then none else some "internal"
    attributes := if (options.inlinePrimitiveWrappers && (checkedPrimitiveWrapper? function).isSome) ||
        (options.inlineUserWordWrappers && (checkedUserWordWrapper? function).isSome) then
      #["nounwind", "alwaysinline"]
    else if isPreserved then
      #["nounwind", "noinline", "\"disable-tail-calls\"=\"true\""]
    else #["nounwind"]
    blocks := finalState.blocks
  }
  LLVM.validateFunction lowered
  pure (lowered, finalState.nextDeviceSite)

private def lowerActionSuiteForProfile (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedActionSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredActionSuite := do
  validateSymbolPrefix options.symbolPrefix
  if options.inlineUserWordWrappers && profile != .user_v0_2 && profile != .user_v0_3 && profile != .user_v0_4 && profile != .user_v0_5 then
    throw "checked virtual word wrapper optimization requires core0-user-v0.2"
  unless profile == .v0_4 || profile == .v0_5 || profile == .v0_6 ||
      profile == .v0_7 || profile.isExecution do
    throw "Action lowering requires profile core0-v0.4, core0-v0.5, core0-v0.6, or core0-v0.7"
  unless suite.contractVersion == profile.contractVersion do
    throw s!"Action lowering requires `{profile.contractVersion}`, got `{suite.contractVersion}`"
  unless Lemma.Core0.Memory.tableValid do
    throw "the compiled fixed-region table is internally invalid"
  let mut actualDeviceOps : Array Lemma.Core0.Device.Op := #[]
  for function in suite.actionFunctions do
    actualDeviceOps := collectDeviceOps actualDeviceOps function.body
  let mut seenDeviceMetadata : Array Lemma.Core0.Device.Op := #[]
  for operation in suite.usedDeviceOps do
    if operation == .uartEnableAndResetFifo14 && profile != .kernel_v0_2 && profile != .kernel_v0_3 && profile != .kernel_v0_4 && profile != .kernel_v0_5 && profile != .kernel_v0_6 && profile != .kernel_v0_7 then
      throw s!"device operation `{operation.stableId}` is denied by `{profile.contractVersion}`"
    if seenDeviceMetadata.contains operation then
      throw s!"checked Action suite repeats device metadata `{operation.stableId}`"
    seenDeviceMetadata := seenDeviceMetadata.push operation
    let some spec := Lemma.Core0.Device.findSpec? operation
      | throw s!"checked Action suite names uncatalogued device operation `{operation.stableId}`"
    unless spec == expectedDeviceSpec operation do
      throw s!"device operation `{operation.stableId}` disagrees with the closed backend contract"
  unless actualDeviceOps.size == suite.usedDeviceOps.size &&
      actualDeviceOps.all suite.usedDeviceOps.contains &&
      suite.usedDeviceOps.all actualDeviceOps.contains do
    throw "checked Action suite has stale device-operation metadata"
  let mut actualTrapOps : Array Lemma.Core0.Trap.Op := #[]
  for function in suite.actionFunctions do
    actualTrapOps := collectTrapOps actualTrapOps function.body
  let mut seenTrapMetadata : Array Lemma.Core0.Trap.Op := #[]
  for operation in suite.usedTrapOps do
    if seenTrapMetadata.contains operation then
      throw s!"checked Action suite repeats trap metadata `{operation.stableId}`"
    seenTrapMetadata := seenTrapMetadata.push operation
    let some spec := Lemma.Core0.Trap.findSpec? operation
      | throw s!"checked Action suite names uncatalogued trap operation `{operation.stableId}`"
    unless spec == expectedTrapSpec operation do
      throw s!"trap operation `{operation.stableId}` disagrees with the closed backend contract"
  unless actualTrapOps.size == suite.usedTrapOps.size &&
      actualTrapOps.all suite.usedTrapOps.contains &&
      suite.usedTrapOps.all actualTrapOps.contains do
    throw "checked Action suite has stale trap-operation metadata"
  let mut actualTimerOps : Array Lemma.Core0.Timer.Op := #[]
  for function in suite.actionFunctions do
    actualTimerOps := collectTimerOps actualTimerOps function.body
  let mut seenTimerMetadata : Array Lemma.Core0.Timer.Op := #[]
  for operation in suite.usedTimerOps do
    if seenTimerMetadata.contains operation then
      throw s!"checked Action suite repeats timer metadata `{operation.stableId}`"
    seenTimerMetadata := seenTimerMetadata.push operation
    let some spec := Lemma.Core0.Timer.findSpec? operation
      | throw s!"checked Action suite names uncatalogued timer operation `{operation.stableId}`"
    unless spec == expectedTimerSpec operation do
      throw s!"timer operation `{operation.stableId}` disagrees with the closed backend contract"
  unless actualTimerOps.size == suite.usedTimerOps.size &&
      actualTimerOps.all suite.usedTimerOps.contains &&
      suite.usedTimerOps.all actualTimerOps.contains do
    throw "checked Action suite has stale timer-operation metadata"
  let mut actualExecutionOps : Array Lemma.Core0.Execution.OpSpec := #[]
  for function in suite.actionFunctions do
    actualExecutionOps := collectExecutionOps actualExecutionOps function.body
  let mut seenExecutionOps : Array Lemma.Core0.Execution.OpSpec := #[]
  for spec in suite.usedExecutionOps do
    if seenExecutionOps.contains spec then throw "checked Action suite repeats execution metadata"
    seenExecutionOps := seenExecutionOps.push spec
    unless spec == Lemma.Core0.Execution.specification spec.operation do
      throw "checked execution primitive signature disagrees with the closed catalog"
    unless spec.operation.admits profile do
      throw s!"execution operation `{spec.stableId}` is denied by `{profile.contractVersion}`"
  unless actualExecutionOps.size == suite.usedExecutionOps.size &&
      actualExecutionOps.all suite.usedExecutionOps.contains &&
      suite.usedExecutionOps.all actualExecutionOps.contains do
    throw "checked Action suite has stale execution-operation metadata"
  let mut actualLoops : Array Lemma.Core0.ActionLoopUse := #[]
  for function in suite.actionFunctions do
    let localLoops := collectActionLoops #[] function.body
    for use in localLoops do
      unless function.actionDependencies.contains use.callback do
        throw s!"checked Action.loop callback `{use.callback}` is absent from its dependency metadata"
    actualLoops := collectActionLoops actualLoops function.body
  let mut seenLoops : Array Lemma.Core0.ActionLoopUse := #[]
  for use in suite.usedLoops do
    if seenLoops.contains use then throw "checked Action suite repeats loop metadata"
    seenLoops := seenLoops.push use
    unless use.stableId == "action.loop" do throw "checked Action suite has unknown loop identity"
  unless actualLoops.size == suite.usedLoops.size && actualLoops.all suite.usedLoops.contains &&
      suite.usedLoops.all actualLoops.contains do
    throw "checked Action suite has stale loop metadata"
  unless actualLoops.isEmpty || profile.isKernel || profile.isUser do
    throw "checked Action.loop is denied outside kernel/user execution profiles"
  if profile.isExecution then
    unless Lemma.Core0.Execution.catalogValid && Lemma.Core0.Execution.memoryRegionsValid profile do
      throw "production execution catalog or authority intervals are invalid"
    unless suite.usedMemoryOps.isEmpty && suite.usedTrapOps.isEmpty && suite.usedTimerOps.isEmpty do
      throw "production profiles reject diagnostic memory/trap/timer metadata"
  if profile.isUser && !actualDeviceOps.isEmpty then
    throw "user profile rejects direct MMIO operations"
  if profile == .v0_4 && !actualDeviceOps.isEmpty then
    throw s!"device operations require `{Lemma.Core0.Profile.v0_5.contractVersion}`"
  if (profile == .v0_4 || profile == .v0_5) && !actualTrapOps.isEmpty then
    throw s!"trap operations require `{Lemma.Core0.Profile.v0_6.contractVersion}`"
  if profile != .v0_7 && !actualTimerOps.isEmpty then
    throw s!"timer operations require `{Lemma.Core0.Profile.v0_7.contractVersion}`"
  if profile == .v0_5 || profile == .v0_6 || profile == .v0_7 ||
      profile.isFirmware || profile.isKernel || profile.isBoot then
    unless Lemma.Core0.Device.catalogValid && deviceCatalogMatchesBackend &&
        Lemma.Core0.Device.UART.base.toNat == LLVM.UARTReadRegister.rbr.address &&
        Lemma.Core0.Device.UART.base.toNat + Lemma.Core0.Device.UART.lsrOffset.toNat ==
          LLVM.UARTReadRegister.lsr.address &&
        Lemma.Core0.Device.UART.base.toNat == 0x10000000 &&
        Lemma.Core0.Device.UART.rbrThrOffset.toNat == 0 &&
        Lemma.Core0.Device.UART.fcrOffset.toNat == 2 &&
        Lemma.Core0.Device.UART.lsrOffset.toNat == 5 &&
        Lemma.Core0.Device.UART.registerWidthBytes == 1 &&
        Lemma.Core0.Device.UART.fcrEnableAndReset.toNat == 0x07 do
      throw "the compiled core0-v0.5 UART catalog disagrees with the closed LLVM lowering"
  if profile == .kernel_v0_2 || profile == .kernel_v0_3 || profile == .kernel_v0_4 || profile == .kernel_v0_5 || profile == .kernel_v0_6 || profile == .kernel_v0_7 then
    unless Lemma.Core0.Device.kernelCatalogValid && kernelDeviceCatalogMatchesBackend &&
        Lemma.Core0.Device.UART.fcrEnableAndReset14.toNat == 0xc7 do
      throw "the compiled kernel-v0.2 UART catalog disagrees with the closed LLVM lowering"
  if profile == .v0_6 || profile == .v0_7 then
    unless Lemma.Core0.Trap.catalogValid && trapCatalogMatchesBackend do
      throw "the compiled core0-v0.6 trap catalog disagrees with the closed LLVM lowering"
  if profile == .v0_7 then
    unless Lemma.Core0.Timer.catalogValid && timerCatalogMatchesBackend &&
        Lemma.Core0.Timer.MachineTimer.timeAddress.toNat == 0x0200bff8 &&
        Lemma.Core0.Timer.MachineTimer.compareAddress.toNat == 0x02004000 &&
        Lemma.Core0.Timer.MachineTimer.registerWidthBytes == 8 do
      throw "the compiled core0-v0.7 timer catalog disagrees with the closed machine ABI"
  unless !suite.roots.isEmpty do throw "checked Action suite has no roots"
  unless !suite.actionFunctions.isEmpty do throw "checked Action suite has no functions"

  let mut seenScalar : Array Lean.Name := #[]
  for function in suite.scalarFunctions do
    if seenScalar.contains function.name then
      throw s!"checked Action suite contains duplicate scalar function `{function.name}`"
    unless function.params.size == function.signature.args.size &&
        function.body.type == function.signature.result do
      throw s!"checked scalar dependency `{function.name}` has an inconsistent signature"
    let missing := function.dependencies.filter fun dependency =>
      !seenScalar.contains dependency
    unless missing.isEmpty do
      throw s!"checked scalar dependency `{function.name}` is not dependency-first"
    seenScalar := seenScalar.push function.name

  let mut seenActions : Array Lean.Name := #[]
  for function in suite.actionFunctions do
    if seenActions.contains function.name then
      throw s!"checked Action suite contains duplicate Action function `{function.name}`"
    unless function.params.size == function.signature.args.size do
      throw s!"checked Action function `{function.name}` has inconsistent parameter arity"
    for h : index in [:function.params.size] do
      unless function.params[index].ty == function.signature.args[index]! do
        throw s!"checked Action function `{function.name}` has an inconsistent parameter type"
    for dependency in function.scalarDependencies do
      unless seenScalar.contains dependency do
        throw s!"Action function `{function.name}` names missing scalar dependency `{dependency}`"
    let actualDirectEffects := directActionEffects function.body
    unless function.directEffects.checkedAccess == actualDirectEffects.checkedAccess &&
        function.directEffects.ramRead == actualDirectEffects.ramRead &&
        function.directEffects.ramWrite == actualDirectEffects.ramWrite do
      throw s!"checked Action function `{function.name}` has stale direct memory effects"
    unless function.directEffects.mmioRead ==
          actualDirectEffects.mmioRead &&
        function.directEffects.mmioWrite == actualDirectEffects.mmioWrite &&
        function.directEffects.ioOrder == actualDirectEffects.ioOrder do
      throw s!"checked Action function `{function.name}` has stale direct device effects"
    unless function.directEffects.syncTrap == actualDirectEffects.syncTrap &&
        function.directEffects.machineState == actualDirectEffects.machineState do
      throw s!"checked Action function `{function.name}` has stale direct trap effects"
    unless function.directEffects.timerState == actualDirectEffects.timerState &&
        function.directEffects.interruptState == actualDirectEffects.interruptState do
      throw s!"checked Action function `{function.name}` has stale direct timer effects"
    unless function.directEffects == actualDirectEffects do
      throw s!"checked Action function `{function.name}` has stale direct effects"
    let missing := function.actionDependencies.filter fun dependency =>
      !seenActions.contains dependency
    unless missing.isEmpty do
      throw s!"checked Action function `{function.name}` is not dependency-first"
    let mut expectedEffects := function.directEffects
    for dependency in function.actionDependencies do
      let callee ← lookupActionFunction suite.actionFunctions dependency
      expectedEffects := expectedEffects ∪ callee.effects
    unless expectedEffects == function.effects do
      throw s!"checked Action function `{function.name}` has stale transitive effects"
    seenActions := seenActions.push function.name

  let mut seenRoots : Array Lean.Name := #[]
  for h : index in [:suite.roots.size] do
    let root := suite.roots[index]
    unless root.id == index + 1 do
      throw s!"checked Action root `{root.source}` has non-canonical id {root.id}"
    if seenRoots.contains root.source then
      throw s!"checked Action suite contains duplicate root `{root.source}`"
    let function ← lookupActionFunction suite.actionFunctions root.source
    unless function.signature == root.signature do
      throw s!"checked Action root `{root.source}` has an inconsistent signature"
    seenRoots := seenRoots.push root.source

  let mut seenPreserved : Array Lean.Name := #[]
  for name in options.preserveCalls do
    if seenPreserved.contains name then
      throw s!"preserved-call set contains duplicate declaration `{name}`"
    unless seenScalar.contains name || seenActions.contains name do
      throw s!"preserved-call declaration `{name}` is absent from the Action suite"
    seenPreserved := seenPreserved.push name

  let scalarSymbols := suite.scalarFunctions.mapIdx fun index function =>
    ({ source := function.name, llvm := s!"{options.symbolPrefix}core0_scalar_{index}" } : Symbol)
  let actionSymbols := suite.actionFunctions.mapIdx fun index function =>
    ({ source := function.name, llvm := s!"{options.symbolPrefix}core0_action_{index}" } : Symbol)
  let symbols := scalarSymbols ++ actionSymbols
  let mut functions : Array LLVM.Function := #[]
  for function in suite.scalarFunctions do
    functions := functions.push
      (← lowerScalarActionFunction profile suite symbols options function)
  let mut nextDeviceSite := 0
  for function in suite.actionFunctions do
    let (loweredFunction, followingDeviceSite) ←
      lowerActionFunction profile suite symbols options nextDeviceSite function
    functions := functions.push loweredFunction
    nextDeviceSite := followingDeviceSite
  let mut roots : Array LoweredActionRoot := #[]
  for root in suite.roots do
    roots := roots.push {
      id := root.id
      source := root.source
      llvm := ← lookupSymbol symbols root.source
      signature := root.signature
    }
  let mut inlineLiterals : Array ClosedLiteral := #[]
  if options.inlineLiteralConstants then
    for function in suite.scalarFunctions do
      if let some (ty, value) := closedLiteral? function then
        inlineLiterals := inlineLiterals.push {
          source := function.name, symbol := ← lookupSymbol symbols function.name, ty, value }
  let mut inlineWrappers : Array CheckedPrimitiveWrapper := #[]
  if options.inlinePrimitiveWrappers then
    for function in suite.actionFunctions do
      if let some operation := checkedPrimitiveWrapper? function then
        inlineWrappers := inlineWrappers.push {
          source := function.name, symbol := ← lookupSymbol symbols function.name,
          operation, effects := function.effects }
  let mut inlineUserWrappers : Array CheckedPrimitiveWrapper := #[]
  if options.inlineUserWordWrappers then
    for function in suite.actionFunctions do
      if let some operation := checkedUserWordWrapper? function then
        inlineUserWrappers := inlineUserWrappers.push {
          source := function.name, symbol := ← lookupSymbol symbols function.name,
          operation, effects := function.effects }
  pure { functions, symbols, roots, inlineLiterals, inlineWrappers, inlineUserWrappers }

/-- Lower a complete checked `core0-v0.4` fixed-region Action suite.  Device
constructors remain rejected by both the v0.4 checker and this backend entry. -/
def lowerActionSuiteV04 (suite : Lemma.Core0.CheckedActionSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredActionSuite :=
  lowerActionSuiteForProfile .v0_4 suite options

/-- Lower a checked `core0-v0.5` Action suite with the four closed ordered UART
operations in addition to the unchanged v0.4 fixed-region path. -/
def lowerActionSuiteV05 (suite : Lemma.Core0.CheckedActionSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredActionSuite :=
  lowerActionSuiteForProfile .v0_5 suite options

/-- Lower a checked `core0-v0.6` Action suite with the unchanged v0.5 UART path
and the four closed synchronous-trap primitive calls. -/
def lowerActionSuiteV06 (suite : Lemma.Core0.CheckedActionSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredActionSuite :=
  lowerActionSuiteForProfile .v0_6 suite options

/-- Lower a checked `core0-v0.7` Action suite with the unchanged UART/trap paths
and the seven closed timer/interrupt primitive calls. -/
def lowerActionSuiteV07 (suite : Lemma.Core0.CheckedActionSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredActionSuite :=
  lowerActionSuiteForProfile .v0_7 suite options

/-- Privilege-specific production Action lowering; diagnostic profiles cannot
enter through this interface. -/
def lowerActionSuiteExecution (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedActionSuite) (options : SuiteLowerOptions := {}) :
    Except String LoweredActionSuite := do
  unless profile.isExecution do throw "production lowering requires a production execution profile"
  lowerActionSuiteForProfile profile suite options

def lowerActionSuiteForExecution (profile : Lemma.Core0.Profile)
    (suite : Lemma.Core0.CheckedActionSuite) (options : SuiteLowerOptions := {}) :
    Except String LoweredActionSuite :=
  lowerActionSuiteExecution profile suite options

end Lemma.Compiler
