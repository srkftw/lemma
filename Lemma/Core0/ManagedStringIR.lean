import Lean.Compiler.Main
import Lean.Compiler.IR.Format
import Lemma.Core0.ActionIR
import Lemma.User.Runtime.ManagedString

/-! Checked lowering of ordinary nonrecursive String/UTF8 code. The actual
upstream IR supplies all ownership/control operations. No hand-authored IR
or host runtime supplies source behavior. Historical bridges remain separate. -/
namespace Lemma.Core0.ManagedStringIR
open Lean
abbrev A := ActionExpr
abbrev E := Expr
abbrev P := Param
inductive ValueTy where
  | scalar | byte | natural | buffer | text | optional | boolean
  deriving Inhabited, Repr, BEq
structure Local where
  x : IR.VarId
  ty : ValueTy
  value : E
  references : Nat := 0
  alive : Bool := true
  borrowedFrom : Option IR.VarId := none
  variant : Option Nat := none
  taggedText : Bool := false
structure State where
  next : Nat := 10000
  locals : Array Local := #[]
  callees : Array Name := #[]
  fuel : Nat := 4096
  resultTy : ValueTy := .scalar
  root : Name := .anonymous
abbrev M := StateT State (Except String)
def literal (n : Nat) : E := .lit .u64 n
def fresh (ty : Ty) : M P := do
  let s ← get
  unless s.next < 65536 do throw "String SSA budget exceeded"
  set {s with next := s.next + 1}
  return {id := s.next, name := .anonymous, ty}
def lookupLocal (x : IR.VarId) : M Local := do
  let some l := (← get).locals.find? (·.x == x) | throw s!"Unknown IR variable {x}"
  unless l.alive do throw "Read after reference consumption rejected"
  if let some owner := l.borrowedFrom then
    let some parent := (← get).locals.find? (·.x == owner) | throw "String projection owner absent"
    unless parent.alive && parent.ty == .optional && parent.variant == some 1 do
      throw "String projection outlived its exact Option.some owner"
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
  unless entry.ty == ty do throw "ByteArray primitive/source argument type differs"
  return entry.value
def consume (x : IR.VarId) : M Unit := do
  let l ← lookupLocal x
  unless (l.ty == .buffer || l.ty == .text || l.ty == .optional) && l.references > 0 do
    throw "Consume of borrowed managed value rejected"
  modify fun s => {s with locals := s.locals.map fun v => if v.x == x then
    {v with references := v.references-1, alive := v.references>1} else v}
