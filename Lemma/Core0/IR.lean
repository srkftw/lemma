import Lean

/-!
The checked, backend-neutral representation for the versioned Core0 profiles.

`Expr` deliberately has no generic application, closure, allocation, projection, or
foreign-call node.  The frontend is the only module which translates kernel-checked
Lean expressions into this type.  Thus an LLVM backend can be total over the small
set of constructors below without silently accepting another Lean feature.
-/

namespace Lemma.Core0

open Lean

/-- Closed, versioned source-language profiles.  New operations are never made
available by silently changing the meaning of an older contract string. -/
inductive Profile where
  | v0_1
  | v0_2
  | v0_3
  | v0_4
  | v0_5
  | v0_6
  | v0_7
  | firmware_v0_1
  | kernel_v0_1
  | kernel_v0_2
  | kernel_v0_3
  | user_v0_1
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Profile

def contractVersion : Profile → String
  | .v0_1 => "core0-v0.1"
  | .v0_2 => "core0-v0.2"
  | .v0_3 => "core0-v0.3"
  | .v0_4 => "core0-v0.4"
  | .v0_5 => "core0-v0.5"
  | .v0_6 => "core0-v0.6"
  | .v0_7 => "core0-v0.7"
  | .firmware_v0_1 => "core0-firmware-v0.1"
  | .kernel_v0_1 => "core0-kernel-v0.1"
  | .kernel_v0_2 => "core0-kernel-v0.2"
  | .kernel_v0_3 => "core0-kernel-v0.3"
  | .user_v0_1 => "core0-user-v0.1"

def ofContractVersion? : String → Option Profile
  | "core0-v0.1" => some .v0_1
  | "core0-v0.2" => some .v0_2
  | "core0-v0.3" => some .v0_3
  | "core0-v0.4" => some .v0_4
  | "core0-v0.5" => some .v0_5
  | "core0-v0.6" => some .v0_6
  | "core0-v0.7" => some .v0_7
  | "core0-firmware-v0.1" => some .firmware_v0_1
  | "core0-kernel-v0.1" => some .kernel_v0_1
  | "core0-kernel-v0.2" => some .kernel_v0_2
  | "core0-kernel-v0.3" => some .kernel_v0_3
  | "core0-user-v0.1" => some .user_v0_1
  | _ => none

/-- Production execution profiles have separate authority from the diagnostic profiles. -/
def isExecution : Profile → Bool
  | .firmware_v0_1 | .kernel_v0_1 | .kernel_v0_2 | .kernel_v0_3 | .user_v0_1 => true
  | _ => false

def isKernel : Profile → Bool
  | .kernel_v0_1 | .kernel_v0_2 | .kernel_v0_3 => true
  | _ => false

end Profile

/-- Runtime scalar types shared by the implemented Core0 profiles. -/
inductive Ty where
  | bool
  | u8
  | u32
  | u64
  deriving BEq, DecidableEq, Inhabited, Repr

namespace Ty

def width : Ty → Nat
  | .bool => 1
  | .u8 => 8
  | .u32 => 32
  | .u64 => 64

def isInteger : Ty → Bool
  | .bool => false
  | _ => true

def render : Ty → String
  | .bool => "bool"
  | .u8 => "u8"
  | .u32 => "u32"
  | .u64 => "u64"

end Ty

inductive BinOp where
  | add
  | sub
  | mul
  | band
  | bor
  | bxor
  | shl
  | lshr
  | udiv
  | urem
  deriving BEq, DecidableEq, Inhabited, Repr

namespace BinOp

def render : BinOp → String
  | .add => "add"
  | .sub => "sub"
  | .mul => "mul"
  | .band => "and"
  | .bor => "or"
  | .bxor => "xor"
  | .shl => "shl"
  | .lshr => "lshr"
  | .udiv => "udiv"
  | .urem => "urem"

end BinOp

inductive UnaryOp where
  | complement
  deriving BEq, DecidableEq, Inhabited, Repr

namespace UnaryOp

def render : UnaryOp → String
  | .complement => "complement"

end UnaryOp

inductive CmpOp where
  | eq
  | ult
  | ule
  deriving BEq, DecidableEq, Inhabited, Repr

namespace CmpOp

