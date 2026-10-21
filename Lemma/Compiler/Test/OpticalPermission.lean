import Lemma.Compiler.CFGLower
import Lemma.Platform.LemmaSim.IO
import Lemma.Compiler.DeploymentCatalog

/-! Genuine frontend/LLVM export for the additive optical permission boundary.
The independent host observer optimizes these actual modules and checks that
denied literal accesses have no volatile operation. No controller or guest is
executed by this fixture. -/
namespace Lemma.Compiler.Test.OpticalPermission
open Lean Elab Command Lemma.Core0 Lemma.Compiler
open Lemma.Platform.LemmaSim

def readMagic : Memory.Action := IO.read64 0x10016000
def readConsentFloor : Memory.Action := IO.read64 0x10016118
def writeCommand : Memory.Action := IO.write64 0x10016118 6
def writeInhibit : Memory.Action := IO.write64 0x10016038 1
def writeReadOnly : Memory.Action := IO.write64 0x10016000 99
def readWriteOnly : Memory.Action := IO.read64 0x10016030
def readReserved : Memory.Action := IO.read64 0x10016400
def readPastAperture : Memory.Action := IO.read64 0x10017000
def readWrongWidth : Memory.Action := IO.read32 0x10016000
def writeWrongWidth : Memory.Action := IO.write32 0x10016118 6
def readMisaligned : Memory.Action := IO.read64 0x10016001

private def admitsAddress (profile : Profile) (operation : Execution.Op) (address : Nat) : Bool :=
  match operation.widthBytes? with
  | none => false
  | some width => address % width == 0 &&
      (Execution.deviceRegionsFor profile operation).any fun region =>
        region.start ≤ address && width ≤ region.stop - region.start && address ≤ region.stop - width

run_cmd do
  for profile in #[Profile.kernel_v0_9, .kernel_v0_10] do
    for address in #[0x10016000, 0x10016118, 0x100163f8, 0x10016400, 0x10017000] do
      for operation in #[Execution.Op.deviceRead32, .deviceWrite32, .deviceRead64, .deviceWrite64] do
        unless !admitsAddress profile operation address do
          throwError "An older kernel acquired Optical MMIO authority"
  for (operation, address) in #[(Execution.Op.deviceRead64, 0x10016000),
      (.deviceRead64, 0x10016118), (.deviceWrite64, 0x10016118), (.deviceWrite64, 0x10016038)] do
    unless admitsAddress .kernel_v0_11 operation address do
      throwError "Defined Optical direction refused"
  for (operation, address) in #[(Execution.Op.deviceWrite64, 0x10016000),
      (.deviceRead64, 0x10016030), (.deviceRead64, 0x10016400), (.deviceRead64, 0x10017000),
      (.deviceRead64, 0x10016001), (.deviceRead32, 0x10016000), (.deviceWrite32, 0x10016118)] do
    unless !admitsAddress .kernel_v0_11 operation address do
      throwError "Wrong Optical width/direction/offset/alignment admitted"
  let env ← getEnv
  let some destination ← IO.getEnv "LEMMA_OPTICAL_PERMISSION_OUTPUT"
    | throwError "An unused exact optical permission output is required"
  let directory : System.FilePath := destination
  IO.FS.createDirAll directory
  let cases := #[(``readMagic, "read-magic"), (``readConsentFloor, "read-floor"),
    (``writeCommand, "write-command"), (``writeInhibit, "write-inhibit"),
    (``writeReadOnly, "write-ro"), (``readWriteOnly, "read-wo"),
    (``readReserved, "read-reserved"), (``readPastAperture, "read-past"),
    (``readWrongWidth, "read-width32"), (``writeWrongWidth, "write-width32"),
    (``readMisaligned, "read-misaligned")]
  let mut records : Array Json := #[]
  for profile in #[Profile.kernel_v0_9, .kernel_v0_10, .kernel_v0_11] do
    for (source, label) in cases do
      let suite ← match checkAndLowerActionSuiteForProfile env profile #[source] with
        | .ok suite => pure suite | .error error => throwError error.render
      let lowered ← match lowerActionSuiteExecution profile suite with
        | .ok lowered => pure lowered | .error error => throwError error
      let module : LLVM.Module := {
        sourceName := "genuine optical permission regression"
        declarations := #[{name := "core0_io_fence", returnType := .void, parameters := #[]}]
        functions := lowered.functions }
      match LLVM.validateModule module with
      | .error error => throwError error | .ok _ => pure ()
      let filename := profile.contractVersion ++ "-" ++ label ++ ".ll"
      IO.FS.writeFile (directory / filename) module.render
      let some root := lowered.roots[0]?
        | throwError "The genuine permission export omitted its selected root"
      records := records.push <| Json.mkObj [
        ("contract_version", .str profile.contractVersion), ("case", .str label),
        ("source", .str source.toString), ("file", .str filename),
        ("root", .str root.llvm),
        ("operation_count", toJson suite.usedExecutionOps.size)]
  IO.FS.writeFile (directory / "unit.json") ((Json.arr records).pretty ++ "\n")
  logInfo "PASS: genuine optical permission33 LLVM modules and exact old/new register authority"

end Lemma.Compiler.Test.OpticalPermission