def sourceType (e : Lean.Expr) : Except String ValueTy := do
  if e == .app (.const ``Option [Level.zero]) (.const ``String []) then return .optional
  let .const n [] := e | throw "String signature must be closed and monomorphic"
  if n == ``UInt64 then return .scalar
  if n == ``UInt8 then return .byte
  if n == ``ByteArray then return .buffer
  if n == ``String then return .text
  throw s!"Unadmitted ordinary source type {n}"
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
def genName (root name : Name) : Name := root ++ `__lemma_managed_string_v06 ++ name
def primitive (name : Name) : Bool :=
  [``UInt64.add, ``UInt64.sub, ``UInt64.mul, ``UInt64.shiftLeft, ``UInt64.shiftRight,
   ``UInt64.land, ``UInt64.lor, ``UInt64.xor, ``UInt64.decEq, ``UInt64.decLt,
   ``UInt64.toUInt8, ``UInt8.toUInt64,
   ``UInt64.toNat, ``UInt64.ofNat, ``ByteArray.emptyWithCapacity, ``ByteArray.push,
   ``ByteArray.set!, ``ByteArray.get!, ``ByteArray.size,
   ``ByteArray.validateUTF8, ``String.ofByteArray, ``String.append,
   ``String.length, ``String.utf8ByteSize, ``String.toByteArray].contains name
partial def dependencies (body : IR.FnBody) : Except String (Array Name) := do
  match body with
  | .ret _ => return #[]
  | .vdecl _ _ expression next =>
    let rest ← dependencies next
    match expression with
    | .fap name _ => return if primitive name || rest.contains name then rest else rest.push name
    | .lit (.num _) | .ctor _ _ | .proj _ _ => return rest
    | _ => throw "Unsupported ByteArray IR expression/static object"
  | .inc _ _ _ _ next | .dec _ _ _ _ next => dependencies next
  | .case _ _ _ alternatives =>
    let mut result := #[]
    for alternative in alternatives do
      let branch := match alternative with | .ctor _ b => b | .default b => b
      for name in ← dependencies branch do
        unless result.contains name do result := result.push name
    return result
  | _ => throw "Unsupported ByteArray IR control/ownership form"
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
        if visiting.contains name then throw "Recursive ByteArray call rejected" else
        unless depth ≤ 8 && done.size + visiting.size < 32 do throw "ByteArray closure bound exceeded"
        let _ ← signature env name
        let some (.fdecl _ _ _ ir info) := IR.findEnvDecl env name | throw "Missing genuine ordinary compiler IR"
        unless info.sorryDep?.isNone do throw "Sorry-dependent source rejected"
        let callees ← dependencies ir
        visiting := visiting.push name
        stack := callees.toList.map (fun n => .enter n (depth+1)) ++ [.exit name] ++ stack
      | .exit name =>
        visiting := visiting.filter (· != name)
        unless done.contains name do done := done.push name
  return done
def releaseName (ty : ValueTy) : Name :=
  if ty == .text then ``Lemma.User.Runtime.ManagedString.release else
  if ty == .optional then ``Lemma.User.Runtime.ManagedString.releaseOption else
  ``Lemma.User.Runtime.Arena.release
def cleanup (status : E) (live : List (ValueTy × E)) : M A := do
  match live with
  | [] => return .done status (literal 0)
  | (ty,handle) :: rest =>
    let cleanupStatus ← fresh .u8
    let unused ← fresh .u64
    let selected : E := .ite .u8 (.cmp .eq .u8 status (.lit .u8 0)) (.var cleanupStatus.id .u8) status
    let next ← cleanup selected rest
    let release := releaseName ty
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
  | .byte | .boolean => actual == .uint8
  | .natural => actual == .tagged || actual == .tobject
  | .buffer => actual == .object
  | .text => actual == .object
  | .optional => actual == .tobject
partial def body (env : Environment) (b : IR.FnBody) : M A := do
  let state ← get
  unless state.fuel>0 do throw "ByteArray IR node budget exceeded"
  modify fun s => {s with fuel := s.fuel-1}
  match b with
  | .ret a =>
    let entry ← arg a
    unless entry.ty == (← get).resultTy do throw "Source/IR return type differs"
    if entry.ty == .buffer || entry.ty == .text || entry.ty == .optional then
      unless entry.references == 1 || (entry.ty == .optional && entry.variant == some 0 && entry.references == 0) do
        throw "Returned managed value requires one owned root or immediate Option.none"
    unless !(← get).locals.any (fun l => l.references>0 && l.x != entry.x) do throw "Unreleased buffer at return"
    return .done (.lit .u8 0) entry.value
  | .vdecl x ty expression next =>
    match expression with
    | .lit (.num n) =>
      let valueTy ← if ty == .uint64 && n<2^64 then pure ValueTy.scalar else
        if ty == .uint8 && n<256 then pure ValueTy.byte else
        if ty == .tagged && n≤48 then pure ValueTy.natural else throw "Unadmitted literal/layout"
      addLocal {x, ty := valueTy, value := literal n}
      body env next
    | .fap name args =>
      if [``UInt64.add, ``UInt64.sub, ``UInt64.mul, ``UInt64.shiftLeft, ``UInt64.shiftRight,
          ``UInt64.land, ``UInt64.lor, ``UInt64.xor, ``UInt64.decEq, ``UInt64.decLt].contains name then
        unless args.size == 2 do throw "Scalar primitive arity differs"
        let lhs ← requireArg args[0]! .scalar
        let rhs ← requireArg args[1]! .scalar
        if name == ``UInt64.decEq || name == ``UInt64.decLt then
          unless ty == .uint8 do throw "Boolean result layout differs"
          addLocal {x, ty := .boolean, value := .cast .zext .bool .u64 (.cmp (if name == ``UInt64.decEq then .eq else .ult) .u64 lhs rhs)}
        else
          unless ty == .uint64 do throw "Scalar result layout differs"
          let op := if name == ``UInt64.add then BinOp.add else if name == ``UInt64.sub then .sub else
            if name == ``UInt64.mul then .mul else if name == ``UInt64.shiftLeft then .shl else
            if name == ``UInt64.shiftRight then .lshr else if name == ``UInt64.land then .band else
            if name == ``UInt64.lor then .bor else .bxor
          addLocal {x, ty := .scalar, value := .bin op .u64 lhs (if op == .shl || op == .lshr then .bin .band .u64 rhs (literal 63) else rhs)}
        body env next
      else if name == ``UInt64.toUInt8 || name == ``UInt8.toUInt64 || name == ``UInt64.ofNat then
        unless args.size == 1 do throw "Conversion arity differs"
        let inputTy : ValueTy := if name == ``UInt64.toUInt8 then ValueTy.scalar else if name == ``UInt8.toUInt64 then .byte else .natural
        let result := if name == ``UInt64.toUInt8 then ValueTy.byte else .scalar
        unless irType result ty do throw "Conversion result layout differs"
        let value ← requireArg args[0]! inputTy
        addLocal {x, ty := result, value := if result == .byte then .bin .band .u64 value (literal 255) else value}
        body env next
      else if primitive name then
        let (runtime,result,arguments) ← if name == ``UInt64.toNat then
          unless args.size == 1 && irType .natural ty do throw "Bounded Nat conversion IR differs"
          pure (``Lemma.User.Runtime.ManagedBytes.natural, ValueTy.natural, [← requireArg args[0]! .scalar])
        else if name == ``ByteArray.emptyWithCapacity then
          unless args.size == 1 && irType .buffer ty do throw "ByteArray allocation IR differs"
          pure (``Lemma.User.Runtime.ManagedBytes.emptyWithCapacity, ValueTy.buffer, [← requireArg args[0]! .natural])
        else if name == ``ByteArray.size then
          unless args.size == 1 && irType .natural ty do throw "ByteArray size IR differs"
          pure (``Lemma.User.Runtime.ManagedBytes.size, ValueTy.natural, [← requireArg args[0]! .buffer])
        else if name == ``ByteArray.get! then
          unless args.size == 2 && irType .byte ty do throw "ByteArray access IR differs"
          pure (``Lemma.User.Runtime.ManagedBytes.get, ValueTy.byte, [← requireArg args[0]! .buffer, ← requireArg args[1]! .natural])
        else if name == ``ByteArray.validateUTF8 then
          unless args.size == 1 && irType .boolean ty do throw "UTF8 validation result/arity differs"
          pure (``Lemma.User.Runtime.ManagedString.validateUTF8,ValueTy.boolean,[← requireArg args[0]! .buffer])
        else if name == ``String.ofByteArray then
          unless args.size == 2 && args[1]! == .erased && irType .text ty do
            throw "String constructor's exact erased proof/IR differs"
          let input ← arg args[0]!
          unless input.ty == .buffer do throw "String constructor requires an owned ByteArray"
          consume input.x
          pure (``Lemma.User.Runtime.ManagedString.fromByteArray,ValueTy.text,[input.value])
        else if name == ``String.length || name == ``String.utf8ByteSize then
          unless args.size == 1 && irType .natural ty do throw "String size IR differs"
          pure ((if name == ``String.length then ``Lemma.User.Runtime.ManagedString.length else
            ``Lemma.User.Runtime.ManagedString.byteSize),ValueTy.natural,[← requireArg args[0]! .text])
        else if name == ``String.toByteArray then
          unless args.size == 1 && irType .buffer ty do throw "String byte extraction IR differs"
          let input ← arg args[0]!
          unless input.ty == .text do throw "String byte extraction requires an owned String"
          consume input.x
          pure (``Lemma.User.Runtime.ManagedString.toByteArray,ValueTy.buffer,[input.value])
        else if name == ``String.append then
          unless args.size == 2 && irType .text ty do throw "String append IR differs"
          let left ← arg args[0]!
          let right ← arg args[1]!
          unless left.ty == .text && right.ty == .text do throw "String append argument types differ"
          consume left.x
          pure (``Lemma.User.Runtime.ManagedString.append,ValueTy.text,[left.value,right.value])
        else if name == ``ByteArray.push || name == ``ByteArray.set! then
          unless args.size == (if name == ``ByteArray.push then 2 else 3) && irType .buffer ty do throw "ByteArray update IR differs"
          let buffer ← arg args[0]!
          unless buffer.ty == .buffer do throw "Update source is not exact ByteArray"
          let tail ← if name == ``ByteArray.push then pure [← requireArg args[1]! .byte] else
            pure [← requireArg args[1]! .natural, ← requireArg args[2]! .byte]
          consume buffer.x
          pure ((if name == ``ByteArray.push then ``Lemma.User.Runtime.ManagedBytes.push else ``Lemma.User.Runtime.ManagedBytes.set),ValueTy.buffer,buffer.value::tail)
        else throw "Unimplemented ByteArray primitive"
        let live ← liveValues
        let value ← fresh .u64
        addLocal {x, ty := result, value := .var value.id .u64, references := if result == .buffer || result == .text || result == .optional then 1 else 0}
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
          if (actual.ty == .buffer || actual.ty == .text || actual.ty == .optional) && !params[i]!.borrow then consume actual.x
          arguments := arguments ++ [actual.value]
        let live ← liveValues
        let value ← fresh .u64
        addLocal {x, ty := resultTy, value := .var value.id .u64, references := if resultTy == .buffer || resultTy == .text || resultTy == .optional then 1 else 0}
        let continuation ← body env next
        invoke (genName (← get).root name) arguments value live continuation
    | .ctor info args =>
      unless info.usize == 0 && info.ssize == 0 do throw "Option constructor scalar layout differs"
      if info.name == ``Option.none then
        unless info.cidx == 0 && info.size == 0 && args.isEmpty && ty == .tagged do
          throw "Immediate Option.none layout differs"
        addLocal {x,ty := .optional,value := literal 0,variant := some 0}
        body env next
      else if info.name == ``Option.some then
        unless info.cidx == 1 && info.size == 1 && args.size == 1 && ty == .object do
          throw "Option.some String object layout differs"
        let child ← arg args[0]!
        unless child.ty == .text do throw "Option.some payload is not exact String"
        consume child.x
        let live ← liveValues
        let value ← fresh .u64
        addLocal {x,ty := .optional,value := .var value.id .u64,references := 1,variant := some 1}
        let continuation ← body env next
        invoke ``Lemma.User.Runtime.ManagedString.some [child.value] value live continuation
      else throw "Constructor outside exact Option String family"
    | .proj index owner =>
      let parent ← lookupLocal owner
      unless index == 0 && parent.ty == .optional && parent.variant == some 1 &&
          parent.references>0 && ty == .tobject do throw "String projection lacks a live exact Option.some witness"
      let live ← liveValues
      let value ← fresh .u64
      addLocal {x,ty := .text,value := .var value.id .u64,borrowedFrom := some owner,taggedText := true}
      let continuation ← body env next
      invoke ``Lemma.User.Runtime.ManagedString.getSome [parent.value] value live continuation
    | _ => throw "Static objects/closures/unknown constructors/projections outside String subset"
  | .inc x n conditional persistent next =>
    let entry ← lookupLocal x
    unless n == 1 && !persistent && (!conditional || entry.ty == .optional ||
        (entry.ty == .text && entry.borrowedFrom.isSome)) do
      throw "Unsupported increment metadata"
    unless (entry.ty == .buffer || entry.ty == .text || entry.ty == .optional) &&
        (entry.references>0 || (entry.ty == .text && entry.borrowedFrom.isSome)) && entry.references<8 do
      throw "Increment requires an owned root or a witnessed String projection"
    let live ← liveValues
    modify fun s => {s with locals := s.locals.map fun l => if l.x == x then
      {l with references := l.references+1,borrowedFrom := none} else l}
    let unused ← fresh .u64
    let continuation ← body env next
    invoke (if entry.ty == .text then ``Lemma.User.Runtime.ManagedString.retain else
      if entry.ty == .optional then ``Lemma.User.Runtime.ManagedString.retainOption else
      ``Lemma.User.Runtime.ManagedBytes.retain) [entry.value] unused live continuation
  | .dec x n conditional persistent next =>
    let entry ← lookupLocal x
    unless n == 1 && !persistent && (entry.ty == .natural || entry.ty == .optional || (entry.ty == .text && entry.taggedText) || !conditional) do
      throw s!"Unsupported decrement metadata {x} {n} {conditional} {persistent}"
    if entry.ty == .natural then
      -- This Nat is known to be a ≤48 scalar, so genuine IR's decrement has
      -- no allocated box to reclaim. It is never a fabricated RC helper.
      modify fun s => {s with locals := s.locals.map fun l => if l.x == x then {l with alive := false} else l}
      body env next
    else
      consume x
      let live ← liveValues
      let unused ← fresh .u64
      let continuation ← body env next
      invoke (releaseName entry.ty) [entry.value] unused live continuation
  | .case name source irTy alternatives =>
    let entry ← lookupLocal source
    let optionCase := entry.ty == .optional
    unless alternatives.size == 2 &&
        ((entry.ty == .boolean && name == ``UInt8 && irTy == .uint8) ||
         (optionCase && name == `tobj && irTy == .tobject)) do
      throw "Only exhaustive exact Bool or Option String cases admitted"
    let baseline ← get
    let mut finalState := baseline
    let mut branches : Array (Nat × A) := #[]
    for alternative in alternatives do
      let .ctor info branch := alternative | throw "Default case rejected"
      unless info.usize == 0 && info.ssize == 0 && !branches.any (·.1 == info.cidx) &&
        (if optionCase then
          (info.name == ``Option.none && info.cidx == 0 && info.size == 0) ||
          (info.name == ``Option.some && info.cidx == 1 && info.size == 1)
        else info.size == 0 &&
          ((info.name == ``Bool.false && info.cidx == 0) || (info.name == ``Bool.true && info.cidx == 1))) do
        throw "Exact constructor family/layout differs"
      set {baseline with next := finalState.next, fuel := finalState.fuel, callees := finalState.callees}
      if optionCase then modify fun s => {s with locals := s.locals.map fun l => if l.x == source then
        {l with variant := some info.cidx, references := if info.cidx == 0 then 0 else l.references, alive := info.cidx != 0} else l}
      let lowered ← body env branch
      finalState ← get
      branches := branches.push (info.cidx,lowered)
    set {baseline with next := finalState.next, fuel := finalState.fuel, callees := finalState.callees}
    if optionCase then
      let live ← liveValues
      let tag ← fresh .u64
      invoke ``Lemma.User.Runtime.ManagedString.optionTag [entry.value] tag live
        (.ite (.cmp .eq .u64 (.var tag.id .u64) (literal branches[0]!.1)) branches[0]!.2 branches[1]!.2)
    else return .ite (.cmp .eq .u64 entry.value (literal branches[0]!.1)) branches[0]!.2 branches[1]!.2
  | _ => throw "IR join/loop/reuse/closure form outside String subset"
