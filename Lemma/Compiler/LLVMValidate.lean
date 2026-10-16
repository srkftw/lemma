import Lemma.Compiler.LLVMIR
import Lemma.Compiler.LLVMNameSets
import Std.Data.HashMap.Basic

/-!
Fail-closed validation for Lemma's structured LLVM subset.

The renderer in `LLVMIR` is intentionally small and total, but rendering alone does
not establish that a function is a well-formed control-flow graph or SSA program.
This module validates the closed representation before an exporter hands it to LLVM.

The checks here are deliberately stricter than general LLVM IR in a few places.  In
particular, every block must be reachable from the first block, the entry block may
not have predecessors, and the two successors of a conditional branch must differ.
Those restrictions match Lemma's structured generators and make predecessor/phi
accounting unambiguous.

This is a structural/type validator, not a semantic proof of source lowering.  In
particular, operation-specific premises such as a nonzero divisor or an in-range
shift count still need to be established by the checked lowering and independently
audited.  LLVM attributes, target data layout, global definitions, and machine-code
closure are likewise validated by their dedicated artifact audits.
-/

namespace Lemma.Compiler.LLVM

private def failAt (fn : Function) (message : String) : Except String α :=
  throw s!"LLVM validation `{fn.name}`: {message}"

private def failIn (fn : Function) (block : String) (message : String) : Except String α :=
  failAt fn s!"block `%{block}`: {message}"

private def insertName (names : Array String) (name : String) : Array String :=
  if names.contains name then names else names.push name

private def sameNameSet (lhs rhs : Array String) : Bool :=
  NameSets.equal lhs rhs

private def intersectNames (lhs rhs : Array String) : Array String :=
  NameSets.intersect lhs rhs

private def integerWidth? : Ty → Option Nat
  | .i1 => some 1
  | .i8 => some 8
  | .i32 => some 32
  | .i64 => some 64
  | .void | .ptr | .checkedResult => none

private def isInteger (ty : Ty) : Bool := integerWidth? ty |>.isSome

private def extensionAllowed (ty : Ty) (extension : Option ABIExtension) : Bool :=
  match extension with
  | none => true
  | some _ =>
      match integerWidth? ty with
      | some width => width < 64
      | none => false

private def isTerminator : Instruction → Bool
  | .branch .. | .jump .. | .ret .. | .retVoid | .unreachable => true
  | _ => false

private def successors : Instruction → Array String
  | .branch _ onTrue onFalse => #[onTrue, onFalse]
  | .jump target => #[target]
  | _ => #[]

private def resultDefinition? : Instruction → Option (String × Ty)
  | .bin result _ ty _ _ => some (result, ty)
  | .icmp result _ _ _ _ => some (result, .i1)
  | .zext result _ _ targetTy => some (result, targetTy)
  | .sext result _ _ targetTy => some (result, targetTy)
  | .trunc result _ _ targetTy => some (result, targetTy)
  | .select result _ ty _ _ => some (result, ty)
  | .ptrFromInt result _ => some (result, .ptr)
  | .intToPtr result _ => some (result, .ptr)
  | .load result ty _ _ _ => some (result, ty)
  | .uartRead8 result _ _ => some (result, .i8)
  | .insertResultStatus result _ => some (result, .checkedResult)
  | .insertResultValue result _ _ => some (result, .checkedResult)
  | .extractResultStatus result _ => some (result, .i64)
  | .extractResultValue result _ => some (result, .i64)
  | .call (some result) returnType _ _ => some (result, returnType)
  | .abiCall (some result) returnType _ _ _ => some (result, returnType)
  | .phi result ty _ => some (result, ty)
  | _ => none

private structure Definition where
  name : String
  ty : Ty
  block? : Option String
  instructionIndex : Nat := 0
  deriving BEq

private structure DominatorEntry where
  label : String
  dominators : Array String
  deriving BEq

private def findBlock? (blocks : Array Block) (label : String) : Option Block :=
  blocks.find? fun block => block.label == label

private def blockSuccessors (block : Block) : Array String :=
  match block.instructions.back? with
  | some terminator => successors terminator
  | none => #[]

