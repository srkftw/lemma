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

/-- Calling-convention mode used internally by lowering.  The legacy mode is kept
for the Task 001 artifact path; suites always select the reviewed RV64 LP64 mode. -/
private inductive LoweringABI where
  | legacy
  | rv64LP64

/-- Suite functions named here receive `noinline`, making selected source-level call
boundaries inspectable after optimization without changing ordinary lowering. -/
structure SuiteLowerOptions where
  preserveCalls : Array Lean.Name := #[]
  /-- Independent production objects may use a distinct checked symbol namespace.
  Empty preserves every historical symbol identity. -/
  symbolPrefix : String := ""
  /-- Opt-in Action-suite optimization of checked zero-argument literal scalars.
  Historical producers retain their original call boundaries by default. -/
  inlineLiteralConstants : Bool := false
  /-- Opt-in exact single physical-memory platform wrappers. No policy, device
  operation, virtual-memory operation or multi-step Action qualifies. -/
  inlinePrimitiveWrappers : Bool := false
  deriving Inhabited, Repr

def validateSymbolPrefix (symbolPrefix : String) : Except String Unit := do
  unless symbolPrefix.toList.all
      (fun character => "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_".toList.contains character) do
    throw "symbol prefix must contain only ASCII letters, digits, or underscores"
  if let some first := symbolPrefix.toList.head? then
    unless "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ_".toList.contains first do
      throw "symbol prefix must begin with an ASCII letter or underscore"

structure LoweredRoot where
  id : Nat
  source : Lean.Name
  llvm : String
  signature : Lemma.Core0.Signature
  deriving Repr, BEq

structure LoweredSuite where
  functions : Array LLVM.Function
  symbols : Array Symbol
  roots : Array LoweredRoot
  deriving Repr

/-- Width-preserving Core0 scalar representation in structured LLVM. -/
def llvmTy : Lemma.Core0.Ty → LLVM.Ty
  | .bool => .i1
  | .u8 => .i8
  | .u32 => .i32
  | .u64 => .i64

/-- Exact integer-extension attributes selected by the pinned RISC-V LP64 psABI.
`UInt32` uses `signext` to establish the ABI's XLEN carrier invariant; this does not
change Core0's unsigned source semantics. -/
def rv64LP64Extension : Lemma.Core0.Ty → Option LLVM.ABIExtension
  | .bool => some .zeroext
  | .u8 => some .zeroext
  | .u32 => some .signext
  | .u64 => none

private def llvmBinOp : Lemma.Core0.BinOp → LLVM.BinOp
  | .add => .add
  | .sub => .sub
  | .mul => .mul
  | .band => .and
  | .bor => .or
  | .bxor => .xor
  | .shl => .shl
  | .lshr => .lshr
  | .udiv => .udiv
  | .urem => .urem

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

private def lookupFunction (functions : Array Lemma.Core0.Function) (name : Lean.Name) :
    Except String Lemma.Core0.Function :=
  match functions.find? (fun function => function.name == name) with
  | some function => pure function
  | none => throw s!"checked Core0 call has no function definition for `{name}`"

private def withLocal (id : Nat) (value : LLVM.Operand) (action : LowerM α) : LowerM α := do
  let before ← get
  set { before with locals := (id, value) :: before.locals }
  let result ← action
  modify fun after => { after with locals := before.locals }
  pure result

