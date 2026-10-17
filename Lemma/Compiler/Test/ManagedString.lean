import Lean
import Lean.Compiler.Main
import Lean.Compiler.IR.Format
import Lemma.Core0.Frontend
import Lemma.Compiler.CFGLower
import Lemma.Core0.MemoryModel
import Lemma.Mathematics.ManagedStringSubmission

/-! Genuine ordinary source/ownership/LLVM component qualification. Rejection
mutations below transform real compiler output only; they never supply admitted
source behavior. Linked isolated execution and production authority are separate. -/
namespace Lemma.Compiler.Test.ManagedString
open Lemma.Core0.Memory
@[noinline] def bytes (capacity a b : UInt64) : ByteArray :=
  (ByteArray.emptyWithCapacity capacity.toNat).push a.toUInt8 |>.push b.toUInt8
@[noinline] def parse (input : ByteArray) : Option String := String.fromUTF8? input
@[noinline] def doubled (text : String) : String := text ++ text
@[noinline] def observe (text : String) : UInt64 :=
  text.length.toUInt64 * 256 + text.utf8ByteSize.toUInt64
@[noinline] def utf8 (a b : UInt64) : UInt64 :=
  match parse (bytes 2 a b) with
  | none => 0
  | some text => observe (doubled text)
@[noinline] def staticString (a b : UInt64) : UInt64 :=
  ("hello" ++ String.fromUTF8! (bytes 2 a b)).length.toUInt64
@[noinline] def scalarOnly (a b : UInt64) : UInt64 := a + b
@[noinline] def recursiveLoop (fuel : Nat) (value : UInt64) : UInt64 :=
  match fuel with
  | 0 => value
  | n+1 => recursiveLoop n (value+1)
@[noinline] def recursive (a b : UInt64) : UInt64 := recursiveLoop a.toNat b
@[noinline] def optionalOther (a b : UInt64) : UInt64 :=
  let value : Option UInt64 := some a
  value.getD b

@[noinline] def collisionSource (a b : UInt64) : UInt64 := utf8 a b

def entry (a b : UInt64) : Action :=
  .managedString2 Lemma.Mathematics.ManagedStringSubmission.compareFiveSix a b fun s v => .done s v

def roundtripEntry (a b : UInt64) : Action :=
  .managedString2 Lemma.Mathematics.ManagedStringSubmission.roundtrip a b fun s v => .done s v

def utf8Entry (a b : UInt64) : Action := .managedString2 utf8 a b fun s v => .done s v

def dynamic (function : UInt64 → UInt64 → UInt64) (a b : UInt64) : Action :=
  .managedString2 function a b fun s v => .done s v

end Lemma.Compiler.Test.ManagedString

/-- Quarantined negative: a declaration cannot impersonate source-derived code. -/
def Lemma.Compiler.Test.ManagedString.collisionSource.__lemma_managed_string_v06.Lemma.Compiler.Test.ManagedString.collisionSource
    (a b : UInt64) : Lemma.Core0.Memory.Action := .done 0 (a+b)
def Lemma.Compiler.Test.ManagedString.collision (a b : UInt64) : Lemma.Core0.Memory.Action :=
  Lemma.Compiler.Test.ManagedString.collisionSource.__lemma_managed_string_v06.Lemma.Compiler.Test.ManagedString.collisionSource a b

