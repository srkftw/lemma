import Lean.Compiler.Main
import Lean.Compiler.IR.Format
import Lemma.Core0.ActionIR
import Lemma.User.Runtime.ManagedRecords

/-! Checked `lemma-managed-records-v1` lowering from genuine upstream Lean IR.
Only closed scalar-field structures, borrowed arguments and nonrecursive calls
are admitted here. Missing IR/layout/ownership forms fail closed. No supplied
demonstration AST, foreign allocation helper or upstream target runtime is used.
The generated Action functions call the real owned-page arena. -/

namespace Lemma.Core0.ManagedIR
open Lean
abbrev A := Lemma.Core0.ActionExpr
abbrev E := Lemma.Core0.Expr
abbrev P := Lemma.Core0.Param
abbrev T := Lemma.Core0.Ty

structure Shape where
  typeName : Name
  constructor : Name
  id : Nat
  bytes : Nat
  deriving Inhabited, Repr

inductive ValueTy where
  | scalar | object (shape : Shape)
  deriving Inhabited, Repr

structure Local where
  x : IR.VarId
  ty : ValueTy
  value : E
  owned : Bool := false
  alive : Bool := true
  initialized : Nat := 0

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
  match entry.ty with
  | .scalar => true
  | .object shape => entry.initialized == 2 ^ (shape.bytes / 8 - 1) - 1

def deriveShape (env : Environment) (name : Name) (id : Nat) : Except String Shape := do
  unless 0 < id && id < 65536 do throw "Invalid managed shape identity"
  let some fields := getStructureInfo? env name | throw "Only ordinary Lean structures admitted initially"
  unless fields.parentInfo.isEmpty && 0 < fields.fieldNames.size && fields.fieldNames.size ≤ 7 do
    throw "Only one to seven direct scalar fields admitted"
  let some (.inductInfo info) := env.find? name | throw "Source structure lacks checked inductive declaration"
  unless info.levelParams.isEmpty && info.numParams == 0 && info.numIndices == 0 &&
      info.all == [name] && info.ctors.length == 1 && !info.isRec && !info.isUnsafe &&
      !info.isReflexive && info.numNested == 0 do throw "Unsupported structure parameters or recursion"
  let constructor := info.ctors[0]!
  let some (.ctorInfo ctor) := env.find? constructor | throw "Missing source constructor"
  unless ctor.numParams == 0 && ctor.numFields == fields.fieldNames.size && ctor.cidx == 0 do
    throw "Source constructor metadata differs"
  let mut ty := ctor.type
  for _ in [:fields.fieldNames.size] do
    let .forallE _ field next binder := ty | throw "Malformed source constructor signature"
    unless field == .const ``UInt64 [] && binder == .default do
      throw "Only explicit nondependent UInt64 fields admitted"
    ty := next
  unless ty == .const name [] do throw "Source constructor result is not exact structure"
  return {typeName := name, constructor, id, bytes := 8 * (fields.fieldNames.size + 1)}

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