def render : CmpOp → String
  | .eq => "eq"
  | .ult => "ult"
  | .ule => "ule"

end CmpOp

/-- Conversions are unsigned zero-extension or low-bit truncation. -/
inductive CastOp where
  | zext
  | trunc
  deriving BEq, DecidableEq, Inhabited, Repr

namespace CastOp

def render : CastOp → String
  | .zext => "zext"
  | .trunc => "trunc"

end CastOp

/-- Every node carries enough type information for lowering to check its inputs. -/
inductive Expr where
  | var (id : Nat) (ty : Ty)
  | lit (ty : Ty) (value : Nat)
  | boolLit (value : Bool)
  | letE (id : Nat) (name : Name) (ty : Ty) (value body : Expr)
  | bin (op : BinOp) (ty : Ty) (lhs rhs : Expr)
  | unary (op : UnaryOp) (ty : Ty) (value : Expr)
  | cmp (op : CmpOp) (operandTy : Ty) (lhs rhs : Expr)
  | ite (resultTy : Ty) (cond thenBranch elseBranch : Expr)
  | call (callee : Name) (resultTy : Ty) (args : List Expr)
  | cast (op : CastOp) (sourceTy targetTy : Ty) (value : Expr)
  /-- A profile-v0.3 bounded fold.  The callback is a statically resolved,
  checked function with signature `(u32, u32) -> u32`; it is not a runtime
  closure.  `budget` is a checked source literal and `count` is runtime data. -/
  | boundedFoldU32 (budget : Nat) (callback : Name) (count initial : Expr)
  deriving BEq, Inhabited, Repr

def Expr.type : Expr → Ty
  | .var _ ty => ty
  | .lit ty _ => ty
  | .boolLit _ => .bool
  | .letE _ _ _ _ body => body.type
  | .bin _ ty _ _ => ty
  | .unary _ ty _ => ty
  | .cmp .. => .bool
  | .ite ty _ _ _ => ty
  | .call _ ty _ => ty
  | .cast _ _ targetTy _ => targetTy
  | .boundedFoldU32 .. => .u64

/-- A deterministic, typed representation of the checked expression consumed by
the backend.  This is deliberately independent of Lean's derived `Repr` format so
the evidence artifact changes only when the Core0 program changes deliberately. -/
def Expr.renderNormalized : Expr → String
  | .var id ty => s!"(var {id} {ty.render})"
  | .lit ty value => s!"(lit {ty.render} {value})"
  | .boolLit value => if value then "(bool true)" else "(bool false)"
  | .letE id name ty value body =>
      s!"(let {id} {name} {ty.render} {value.renderNormalized} {body.renderNormalized})"
  | .bin op ty lhs rhs =>
      s!"(bin {op.render} {ty.render} {lhs.renderNormalized} {rhs.renderNormalized})"
  | .unary op ty value =>
      s!"(unary {op.render} {ty.render} {value.renderNormalized})"
  | .cmp op operandTy lhs rhs =>
      s!"(cmp {op.render} {operandTy.render} {lhs.renderNormalized} {rhs.renderNormalized})"
  | .ite resultTy cond thenBranch elseBranch =>
      s!"(ite {resultTy.render} {cond.renderNormalized} " ++
        s!"{thenBranch.renderNormalized} {elseBranch.renderNormalized})"
  | .call callee resultTy args =>
      let renderedArgs := String.intercalate " " (args.map Expr.renderNormalized)
      s!"(call {callee} {resultTy.render} [{renderedArgs}])"
  | .cast op sourceTy targetTy value =>
      s!"(cast {op.render} {sourceTy.render} {targetTy.render} {value.renderNormalized})"
  | .boundedFoldU32 budget callback count initial =>
      s!"(bounded-fold-u32 budget={budget} callback={callback} " ++
        s!"count={count.renderNormalized} initial={initial.renderNormalized})"

structure Param where
  id : Nat
  name : Name
  ty : Ty
  deriving BEq, Inhabited, Repr

structure Signature where
  args : Array Ty
  result : Ty
  deriving BEq, Inhabited, Repr

structure Function where
  name : Name
  signature : Signature
  params : Array Param
  body : Expr
  /-- Direct user-declaration dependencies, in first-occurrence order. -/
  dependencies : Array Name
  deriving BEq, Inhabited, Repr

