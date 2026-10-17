import Lean
import Lean.Compiler.Main
import Lean.Compiler.IR.Format
import Lemma.Core0.Frontend
import Lemma.Compiler.CFGLower
import Lemma.Core0.MemoryModel
import Lemma.User.ClosureExamples

/-- Genuine ordinary negative: this global cannot collide with dispatch ABI. -/
@[noinline] def __apply (capture input : UInt64) : UInt64 := capture+input

namespace Lemma.Compiler.Test.ManagedClosure
open Lemma.Core0.Memory
@[noinline] def staticCapture (a b : UInt64) : UInt64 :=
  let function := Lemma.User.ClosureExamples.plus 3
  Lemma.User.ClosureExamples.apply function (a+b)
@[noinline] def choose (selector : UInt64) (left right : UInt64 → UInt64) : UInt64 → UInt64 :=
  if selector = 0 then left else right
@[noinline] def nestedCapture (a b : UInt64) : UInt64 :=
  let function := choose a (Lemma.User.ClosureExamples.plus b) (Lemma.User.ClosureExamples.times b)
  Lemma.User.ClosureExamples.apply function b
@[noinline] def dispatcherCollision (a b : UInt64) : UInt64 :=
  let function := __apply a
  Lemma.User.ClosureExamples.apply function b
@[noinline] def scalarOnly (a b : UInt64) : UInt64 := a+b
@[noinline] def loop (n : Nat) (v : UInt64) : UInt64 :=
  match n with | 0 => v | n+1 => loop n (v+1)
@[noinline] def recursive (a b : UInt64) : UInt64 := loop a.toNat b

def selected (a b : UInt64) : Action :=
  .managedClosure2 Lemma.User.ClosureExamples.selected a b fun s v => .done s v
def four (a b : UInt64) : Action :=
  .managedClosure2 Lemma.User.ClosureExamples.fourCaptures a b fun s v => .done s v
def lambda (a b : UInt64) : Action :=
  .managedClosure2 Lemma.User.ClosureExamples.lambdaEntry a b fun s v => .done s v
def shared (a b : UInt64) : Action :=
  .managedClosure2 Lemma.User.ClosureExamples.sharedCaptures a b fun s v => .done s v
def dynamic (function : UInt64 → UInt64 → UInt64) (a b : UInt64) : Action :=
  .managedClosure2 function a b fun s v => .done s v
namespace Mutations
@[noinline] def plus (capture input : UInt64) : UInt64 := input+capture
@[noinline] def times (capture input : UInt64) : UInt64 := input*capture
@[noinline] def chooseApply (selector : UInt64) (left right : UInt64 → UInt64) (input : UInt64) : UInt64 :=
  if selector = 0 then left input else right input
@[noinline] def selected (selector input : UInt64) : UInt64 :=
  let left := plus input
  let right := times (input+selector)
  let first := chooseApply selector left right 0xffffffffffffffff
  let second := chooseApply selector left right 0x8000000000000001
  first ^^^ second
end Mutations
end Lemma.Compiler.Test.ManagedClosure