def genName (root name : Name) : Name := root ++ `__lemma_managed_v02 ++ name

def sameType (a b : ValueTy) : Bool :=
  match a,b with
  | .scalar,.scalar => true
  | .object x,.object y => x.typeName == y.typeName && x.id == y.id && x.bytes == y.bytes
  | _,_ => false

def primitive (n : Name) : Bool := n == ``UInt64.add || n == ``UInt64.sub || n == ``UInt64.mul

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
      if ty != ``UInt64 && !types.contains ty then types := types.push ty
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
    | .scalar => pure ()
    unless !(← get).locals.any (fun l => l.owned && l.x != returned) do
      throw "Unreleased owned object at return"
    return .done (.lit .u8 0) result.value
  | .vdecl x ty e next =>
    match e with
    | .lit (.num n) =>
      unless ty == .uint64 && n < 2^64 do throw "Only bounded UInt64 literal is admitted"
      addLocal {x, ty := .scalar, value := literal n}
      body env shapes next
    | .fap name args =>
      if primitive name then
        unless ty == .uint64 && args.size == 2 do throw "Wrong scalar primitive signature"
        let lhs ← borrowedScalar args[0]!
        let rhs ← borrowedScalar args[1]!
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
          | .object a, .object b =>
            unless a.id == b.id && d.params[i]!.ty == .object && d.params[i]!.borrow do
              throw "Only exact borrowed object call arguments admitted"
          | _, _ => throw "Managed call type mismatch"
        match resultTy with
        | .scalar => unless d.resultType == .uint64 && ty == .uint64 do throw "Call result type mismatch"
        | .object _ => unless d.resultType == .object && ty == .object do throw "Call object result type mismatch"
        let arguments ← args.toList.mapM arg
        let live ← liveValues
        let value ← fresh .u64
        let owned := match resultTy with | .object _ => true | _ => false
        let initialized := match resultTy with | .object shape => 2 ^ (shape.bytes / 8 - 1) - 1 | _ => 0
        let output : Local := { x, ty := resultTy, value := .var value.id .u64, owned, initialized }
        addLocal output
        let continuation ← body env shapes next
        invoke (genName (← get).root name) arguments value live continuation
    | .ctor info args =>
      let some shape := shapes.find? (·.constructor == info.name) | throw "Unregistered genuine constructor"
      unless ty == .object && info.cidx == 0 && info.size == 0 && info.usize == 0 &&
          info.ssize + 8 == shape.bytes && args.isEmpty do throw "Constructor layout mismatch"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x, ty := .object shape, value := .var value.id .u64, owned := true}
      let continuation ← body env shapes next
      invoke ``Lemma.User.Runtime.ManagedRecords.allocate [literal shape.id, literal shape.bytes] value live continuation
    | .sproj n offset source =>
      unless ty == .uint64 && n == 0 && offset % 8 == 0 do throw "Unsupported scalar projection"
      let input ← lookupLocal source
      let .object shape := input.ty | throw "Projection source is not a checked object"
      unless offset + 16 ≤ shape.bytes do throw "Projection exceeds source layout"
      unless input.initialized / 2 ^ (offset / 8) % 2 == 1 do throw "Uninitialized managed projection"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x, ty := .scalar, value := .var value.id .u64}
      let continuation ← body env shapes next
      invoke ``Lemma.User.Runtime.ManagedRecords.readField [input.value, literal shape.id, literal shape.bytes, literal (offset + 8)] value live continuation
    | _ => throw "IR expression outside initial managed subset"
  | .sset target n offset source ty next =>
    unless ty == .uint64 && n == 0 && offset % 8 == 0 do throw "Unsupported scalar field write"
    let input ← lookupLocal target
    let .object shape := input.ty | throw "Field write source is not a checked object"
    unless offset + 16 ≤ shape.bytes do throw "Field write exceeds source layout"
    unless input.owned && input.initialized / 2 ^ (offset / 8) % 2 == 0 do
      throw "Only initial writes to an owned constructor admitted"
    let value ← borrowedScalar (.var source)
    let live ← liveValues
    let unused ← fresh .u64
    modify fun s => {s with locals := s.locals.map fun l => if l.x == target then
      {l with initialized := l.initialized + 2 ^ (offset / 8)} else l}
    let continuation ← body env shapes next
    invoke ``Lemma.User.Runtime.ManagedRecords.writeField [input.value, literal shape.id, literal shape.bytes, literal (offset + 8), value] unused live continuation
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
  unless names.all (fun n => !(n.toString.splitOn ".__lemma_managed_v02.").length > 1) do
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
    | .object _ => unless result == .object do throw "IR/source return object type mismatch"
    let mut initial : State := {resultTy := sourceResult, root}
    for i in [:params.size] do
      unless params[i]!.x.idx < 10000 do throw "Genuine IR parameter exceeds SSA range"
      match sourceParams[i]! with
      | .scalar => unless params[i]!.ty == .uint64 do throw "IR/source scalar parameter mismatch"
      | .object _ => unless params[i]!.ty == .object && params[i]!.borrow do
          throw "Only exact borrowed object parameters admitted"
      let initialized := match sourceParams[i]! with
        | .object shape => 2 ^ (shape.bytes / 8 - 1) - 1
        | .scalar => 0
      initial := {initial with locals := initial.locals.push {
        x := params[i]!.x, ty := sourceParams[i]!, value := .var params[i]!.x.idx .u64, initialized}}
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
  match name.toString.splitOn ".__lemma_managed_v02." with
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

end Lemma.Core0.ManagedIR