private def predecessorLabels (blocks : Array Block) (label : String) : Array String :=
  blocks.foldl (init := #[]) fun result block =>
    if (blockSuccessors block).contains label then insertName result block.label else result

private def reachableLabels (blocks : Array Block) : Array String := Id.run do
  let some entry := blocks[0]?
    | return #[]
  let mut work : List String := [entry.label]
  let mut reached : Array String := #[]
  while !work.isEmpty do
    match work with
    | [] => pure ()
    | label :: rest =>
        work := rest
        unless reached.contains label do
          reached := reached.push label
          if let some block := findBlock? blocks label then
            for target in blockSuccessors block do
              unless reached.contains target do
                work := work ++ [target]
  return reached

private def lookupDominators? (entries : Array DominatorEntry) (label : String) :
    Option (Array String) :=
  (entries.find? fun entry => entry.label == label).map (·.dominators)

private def computeDominators (fn : Function) : Except String (Array DominatorEntry) := do
  let some entry := fn.blocks[0]?
    | failAt fn "has no entry block"
  let labels := fn.blocks.map (·.label)
  -- Block structure has already established unique labels and closed edges.
  -- Keep its original predecessor and update order, indexing only lookups.
  let positions : Std.HashMap String Nat :=
    (labels.mapIdx fun index label => (label, index)).foldl
      (fun result entry => result.insert entry.1 entry.2) {}
  let predecessorsByIndex := labels.map (predecessorLabels fn.blocks)
  let lookup (values : Array DominatorEntry) (label : String) : Option (Array String) :=
    (positions[label]?).bind fun index => (values[index]?).map (·.dominators)
  let mut entries := labels.map fun label =>
    ({
      label
      dominators := if label == entry.label then #[entry.label] else labels
    } : DominatorEntry)
  let mut changed := true
  let mut fuel := labels.size * labels.size + labels.size + 1
  while changed do
    if fuel == 0 then
      failAt fn "internal dominance iteration did not converge"
    fuel := fuel - 1
    changed := false
    for h : index in [:labels.size] do
      let label := labels[index]
      unless label == entry.label do
        let predecessors := predecessorsByIndex[index]!
        let some first := predecessors[0]?
          | failIn fn label "reachable non-entry block has no predecessor"
        let some firstDominators := lookup entries first
          | failIn fn label s!"internal missing dominator state for predecessor `%{first}`"
        let mut common := firstDominators
        for predecessor in predecessors.extract 1 predecessors.size do
          let some predecessorDominators := lookup entries predecessor
            | failIn fn label s!"internal missing dominator state for predecessor `%{predecessor}`"
          common := intersectNames common predecessorDominators
        let updated := insertName common label
        let some current := entries[index]?
          | failIn fn label "internal missing dominator entry"
        unless sameNameSet current.dominators updated do
          entries := entries.set! index { label, dominators := updated }
          changed := true
  pure entries

private def dominates (entries : Array DominatorEntry) (definitionBlock useBlock : String) : Bool :=
  match lookupDominators? entries useBlock with
  | some dominators => dominators.contains definitionBlock
  | none => false

private def lookupDefinition? (definitions : Array Definition) (name : String) : Option Definition :=
  definitions.find? fun definition => definition.name == name

private def validateLiteral (fn : Function) (block context : String) (ty : Ty)
    (value : Nat) : Except String Unit := do
  let some width := integerWidth? ty
    | failIn fn block s!"{context} uses an integer literal tagged `{ty.render}`"
  unless value < 2 ^ width do
    failIn fn block s!"{context} literal {value} is outside `{ty.render}`"

private def validateOperandType (fn : Function) (block context : String)
    (definitions : Array Definition) (operand : Operand) (expected : Ty) : Except String Unit := do
  match operand with
  | .local name =>
      let some definition := lookupDefinition? definitions name
        | failIn fn block s!"{context} refers to unknown SSA value `%{name}`"
      unless definition.ty == expected do
        failIn fn block
          s!"{context} expects `{expected.render}`, but `%{name}` has `{definition.ty.render}`"
  | .global name =>
      unless expected == .ptr do
        failIn fn block s!"{context} uses global `@{name}` where `{expected.render}` is required"
  | .int literalTy value =>
      unless literalTy == expected do
        failIn fn block
          s!"{context} expects `{expected.render}`, but literal is tagged `{literalTy.render}`"
      validateLiteral fn block context literalTy value
  | .null =>
      unless expected == .ptr do
        failIn fn block s!"{context} uses `null` where `{expected.render}` is required"
  | .poison =>
      failIn fn block
        s!"{context} uses explicit `poison`; poison is only implicit in checked-result construction"

private def validateOrdinaryDominance (fn : Function) (block : String) (instructionIndex : Nat)
    (definitions : Array Definition) (dominators : Array DominatorEntry)
    (operand : Operand) (context : String) : Except String Unit := do
  if let .local name := operand then
    let some definition := lookupDefinition? definitions name
      | failIn fn block s!"{context} refers to unknown SSA value `%{name}`"
    match definition.block? with
    | none => pure ()
    | some definitionBlock =>
        if definitionBlock == block then
          unless definition.instructionIndex < instructionIndex do
            failIn fn block s!"{context} uses `%{name}` before its definition"
        else
          unless dominates dominators definitionBlock block do
            failIn fn block
              s!"{context} uses `%{name}` from non-dominating block `%{definitionBlock}`"

private def validateOrdinaryOperand (fn : Function) (block : String)
    (instructionIndex : Nat) (definitions : Array Definition)
    (dominators : Array DominatorEntry) (operand : Operand) (expected : Ty)
    (context : String) : Except String Unit := do
  validateOperandType fn block context definitions operand expected
  validateOrdinaryDominance fn block instructionIndex definitions dominators operand context

private def validatePhiOperand (fn : Function) (block predecessor : String)
    (definitions : Array Definition) (dominators : Array DominatorEntry)
    (blocks : Array Block) (operand : Operand) (expected : Ty) (context : String) :
    Except String Unit := do
  validateOperandType fn block context definitions operand expected
  if let .local name := operand then
    let some definition := lookupDefinition? definitions name
      | failIn fn block s!"{context} refers to unknown SSA value `%{name}`"
    match definition.block? with
    | none => pure ()
    | some definitionBlock =>
        if definitionBlock == predecessor then
          let some predecessorBlock := findBlock? blocks predecessor
            | failIn fn block s!"{context} names unknown predecessor `%{predecessor}`"
          let terminatorIndex := predecessorBlock.instructions.size - 1
          unless definition.instructionIndex < terminatorIndex do
            failIn fn block
              s!"{context} value `%{name}` is not available on edge `%{predecessor}` -> `%{block}`"
        else
          unless dominates dominators definitionBlock predecessor do
            failIn fn block
              s!"{context} value `%{name}` does not dominate predecessor `%{predecessor}`"

private def validateAlignment (fn : Function) (block context : String)
    (alignment : Nat) : Except String Unit := do
  unless alignment > 0 && alignment &&& (alignment - 1) == 0 do
    failIn fn block s!"{context} alignment {alignment} is not a positive power of two"

private def validateInstruction (fn : Function) (block : Block) (instructionIndex : Nat)
    (definitions : Array Definition) (dominators : Array DominatorEntry)
    (instruction : Instruction) : Except String Unit := do
  let operand := validateOrdinaryOperand fn block.label instructionIndex definitions dominators
  let context := s!"instruction #{instructionIndex}"
  match instruction with
  | .bin _ _ ty lhs rhs =>
      unless isInteger ty do failIn fn block.label s!"{context} binary operation has non-integer type"
      operand lhs ty (context ++ " left operand")
      operand rhs ty (context ++ " right operand")
  | .icmp _ _ ty lhs rhs =>
      unless isInteger ty || ty == .ptr do
        failIn fn block.label s!"{context} comparison has unsupported type `{ty.render}`"
      operand lhs ty (context ++ " left operand")
      operand rhs ty (context ++ " right operand")
  | .zext _ sourceTy value targetTy | .sext _ sourceTy value targetTy =>
      let some sourceWidth := integerWidth? sourceTy
        | failIn fn block.label s!"{context} extension source is not an integer"
      let some targetWidth := integerWidth? targetTy
        | failIn fn block.label s!"{context} extension target is not an integer"
      unless sourceWidth < targetWidth do
        failIn fn block.label s!"{context} extension does not increase width"
      operand value sourceTy (context ++ " source")
  | .trunc _ sourceTy value targetTy =>
      let some sourceWidth := integerWidth? sourceTy
        | failIn fn block.label s!"{context} truncation source is not an integer"
      let some targetWidth := integerWidth? targetTy
        | failIn fn block.label s!"{context} truncation target is not an integer"
      unless targetWidth < sourceWidth do
        failIn fn block.label s!"{context} truncation does not decrease width"
      operand value sourceTy (context ++ " source")
  | .select _ condition ty onTrue onFalse =>
      unless ty != .void do failIn fn block.label s!"{context} select result is void"
      operand condition .i1 (context ++ " condition")
      operand onTrue ty (context ++ " true value")
      operand onFalse ty (context ++ " false value")
  | .ptrFromInt _ value =>
      unless value < 2 ^ 64 do
        failIn fn block.label s!"{context} pointer address exceeds i64"
  | .intToPtr _ value => operand value .i64 (context ++ " integer address")
  | .load _ ty address alignment _ =>
      unless ty != .void && ty != .checkedResult do
        failIn fn block.label s!"{context} loads unsupported type `{ty.render}`"
      operand address .ptr (context ++ " address")
      validateAlignment fn block.label context alignment
  | .store ty value address alignment _ =>
      unless ty != .void && ty != .checkedResult do
        failIn fn block.label s!"{context} stores unsupported type `{ty.render}`"
      operand value ty (context ++ " value")
      operand address .ptr (context ++ " address")
      validateAlignment fn block.label context alignment
  | .uartRead8 _ _ _ => pure ()
  | .uartWrite8 _ value =>
      operand value .i8 (context ++ " UART THR byte")
  | .uartEnableAndResetFifo _ => pure ()
  | .uartEnableAndResetFifo14 _ => pure ()
  | .insertResultStatus _ status =>
      operand status .i64 (context ++ " checked-result status")
  | .insertResultValue _ aggregate value =>
      operand aggregate .checkedResult (context ++ " partial checked result")
      operand value .i64 (context ++ " checked-result value")
  | .extractResultStatus _ aggregate =>
      operand aggregate .checkedResult (context ++ " checked result")
  | .extractResultValue _ aggregate =>
      operand aggregate .checkedResult (context ++ " checked result")
  | .call result returnType callee args =>
      unless !callee.isEmpty do failIn fn block.label s!"{context} has an empty callee"
      if returnType == .checkedResult then
        failIn fn block.label s!"{context} checked-result call requires explicit ABI call"
      if returnType == .void && result.isSome then
        failIn fn block.label s!"{context} assigns the result of a void call"
      for argument in args do
        unless argument.1 != .void do
          failIn fn block.label s!"{context} passes a void argument"
        operand argument.2 argument.1 (context ++ " call argument")
  | .abiCall result returnType returnExtension callee args =>
      unless !callee.isEmpty do failIn fn block.label s!"{context} has an empty callee"
      unless extensionAllowed returnType returnExtension do
        failIn fn block.label s!"{context} has an invalid return extension"
      if returnType == .void && result.isSome then
        failIn fn block.label s!"{context} assigns the result of a void call"
      for argument in args do
        unless argument.ty != .void do
          failIn fn block.label s!"{context} passes a void argument"
        unless extensionAllowed argument.ty argument.extension do
          failIn fn block.label s!"{context} has an invalid argument extension"
        operand argument.value argument.ty (context ++ " ABI call argument")
  | .phi .. => pure ()
  | .branch condition _ _ => operand condition .i1 (context ++ " branch condition")
  | .jump _ => pure ()
  | .ret ty value =>
      unless fn.returnType == ty && ty != .void do
        failIn fn block.label
          s!"{context} returns `{ty.render}` from function returning `{fn.returnType.render}`"
      operand value ty (context ++ " return value")
  | .retVoid =>
      unless fn.returnType == .void do
        failIn fn block.label
          s!"{context} returns void from function returning `{fn.returnType.render}`"
  | .unreachable => pure ()

private def collectDefinitions (fn : Function) : Except String (Array Definition) := do
  let mut definitions : Array Definition := #[]
  for parameter in fn.parameters do
    unless !parameter.name.isEmpty do failAt fn "has an empty parameter name"
    if (lookupDefinition? definitions parameter.name).isSome then
      failAt fn s!"has duplicate SSA definition `%{parameter.name}`"
    unless parameter.ty != .void do failAt fn s!"parameter `%{parameter.name}` has void type"
    if parameter.ty == .checkedResult then
      failAt fn s!"parameter `%{parameter.name}` uses the non-parameter checked-result ABI type"
    definitions := definitions.push {
      name := parameter.name
      ty := parameter.ty
      block? := none
    }
  for block in fn.blocks do
    for h : index in [:block.instructions.size] do
      if let some (name, ty) := resultDefinition? block.instructions[index] then
        unless !name.isEmpty do failIn fn block.label s!"instruction #{index} has an empty result name"
        if (lookupDefinition? definitions name).isSome then
          failIn fn block.label s!"instruction #{index} redefines SSA value `%{name}`"
        unless ty != .void do
          failIn fn block.label s!"instruction #{index} defines `%{name}` with void type"
        definitions := definitions.push {
          name
          ty
          block? := some block.label
          instructionIndex := index
        }
  pure definitions

private def validateBlockStructure (fn : Function) : Except String Unit := do
  unless !fn.blocks.isEmpty do failAt fn "has no basic blocks"
  let mut labels : Array String := #[]
  for block in fn.blocks do
    unless !block.label.isEmpty do failAt fn "has an empty basic-block label"
    if labels.contains block.label then failAt fn s!"has duplicate block label `%{block.label}`"
    labels := labels.push block.label
    unless !block.instructions.isEmpty do failIn fn block.label "has no terminator"
    for h : index in [:block.instructions.size] do
      let terminal := isTerminator block.instructions[index]
      if index + 1 == block.instructions.size then
        unless terminal do failIn fn block.label "final instruction is not a terminator"
      else if terminal then
        failIn fn block.label s!"terminator appears before final instruction at index {index}"
    match block.instructions.back? with
    | some (.branch _ onTrue onFalse) =>
        if onTrue == onFalse then
          failIn fn block.label "conditional branch has duplicate successor labels"
    | _ => pure ()
  for block in fn.blocks do
    for target in blockSuccessors block do
      unless labels.contains target do
        failIn fn block.label s!"terminator targets unknown block `%{target}`"
  let some entryBlock := fn.blocks[0]?
    | failAt fn "has no entry block"
  let entry := entryBlock.label
  let entryPredecessors := predecessorLabels fn.blocks entry
  unless entryPredecessors.isEmpty do
    failIn fn entry s!"entry block has predecessors {repr entryPredecessors}"
  let reached := reachableLabels fn.blocks
  unless sameNameSet reached labels do
    let missing := labels.filter fun label => !reached.contains label
    failAt fn s!"contains unreachable blocks {repr missing}"

private def validatePhis (fn : Function) (definitions : Array Definition)
    (dominators : Array DominatorEntry) : Except String Unit := do
  for block in fn.blocks do
    let predecessors := predecessorLabels fn.blocks block.label
    let mut sawNonPhi := false
    for h : index in [:block.instructions.size] do
      match block.instructions[index] with
      | .phi _ ty incoming =>
          if sawNonPhi then
            failIn fn block.label s!"phi at index {index} is not in the block's phi prefix"
          unless !incoming.isEmpty do
            failIn fn block.label s!"phi at index {index} has no incoming operands"
          let mut incomingLabels : Array String := #[]
          for pair in incoming do
            let predecessor := pair.2
            if incomingLabels.contains predecessor then
              failIn fn block.label
                s!"phi at index {index} repeats predecessor `%{predecessor}`"
            incomingLabels := incomingLabels.push predecessor
            validatePhiOperand fn block.label predecessor definitions dominators fn.blocks
              pair.1 ty s!"phi at index {index} incoming from `%{predecessor}`"
          unless sameNameSet incomingLabels predecessors do
            failIn fn block.label
              (s!"phi at index {index} predecessor set differs: " ++
                s!"incoming={repr incomingLabels}, actual={repr predecessors}")
      | _ => sawNonPhi := true

private def uartSite? : Instruction → Option Nat
  | .uartRead8 _ site _ | .uartWrite8 site _ | .uartEnableAndResetFifo site |
      .uartEnableAndResetFifo14 site =>
      some site
  | _ => none

/-- UART sites are consecutive in deterministic structured-emission order within
a function.  The module validator below additionally requires the first site in
the first function to be zero and the complete cross-function sequence to be dense. -/
private def validateUARTSites (fn : Function) : Except String Unit := do
  let mut previous? : Option Nat := none
  for block in fn.blocks do
    for h : index in [:block.instructions.size] do
      if let some site := uartSite? block.instructions[index] then
        if let some previous := previous? then
          unless site == previous + 1 do
            failIn fn block.label
              s!"instruction #{index} has UART site {site}, expected consecutive site {previous + 1}"
        previous? := some site

/--
Validate one structured function's block graph, phi/predecessor relation, SSA
definitions, dominance, operand types, ABI annotations, and returns.
-/
def validateFunction (fn : Function) : Except String Unit := do
  unless !fn.name.isEmpty do failAt fn "has an empty symbol name"
  unless extensionAllowed fn.returnType fn.returnExtension do
    failAt fn "has an invalid return extension"
  unless fn.parameterExtensions.isEmpty ||
      fn.parameterExtensions.size == fn.parameters.size do
    failAt fn "parameter-extension count differs from parameter count"
  if !fn.parameterExtensions.isEmpty then
    for h : index in [:fn.parameters.size] do
      unless extensionAllowed fn.parameters[index].ty fn.parameterExtensions[index]! do
        failAt fn s!"parameter #{index} has an invalid ABI extension"
  validateBlockStructure fn
  validateUARTSites fn
  let definitions ← collectDefinitions fn
  let dominators ← computeDominators fn
  validatePhis fn definitions dominators
  for block in fn.blocks do
    for h : index in [:block.instructions.size] do
      validateInstruction fn block index definitions dominators block.instructions[index]

private structure Callable where
  name : String
  returnType : Ty
  returnExtension : Option ABIExtension
  parameters : Array Ty
  parameterExtensions : Array (Option ABIExtension)
  deriving BEq

private def normalizedParameterExtensions (fn : Function) : Array (Option ABIExtension) :=
  if fn.parameterExtensions.isEmpty then
    Array.replicate fn.parameters.size none
  else
    fn.parameterExtensions

private def functionCallable (fn : Function) : Callable := {
  name := fn.name
  returnType := fn.returnType
  returnExtension := fn.returnExtension
  parameters := fn.parameters.map (·.ty)
  parameterExtensions := normalizedParameterExtensions fn
}

private def declarationCallable (declaration : Declaration) : Callable := {
  name := declaration.name
  returnType := declaration.returnType
  returnExtension := none
  parameters := declaration.parameters
  parameterExtensions := Array.replicate declaration.parameters.size none
}

private def lookupCallable? (callables : Array Callable) (name : String) : Option Callable :=
  callables.find? fun callable => callable.name == name

private def validateCallSignature (fn : Function) (block : Block) (index : Nat)
    (callables : Array Callable) (instruction : Instruction) : Except String Unit := do
  let context := s!"block `%{block.label}` instruction #{index}"
  match instruction with
  | .call _ returnType callee args =>
      let some target := lookupCallable? callables callee
        | failAt fn s!"{context} calls undeclared function `@{callee}`"
      unless target.returnType == returnType do
        failAt fn s!"{context} call return type disagrees with `@{callee}`"
      unless target.returnExtension.isNone && target.parameterExtensions.all Option.isNone do
        failAt fn s!"{context} omits required ABI extensions for `@{callee}`"
      unless args.size == target.parameters.size do
        failAt fn s!"{context} call arity disagrees with `@{callee}`"
      for _h : argumentIndex in [:args.size] do
        let some argument := args[argumentIndex]?
          | failAt fn s!"{context} internal missing call argument #{argumentIndex}"
        let some parameterTy := target.parameters[argumentIndex]?
          | failAt fn s!"{context} internal missing callee parameter #{argumentIndex}"
        unless argument.1 == parameterTy do
          failAt fn s!"{context} call argument #{argumentIndex} type disagrees with `@{callee}`"
  | .abiCall _ returnType returnExtension callee args =>
      let some target := lookupCallable? callables callee
        | failAt fn s!"{context} calls undeclared function `@{callee}`"
      unless target.returnType == returnType && target.returnExtension == returnExtension do
        failAt fn s!"{context} ABI call result contract disagrees with `@{callee}`"
      unless args.size == target.parameters.size do
        failAt fn s!"{context} ABI call arity disagrees with `@{callee}`"
      for _h : argumentIndex in [:args.size] do
        let some argument := args[argumentIndex]?
          | failAt fn s!"{context} internal missing ABI call argument #{argumentIndex}"
        let some parameterTy := target.parameters[argumentIndex]?
          | failAt fn s!"{context} internal missing callee parameter #{argumentIndex}"
        let some parameterExtension := target.parameterExtensions[argumentIndex]?
          | failAt fn s!"{context} internal missing callee extension #{argumentIndex}"
        unless argument.ty == parameterTy &&
            argument.extension == parameterExtension do
          failAt fn s!"{context} ABI call argument #{argumentIndex} disagrees with `@{callee}`"
  | _ => pure ()

/--
Validate every function plus the module's closed direct-call signature graph.
Declarations and definitions share one symbol namespace and all calls must resolve.
-/
def validateModule (llvmModule : Module) : Except String Unit := do
  unless !llvmModule.functions.isEmpty do
    throw "LLVM validation: module has no function definitions"
  let mut callables : Array Callable := #[]
  for declaration in llvmModule.declarations do
    unless !declaration.name.isEmpty do
      throw "LLVM validation: declaration has an empty symbol name"
    if (lookupCallable? callables declaration.name).isSome then
      throw s!"LLVM validation: duplicate declaration/definition `@{declaration.name}`"
    for parameter in declaration.parameters do
      unless parameter != .void do
        throw s!"LLVM validation: declaration `@{declaration.name}` has a void parameter"
    callables := callables.push (declarationCallable declaration)
  for fn in llvmModule.functions do
    validateFunction fn
    if (lookupCallable? callables fn.name).isSome then
      throw s!"LLVM validation: duplicate declaration/definition `@{fn.name}`"
    callables := callables.push (functionCallable fn)
  let usesUART := llvmModule.functions.any fun fn =>
    fn.blocks.any fun block => block.instructions.any fun instruction =>
      (uartSite? instruction).isSome
  if usesUART then
    let mut expectedSite := 0
    for fn in llvmModule.functions do
      for block in fn.blocks do
        for instruction in block.instructions do
          if let some site := uartSite? instruction then
            unless site == expectedSite do
              throw s!"LLVM validation: UART site {site} in `@{fn.name}` is not global canonical site {expectedSite}"
            expectedSite := expectedSite + 1
    let some fence := llvmModule.declarations.find? fun declaration =>
        declaration.name == "core0_io_fence"
      | throw "LLVM validation: ordered UART access requires declaration `@core0_io_fence`"
    unless fence.returnType == .void && fence.parameters.isEmpty &&
        fence.attributes == #["nounwind"] do
      throw "LLVM validation: `@core0_io_fence` must be declared exactly `void () nounwind`"
  for fn in llvmModule.functions do
    for block in fn.blocks do
      for h : index in [:block.instructions.size] do
        validateCallSignature fn block index callables block.instructions[index]

end Lemma.Compiler.LLVM
