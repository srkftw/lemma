import Lemma.Compiler.Lower

/-!
Closed, test-only compiler fault injection over Lemma's structured LLVM form.

This module is not imported by the production exporter. A request names one of six
reviewed defects and one exact elaborated source declaration. The transform must find
exactly one typed instruction fingerprint in that declaration or fail.
-/

namespace Lemma.Compiler.Test.Mutation

open Lean LLVM

inductive FaultId where
  | ultAsUle
  | ultAsSlt
  | addAsSub
  | zextAsSext
  | truncHighHalf
  | swapCallArgs
  deriving BEq, DecidableEq, Inhabited, Repr

namespace FaultId

def stableId : FaultId → String
  | .ultAsUle => "ult-as-ule"
  | .ultAsSlt => "ult-as-slt"
  | .addAsSub => "add-as-sub"
  | .zextAsSext => "zext-as-sext"
  | .truncHighHalf => "trunc-high-half"
  | .swapCallArgs => "swap-call-args"

def parse? : String → Option FaultId
  | "ult-as-ule" => some .ultAsUle
  | "ult-as-slt" => some .ultAsSlt
  | "add-as-sub" => some .addAsSub
  | "zext-as-sext" => some .zextAsSext
  | "trunc-high-half" => some .truncHighHalf
  | "swap-call-args" => some .swapCallArgs
  | _ => none

def all : Array FaultId :=
  #[.ultAsUle, .ultAsSlt, .addAsSub, .zextAsSext, .truncHighHalf, .swapCallArgs]

end FaultId

structure Request where
  fault : FaultId
  targetSource : Name
  deriving Inhabited, Repr

structure Report where
  fault : FaultId
  targetSource : Name
  targetLLVM : String
  before : String
  after : String
  matchCount : Nat
  deriving Inhabited, Repr

private def renderInstructions (instructions : Array LLVM.Instruction) : String :=
  String.intercalate "\n" (instructions.toList.map LLVM.Instruction.render)

private def mutateInstruction (fault : FaultId) (instruction : LLVM.Instruction) :
    Array LLVM.Instruction × Option (String × String) :=
  let unchanged := (#[instruction], none)
  match fault, instruction with
  | .ultAsUle, .icmp result .ult .i64 (.local "arg0") (.local "arg1") =>
      let changed := LLVM.Instruction.icmp result .ule .i64 (.local "arg0") (.local "arg1")
      (#[changed], some (instruction.render, changed.render))
  | .ultAsSlt, .icmp result .ult .i64 (.local "arg0") (.local "arg1") =>
      let changed := LLVM.Instruction.icmp result .slt .i64 (.local "arg0") (.local "arg1")
      (#[changed], some (instruction.render, changed.render))
  | .addAsSub, .bin result .add .i64 (.local "arg0") (.local "arg1") =>
      let changed := LLVM.Instruction.bin result .sub .i64 (.local "arg0") (.local "arg1")
      (#[changed], some (instruction.render, changed.render))
  | .zextAsSext, .zext result .i32 (.local "arg0") .i64 =>
      let changed := LLVM.Instruction.sext result .i32 (.local "arg0") .i64
      (#[changed], some (instruction.render, changed.render))
  | .truncHighHalf, .trunc result .i64 (.local "arg0") .i32 =>
      let shiftedName := result ++ "_fault_high"
      let shifted := LLVM.Instruction.bin shiftedName .lshr .i64 (.local "arg0") (.int .i64 32)
      let narrowed := LLVM.Instruction.trunc result .i64 (.local shiftedName) .i32
      let changed := #[shifted, narrowed]
      (changed, some (instruction.render, renderInstructions changed))
  | .swapCallArgs, .call result returnType callee args =>
      match args.toList with
      | [first, second] =>
          if callee.startsWith "core0_user_" &&
              first == (.i64, .local "arg0") && second == (.i64, .local "arg1") then
            let swapped := #[second, first]
            let changed := LLVM.Instruction.call result returnType callee swapped
            (#[changed], some (instruction.render, changed.render))
          else
            unchanged
      | _ => unchanged
  | _, _ => unchanged

private def mutateFunction (fault : FaultId) (function : LLVM.Function) :
    LLVM.Function × Array (String × String) := Id.run do
  let mut findings : Array (String × String) := #[]
  let mut blocks : Array LLVM.Block := #[]
  for block in function.blocks do
    let mut instructions : Array LLVM.Instruction := #[]
    for instruction in block.instructions do
      let (replacement, matched?) := mutateInstruction fault instruction
      instructions := instructions ++ replacement
      if let some matched := matched? then
        findings := findings.push matched
    blocks := blocks.push { block with instructions }
  return ({ function with blocks }, findings)

/-- Apply one closed test fault to one exact source declaration. -/
def apply (request : Request) (lowered : LoweredApplication) :
    Except String (LoweredApplication × Report) := do
  let some symbol := lowered.symbols.find? (fun candidate => candidate.source == request.targetSource)
    | throw s!"compiler-fault target `{request.targetSource}` is absent from the checked closure"
  let mut functions : Array LLVM.Function := #[]
  let mut findings : Array (String × String) := #[]
  for function in lowered.functions do
    if function.name == symbol.llvm then
      let (changed, found) := mutateFunction request.fault function
      functions := functions.push changed
      findings := findings ++ found
    else
      functions := functions.push function
  unless findings.size == 1 do
    throw (s!"compiler fault `{request.fault.stableId}` at `{request.targetSource}` matched " ++
      s!"{findings.size} instructions; exactly one is required")
  let matched := findings[0]!
  let report : Report := {
    fault := request.fault
    targetSource := request.targetSource
    targetLLVM := symbol.llvm
    before := matched.1
    after := matched.2
    matchCount := 1
  }
  pure ({ lowered with functions }, report)

end Lemma.Compiler.Test.Mutation