open Lean Elab Command
partial def corruptString (which : Nat) (body : IR.FnBody) : IR.FnBody × Nat :=
  match body with
  | .vdecl x ty expression next =>
    let (next,count) := corruptString which next
    match expression with
    | .fap name args =>
      if which == 1 && name == ``String.ofByteArray then
        (.vdecl x ty (.fap name (args.set! 1 args[0]!)) next,count+1)
      else if which == 2 && name == ``ByteArray.validateUTF8 then
        (.vdecl x ty (.fap ``IO.println args) next,count+1)
      else (.vdecl x ty expression next,count)
    | .ctor info args =>
      if which == 3 && info.name == ``Option.some then
        (.vdecl x ty (.ctor {info with size := 2} args) next,count+1)
      else if which == 4 && info.name == ``Option.none then
        (.vdecl x ty (.ctor {info with cidx := 1} args) next,count+1)
      else (.vdecl x ty expression next,count)
    | .proj index owner =>
      if which == 5 then (.vdecl x ty (.proj (index+1) owner) next,count+1)
      else (.vdecl x ty expression next,count)
    | _ => (.vdecl x ty expression next,count)
  | .inc x n c p next =>
    let (next,count) := corruptString which next
    if which == 6 then (.inc x 2 c p next,count+1) else
    if which == 7 then (next,count+1) else (.inc x n c p next,count)
  | .dec x n c p next =>
    let (next,count) := corruptString which next
    if which == 8 then (.dec x n c true next,count+1) else (.dec x n c p next,count)
  | .case name source ty alternatives =>
    let changed : Array (IR.Alt × Nat) := alternatives.map fun alternative =>
      match alternative with
      | .ctor info branch =>
        let (branch,count) := corruptString which branch
        if which == 10 && info.name == ``Option.some then
          (.ctor {info with name := ``Bool.true} branch,count+1)
        else (.ctor info branch,count)
      | .default branch => let (branch,count) := corruptString which branch; (.default branch,count)
    (.case (if which == 9 && name == `tobj then ``Option else name) source ty (changed.map (·.1)),
      (changed.foldl (fun count row => count+row.2) 0) + (if which == 9 && name == `tobj then 1 else 0))
  | _ => (body,0)

