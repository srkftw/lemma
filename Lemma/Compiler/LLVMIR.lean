namespace Lemma.Compiler.LLVM

inductive Ty where
  | void | i1 | i8 | i32 | i64 | ptr
  deriving Repr, BEq

def Ty.render : Ty → String
  | .void => "void"
  | .i1 => "i1"
  | .i8 => "i8"
  | .i32 => "i32"
  | .i64 => "i64"
  | .ptr => "ptr"

inductive Operand where
  | local (name : String)
  | global (name : String)
  | int (ty : Ty) (value : Nat)
  | null
  deriving Repr, BEq

def Operand.render : Operand → String
  | .local name => "%" ++ name
  | .global name => "@" ++ name
  | .int _ value => toString value
  | .null => "null"

def Operand.typed (op : Operand) (ty : Ty) : String :=
  ty.render ++ " " ++ op.render

inductive BinOp where
  | add | sub | mul | and | or | xor | lshr
  deriving Repr, BEq

def BinOp.render : BinOp → String
  | .add => "add"
  | .sub => "sub"
  | .mul => "mul"
  | .and => "and"
  | .or => "or"
  | .xor => "xor"
  | .lshr => "lshr"

inductive Predicate where
  | eq | ne | ult | ule | ugt | uge | slt
  deriving Repr, BEq

def Predicate.render : Predicate → String
  | .eq => "eq"
  | .ne => "ne"
  | .ult => "ult"
  | .ule => "ule"
  | .ugt => "ugt"
  | .uge => "uge"
  | .slt => "slt"

/-- Integer extension attributes that participate in a platform calling convention.
This is deliberately closed instead of accepting arbitrary textual LLVM attributes. -/
inductive ABIExtension where
  | zeroext
  | signext
  deriving Repr, BEq, DecidableEq

def ABIExtension.render : ABIExtension → String
  | .zeroext => "zeroext"
  | .signext => "signext"

private def renderExtensionPrefix : Option ABIExtension → String
  | some extension => extension.render ++ " "
  | none => ""

private def renderExtensionSuffix : Option ABIExtension → String
  | some extension => " " ++ extension.render
  | none => ""

/-- A call operand together with the exact ABI extension attached at that call site. -/
structure ABIArgument where
  ty : Ty
  value : Operand
  extension : Option ABIExtension := none
  deriving Repr, BEq

def ABIArgument.render (argument : ABIArgument) : String :=
  argument.ty.render ++ renderExtensionSuffix argument.extension ++ " " ++ argument.value.render

inductive Instruction where
  | bin (result : String) (op : BinOp) (ty : Ty) (lhs rhs : Operand)
  | icmp (result : String) (predicate : Predicate) (ty : Ty) (lhs rhs : Operand)
  | zext (result : String) (sourceTy : Ty) (value : Operand) (targetTy : Ty)
  | sext (result : String) (sourceTy : Ty) (value : Operand) (targetTy : Ty)
  | trunc (result : String) (sourceTy : Ty) (value : Operand) (targetTy : Ty)
  | select (result : String) (condition : Operand) (ty : Ty) (onTrue onFalse : Operand)
  | ptrFromInt (result : String) (value : Nat)
  | intToPtr (result : String) (value : Operand)
  | load (result : String) (ty : Ty) (address : Operand) (alignment : Nat) (volatile : Bool)
  | store (ty : Ty) (value address : Operand) (alignment : Nat) (volatile : Bool)
  | call (result : Option String) (returnType : Ty) (callee : String)
      (args : Array (Ty × Operand))
  | abiCall (result : Option String) (returnType : Ty)
      (returnExtension : Option ABIExtension) (callee : String) (args : Array ABIArgument)
  | phi (result : String) (ty : Ty) (incoming : Array (Operand × String))
  | branch (condition : Operand) (onTrue onFalse : String)
  | jump (target : String)
  | ret (ty : Ty) (value : Operand)
  | retVoid
  | unreachable
  deriving Repr, BEq

private def assignment (result : String) : String := "%" ++ result ++ " = "

