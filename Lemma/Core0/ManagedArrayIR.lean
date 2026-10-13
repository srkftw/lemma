import Lean.Compiler.Main
import Lean.Compiler.IR.Format
import Lemma.Core0.ActionIR
import Lemma.User.Runtime.ManagedArray

/-! Checked lowering of ordinary nonrecursive Array UInt64 code. The actual
upstream IR supplies all ownership/control operations. No hand-authored IR
or host runtime supplies source behavior. Historical bridges remain separate. -/
namespace Lemma.Core0.ManagedArrayIR
open Lean
abbrev A := ActionExpr
abbrev E := Expr
abbrev P := Param
inductive ValueTy where
  | scalar | natural | buffer | boxed | defaultBox | boolean
  deriving Inhabited, Repr, BEq
structure Local where
  x : IR.VarId
  ty : ValueTy
  value : E
  references : Nat := 0
  alive : Bool := true
  borrowedFrom : Option IR.VarId := none
structure State where
  next : Nat := 10000
  locals : Array Local := #[]
  callees : Array Name := #[]
  fuel : Nat := 4096
  resultTy : ValueTy := .scalar
  root : Name := .anonymous
  source : Name := .anonymous
  defaultInitializers : Array Name := #[]
abbrev M := StateT State (Except String)
def literal (n : Nat) : E := .lit .u64 n
def fresh (ty : Ty) : M P := do
  let s ← get
  unless s.next < 65536 do throw "Array UInt64 SSA budget exceeded"
  set {s with next := s.next + 1}
  return {id := s.next, name := .anonymous, ty}
def lookupLocal (x : IR.VarId) : M Local := do
  let some l := (← get).locals.find? (·.x == x) | throw s!"Unknown IR variable {x}"
  unless l.alive do throw "Read after reference consumption rejected"
  if let some owner := l.borrowedFrom then
    let some source := (← get).locals.find? (·.x == owner) | throw "Borrow owner absent"
    unless source.alive && source.ty == .buffer do throw "Element borrow outlived its array"
  return l
def addLocal (entry : Local) : M Unit := do
  unless entry.x.idx < 10000 && !(← get).locals.any (·.x == entry.x) do
    throw "Source SSA range or uniqueness differs"
  modify fun s => {s with locals := s.locals.push entry}
def arg (a : IR.Arg) : M Local := do
  let .var x := a | throw "Erased runtime argument rejected"
  lookupLocal x
def requireArg (a : IR.Arg) (ty : ValueTy) : M E := do
  let entry ← arg a
  unless entry.ty == ty do throw "Array UInt64 primitive/source argument type differs"
  return entry.value
def consume (x : IR.VarId) : M Unit := do
  let l ← lookupLocal x
  unless (l.ty == .buffer || l.ty == .boxed) && l.references > 0 do throw "Consume of borrowed buffer rejected"
  modify fun s => {s with locals := s.locals.map fun v => if v.x == x then
    {v with references := v.references-1, alive := v.references>1} else v}
def sourceType (e : Lean.Expr) : Except String ValueTy := do
  if e == Lean.Expr.const ``UInt64 [] then return .scalar
  if e == Lean.Expr.app (Lean.Expr.const ``Array [Level.zero]) (Lean.Expr.const ``UInt64 []) then return .buffer
  throw "Only exact UInt64 and Array UInt64 source types are admitted"
partial def signature (env : Environment) (name : Name) : Except String (Array ValueTy × ValueTy) := do
  let some (.defnInfo info) := env.find? name | throw s!"Source {name} is not an ordinary definition"
  unless info.safety == .safe && info.levelParams.isEmpty && (getExternAttrData? env name).isNone &&
    !hasInitAttr env name && !isIOUnitInitFn env name && (Compiler.getImplementedBy? env name).isNone do
    throw "Foreign/replaced/initialized/polymorphic source rejected"
  let rec walk (e : Lean.Expr) (params : Array ValueTy) := do
    match e with
    | .forallE _ ty next .default => walk next (params.push (← sourceType ty))
    | .forallE .. => throw "Implicit/dependent binder rejected"
    | result => return (params, ← sourceType result)
  walk info.type #[]
