import Lean.Compiler.Main
import Lean.Compiler.IR.Format
import Lemma.Core0.ActionIR
import Lemma.User.Runtime.ManagedSums

/-! Checked `lemma-managed-sums-v1` lowering from genuine upstream Lean IR.
The distinct bridge admits closed nonrecursive sum values, scalar payloads and
exhaustive tag cases. Every missing ownership/control/layout form fails closed.
Historical managed-records-v1 lowering remains separate and unchanged. -/

namespace Lemma.Core0.ManagedSumsIR
open Lean
abbrev A := Lemma.Core0.ActionExpr
abbrev E := Lemma.Core0.Expr
abbrev P := Lemma.Core0.Param
abbrev T := Lemma.Core0.Ty

structure Constructor where
  constructor : Name
  tag : Nat
  bytes : Nat
  deriving Inhabited, Repr

structure Shape where
  typeName : Name
  id : Nat
  constructors : Array Constructor
  deriving Inhabited, Repr

inductive ValueTy where
  | scalar | boolean | object (shape : Shape)
  deriving Inhabited, Repr

structure Local where
  x : IR.VarId
  ty : ValueTy
  value : E
  owned : Bool := false
  alive : Bool := true
  constructor : Option Constructor := none
  /-- None means an already checked complete borrowed/returned value.
  New constructors track every initial field write before publication. -/
  initialized : Option Nat := none

structure State where
  next : Nat := 10000
  locals : Array Local := #[]
  callees : Array Name := #[]
  fuel : Nat := 4096
  resultTy : ValueTy := .scalar
  root : Name := .anonymous

abbrev M := StateT State (Except String)

def literal (n : Nat) : E := .lit .u64 n

def fresh (ty : T) : M P := do
  let s ← get
  unless s.next < 65536 do throw "Managed SSA budget exceeded"
  set {s with next := s.next + 1}
  return {id := s.next, name := .anonymous, ty}

def lookupLocal (x : IR.VarId) : M Local := do
  let some l := (← get).locals.find? (·.x == x) | throw s!"Unknown IR variable {x}"
  unless l.alive do throw "Read after owned-reference release rejected"
  return l

def addLocal (entry : Local) : M Unit := do
  unless entry.x.idx < 10000 do throw "Genuine IR variable exceeds disjoint source/SSA range"
  unless !(← get).locals.any (·.x == entry.x) do throw "Duplicate genuine IR variable rejected"
  modify fun s => {s with locals := s.locals.push entry}

def complete (entry : Local) : Bool :=
  match entry.initialized with
  | none => true
  | some mask => match entry.constructor with
    | some constructor => mask == 2 ^ (constructor.bytes / 8 - 1) - 1
    | none => false

def deriveShape (env : Environment) (name : Name) (id : Nat) : Except String Shape := do
  unless 0 < id && id < 65536 do throw "Invalid managed shape identity"
  let some (.inductInfo info) := env.find? name | throw "Source sum lacks checked inductive declaration"
  unless info.levelParams.isEmpty && info.numParams == 0 && info.numIndices == 0 &&
      info.all == [name] && 2 ≤ info.ctors.length && info.ctors.length ≤ 8 && !info.isRec && !info.isUnsafe &&
      !info.isReflexive && info.numNested == 0 do throw "Only closed nonrecursive sums with2..8 constructors admitted"
  let mut constructors := #[]
  for tag in [:info.ctors.length] do
    let constructor := info.ctors[tag]!
    let some (.ctorInfo ctor) := env.find? constructor | throw "Missing source constructor"
    unless ctor.numParams == 0 && 0 < ctor.numFields && ctor.numFields ≤ 7 && ctor.cidx == tag do
      throw "Only constructor tags with1..7 explicit scalar fields admitted"
    let mut ty := ctor.type
    for _ in [:ctor.numFields] do
      let .forallE _ field next binder := ty | throw "Malformed source constructor signature"
      unless field == .const ``UInt64 [] && binder == .default do
        throw "Only explicit nondependent UInt64 payloads admitted"
      ty := next
    unless ty == .const name [] do throw "Source constructor result is not exact sum"
    constructors := constructors.push {constructor, tag, bytes := 8 * (ctor.numFields + 1)}
  return {typeName := name, id, constructors}