def Instruction.render : Instruction → String
  | .bin result op ty lhs rhs =>
      assignment result ++ s!"{op.render} {ty.render} {lhs.render}, {rhs.render}"
  | .icmp result predicate ty lhs rhs =>
      assignment result ++ s!"icmp {predicate.render} {ty.render} {lhs.render}, {rhs.render}"
  | .zext result sourceTy value targetTy =>
      assignment result ++ s!"zext {sourceTy.render} {value.render} to {targetTy.render}"
  | .sext result sourceTy value targetTy =>
      assignment result ++ s!"sext {sourceTy.render} {value.render} to {targetTy.render}"
  | .trunc result sourceTy value targetTy =>
      assignment result ++ s!"trunc {sourceTy.render} {value.render} to {targetTy.render}"
  | .select result condition ty onTrue onFalse =>
      assignment result ++ s!"select i1 {condition.render}, {ty.render} {onTrue.render}, {ty.render} {onFalse.render}"
  | .ptrFromInt result value =>
      assignment result ++ s!"inttoptr i64 {value} to ptr"
  | .intToPtr result value =>
      assignment result ++ s!"inttoptr i64 {value.render} to ptr"
  | .load result ty address alignment volatile =>
      assignment result ++ "load " ++ (if volatile then "volatile " else "") ++
        s!"{ty.render}, ptr {address.render}, align {alignment}"
  | .store ty value address alignment volatile =>
      "store " ++ (if volatile then "volatile " else "") ++
        s!"{ty.render} {value.render}, ptr {address.render}, align {alignment}"
  | .call result returnType callee args =>
      let pre := result.map (fun name => assignment name) |>.getD ""
      let renderedArgs := args.toList.map (fun (ty, value) => value.typed ty)
      pre ++ s!"call {returnType.render} @{callee}(" ++ String.intercalate ", " renderedArgs ++ ")"
  | .abiCall result returnType returnExtension callee args =>
      let pre := result.map (fun name => assignment name) |>.getD ""
      let renderedArgs := args.toList.map ABIArgument.render
      pre ++ "call " ++ renderExtensionPrefix returnExtension ++
        s!"{returnType.render} @{callee}(" ++ String.intercalate ", " renderedArgs ++ ")"
  | .phi result ty incoming =>
      let rendered := incoming.toList.map fun (value, label) => s!"[ {value.render}, %{label} ]"
      assignment result ++ s!"phi {ty.render} " ++ String.intercalate ", " rendered
  | .branch condition onTrue onFalse =>
      s!"br i1 {condition.render}, label %{onTrue}, label %{onFalse}"
  | .jump target => s!"br label %{target}"
  | .ret ty value => s!"ret {ty.render} {value.render}"
  | .retVoid => "ret void"
  | .unreachable => "unreachable"

structure Block where
  label : String
  instructions : Array Instruction
  deriving Repr, BEq

def Block.render (block : Block) : String :=
  block.label ++ ":\n" ++ String.intercalate "\n" (block.instructions.toList.map fun i => "  " ++ i.render)

structure Parameter where
  ty : Ty
  name : String
  deriving Repr, BEq

structure Function where
  name : String
  returnType : Ty
  returnExtension : Option ABIExtension := none
  parameters : Array Parameter
  /-- Empty means no ABI extensions (the legacy representation).  Typed ABI
  producers provide one entry per parameter. -/
  parameterExtensions : Array (Option ABIExtension) := #[]
  linkage : Option String := none
  attributes : Array String := #["nounwind"]
  blocks : Array Block
  deriving Repr, BEq

def Function.render (fn : Function) : String :=
  let linkage := fn.linkage.map (· ++ " ") |>.getD ""
  let params := fn.parameters.mapIdx (fun index p =>
    let extension := (fn.parameterExtensions[index]?).getD none
    p.ty.render ++ renderExtensionSuffix extension ++ " %" ++ p.name) |>.toList
  let attrs := if fn.attributes.isEmpty then "" else " " ++ String.intercalate " " fn.attributes.toList
  let header := "define " ++ linkage ++ renderExtensionPrefix fn.returnExtension ++
    s!"{fn.returnType.render} @{fn.name}(" ++ String.intercalate ", " params ++ ")" ++ attrs ++ " {"
  header ++ "\n" ++ String.intercalate "\n" (fn.blocks.toList.map Block.render) ++ "\n}"

structure Declaration where
  name : String
  returnType : Ty
  parameters : Array Ty
  attributes : Array String := #["nounwind"]
  deriving Repr, BEq

def Declaration.render (decl : Declaration) : String :=
  let parameters := String.intercalate ", " (decl.parameters.toList.map Ty.render)
  let attributes :=
    if decl.attributes.isEmpty then "" else " " ++ String.intercalate " " decl.attributes.toList
  s!"declare {decl.returnType.render} @{decl.name}(" ++ parameters ++ ")" ++ attributes

structure Module where
  sourceName : String
  functions : Array Function
  declarations : Array Declaration := #[]
  targetTriple : String := "riscv64-unknown-unknown-elf"
  dataLayout : String := "e-m:e-p:64:64-i64:64-i128:128-n32:64-S128"
  deriving Repr, BEq

def Module.render (module : Module) : String :=
  String.intercalate "\n" <| [
    s!"; generated by Lemma Core0 from {module.sourceName}",
    s!"source_filename = \"{module.sourceName}\"",
    s!"target datalayout = \"{module.dataLayout}\"",
    s!"target triple = \"{module.targetTriple}\"",
    ""
  ] ++ module.declarations.toList.map Declaration.render ++ [""] ++
  module.functions.toList.map Function.render ++ [
    "",
    "!llvm.module.flags = !{!0, !1, !2}",
    "!0 = !{i32 1, !\"wchar_size\", i32 4}",
    "!1 = !{i32 1, !\"target-abi\", !\"lp64\"}",
    "!2 = !{i32 8, !\"SmallDataLimit\", i32 0}",
    ""
  ]

end Lemma.Compiler.LLVM