private def lowerExpr (abi : LoweringABI) (functions : Array Lemma.Core0.Function)
    (symbols : Array Symbol) : Lemma.Core0.Expr → LowerM LLVM.Operand
  | .var id _ => lookupLocal id
  | .lit ty value => pure (.int (llvmTy ty) (normalizeLiteral ty value))
  | .boolLit value => pure (.int .i1 (if value then 1 else 0))
  | .letE id _ _ value body => do
      let value ← lowerExpr abi functions symbols value
      withLocal id value (lowerExpr abi functions symbols body)
  | .bin op ty lhs rhs => do
      if op == .shl || op == .lshr || op == .udiv || op == .urem then
        throw s!"{op.render} requires structured {Lemma.Core0.Profile.v0_2.contractVersion} lowering"
      let lhs ← lowerExpr abi functions symbols lhs
      let rhs ← lowerExpr abi functions symbols rhs
      let result ← fresh "bin"
      emit (.bin result (llvmBinOp op) (llvmTy ty) lhs rhs)
      pure (.local result)
  | .unary op _ _ =>
      throw s!"{op.render} requires structured {Lemma.Core0.Profile.v0_2.contractVersion} lowering"
  | .cmp op operandTy lhs rhs => do
      let lhs ← lowerExpr abi functions symbols lhs
      let rhs ← lowerExpr abi functions symbols rhs
      let result ← fresh "cmp"
      emit (.icmp result (llvmCmpOp op) (llvmTy operandTy) lhs rhs)
      pure (.local result)
  | .ite resultTy condition thenBranch elseBranch => do
      -- Core0 v0.1 is pure, first-order, total, and recursion-free.  Eagerly
      -- computing both scalar branches before `select` is therefore equivalent
      -- to Lean's conditional while avoiding an effect-sensitive CFG rule.
      let condition ← lowerExpr abi functions symbols condition
      let thenValue ← lowerExpr abi functions symbols thenBranch
      let elseValue ← lowerExpr abi functions symbols elseBranch
      let result ← fresh "select"
      emit (.select result condition (llvmTy resultTy) thenValue elseValue)
      pure (.local result)
  | .call callee resultTy args => do
      let symbol ← match lookupSymbol symbols callee with
        | .ok symbol => pure symbol
        | .error message => throw message
      match abi with
      | .legacy =>
          let some functionSymbol := symbols.find? (fun candidate => candidate.source == callee)
            | throw s!"missing checked function `{callee}`"
          let _ := functionSymbol
          let mut lowered : Array (LLVM.Ty × LLVM.Operand) := #[]
          -- Preserve the original Core0 v0.1 textual lowering exactly.
          for arg in args do
            lowered := lowered.push
              (llvmTy arg.type, ← lowerExpr abi functions symbols arg)
          let result ← fresh "call"
          emit (.call (some result) (llvmTy resultTy) symbol lowered)
          pure (.local result)
      | .rv64LP64 =>
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
              value := ← lowerExpr abi functions symbols argument
              extension := rv64LP64Extension expected
            }
            index := index + 1
          let result ← fresh "call"
          emit (.abiCall (some result) (llvmTy resultTy)
            (rv64LP64Extension resultTy) symbol lowered)
          pure (.local result)
  | .boundedFoldU32 .. =>
      throw s!"bounded iteration requires structured {Lemma.Core0.Profile.v0_3.contractVersion} lowering"
  | .cast op sourceTy targetTy value => do
      let value ← lowerExpr abi functions symbols value
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
  let (result, state) ← lowerExpr .legacy #[] symbols function.body |>.run initial
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
  unless program.contractVersion == Lemma.Core0.Profile.v0_1.contractVersion do
    throw s!"legacy lowering requires `{Lemma.Core0.Profile.v0_1.contractVersion}`, got `{program.contractVersion}`"
  unless !program.functions.isEmpty do
    throw "checked Core0 program has an empty function corpus"
  let symbols := program.functions.mapIdx fun index function =>
    ({ source := function.name, llvm := s!"core0_user_{index}" } : Symbol)
  let mut functions := #[]
  for function in program.functions do
    functions := functions.push (← lowerFunction symbols program.root function)
  let rootSymbol ← lookupSymbol symbols program.root
  pure { functions, symbols, rootSymbol }

private def lowerSuiteFunction (suite : Lemma.Core0.CheckedSuite)
    (symbols : Array Symbol) (options : SuiteLowerOptions)
    (function : Lemma.Core0.Function) : Except String LLVM.Function := do
  let parameters := function.params.mapIdx fun index param =>
    ({
      ty := llvmTy param.ty
      name := s!"arg{index}"
    } : LLVM.Parameter)
  let parameterExtensions := function.params.map fun param => rv64LP64Extension param.ty
  let locals := function.params.mapIdx (fun index param =>
    (param.id, LLVM.Operand.local s!"arg{index}")) |>.toList
  let initial : LowerState := { locals }
  let (result, state) ← lowerExpr .rv64LP64 suite.functions symbols function.body |>.run initial
  let symbol ← lookupSymbol symbols function.name
  let isRoot := suite.roots.any fun root => root.source == function.name
  let isPreserved := options.preserveCalls.contains function.name
  let attributes :=
    if isPreserved then
      #["nounwind", "noinline", "\"disable-tail-calls\"=\"true\""]
    else #["nounwind"]
  pure {
    name := symbol
    returnType := llvmTy function.signature.result
    returnExtension := rv64LP64Extension function.signature.result
    parameters
    parameterExtensions
    -- A preserved ABI boundary must keep the platform calling convention.  An
    -- internal function may be rewritten to `fastcc` by O2, which would erase
    -- the LP64 register/stack contract this dedicated test configuration audits.
    linkage := if isRoot || isPreserved then none else some "internal"
    attributes
    blocks := #[{
      label := "entry"
      instructions := state.instructions.push (.ret (llvmTy function.signature.result) result)
    }]
  }

/-- Lower a deduplicated multi-root corpus with exact RV64 LP64 scalar extension
attributes.  This is additive; `lowerApplication` remains the legacy artifact path. -/
def lowerSuite (suite : Lemma.Core0.CheckedSuite)
    (options : SuiteLowerOptions := {}) : Except String LoweredSuite := do
  validateSymbolPrefix options.symbolPrefix
  unless suite.contractVersion == "core0-v0.1" do
    throw s!"unsupported checked suite contract `{suite.contractVersion}`"
  unless !suite.roots.isEmpty do
    throw "checked Core0 suite has no declared roots"
  unless !suite.functions.isEmpty do
    throw "checked Core0 suite has an empty function corpus"
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
    functions := functions.push (← lowerSuiteFunction suite symbols options function)
  let mut roots := #[]
  for root in suite.roots do
    roots := roots.push {
      id := root.id
      source := root.source
      llvm := ← lookupSymbol symbols root.source
      signature := root.signature
    }
  pure { functions, symbols, roots }

def LoweredApplication.renderSymbolManifest (lowered : LoweredApplication) : String :=
  String.join <| lowered.symbols.toList.map fun symbol =>
    s!"source={symbol.source};llvm={symbol.llvm}\n"

def LoweredSuite.renderSymbolManifest (lowered : LoweredSuite) : String :=
  String.join <| lowered.symbols.toList.map fun symbol =>
    s!"source={symbol.source};llvm={symbol.llvm}\n"

end Lemma.Compiler