def arg (a : IR.Arg) : M E := do
  match a with
  | .var x => return (← lookupLocal x).value
  | .erased => throw "Erased runtime argument is not admitted"

def borrowedScalar (a : IR.Arg) : M E := do
  match a with
  | .var x => match (← lookupLocal x).ty with
    | .scalar => return (← lookupLocal x).value
    | _ => throw "Scalar operation on managed reference rejected"
  | .erased => throw "Erased scalar argument rejected"

def sourceType (shapes : Array Shape) (e : Lean.Expr) : Except String ValueTy := do
  let .const n [] := e | throw "Managed signature must use closed monomorphic types"
  if n == ``UInt64 then return .scalar
  if n == ``Bool then return .boolean
  let some shape := shapes.find? (·.typeName == n) | throw s!"Unregistered source type {n}"
  return .object shape

partial def sourceSignature (env : Environment) (shapes : Array Shape) (name : Name) :
    Except String (Array ValueTy × ValueTy) := do
  let some (.defnInfo info) := env.find? name | throw "Managed callee is not an ordinary source definition"
  unless info.safety == .safe && info.levelParams.isEmpty do throw "Unsafe/polymorphic source definition rejected"
  unless (getExternAttrData? env name).isNone && !hasInitAttr env name && !isIOUnitInitFn env name &&
      (Compiler.getImplementedBy? env name).isNone do throw "Foreign/replaced/initialized managed definition rejected"
  let rec walk (e : Lean.Expr) (params : Array ValueTy) := do
    match e with
    | .forallE _ ty next binder =>
      unless binder == .default do throw "Implicit/dependent binder rejected"
      walk next (params.push (← sourceType shapes ty))
    | result => return (params, ← sourceType shapes result)
  walk info.type #[]

