import Lemma.Radio.WiFi.Queue
import Lemma.Compiler.CFGLower

/-! Finite authority/lowering fixtures, not target execution or a proof. -/
open Lean Elab Command Lemma.Core0 Lemma.Compiler
namespace WiFiKernel8Fixture
private def accessible (profile : Profile) (op : Execution.Op) (address bytes : Nat) : Bool :=
 (Execution.deviceRegionsFor profile op).any fun r => r.start ≤ address && address+bytes ≤ r.stop
private def require (b : Bool) (message : String) : IO Unit :=
 unless b do throw <| IO.userError message

def check : IO Unit := do
 require (Profile.ofContractVersion? "core0-kernel-v0.8" == some .kernel_v0_8) "new contract roundtrip"
 for op in [Execution.Op.deviceRead64,Execution.Op.deviceWrite64] do
  for address in [0x10013000,0x100133f8] do
   require (accessible .kernel_v0_8 op address 8) "new exact64bit controller edge denied"
   for old in [Profile.kernel_v0_1,.kernel_v0_2,.kernel_v0_3,.kernel_v0_4,.kernel_v0_5,.kernel_v0_6,.kernel_v0_7,.boot_v0_1,.counter_su_v0_1] do
    require (!(accessible old op address 8)) "historical profile gained Wi-Fi aperture"
  for address in [0x10012000,0x100123f8,0x10012ff8,0x10013400] do
   require (!(accessible .kernel_v0_8 op address 8)) "Kernel8 gained NV or crossed Wi-Fi edge"
 for op in [Execution.Op.deviceRead32,Execution.Op.deviceWrite32] do
  require (accessible .kernel_v0_8 op 0x0c000048 4) "priority18 denied"
  require (!(accessible .kernel_v0_8 op 0x0c000044 4)) "unsupported priority17 admitted"
  require (!(accessible .kernel_v0_8 op 0x0c00004c 4)) "priority19 admitted"
  require (!(accessible .kernel_v0_8 op 0x10013000 4)) "Wi-Fi gained32bit transfer"
  require (!(accessible .kernel_v0_6 op 0x0c000048 4)) "Kernel6 gained priority18"
 require ((Execution.memoryRegions .kernel_v0_8)==(Execution.memoryRegions .kernel_v0_6)) "Kernel8 memory inherited something beyond Kernel6"
 require ((Execution.deviceRegionsFor .kernel_v0_7 .deviceRead64).any (fun r => r.name=="boot-nv-controller")) "Kernel7 lost NV authority"
 require (!(Execution.Op.readMisa.admits .kernel_v0_8) && !(Execution.Op.counterEnterUser.admits .kernel_v0_8)) "Kernel8 gained counter diagnostic privilege"
 for (offset,length,seed) in [(4096,1,1),(4095,2,1),(0,0,1),(0,17,1),(0,16,0),(0,16,128),(0xffffffffffffffff,1,1)] do
  require (!(Lemma.Radio.WiFi.Controller.descriptorValid offset length seed)) "wrapped/out-of-frame descriptor admitted"
 for (offset,length,seed) in [(0,1,1),(4080,16,127),(4095,1,93)] do
  require (Lemma.Radio.WiFi.Controller.descriptorValid offset length seed) "last byte/exact resource edge denied"
 IO.println "WIFI_KERNEL8_HOST:PASS finite authority edges; historical memory/NV/counter scope preserved"
end WiFiKernel8Fixture
#eval WiFiKernel8Fixture.check

run_cmd do
 let roots := #[``Lemma.Radio.WiFi.Controller.initialize,``Lemma.Radio.WiFi.Controller.submitPinned,
  ``Lemma.Radio.WiFi.Controller.arm,``Lemma.Radio.WiFi.Controller.receiveOwned,
  ``Lemma.Radio.WiFi.Queue.initialize,``Lemma.Radio.WiFi.Queue.enqueue,
  ``Lemma.Radio.WiFi.Queue.kick,``Lemma.Radio.WiFi.Queue.complete]
 let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_8 roots with
  | .ok v => pure v | .error e => throwError e.render
 let lowered ← match lowerActionSuiteExecution .kernel_v0_8 suite {
  preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),symbolPrefix:="wifi_kernel8_"} with
  | .ok v => pure v | .error e => throwError e
 let module : LLVM.Module := {
  sourceName := "genuine Kernel8 CommonOFDM owned-buffer queue"
  functions := lowered.functions
  declarations := #[{name := "core0_io_fence", returnType := .void, parameters := #[]}] }
 match LLVM.validateModule module with
 | .ok _ => pure () | .error e => throwError e
 let some output ← liftIO <| IO.getEnv "LEMMA_WIFI_KERNEL8_OUTPUT" | throwError "new output required"
 let path := System.FilePath.mk output
 if ← liftIO path.pathExists then throwError "refusing retained output"
 liftIO <| IO.FS.createDirAll path
 liftIO <| IO.FS.writeFile (path/"queue.ll") module.render
 liftIO <| IO.FS.writeFile (path/"queue.symbols") lowered.renderSymbolManifest
 logInfo "WIFI_KERNEL8_LOWERING:PASS genuine Controller/Queue/Frames source, not target execution"