inductive Effect where
  | pure
  deriving BEq, DecidableEq, Inhabited, Repr

/--
An exact primitive contract.  `leanDecl` is the canonical implementation identity;
notation wrappers are accepted only after their type and instance arguments have
been checked to select this exact declaration.
-/
structure PrimitiveSpec where
  stableId : String
  leanDecl : Name
  signature : Signature
  effect : Effect := .pure
  deriving BEq, Inhabited, Repr

/-- Metadata for a compiler-recognized iteration form.  This is intentionally
separate from `PrimitiveSpec`: the static budget and statically resolved callback
are not ordinary runtime scalar arguments. -/
structure IterationSpec where
  stableId : String
  leanDecl : Name
  runtimeSignature : Signature
  callbackSignature : Signature
  maximumBudget : Nat
  effect : Effect := .pure
  deriving BEq, Inhabited, Repr

/-- Stable manifest identity for the only v0.3 iteration form. -/
def boundedFoldU32StableId : String := "u32.bounded-fold"

/-- One checked use of an iteration form, retained in manifests so a build cannot
hide the concrete source budget or callback behind an ordinary primitive ID. -/
structure IterationUse where
  stableId : String
  budget : Nat
  callback : Name
  deriving BEq, Inhabited, Repr

structure Program where
  contractVersion : String := "core0-v0.1"
  root : Name
  /-- Dependency-first topological order; the root is last. -/
  functions : Array Function
  /-- Stable IDs from `primitiveAllowlist`, in first-use order. -/
  usedPrimitives : Array String
  /-- Checked compiler-recognized iteration sites, in first-use order. -/
  usedIterations : Array IterationUse := #[]
  deriving Inhabited, Repr

/-- One externally callable root in an additive, multi-root checked corpus.  IDs are
assigned deterministically from the caller's declared root order and start at one. -/
structure CheckedRoot where
  id : Nat
  source : Name
  signature : Signature
  deriving BEq, Inhabited, Repr

/-- A deduplicated union of programs checked under one explicit Core0 profile. -/
structure CheckedSuite where
  contractVersion : String := "core0-v0.1"
  roots : Array CheckedRoot
  /-- Dependency-first order across the complete root set. -/
  functions : Array Function
  /-- Stable primitive IDs in first-use order across the declared roots. -/
  usedPrimitives : Array String
  /-- Deduplicated checked iteration sites across the declared roots. -/
  usedIterations : Array IterationUse := #[]
  deriving BEq, Inhabited, Repr

def Program.findFunction? (program : Program) (name : Name) : Option Function :=
  program.functions.find? (fun f => f.name == name)

def CheckedSuite.findFunction? (suite : CheckedSuite) (name : Name) : Option Function :=
  suite.functions.find? (fun f => f.name == name)

def CheckedSuite.findRoot? (suite : CheckedSuite) (name : Name) : Option CheckedRoot :=
  suite.roots.find? (fun root => root.source == name)

def CheckedSuite.findRootById? (suite : CheckedSuite) (id : Nat) : Option CheckedRoot :=
  suite.roots.find? (fun root => root.id == id)

private def joinNames (names : Array Name) : String :=
  String.intercalate "," (names.toList.map Name.toString)

private def renderSignature (sig : Signature) : String :=
  let args := String.intercalate "," (sig.args.toList.map Ty.render)
  s!"({args})->{sig.result.render}"

/-- Deterministic, line-oriented manifest suitable for evidence and hash comparison. -/
def Program.renderManifest (program : Program) : String :=
  let header := s!"contract={program.contractVersion}\nroot={program.root}\n"
  let functions := program.functions.toList.map fun f =>
    s!"function={f.name};signature={renderSignature f.signature};" ++
      s!"deps=[{joinNames f.dependencies}];body={f.body.renderNormalized}\n"
  let primitives := program.usedPrimitives.toList.map fun p => s!"primitive={p}\n"
  let iterations := program.usedIterations.toList.map fun site =>
    s!"iteration={site.stableId};budget={site.budget};callback={site.callback}\n"
  header ++ String.join functions ++ String.join primitives ++ String.join iterations

end Lemma.Core0