def genName (root name : Name) : Name := root ++ `__lemma_managed_sums_v03 ++ name

def sameType (a b : ValueTy) : Bool :=
  match a,b with
  | .scalar,.scalar => true
  | .boolean,.boolean => true
  | .object x,.object y => x.typeName == y.typeName && x.id == y.id
  | _,_ => false

def primitive (n : Name) : Bool := n == ``UInt64.add || n == ``UInt64.sub || n == ``UInt64.mul || n == ``UInt64.decEq

partial def irDependencies (b : IR.FnBody) : Except String (Array Name) := do
  match b with
  | .ret _ => return #[]
  | .vdecl _ _ e next =>
    let dependencies ← irDependencies next
    match e with
    | .fap n _ => return if primitive n || dependencies.contains n then dependencies else dependencies.push n
    | .lit _ | .ctor _ _ | .sproj _ _ _ => return dependencies
    | _ => throw "Unsupported real IR expression in managed closure"
  | .sset _ _ _ _ _ next | .dec _ _ _ _ next => irDependencies next
  | .case _ _ _ alternatives =>
    let mut dependencies := #[]
    for alternative in alternatives do
      let branch := match alternative with | .ctor _ body => body | .default body => body
      for dependency in ← irDependencies branch do
        unless dependencies.contains dependency do dependencies := dependencies.push dependency
    return dependencies
  | _ => throw "Unsupported real IR control/ownership form in managed closure"

inductive Visit where
  | enter (name : Name) (depth : Nat)
  | exit (name : Name)

/-- The closure is discovered from genuine compiler IR, in dependency order.
No fixture supplies a list of synthetic function bodies. -/
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
        if visiting.contains name then throw "Recursive/cyclic managed call rejected" else
        unless depth ≤ 8 && done.size + visiting.size < 32 do throw "Managed call/closure bound exceeded"
        let some (.defnInfo info) := env.find? name | throw s!"Managed source {name} is not an ordinary definition"
        unless info.safety == .safe && info.levelParams.isEmpty &&
            (getExternAttrData? env name).isNone && !hasInitAttr env name && !isIOUnitInitFn env name &&
            (Compiler.getImplementedBy? env name).isNone do throw "Managed source replacement rejected"
        let some declaration := IR.findEnvDecl env name | throw s!"Missing genuine compiler IR {name}"
        unless !declaration.isExtern && declaration.getInfo.sorryDep?.isNone do throw "Foreign/sorry-dependent managed IR rejected"
        let .fdecl _ _ _ ir _ := declaration | throw "External genuine IR declaration rejected"
        let dependencies ← irDependencies ir
        visiting := visiting.push name
        stack := dependencies.toList.map (fun n => .enter n (depth+1)) ++ [.exit name] ++ stack
      | .exit name =>
        visiting := visiting.filter (· != name)
        unless done.contains name do done := done.push name
  return done

partial def signatureTypes (e : Lean.Expr) : Except String (Array Name) := do
  let inspect (e : Lean.Expr) : Except String Name := do
    let .const name [] := e | throw "Managed type is not closed/monomorphic"
    return name
  match e with
  | .forallE _ ty next .default =>
    let types ← signatureTypes next
    let name ← inspect ty
    return if types.contains name then types else types.push name
  | .forallE .. => throw "Implicit source parameter rejected"
  | result => return #[← inspect result]

def shapeCatalog (env : Environment) (names : Array Name) : Except String (Array Shape) := do
  let mut types : Array Name := #[]
  for name in names do
    let some (.defnInfo info) := env.find? name | throw "Missing real source signature"
    for ty in ← signatureTypes info.type do
      if ty != ``UInt64 && ty != ``Bool && !types.contains ty then types := types.push ty
  unless types.size ≤ 32 do throw "Managed layout catalog bound exceeded"
  types := types.qsort (fun a b => a.toString < b.toString)
  let mut shapes := #[]
  for i in [:types.size] do shapes := shapes.push (← deriveShape env types[i]! (i+1))
  return shapes

def cleanup (status : E) (live : List E) : M A := do
  match live with
  | [] => return .done status (literal 0)
  | handle :: rest =>
    let cleanupStatus ← fresh .u8
    let unused ← fresh .u64
    -- Retain the first failure while attempting every remaining release.
    let selected : E := .ite .u8 (.cmp .eq .u8 status (.lit .u8 0))
      (.var cleanupStatus.id .u8) status
    let next ← cleanup selected rest
    let releaseName := ``Lemma.User.Runtime.Arena.release
    modify fun s => { s with callees := if s.callees.contains releaseName then s.callees else s.callees.push releaseName }
    return .bind (.call ``Lemma.User.Runtime.Arena.release [handle]) cleanupStatus unused next

def liveValues : M (List E) := return (← get).locals.toList.filterMap fun l => if l.owned then some l.value else none

def invoke (name : Name) (args : List E) (value : P) (live : List E) (next : A) : M A := do
  let status ← fresh .u8
  let failed ← cleanup (.var status.id .u8) live
  modify fun s => {s with callees := if s.callees.contains name then s.callees else s.callees.push name}
  return .bind (.call name args) status value
    (.ite (.cmp .eq .u8 (.var status.id .u8) (.lit .u8 0)) next failed)

-- This initial checked subset deliberately rejects every absent IR form.
-- The source comes from the ordinary Lean compiler, never a supplied IR tree.
partial def body (env : Environment) (shapes : Array Shape) (b : IR.FnBody) : M A := do
  let s ← get
  unless s.fuel > 0 do throw "Managed IR node budget exceeded"
  modify fun s => {s with fuel := s.fuel - 1}
  match b with
  | .ret a =>
    let .var returned := a | throw "Erased managed return rejected"
    let result ← lookupLocal returned
    unless sameType result.ty (← get).resultTy do throw "Source/IR managed return type differs"
    unless complete result do throw "Partially initialized object returned"
    match result.ty with
    | .object _ => unless result.owned do throw "Borrowed object return requires unsupported retain"
    | .scalar | .boolean => pure ()
    unless !(← get).locals.any (fun l => l.owned && l.x != returned) do
      throw "Unreleased owned object at return"
    return .done (.lit .u8 0) result.value
  | .vdecl x ty e next =>
    match e with
    | .lit (.num n) =>
      if ty == .uint64 && n < 2^64 then
        addLocal {x, ty := .scalar, value := literal n}
      else if ty == .uint8 && n < 2 then
        addLocal {x, ty := .boolean, value := literal n}
      else throw "Only bounded UInt64/Boolean literals admitted"
      body env shapes next
    | .fap name args =>
      if primitive name then
        unless args.size == 2 do throw "Wrong scalar primitive arity"
        let lhs ← borrowedScalar args[0]!
        let rhs ← borrowedScalar args[1]!
        if name == ``UInt64.decEq then
          unless ty == .uint8 do throw "Scalar equality must have real Boolean IR result"
          addLocal {x, ty := .boolean, value := .cast .zext .bool .u64 (.cmp .eq .u64 lhs rhs)}
        else
          unless ty == .uint64 do throw "Wrong scalar primitive result"
          let value := Lemma.Core0.Expr.bin (if name == ``UInt64.add then .add else if name == ``UInt64.sub then .sub else .mul) .u64 lhs rhs
          addLocal {x, ty := .scalar, value}
        body env shapes next
      else
        let some d := IR.findEnvDecl env name | throw s!"Missing real compiler declaration {name}"
        unless !d.isExtern && d.params.size == args.size && d.getInfo.sorryDep?.isNone do
          throw s!"Unknown or unsupported managed call {name}"
        let (parameterTypes, resultTy) ← sourceSignature env shapes name
        unless parameterTypes.size == args.size do throw "Source/IR arity differs"
        for i in [:args.size] do
          let .var source := args[i]! | throw "Erased call argument rejected"
          let actual ← lookupLocal source
          unless complete actual do throw "Partially initialized object passed to callee"
          match actual.ty, parameterTypes[i]! with
          | .scalar, .scalar => unless d.params[i]!.ty == .uint64 do throw "IR/source scalar type differs"
          | .boolean, .boolean => unless d.params[i]!.ty == .uint8 do throw "IR/source Boolean type differs"
          | .object a, .object b =>
            unless a.id == b.id && d.params[i]!.ty == .object && d.params[i]!.borrow do
              throw "Only exact borrowed object call arguments admitted"
          | _, _ => throw "Managed call type mismatch"
        match resultTy with
        | .scalar => unless d.resultType == .uint64 && ty == .uint64 do throw "Call result type mismatch"
        | .boolean => unless d.resultType == .uint8 && ty == .uint8 do throw "Call Boolean result type mismatch"
        | .object _ => unless d.resultType == .object && ty == .object do throw "Call object result type mismatch"
        let arguments ← args.toList.mapM arg
        let live ← liveValues
        let value ← fresh .u64
        let owned := match resultTy with | .object _ => true | _ => false
        let output : Local := { x, ty := resultTy, value := .var value.id .u64, owned }
        addLocal output
        let continuation ← body env shapes next
        invoke (genName (← get).root name) arguments value live continuation
    | .ctor info args =>
      let some shape := shapes.find? (fun shape => shape.constructors.any (·.constructor == info.name))
        | throw "Unregistered genuine constructor"
      let some constructor := shape.constructors.find? (·.constructor == info.name)
        | throw "Missing actual constructor layout"
      unless ty == .object && info.cidx == constructor.tag && info.size == 0 && info.usize == 0 &&
          info.ssize + 8 == constructor.bytes && args.isEmpty do throw "Constructor layout mismatch"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x, ty := .object shape, value := .var value.id .u64, owned := true, constructor := some constructor, initialized := some 0}
      let continuation ← body env shapes next
      invoke ``Lemma.User.Runtime.ManagedSums.allocate
        [literal shape.id, literal constructor.tag, literal constructor.bytes] value live continuation
    | .sproj n offset source =>
      unless ty == .uint64 && n == 0 && offset % 8 == 0 do throw "Unsupported scalar projection"
      let input ← lookupLocal source
      let .object shape := input.ty | throw "Projection source is not a checked sum"
      let some constructor := input.constructor | throw "Projection requires exact constructor case"
      unless offset + 16 ≤ constructor.bytes do throw "Projection exceeds constructor layout"
      if let some mask := input.initialized then
        unless mask / 2 ^ (offset / 8) % 2 == 1 do throw "Uninitialized managed projection"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x, ty := .scalar, value := .var value.id .u64}
      let continuation ← body env shapes next
      invoke ``Lemma.User.Runtime.ManagedSums.readField [input.value, literal shape.id,
        literal constructor.tag, literal constructor.bytes, literal (offset + 8)] value live continuation
    | _ => throw "IR expression outside initial managed subset"
  | .sset target n offset source ty next =>
    unless ty == .uint64 && n == 0 && offset % 8 == 0 do throw "Unsupported scalar field write"
    let input ← lookupLocal target
    let .object shape := input.ty | throw "Field write source is not a checked sum"
    let some constructor := input.constructor | throw "Field write requires a fresh constructor"
    let some mask := input.initialized | throw "Already published constructor cannot be initialized again"
    unless offset + 16 ≤ constructor.bytes do throw "Field write exceeds constructor layout"
    unless input.owned && mask / 2 ^ (offset / 8) % 2 == 0 do
      throw "Only initial writes to an owned constructor admitted"
    let value ← borrowedScalar (.var source)
    let live ← liveValues
    let unused ← fresh .u64
    modify fun s => {s with locals := s.locals.map fun l => if l.x == target then
      {l with initialized := some (mask + 2 ^ (offset / 8))} else l}
    let continuation ← body env shapes next
    invoke ``Lemma.User.Runtime.ManagedSums.writeField [input.value, literal shape.id,
      literal constructor.tag, literal constructor.bytes, literal (offset + 8), value] unused live continuation
  | .dec x n conditional persistent next =>
    unless n == 1 && !conditional && !persistent do throw "Unsupported managed decrement metadata"
    let input ← lookupLocal x
    let .object _ := input.ty | throw "Decrement on scalar rejected"
    unless input.owned do throw "Decrement on borrowed object rejected"
    modify fun s => {s with locals := s.locals.map fun l => if l.x == x then {l with owned := false, alive := false} else l}
    let live ← liveValues
    let unused ← fresh .u64
    let continuation ← body env shapes next
    invoke ``Lemma.User.Runtime.Arena.release [input.value] unused live continuation
  | .case typeName source irTy alternatives =>
    let input ← lookupLocal source
    unless complete input do throw "Partially initialized sum examined"
    let booleanCase := sameType input.ty .boolean
    let (shape?, count) ← if booleanCase then
      unless typeName == ``UInt8 && irTy == .uint8 do throw "IR/source Boolean case type differs"
      pure (none, 2)
    else do
      let .object shape := input.ty | throw "Tag case requires a sum or Boolean"
      -- Upstream Lean IR erases the source type here to its exact `obj`
      -- discriminator. The checked source value type and every alternative
      -- constructor below retain the actual sum declaration authority.
      unless typeName == `obj && irTy == .object do throw "IR/source sum case type differs"
      pure (some shape, shape.constructors.size)
    unless alternatives.size == count do throw "Every source constructor must have one exact case"
    let mut seen : Array Nat := #[]
    let mut branches : Array (Nat × A) := #[]
    let tag ← fresh .u64
    let baseline ← get
    let mut finalState := baseline
    for alternative in alternatives do
      let .ctor info branch := alternative | throw "Implicit/default constructor case rejected"
      let constructor? ← if booleanCase then
        unless (info.name == ``Bool.false && info.cidx == 0 || info.name == ``Bool.true && info.cidx == 1) &&
            info.size == 0 && info.usize == 0 && info.ssize == 0 do throw "Boolean case tag metadata differs"
        pure none
      else do
        let some shape := shape? | throw "Missing checked sum case"
        let some constructor := shape.constructors.find? (·.constructor == info.name)
          | throw "Case constructor is outside exact source type"
        unless info.cidx == constructor.tag && info.size == 0 && info.usize == 0 &&
            info.ssize + 8 == constructor.bytes do throw "Case constructor payload metadata differs"
        pure (some constructor)
      unless info.cidx < count && !seen.contains info.cidx do throw "Duplicate or invalid constructor case"
      seen := seen.push info.cidx
      -- Branch-local refinements are never merged into another case. SSA IDs,
      -- node fuel and the genuine call inventory remain globally accounted.
      let refined := baseline.locals.map fun l => if l.x == source then
        {l with constructor := constructor?} else l
      set {baseline with next := finalState.next, fuel := finalState.fuel, callees := finalState.callees, locals := refined}
      let lowered ← body env shapes branch
      finalState ← get
      branches := branches.push (info.cidx, lowered)
    set {baseline with next := finalState.next, fuel := finalState.fuel, callees := finalState.callees}
    let observed := if booleanCase then input.value else .var tag.id .u64
    let mut selected := branches[branches.size-1]!.2
    for i in [:branches.size-1] do
      let index := branches.size - 2 - i
      selected := .ite (.cmp .eq .u64 observed (literal branches[index]!.1)) branches[index]!.2 selected
    if booleanCase then return selected else
      let some shape := shape? | throw "Missing checked tag operation"
      let live ← liveValues
      let lengths := shape.constructors.foldl (fun word constructor =>
        word + constructor.bytes / 8 * 2 ^ (constructor.tag * 4)) 0
      invoke ``Lemma.User.Runtime.ManagedSums.constructorTag
        [input.value, literal shape.id, literal count, literal lengths] tag live selected
  | _ => throw "Control-flow/RC form outside initial managed subset"