run_elab do
  let root := ``Lemma.Mathematics.ManagedStringSubmission.compareFiveSix
  let roundtrip := ``Lemma.Mathematics.ManagedStringSubmission.roundtrip
  let utf8 := ``Lemma.Compiler.Test.ManagedString.utf8
  Compiler.compile #[root,roundtrip,utf8,``Lemma.Compiler.Test.ManagedString.staticString,
    ``Lemma.Compiler.Test.ManagedString.scalarOnly,``Lemma.Compiler.Test.ManagedString.recursive,
    ``Lemma.Compiler.Test.ManagedString.optionalOther]
  let env ← getEnv
  let mut programs : Array Lemma.Core0.ManagedStringIR.Program := #[]
  for source in #[root,roundtrip,utf8] do
    match Lemma.Core0.ManagedStringIR.buildProgram env source with
    | .ok value => programs := programs.push value
    | .error error => throwError "ordinary source rejected: {source}: {error}"
  for source in #[``Lemma.Compiler.Test.ManagedString.staticString,
      ``Lemma.Compiler.Test.ManagedString.scalarOnly,``Lemma.Compiler.Test.ManagedString.recursive,
      ``Lemma.Compiler.Test.ManagedString.optionalOther] do
    match Lemma.Core0.ManagedStringIR.buildProgram env source with
    | .ok _ => throwError "unadmitted String/static/recursive/generic source accepted: {source}"
    | .error _ => pure ()
  let mut rejected : Array Json := #[]
  for which in [1,2,3,4,5,6,7,8,9,10,11] do
    let owner := if which ≤ 4 then ``Lemma.Compiler.Test.ManagedString.parse else utf8
    let some (.fdecl name params result body info) := IR.findEnvDecl env owner | throwError "actual IR mutation owner missing"
    let (body,count) := if which == 11 then (body,1) else corruptString which body
    let params := if which == 11 then params.set! 1 {params[1]! with x := params[0]!.x} else params
    unless count>0 do throwError "actual mutation anchor absent: {which}"
    let mutated := IR.declMapExt.addEntry env (.fdecl name params result body info)
    match Lemma.Core0.ManagedStringIR.buildProgram mutated utf8 with
    | .ok _ => throwError "actual corrupted String/ownership IR admitted: {which}"
    | .error error => rejected := rejected.push <| Json.mkObj [
        ("mutation",toJson which),("actual_changed_nodes",toJson count),("rejected",toJson error)]
  let old := #[Lemma.Core0.Profile.v0_1,.v0_2,.v0_3,.v0_4,.v0_5,.v0_6,.v0_7,
    .firmware_v0_1,.firmware_v0_2,.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,
    .kernel_v0_5,.kernel_v0_6,.kernel_v0_7,.user_v0_1,.user_v0_2,.user_v0_3,.user_v0_4,.user_v0_5,.boot_v0_1,.boot_v0_2]
  for profile in old do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env profile #[``Lemma.Compiler.Test.ManagedString.entry] with
    | .ok _ => throwError "historical profile acquired managedString2: {profile.contractVersion}"
    | .error error => unless error.code == .unsupportedPrimitive || (!profile.isExecution && error.code == .invalidSuite) do
      throwError error.render
  for source in #[``Lemma.Compiler.Test.ManagedString.dynamic,``Lemma.Compiler.Test.ManagedString.collision] do
    match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_6 #[source] with
    | .ok _ => throwError "dynamic/impersonating source acquired String bridge"
    | .error _ => pure ()
  unless Lemma.Core0.Profile.ofContractVersion? "core0-user-v0.6" == some .user_v0_6 &&
    Lemma.Core0.Profile.user_v0_6.isUser && Lemma.Core0.Profile.user_v0_6.isExecution &&
    Lemma.Core0.Execution.Op.all.all (fun op => op.admits .user_v0_6 == op.admits .user_v0_5) &&
    Lemma.Core0.Execution.memoryRegions .user_v0_6 == Lemma.Core0.Execution.memoryRegions .user_v0_5 do
    throwError "String profile altered inherited ISA/privilege/memory boundary"
  match Lemma.Core0.Memory.Model.evaluateDefault ({regions := #[]} : Lemma.Core0.Memory.Model.State)
      (Lemma.Compiler.Test.ManagedString.entry 5 6) with
  | .ok _ => throwError "finite scalar host model supplied managed String authority"
  | .error error => unless error.code == .executionActionUnsupported do throwError error.message
  let suite ← match Lemma.Core0.checkAndLowerActionSuiteForProfile env .user_v0_6
      #[``Lemma.Compiler.Test.ManagedString.entry,``Lemma.Compiler.Test.ManagedString.roundtripEntry,
        ``Lemma.Compiler.Test.ManagedString.utf8Entry] with
    | .ok value => pure value
    | .error error => throwError error.render
  let lowered ← match Lemma.Compiler.lowerActionSuiteExecution .user_v0_6 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineUserWordWrappers := true,symbolPrefix := "managed_string_component_"} with
    | .ok value => pure value
    | .error error => throwError error
  let declarations := suite.usedExecutionOps.filterMap fun spec => spec.primitiveSymbol?.map fun name =>
    ({name,returnType := if spec.resultKind == .checked then .checkedResult else .i64,
      parameters := spec.machineArguments.map Lemma.Compiler.llvmTy} : Lemma.Compiler.LLVM.Declaration)
  let module : Lemma.Compiler.LLVM.Module := {
    sourceName := "genuine ordinary String/UTF8 component; isolated execution separate"
    declarations,functions := lowered.functions}
  match Lemma.Compiler.LLVM.validateModule module with
  | .error error => throwError error
  | .ok _ => pure ()
  let some output ← IO.getEnv "LEMMA_MANAGED_STRING_OUT" | throwError "LEMMA_MANAGED_STRING_OUT must name unused output"
  unless !(← System.FilePath.pathExists output) do throwError "String component output exists"
  IO.FS.createDirAll output
  let rows ← programs.mapM fun program => do
    let ir ← program.sourceNames.mapM fun source => do
      let some declaration := IR.findEnvDecl env source | throwError "genuine String closure missing"
      pure <| Json.mkObj [("source",toJson source.toString),("genuine_ir",toJson (IR.formatDecl declaration).pretty)]
    pure <| Json.mkObj [("root",toJson program.root.toString),("genuine_ir",Json.arr ir)]
  IO.FS.writeFile (System.FilePath.mk output / "program.ll") module.render
  IO.FS.writeFile (System.FilePath.mk output / "symbols.txt") lowered.renderSymbolManifest
  IO.FS.writeFile (System.FilePath.mk output / "catalog.json") ((Json.mkObj [
    ("contract",toJson "lemma-managed-string-v1"),("profile",toJson suite.contractVersion),
    ("compiler_revision",toJson "5045d0056413266e57c625dcd7c365b10e377c52"),
    ("maximum_utf8_bytes",toJson (40 : Nat)),("allocator",toJson "lemma-owned-arena-v1"),
    ("slots",toJson (31 : Nat)),("genuine_ir",Json.arr rows),
    ("actual_ir_mutations",Json.arr rejected),("historical_profiles_rejected",toJson old.size)]).pretty ++ "\n")
  logInfo "MANAGED_STRING_COMPONENT:PASS genuine ordinary String/UTF8/Option ownership->checkedLLVM; isolated RV64 execution separate"
