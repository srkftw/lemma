import Lemma.Radio.BLE.Controller
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

open Lean Elab Command Lemma.Core0 Lemma.Compiler
namespace BLECompileFixture
/-- A normal elaborated Action root retains the maintained scalar whitening
closure in the emitted packet object, independently of the CRC callers. -/
def whiten (channel byte : UInt64) : Lemma.Core0.Memory.Action :=
  .done 0 (Lemma.Radio.BLE.Packet.whiteningByte
    (Lemma.Radio.BLE.Packet.whiteningInitial channel) byte)
end BLECompileFixture
run_cmd do
  let env ← getEnv
  let some directory ← liftIO <| IO.getEnv "LEMMA_BLE_PROBE_OUT"
    | throwError "LEMMA_BLE_PROBE_OUT must name a fresh output directory"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite retained BLE probe"
  liftIO <| IO.FS.createDirAll path
  for (label,profile,roots) in #[
      ("packet",Profile.user_v0_1,#[``Lemma.Radio.BLE.Packet.pduCRC,``Lemma.Radio.BLE.Packet.validateAddress,
        ``BLECompileFixture.whiten]),
      ("controller",Profile.kernel_v0_4,#[``Lemma.Radio.BLE.Controller.«initialize»,``Lemma.Radio.BLE.Controller.configure,
        ``Lemma.Radio.BLE.Controller.submit,``Lemma.Radio.BLE.Controller.receivedHeader,``Lemma.Radio.BLE.Controller.receivedByte,
        ``Lemma.Radio.BLE.Controller.releaseReceived,``Lemma.Radio.BLE.Controller.cancel,
        ``Lemma.Radio.BLE.Controller.events,``Lemma.Radio.BLE.Controller.acknowledge])] do
    let suite ← match checkAndLowerActionSuiteForProfile env profile roots with
      | .ok suite => pure suite
      | .error error => throwError error.render
    let lowered ← match lowerActionSuiteExecution profile suite {
        preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),symbolPrefix := "ble_" } with
      | .ok value => pure value
      | .error error => throwError error
    let module : LLVM.Module := {
      sourceName := "genuinely elaborated maintained BLE " ++ label
      declarations := if label == "controller" then #[{name := "core0_io_fence",returnType := .void,parameters := #[]}] else #[]
      functions := lowered.functions }
    match LLVM.validateModule module with
    | .ok _ => pure ()
    | .error error => throwError error
    liftIO <| IO.FS.writeFile (path / (label ++ ".ll")) module.render
    liftIO <| IO.FS.writeFile (path / (label ++ ".symbols")) lowered.renderSymbolManifest
    let rows := suite.scalarFunctions.map fun f => Json.mkObj [
      ("source",.str f.name.toString),("args",.arr (f.signature.args.map (Json.str ∘ Ty.render)))]
    liftIO <| IO.FS.writeFile (path / (label ++ ".json"))
      (Json.mkObj [("contract",.str profile.contractVersion),("scalar",.arr rows),
        ("action_count",toJson suite.actionFunctions.size),("device_count",toJson suite.usedDeviceOps.size)]).pretty
  for profile in #[Profile.user_v0_1,.user_v0_2,.firmware_v0_1,.firmware_v0_2] do
    match checkAndLowerActionSuiteForProfile env profile #[``Lemma.Radio.BLE.Controller.submit] with
    | .ok _ => throwError "unprivileged/firmware profile admitted BLE device operations"
    | .error _ => pure ()
  logInfo "BLE_LOWERING:PASS ordinary source scalar/folds+privileged PIO; unprivileged rejection; full machine/RV64 integration separate"