structure Program where
  root : Name
  sourceNames : Array Name
  shapes : Array Shape
  functions : Array Lemma.Core0.ActionFunction

/-- An image has one closed scalar entry bridge. Internal borrowed objects are
never exposed as source-level syscall arguments or synthetic environment defs. -/
def buildProgram (env : Environment) (root : Name) : Except String Program := do
  let names ← sourceClosure env root
  unless names.all (fun n => !(n.toString.splitOn ".__lemma_managed_sums_v03.").length > 1) do
    throw "Reserved generated managed identity appears in source closure"
  let shapes ← shapeCatalog env names
  unless !shapes.isEmpty do throw "Managed bridge must have actual ordinary structure layout"
  let (entryParams, entryResult) ← sourceSignature env shapes root
  unless entryParams.size == 2 && entryParams.all (fun t => sameType t .scalar) && sameType entryResult .scalar do
    throw "Managed bridge requires exactly UInt64 -> UInt64 -> UInt64"
  let mut functions := #[]
  for name in names do
    let some (.fdecl _ params result ir info) := IR.findEnvDecl env name
      | throw "Missing genuine ordinary compiler IR"
    unless info.sorryDep?.isNone do throw "Sorry-dependent managed source rejected"
    let (sourceParams, sourceResult) ← sourceSignature env shapes name
    unless sourceParams.size == params.size do throw "Source/IR signature arity mismatch"
    match sourceResult with
    | .scalar => unless result == .uint64 do throw "IR/source return scalar type mismatch"
    | .boolean => unless result == .uint8 do throw "IR/source return Boolean type mismatch"
    | .object _ => unless result == .object do throw "IR/source return object type mismatch"
    let mut initial : State := {resultTy := sourceResult, root}
    for i in [:params.size] do
      unless params[i]!.x.idx < 10000 do throw "Genuine IR parameter exceeds SSA range"
      match sourceParams[i]! with
      | .scalar => unless params[i]!.ty == .uint64 do throw "IR/source scalar parameter mismatch"
      | .boolean => unless params[i]!.ty == .uint8 do throw "IR/source Boolean parameter mismatch"
      | .object _ => unless params[i]!.ty == .object && params[i]!.borrow do
          throw "Only exact borrowed object parameters admitted"
      initial := {initial with locals := initial.locals.push {
        x := params[i]!.x, ty := sourceParams[i]!, value := .var params[i]!.x.idx .u64}}
    let (lowered, finalState) ← (body env shapes ir).run initial
    functions := functions.push {
      name := genName root name
      signature := {args := Array.replicate params.size .u64}
      params := params.map fun p => {id := p.x.idx, name := .anonymous, ty := .u64}
      body := lowered
      scalarDependencies := #[]
      actionDependencies := finalState.callees
      directEffects := .empty
      effects := .empty }
  return {root, sourceNames := names, shapes, functions}

def generatedSource? (name : Name) : Option (Name × Name) :=
  match name.toString.splitOn ".__lemma_managed_sums_v03." with
  | [root, source] => if root.isEmpty || source.isEmpty then none else some (root.toName, source.toName)
  | _ => none

/-- Resolve a generated identity only through its exact ordinary source closure.
There are no fake Lean declarations standing in for functions. -/
def generatedFunction (env : Environment) (name : Name) : Except String Lemma.Core0.ActionFunction := do
  let some (root, source) := generatedSource? name | throw "Not a generated managed identity"
  let program ← buildProgram env root
  unless program.sourceNames.contains source && genName root source == name do
    throw "Generated identity is outside exact genuine managed closure"
  let some function := program.functions.find? (·.name == name) | throw "Managed function missing"
  return function

end Lemma.Core0.ManagedSumsIR