def genName (root name : Name) : Name := root ++ `__lemma_managed_array_v05 ++ name
/-- Only a genuine compiler-derived, owner-bound literal-zero UInt64 box
initializer is admitted. It is not inserted as a fictitious source declaration. -/
def defaultInitializer? (env : Environment) (name : Name) : Option UInt64 := do
  let .str ownerName "_boxed_const_1" := name | none
  unless (env.find? name).isNone do none
  let some (.defnInfo owner) := env.find? ownerName | none
  unless owner.safety == .safe && owner.levelParams.isEmpty &&
      (getExternAttrData? env ownerName).isNone &&
      (Compiler.getImplementedBy? env ownerName).isNone do none
  let some (.fdecl actual params result body info) := IR.findEnvDecl env name | none
  unless actual == name && params.isEmpty && result == .tobject && info.sorryDep?.isNone do none
  let .vdecl literalId .uint64 (.lit (.num 0))
      (.vdecl boxId .tobject (.box .uint64 source) (.ret (.var returned))) := body | none
  unless literalId == source && boxId == returned && literalId != boxId &&
      literalId.idx < 10000 && boxId.idx < 10000 do none
  some 0

def primitive (name : Name) : Bool :=
  [``UInt64.add, ``UInt64.sub, ``UInt64.mul, ``UInt64.shiftLeft, ``UInt64.shiftRight,
   ``UInt64.land, ``UInt64.lor, ``UInt64.xor, ``UInt64.decEq,
   ``UInt64.toNat, ``UInt64.ofNat, ``Array.emptyWithCapacity, ``Array.push,
   ``Array.set!, ``Array.get!InternalBorrowed, ``Array.size].contains name
partial def dependencies (env : Environment) (body : IR.FnBody) : Except String (Array Name) := do
  match body with
  | .ret _ => return #[]
  | .vdecl _ _ expression next =>
    let rest ← dependencies env next
    match expression with
    | .fap name _ =>
      return if primitive name || (defaultInitializer? env name).isSome || rest.contains name then rest else rest.push name
    | .lit _ | .box _ _ | .unbox _ => return rest
    | _ => throw "Unsupported Array UInt64 IR expression/static object"
  | .inc _ _ _ _ next | .dec _ _ _ _ next => dependencies env next
  | .case _ _ _ alternatives =>
    let mut result := #[]
    for alternative in alternatives do
      let branch := match alternative with | .ctor _ b => b | .default b => b
      for name in ← dependencies env branch do
        unless result.contains name do result := result.push name
    return result
  | _ => throw "Unsupported Array UInt64 IR control/ownership form"
inductive Visit where
  | enter (name : Name) (depth : Nat) | exit (name : Name)
def sourceClosure (env : Environment) (root : Name) : Except String (Array Name) := do
  let mut stack : List Visit := [.enter root 1]
  let mut visiting : Array Name := #[]
  let mut done : Array Name := #[]
  while !stack.isEmpty do
    match stack with
    | [] => pure ()
    | task :: rest =>
      stack := rest
      match task with
      | .enter name depth =>
        if done.contains name then pure () else
        if visiting.contains name then throw "Recursive Array UInt64 call rejected" else
        unless depth ≤ 8 && done.size + visiting.size < 32 do throw "Array UInt64 closure bound exceeded"
        let _ ← signature env name
        let some (.fdecl _ _ _ ir info) := IR.findEnvDecl env name | throw "Missing genuine ordinary compiler IR"
        unless info.sorryDep?.isNone do throw "Sorry-dependent source rejected"
        let callees ← dependencies env ir
        visiting := visiting.push name
        stack := callees.toList.map (fun n => .enter n (depth+1)) ++ [.exit name] ++ stack
      | .exit name =>
        visiting := visiting.filter (· != name)
        unless done.contains name do done := done.push name
  return done
def cleanup (status : E) (live : List (ValueTy × E)) : M A := do
  match live with
  | [] => return .done status (literal 0)
  | (ty,handle) :: rest =>
    let cleanupStatus ← fresh .u8
    let unused ← fresh .u64
    let selected : E := .ite .u8 (.cmp .eq .u8 status (.lit .u8 0)) (.var cleanupStatus.id .u8) status
    let next ← cleanup selected rest
    let release := if ty == .buffer then ``Lemma.User.Runtime.ManagedArray.release else ``Lemma.User.Runtime.Arena.release
    modify fun s => {s with callees := if s.callees.contains release then s.callees else s.callees.push release}
    return .bind (.call release [handle]) cleanupStatus unused next
def liveValues : M (List (ValueTy × E)) :=
  return (← get).locals.toList.flatMap fun l => List.replicate l.references (l.ty,l.value)
def invoke (name : Name) (args : List E) (value : P) (live : List (ValueTy × E)) (next : A) : M A := do
  let status ← fresh .u8
  let failed ← cleanup (.var status.id .u8) live
  modify fun s => {s with callees := if s.callees.contains name then s.callees else s.callees.push name}
  return .bind (.call name args) status value (.ite (.cmp .eq .u8 (.var status.id .u8) (.lit .u8 0)) next failed)
def irType (ty : ValueTy) (actual : IR.IRType) : Bool :=
  match ty with
  | .scalar => actual == .uint64
  | .boolean => actual == .uint8
  | .boxed | .defaultBox => actual == .tobject
  | .natural => actual == .tagged || actual == .tobject
  | .buffer => actual == .object
partial def body (env : Environment) (b : IR.FnBody) : M A := do
  let state ← get
  unless state.fuel>0 do throw "Array UInt64 IR node budget exceeded"
  modify fun s => {s with fuel := s.fuel-1}
  match b with
  | .ret a =>
    let entry ← arg a
    unless entry.ty == (← get).resultTy do throw "Source/IR return type differs"
    if entry.ty == .buffer then unless entry.references == 1 do throw "Returned buffer requires exactly one owned reference"
    unless !(← get).locals.any (fun l => l.references>0 && l.x != entry.x) do throw "Unreleased buffer at return"
    return .done (.lit .u8 0) entry.value
  | .vdecl x ty expression next =>
    match expression with
    | .lit (.num n) =>
      let valueTy ← if ty == .uint64 && n<2^64 then pure ValueTy.scalar else
        if ty == .tagged && n≤6 then pure ValueTy.natural else throw "Unadmitted literal/layout"
      addLocal {x, ty := valueTy, value := literal n}
      body env next
    | .fap name args =>
      if [``UInt64.add, ``UInt64.sub, ``UInt64.mul, ``UInt64.shiftLeft, ``UInt64.shiftRight,
          ``UInt64.land, ``UInt64.lor, ``UInt64.xor, ``UInt64.decEq].contains name then
        unless args.size == 2 do throw "Scalar primitive arity differs"
        let lhs ← requireArg args[0]! .scalar
        let rhs ← requireArg args[1]! .scalar
        if name == ``UInt64.decEq then
          unless ty == .uint8 do throw "Boolean result layout differs"
          addLocal {x, ty := .boolean, value := .cast .zext .bool .u64 (.cmp .eq .u64 lhs rhs)}
        else
          unless ty == .uint64 do throw "Scalar result layout differs"
          let op := if name == ``UInt64.add then BinOp.add else if name == ``UInt64.sub then .sub else
            if name == ``UInt64.mul then .mul else if name == ``UInt64.shiftLeft then .shl else
            if name == ``UInt64.shiftRight then .lshr else if name == ``UInt64.land then .band else if name == ``UInt64.lor then .bor else .bxor
          addLocal {x, ty := .scalar, value := .bin op .u64 lhs (if op == .shl || op == .lshr then .bin .band .u64 rhs (literal 63) else rhs)}
        body env next
      else if (defaultInitializer? env name).isSome then
        unless args.isEmpty && ty == .tobject && name.getPrefix == (← get).source do
          throw "Static default initializer owner/use differs"
        modify fun s => {s with defaultInitializers :=
          if s.defaultInitializers.contains name then s.defaultInitializers else s.defaultInitializers.push name}
        addLocal {x,ty := .defaultBox,value := literal 0}
        body env next
      else if name == ``UInt64.ofNat then
        unless args.size == 1 && ty == .uint64 do throw "Bounded Nat conversion result differs"
        let value ← requireArg args[0]! .natural
        addLocal {x,ty := .scalar,value}
        body env next
      else if primitive name then
        let (runtime,result,arguments,borrowedFrom) ← if name == ``UInt64.toNat then
          unless args.size == 1 && irType .natural ty do throw "Bounded Nat conversion IR differs"
          pure (``Lemma.User.Runtime.ManagedArray.natural,ValueTy.natural,[← requireArg args[0]! .scalar],none)
        else if name == ``Array.emptyWithCapacity then
          unless args.size == 2 && args[0]! == .erased && irType .buffer ty do throw "Array allocation type erasure/IR differs"
          pure (``Lemma.User.Runtime.ManagedArray.emptyWithCapacity,ValueTy.buffer,[← requireArg args[1]! .natural],none)
        else if name == ``Array.size then
          unless args.size == 2 && args[0]! == .erased && irType .natural ty do throw "Array size type erasure/IR differs"
          pure (``Lemma.User.Runtime.ManagedArray.size,ValueTy.natural,[← requireArg args[1]! .buffer],none)
        else if name == ``Array.get!InternalBorrowed then
          unless args.size == 4 && args[0]! == .erased && irType .boxed ty do throw "Array get! type erasure/IR differs"
          let _ ← requireArg args[1]! .defaultBox
          let owner ← arg args[2]!
          unless owner.ty == .buffer do throw "Array borrow has wrong owner type"
          pure (``Lemma.User.Runtime.ManagedArray.getBorrowed,ValueTy.boxed,
            [owner.value,← requireArg args[3]! .natural],some owner.x)
        else if name == ``Array.push || name == ``Array.set! then
          unless args.size == (if name == ``Array.push then 3 else 4) && args[0]! == .erased && irType .buffer ty do
            throw "Array update type erasure/IR differs"
          let buffer ← arg args[1]!
          unless buffer.ty == .buffer do throw "Array update source type differs"
          let element ← arg args[if name == ``Array.push then 2 else 3]!
          unless element.ty == .boxed && element.references>0 && element.borrowedFrom.isNone do
            throw "Array update requires an owned full64 element box"
          let tail ← if name == ``Array.push then pure [element.value] else
            pure [← requireArg args[2]! .natural,element.value]
          consume buffer.x
          consume element.x
          pure ((if name == ``Array.push then ``Lemma.User.Runtime.ManagedArray.push else ``Lemma.User.Runtime.ManagedArray.set),
            ValueTy.buffer,buffer.value::tail,none)
        else throw "Unimplemented Array primitive"
        let live ← liveValues
        let value ← fresh .u64
        addLocal {
          x := x
          ty := result
          value := .var value.id .u64
          references := if result == .buffer then 1 else 0
          borrowedFrom := borrowedFrom }
        let continuation ← body env next
        invoke runtime arguments value live continuation
      else
        let some (.fdecl _ params result _ info) := IR.findEnvDecl env name | throw "Unknown or external ordinary call"
        let (parameterTypes,resultTy) ← signature env name
        unless info.sorryDep?.isNone && params.size == args.size && parameterTypes.size == args.size &&
          irType resultTy result && irType resultTy ty do throw "Source/IR call signature differs"
        let mut arguments := []
        for i in [:args.size] do
          let actual ← arg args[i]!
          unless actual.ty == parameterTypes[i]! && irType actual.ty params[i]!.ty do throw "Ordinary call argument differs"
          if actual.ty == .buffer && !params[i]!.borrow then consume actual.x
          arguments := arguments ++ [actual.value]
        let live ← liveValues
        let value ← fresh .u64
        addLocal {x, ty := resultTy, value := .var value.id .u64, references := if resultTy == .buffer then 1 else 0}
        let continuation ← body env next
        invoke (genName (← get).root name) arguments value live continuation
    | .box boxedType source =>
      unless boxedType == .uint64 && ty == .tobject do throw "Only full64 scalar boxing admitted"
      let scalar ← lookupLocal source
      unless scalar.ty == .scalar do throw "Box source is not UInt64"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x,ty := .boxed,value := .var value.id .u64,references := 1}
      let continuation ← body env next
      invoke ``Lemma.User.Runtime.ManagedArray.box [scalar.value] value live continuation
    | .unbox source =>
      let element ← lookupLocal source
      unless ty == .uint64 && element.ty == .boxed do throw "Only real UInt64 boxes may be unboxed"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x,ty := .scalar,value := .var value.id .u64}
      let continuation ← body env next
      invoke ``Lemma.User.Runtime.ManagedArray.unbox [element.value] value live continuation
    | _ => throw "Static objects/closures/constructors/projections outside Array UInt64 subset"
  | .inc x n conditional persistent next =>
    unless n == 1 && !conditional && !persistent do throw "Unsupported increment metadata"
    let entry ← lookupLocal x
    unless entry.ty == .buffer && entry.references>0 && entry.references<8 do throw "Increment requires owned bounded Array UInt64"
    let live ← liveValues
    modify fun s => {s with locals := s.locals.map fun l => if l.x == x then {l with references := l.references+1} else l}
    let unused ← fresh .u64
    let continuation ← body env next
    invoke ``Lemma.User.Runtime.ManagedArray.retain [entry.value] unused live continuation
  | .dec x n conditional persistent next =>
    let entry ← lookupLocal x
    unless n == 1 && !persistent && (entry.ty == .natural || !conditional) do
      throw s!"Unsupported decrement metadata {x} {n} {conditional} {persistent}"
    if entry.ty == .natural then
      -- This Nat is known to be a ≤6 scalar, so genuine IR's decrement has
      -- no allocated box to reclaim. It is never a fabricated RC helper.
      modify fun s => {s with locals := s.locals.map fun l => if l.x == x then {l with alive := false} else l}
      body env next
    else
      consume x
      let live ← liveValues
      let unused ← fresh .u64
      let continuation ← body env next
      invoke (if entry.ty == .buffer then ``Lemma.User.Runtime.ManagedArray.release else ``Lemma.User.Runtime.Arena.release) [entry.value] unused live continuation
  | .case name source irTy alternatives =>
    let entry ← lookupLocal source
    unless entry.ty == .boolean && name == ``UInt8 && irTy == .uint8 && alternatives.size == 2 do
      throw "Only exhaustive exact Boolean cases admitted"
    let baseline ← get
    let mut finalState := baseline
    let mut branches : Array (Nat × A) := #[]
    for alternative in alternatives do
      let .ctor info branch := alternative | throw "Default case rejected"
      unless info.size == 0 && info.usize == 0 && info.ssize == 0 &&
        ((info.name == ``Bool.false && info.cidx == 0) || (info.name == ``Bool.true && info.cidx == 1)) &&
        !branches.any (·.1 == info.cidx) do throw "Boolean constructor metadata differs"
      set {baseline with
        next := finalState.next
        fuel := finalState.fuel
        callees := finalState.callees
        defaultInitializers := finalState.defaultInitializers}
      let lowered ← body env branch
      finalState ← get
      branches := branches.push (info.cidx,lowered)
    set {baseline with
      next := finalState.next
      fuel := finalState.fuel
      callees := finalState.callees
      defaultInitializers := finalState.defaultInitializers}
    return .ite (.cmp .eq .u64 entry.value (literal branches[0]!.1)) branches[0]!.2 branches[1]!.2
  | _ => throw "IR join/loop/reuse/closure form outside Array UInt64 subset"
structure Program where
  root : Name
  sourceNames : Array Name
  functions : Array ActionFunction
  defaultInitializers : Array Name

def buildProgram (env : Environment) (root : Name) : Except String Program := do
  let names ← sourceClosure env root
  unless names.all (fun n => !(n.toString.splitOn ".__lemma_managed_array_v05.").length>1) do throw "Reserved generated source name"
  let (entryParams,entryResult) ← signature env root
  unless entryParams == #[.scalar,.scalar] && entryResult == .scalar do throw "Array UInt64 bridge requires scalar UInt64 -> UInt64 -> UInt64 entry"
  let mut sawBuffer := false
  let mut functions : Array ActionFunction := #[]
  let mut defaultInitializers : Array Name := #[]
  for name in names do
    let some (.fdecl _ params result ir info) := IR.findEnvDecl env name | throw "Missing genuine IR"
    let (sourceParams,sourceResult) ← signature env name
    unless info.sorryDep?.isNone && params.size == sourceParams.size && irType sourceResult result do throw "Source/IR function layout differs"
    let mut initial : State := {resultTy := sourceResult,root,source := name}
    for i in [:params.size] do
      let ty := sourceParams[i]!
      unless irType ty params[i]!.ty && params[i]!.x.idx<10000 &&
          !initial.locals.any (·.x == params[i]!.x) do throw "Parameter layout/range/uniqueness differs"
      if ty == .buffer then sawBuffer := true
      initial := {initial with locals := initial.locals.push {
        x := params[i]!.x, ty := ty, value := .var params[i]!.x.idx .u64,
        references := if ty == .buffer && !params[i]!.borrow then 1 else 0}}
    if sourceResult == .buffer then sawBuffer := true
    let (lowered,state) ← (body env ir).run initial
    for initializer in state.defaultInitializers do
      unless defaultInitializers.contains initializer do defaultInitializers := defaultInitializers.push initializer
    functions := functions.push {
      name := genName root name
      signature := {args := Array.replicate params.size .u64}
      params := params.map fun p => {id := p.x.idx, name := .anonymous, ty := .u64}
      body := lowered
      scalarDependencies := #[]
      actionDependencies := state.callees
      directEffects := .empty
      effects := .empty }
  unless sawBuffer do throw "Array UInt64 entry has no actual ordinary payload"
  return {root,sourceNames := names,functions,defaultInitializers}
def generatedSource? (name : Name) : Option (Name × Name) :=
  match name.toString.splitOn ".__lemma_managed_array_v05." with
  | [root,source] => if root.isEmpty || source.isEmpty then none else some (root.toName,source.toName)
  | _ => none
def generatedFunction (env : Environment) (name : Name) : Except String ActionFunction := do
  unless (env.find? name).isNone do throw "Source declaration collides with reserved generated Array name"
  let some (root,source) := generatedSource? name | throw "Not a generated Array UInt64 source"
  let program ← buildProgram env root
  unless program.sourceNames.contains source && genName root source == name do throw "Generated source outside genuine closure"
  let some function := program.functions.find? (·.name == name) | throw "Missing generated Array UInt64 action"
  return function
end Lemma.Core0.ManagedArrayIR
