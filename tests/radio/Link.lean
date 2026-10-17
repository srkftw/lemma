import Lemma.Radio.BLE.Link
import Lemma.Compiler.CFGLower

open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
 let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
   #[``Lemma.Radio.BLE.Link.begin,``Lemma.Radio.BLE.Link.packetHeader,
     ``Lemma.Radio.BLE.Link.receive,``Lemma.Radio.BLE.Link.retry,``Lemma.Radio.BLE.Link.cancel] with
   | .ok value => pure value
   | .error error => throwError error.render
 let lowered ← match lowerActionSuiteExecution .user_v0_1 suite {
     preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
     symbolPrefix := "ble_manual_link_"} with
   | .ok value => pure value
   | .error error => throwError error
 let module : LLVM.Module := {sourceName := "ordinary Lean bounded manual ACL transitions",functions := lowered.functions}
 match LLVM.validateModule module with
 | .ok _ => pure ()
 | .error error => throwError error
 let some output ← liftIO <| IO.getEnv "LEMMA_BLE_LINK_OUT"
   | throwError "LEMMA_BLE_LINK_OUT must name a new LLVM file"
 let path := System.FilePath.mk output
 if ← liftIO path.pathExists then throwError "refusing to overwrite retained link lowering"
 liftIO <| IO.FS.writeFile path module.render
 logInfo "BLE_LINK_LOWERING ordinary guarded Lean transitions PASS; actual guest execution separate"

namespace BLELinkFixture
open Lemma.Radio.BLE
def require (condition : Bool) (description : String) : IO Unit :=
 unless condition do throw <| IO.userError description
def check : IO Unit := do
 require (Link.beginResult 0=0x104) "first pending context differs"
 require (Link.headerResult 0x104 2 12=2) "initial data header differs"
 let peerReceived := Link.receiveResult 0 2 12 1
 require (peerReceived=0x20002) "first opaque receive was not admitted"
 let peerPending := Link.beginResult (peerReceived &&& Link.stateMask)
 require (peerPending=0x106 && Link.headerResult peerPending 1 0=5) "actual ACK SN/NESN differs"
 -- The first ACK is lost: guest retains exactly SN0 and opaque bytes.
 let guestRetry := Link.retryResult 0x104
 require (guestRetry=0x204 && Link.headerResult guestRetry 2 12=2) "retry changed data SN"
 let duplicate := Link.receiveResult peerPending 2 12 1
 require (duplicate=0x40106) "lost-ACK retry delivered duplicate application payload"
 let peerRetry := Link.retryResult (duplicate &&& Link.stateMask)
 require (peerRetry=0x206 && Link.headerResult peerRetry 1 0=5) "peer changed retained ACK sequence"
 let reconciled := Link.receiveResult guestRetry 5 0 1
 require (reconciled=0x30003) "valid ACK failed to converge actual sequence state"
 require (Link.beginResult (reconciled &&& Link.stateMask)=0x107) "next data sequence did not advance"
 let blocked := Link.receiveResult 0 2 12 0
 require (blocked=0x80000 && Link.headerResult (blocked &&& Link.stateMask) 1 0=1)
   "receive shortage falsely acknowledged bytes"
 require (Link.receiveResult 0 2 12 1=0x20002) "credit restoration did not admit unchanged retry"
 require (Link.retryResult (Link.retryResult (Link.retryResult 0x104))=Link.failure 198 8)
   "bounded exhaustion did not freeze uncertain context"
 require (Link.beginResult 8=Link.failure 196 8 && Link.cancelResult 0x104=Link.failure 200 8)
   "uncertain cancellation permitted new work"
 for state in [0x100,4,0x108,12,0x400,0x10000,0xffffffffffffffff] do
   require (Link.beginResult state=Link.failure 197 0) "malformed logical state accepted"
   require (Link.receiveResult state 5 0 1=Link.failure 197 0) "malformed receive state accepted"
 for (header,length,space) in [(0,0,1),(3,1,1),(32,1,1),(2,0,1),(2,28,1),(2,1,2)] do
   require (Link.receiveResult 0x104 header length space=Link.failure 197 0)
     "invalid untrusted receive inputs changed context"
 IO.println "BLE_LINK_HOST semantic lost-ACK/duplicate/credit/next-sequence/exhaustion/cancel/invalid state PASS; not RV64 execution"
end BLELinkFixture
run_cmd do Lean.Elab.Command.liftTermElabM BLELinkFixture.check