open Lean Elab Command
partial def corruptClosure (which : Nat) (body : IR.FnBody) : IR.FnBody × Nat :=
  match body with
  | .vdecl x ty e next =>
    let (next,count) := corruptClosure which next
    match e with
    | .box .uint64 source => if which == 1 then (.vdecl x ty (.box .uint32 source) next,count+1)
      else (.vdecl x ty e next,count)
    | .fap name args => if which == 2 && name == ``Lemma.Compiler.Test.ManagedClosure.Mutations.plus then
        (.vdecl x ty (.fap name args.reverse) next,count+1) else (.vdecl x ty e next,count)
    | .pap name args => if which == 4 then (.vdecl x ty (.pap name #[]) next,count+1) else (.vdecl x ty e next,count)
    | .ap name args => if which == 5 then (.vdecl x ty (.ap name (args++args)) next,count+1) else (.vdecl x ty e next,count)
    | _ => (.vdecl x ty e next,count)
  | .inc x n c p next =>
    let (next,count) := corruptClosure which next
    if which == 6 then (next,count+1) else
    if which == 7 then (.inc x 2 c p next,count+1) else (.inc x n c p next,count)
  | .dec x n c p next =>
    let (next,count) := corruptClosure which next
    if which == 3 then (.dec x n c true next,count+1) else
    if which == 8 then (next,count+1) else (.dec x n c p next,count)
  | .case name x ty alternatives =>
    let rows : Array (IR.Alt × Nat) := alternatives.map fun a => match a with
      | .ctor info branch => let (branch,count) := corruptClosure which branch; (.ctor info branch,count)
      | .default branch => let (branch,count) := corruptClosure which branch; (.default branch,count)
    (.case (if which == 10 then ``UInt32 else name) x ty (rows.map (·.1)),
      rows.foldl (fun n row => n+row.2) (if which == 10 then 1 else 0))
  | _ => (body,0)

run_elab do
  let roots := #[``Lemma.User.ClosureExamples.selected,``Lemma.User.ClosureExamples.fourCaptures,``Lemma.User.ClosureExamples.lambdaEntry,``Lemma.User.ClosureExamples.sharedCaptures]
  Compiler.compile (roots ++ #[``Lemma.Compiler.Test.ManagedClosure.staticCapture,
    ``Lemma.Compiler.Test.ManagedClosure.nestedCapture,``Lemma.Compiler.Test.ManagedClosure.scalarOnly,
    ``Lemma.Compiler.Test.ManagedClosure.recursive,``Lemma.Compiler.Test.ManagedClosure.Mutations.selected,
    ``Lemma.Compiler.Test.ManagedClosure.dispatcherCollision])
  let env ← getEnv
  let mut programs : Array Lemma.Core0.ManagedClosureIR.Program := #[]
  for root in roots do
    match Lemma.Core0.ManagedClosureIR.buildProgram env root with
    | .ok program => programs := programs.push program
    | .error error => throwError "ordinary closure source rejected: {root}: {error}"
  for root in #[``Lemma.Compiler.Test.ManagedClosure.staticCapture,
      ``Lemma.Compiler.Test.ManagedClosure.nestedCapture,``Lemma.Compiler.Test.ManagedClosure.scalarOnly,
      ``Lemma.Compiler.Test.ManagedClosure.recursive,``Lemma.Compiler.Test.ManagedClosure.dispatcherCollision] do
    match Lemma.Core0.ManagedClosureIR.buildProgram env root with
    | .ok _ => throwError "unadmitted static/nested/recursive source accepted: {root}"
    | .error _ => pure ()
  let mut mutations : Array Json := #[]
  for which in [1,2,3,4,5,6,7,8,9,10] do
    let owner := if which ≤ 3 then ``Lemma.Compiler.Test.ManagedClosure.Mutations.plus ++ `_boxed else
      if which == 5 || which == 8 || which == 10 then ``Lemma.Compiler.Test.ManagedClosure.Mutations.chooseApply else ``Lemma.Compiler.Test.ManagedClosure.Mutations.selected
    let some (.fdecl name params result actual info) := IR.findEnvDecl env owner | throwError "actual mutation owner missing"
    let (changed,count) := if which == 9 then (actual,1) else corruptClosure which actual
    let params := if which == 9 then params.set! 1 {params[1]! with x := params[0]!.x} else params
    unless count>0 do throwError "actual IR mutation anchor missing: {which}"
    let mutated := IR.declMapExt.addEntry env (.fdecl name params result changed info)
    let some applied := IR.findEnvDecl mutated name | throwError "actual mutation lookup absent"
    unless (IR.formatDecl applied).pretty == (IR.formatDecl (.fdecl name params result changed info)).pretty do
      throwError "actual mutation was shadowed by imported IR: {which}"
    match Lemma.Core0.ManagedClosureIR.buildProgram mutated ``Lemma.Compiler.Test.ManagedClosure.Mutations.selected with
    | .ok _ => throwError "corrupt real closure/adapter/ownership IR admitted: {which}"
    | .error error => mutations := mutations.push <| Json.mkObj [
        ("mutation",toJson which),("actual_changed_nodes",toJson count),("rejected",toJson error)]
  let old := #[Lemma.Core0.Profile.v0_1,.v0_2,.v0_3,.v0_4,.v0_5,.v0_6,.v0_7,
    .firmware_v0_1,.firmware_v0_2,.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,
    .kernel_v0_5,.kernel_v0_6,.kernel_v0_7,.kernel_v0_8,.counter_su_v0_1,
    .user_v0_1,.user_v0_2,.user_v0_3,.user_v0_4,.user_v0_5,.user_v0_6,.boot_v0_1,.boot_v0_2]
  for profile in old do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env profile #[``Lemma.Compiler.Test.ManagedClosure.selected] with
    | .ok _ => throwError "historical profile acquired closure bridge: {profile.contractVersion}"
    | .error _ => pure ()
  match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_7 #[``Lemma.Compiler.Test.ManagedClosure.dynamic] with
  | .ok _ => throwError "dynamic source supplied closure authority"
  | .error _ => pure ()
  unless Lemma.Core0.Profile.ofContractVersion? "core0-user-v0.7" == some .user_v0_7 &&
    Lemma.Core0.Execution.Op.all.all (fun op => op.admits .user_v0_7 == op.admits .user_v0_6) &&
    Lemma.Core0.Execution.memoryRegions .user_v0_7 == Lemma.Core0.Execution.memoryRegions .user_v0_6 do
    throwError "Closure profile changed inherited hardware/privilege/memory boundary"
  match Lemma.Core0.Memory.Model.evaluateDefault ({regions := #[]} : Lemma.Core0.Memory.Model.State)
      (Lemma.Compiler.Test.ManagedClosure.selected 0 7) with
  | .ok _ => throwError "finite host model provided ordinary closure execution"
  | .error error => unless error.code == .executionActionUnsupported do throwError error.message
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_7
      #[``Lemma.Compiler.Test.ManagedClosure.selected,``Lemma.Compiler.Test.ManagedClosure.four,``Lemma.Compiler.Test.ManagedClosure.lambda,``Lemma.Compiler.Test.ManagedClosure.shared] with
    | .ok suite => pure suite | .error error => throwError error.render
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_7 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineUserWordWrappers := true,symbolPrefix := "managed_closure_component_"} with
    | .ok value => pure value | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name,returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map Lemma.Compiler.llvmTy} : Lemma.Compiler.LLVM.Declaration)
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "genuine ordinary bounded closures; isolated execution separate"
    declarations,functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
  | .error error => throwError error | .ok _ => pure ()
  let some output ← IO.getEnv "LEMMA_MANAGED_CLOSURE_OUT" | throwError "LEMMA_MANAGED_CLOSURE_OUT required"
  unless !(← System.FilePath.pathExists output) do throwError "Retained closure output exists"
  IO.FS.createDirAll output
  let rows ← programs.mapM fun program => do
    let sources ← program.sourceNames.mapM fun source => do
      let some declaration := IR.findEnvDecl env source | throwError "actual source IR missing"
      let some ci := env.find? source | throwError "actual source type missing"
      pure <| Json.mkObj [("source",toJson source.toString),("source_type",toJson (← PrettyPrinter.ppExpr ci.type).pretty),
        ("genuine_ir",toJson (IR.formatDecl declaration).pretty)]
    let adapters ← program.targets.mapM fun target => do
      let some declaration := IR.findEnvDecl env target.adapter | throwError "actual adapter IR missing"
      pure <| Json.mkObj [("adapter",toJson target.adapter.toString),("owner",toJson target.source.toString),
        ("captures",toJson target.captures),("genuine_ir",toJson (IR.formatDecl declaration).pretty)]
    pure <| Json.mkObj [("root",toJson program.root.toString),("sources",Json.arr sources),("adapters",Json.arr adapters)]
  IO.FS.writeFile (System.FilePath.mk output / "program.ll") module.render
  IO.FS.writeFile (System.FilePath.mk output / "symbols.txt") lowered.renderSymbolManifest
  IO.FS.writeFile (System.FilePath.mk output / "catalog.json") ((Json.mkObj [
    ("contract",toJson "lemma-managed-closure-v1"),("profile",toJson suite.contractVersion),
    ("compiler_revision",toJson "5045d0056413266e57c625dcd7c365b10e377c52"),
    ("maximum_captures",toJson (4 : Nat)),("maximum_targets",toJson (8 : Nat)),
    ("allocator",toJson "lemma-owned-arena-v1"),("slots",toJson (31 : Nat)),
    ("genuine_ir",Json.arr rows),("actual_ir_mutations",Json.arr mutations),("historical_profiles_rejected",toJson old.size)]).pretty ++ "\n")
  logInfo "MANAGED_CLOSURE_COMPONENT:PASS genuine source/PAP/boxed-adapter/application->checkedLLVM; guest execution separate"