structure Program where
  root : Name
  sourceNames : Array Name
  functions : Array ActionFunction

def buildProgram (env : Environment) (root : Name) : Except String Program := do
  let names ← sourceClosure env root
  unless names.all (fun n => !(n.toString.splitOn ".__lemma_managed_string_v06.").length>1) do throw "Reserved generated source name"
  let (entryParams,entryResult) ← signature env root
  unless entryParams == #[.scalar,.scalar] && entryResult == .scalar do throw "ByteArray bridge requires scalar UInt64 -> UInt64 -> UInt64 entry"
  let mut sawString := false
  let mut functions : Array ActionFunction := #[]
  for name in names do
    let some (.fdecl _ params result ir info) := IR.findEnvDecl env name | throw "Missing genuine IR"
    let (sourceParams,sourceResult) ← signature env name
    unless info.sorryDep?.isNone && params.size == sourceParams.size && irType sourceResult result do throw "Source/IR function layout differs"
    let mut initial : State := {resultTy := sourceResult,root}
    for i in [:params.size] do
      let ty := sourceParams[i]!
      unless irType ty params[i]!.ty && params[i]!.x.idx<10000 &&
          !initial.locals.any (·.x == params[i]!.x) do throw "Parameter layout/range/uniqueness differs"
      if ty == .text then sawString := true
      initial := {initial with locals := initial.locals.push {
        x := params[i]!.x, ty := ty, value := .var params[i]!.x.idx .u64,
        references := if (ty == .buffer || ty == .text || ty == .optional) && !params[i]!.borrow then 1 else 0}}
    if sourceResult == .text then sawString := true
    let (lowered,state) ← (body env ir).run initial
    functions := functions.push {
      name := genName root name
      signature := {args := Array.replicate params.size .u64}
      params := params.map fun p => {id := p.x.idx, name := .anonymous, ty := .u64}
      body := lowered
      scalarDependencies := #[]
      actionDependencies := state.callees
      directEffects := .empty
      effects := .empty }
  unless sawString do throw "String entry has no actual ordinary String value"
  return {root,sourceNames := names,functions}
def generatedSource? (name : Name) : Option (Name × Name) :=
  match name.toString.splitOn ".__lemma_managed_string_v06." with
  | [root,source] => if root.isEmpty || source.isEmpty then none else some (root.toName,source.toName)
  | _ => none
def generatedFunction (env : Environment) (name : Name) : Except String ActionFunction := do
  let some (root,source) := generatedSource? name | throw "Not a generated String source"
  let program ← buildProgram env root
  unless program.sourceNames.contains source && genName root source == name do throw "Generated source outside genuine closure"
  let some function := program.functions.find? (·.name == name) | throw "Missing generated ByteArray action"
  return function
end Lemma.Core0.ManagedStringIR