namespace BLEHostFixture
open Lemma.Core0.Memory Lemma.Radio.BLE
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  calls : Array (UInt64 × UInt64 × UInt64) := #[]
partial def execute (ref : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
 match action with
 | .done s v => pure (s,v)
 | .bind first next => let (s,v) ← execute ref first;execute ref (next s v)
 | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
   if count.toNat > budget then execute ref (next 9 initial) else
   let mut value := initial;let mut status : UInt8 := 0
   for i in [:count.toNat] do
     if status = 0 then let (s,v) ← execute ref (step i.toUInt32 count value c0 c1 c2 c3);status := s;value := v
   execute ref (next status value)
 | .platform op a b c d e f next =>
   unless c=0 && d=0 && e=0 && f=0 && a%8=0 && 0x10010600≤a && a<0x10010a00 do
     throw <| IO.userError "unexpected BLE operation arguments"
   let state ← ref.get
   if op = .deviceRead64 then
     ref.set {state with calls := state.calls.push (0,a,0)};execute ref (next 0 (state.words.getD a 0))
   else if op = .deviceWrite64 then
     ref.set {state with words := state.words.insert a b,calls := state.calls.push (1,a,b)};execute ref (next 0 0)
   else throw <| IO.userError "BLE fixture attempted non-PIO effect"
 | _ => throw <| IO.userError "BLE fixture attempted unsupported Action"
def require (b : Bool) (message : String) : IO Unit := unless b do throw <| IO.userError message
def check : IO Unit := do
 let ref ← IO.mkRef ({} : State)
 let result ← execute ref (Packet.pduCRC 0x16 5 0x0504030201 0 0 0 0xc4c181)
 require (result=(0,0xa20b4b)) "official5.4 data CRC mismatch"
 let adv := [0x42,0x09,0xa6,0xa5,0xa4,0xa3,0xa2,0xc1,1,2,3]
 let mut crc : UInt64 := 0x555555
 for b in adv do crc := Packet.crcByte crc b
 require (crc=0xb52dd7) "official5.4 independent advertising CRC mismatch"
 for (channel,expected) in [(0,[0x40,0xb2,0xbc,0xc3,0x1f,0x37,0x4a,0x5f]),
   (16,[0xd0,0x9e,0x53,0x33,0xd8,0xba,0x98,0x08]),
   (36,[0x44,0x20,0x59,0xde,0xe1,0x8f,0x1b,0xa5])] do
   let mut state := Packet.whiteningInitial channel
   for expectedByte in expected do
     let packed := Packet.whiteningByte state 0
     require (packed &&& 255 = expectedByte) "official5.4 whitening vector mismatch"
     let input : UInt64 := 0xa7
     require ((Packet.whiteningByte state ((Packet.whiteningByte state input) &&& 255)) &&& 255 = input)
       "whitening involution mismatch"
     state := packed >>> 8
 for (h,len,init) in [(0,5,1),(3,5,1),(32,5,1),(2,0,1),(2,28,1),(2,0xffffffffffffffff,1),(2,5,0x1000000)] do
   require ((← execute ref (Packet.pduCRC h len 0 0 0 0 init))=(16,0)) "invalid packet produced CRC"
 for aa in [0xaa08192b,0xaa173c42,0x12333333] do
   require ((← execute ref (Packet.validateAddress aa))=(0,aa)) "valid official access address rejected"
 for aa in [0,0xffffffff,0x8e89bed6,0x8e89bed7,0xaaaaaaaa,0x33333333,0x100000000] do
   require ((← execute ref (Packet.validateAddress aa))=(16,0)) "invalid access address admitted"
 ref.set {words := ({} : Std.HashMap UInt64 UInt64).insert 0x10010610 16}
 require ((← execute ref (Controller.submit 0x10010600 2 27 0x0706050403020100 0x0f0e0d0c0b0a0908
   0x1716151413121110 0x1a1918))=(0,1)) "bounded PIO submission rejected"
 let actual ← ref.get
 for i in [:27] do require (actual.words.getD (0x10010700+i.toUInt64*8) 99 = i.toUInt64) "PIO altered opaque payload"
 require (actual.calls.size=32) "PIO operation count changed"
 for state in [1,2,8,0] do
   ref.set {words := ({} : Std.HashMap UInt64 UInt64).insert 0x10010610 state}
   require ((← execute ref (Controller.submit 0x10010600 2 1 1 0 0 0))=(196,0)) "busy/coex block did not backpressure"
   require ((← ref.get).calls.size=1) "busy/coex block wrote device"
 ref.set {}
 require ((← execute ref (Controller.submit 0x10010600 2 28 0 0 0 0))=(197,0)) "driver oversized submission"
 require ((← ref.get).calls.isEmpty) "oversized submission touched device"
 IO.println "BLE_HOST_MODEL:PASS official CRC/whitening vectors; static addresses;27-byte owned PIO and no-write backpressure/errors; not RV64 execution"
end BLEHostFixture
run_cmd do Lean.Elab.Command.liftTermElabM BLEHostFixture.check
