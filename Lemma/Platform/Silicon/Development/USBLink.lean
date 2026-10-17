import Lemma.USB.Block
import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.Console

/-! Opt-in USB6 actual guest control policy, owned bulk protocol and independent
opaque peer barrier/read probe. No document format is interpreted here, no USB
ACK means durable success, and decoded packets do not qualify a physical PHY. -/
namespace Lemma.Platform.Silicon.Development.USBLink
open Lemma.Core0.Memory Lemma.Kernel.Memory
private def fatal : Action := .done 255 0
private def waitStep : Action :=
  .bind (Lemma.Kernel.MachineServices.rearmRelative 1000) fun s _ => if s = 0 then
  Lemma.Kernel.MachineServices.wait else .done s 0
private def configureIRQ : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c000040 1) fun s _ => if s = 0 then
  .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c002080 0x10000) fun s _ => if s = 0 then
  Lemma.Platform.LemmaSim.IO.write32 0x0c201000 0 else .done s 0 else .done s 0
private def completeIRQ : Action :=
  .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c201004) fun s source => if s = 0 then
  if source = 0 then .done 0 0 else if source = 16 then
  Lemma.Platform.LemmaSim.IO.write32 0x0c201004 source else .done 197 0 else .done s 0
private def fixtureState : UInt64 := 0x804f0100
private def headStep (i _count : UInt32) (crc _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.USB.Controller.read Lemma.USB.Block.mmio (576+i.toUInt64*8)) fun s word => if s = 0 then
  .done 0 (Lemma.USB.BlockProtocol.crcWord crc word) else .done s 0
private def headCRC : Action :=
  .boundedFoldU64 8 headStep 8 0 0 0 0 0 fun s crc => .done s crc
private def rejected (status expected : UInt8) : Action :=
  if status = expected then .done 0 0 else .done 197 0
private def ownedNegative : Action :=
  .bind (Access.read64 fixtureState) fun s tested => if s = 0 then
  if tested = 0 then
  .bind (Lemma.USB.Controller.read Lemma.USB.Block.mmio 16) fun s status => if s = 0 then
  if status &&& 32 = 32 then
  .bind (Lemma.USB.Controller.read Lemma.USB.Block.mmio 88) fun s before => if s = 0 then
  .bind headCRC fun s crc => if s = 0 then
  .bind Lemma.USB.Block.context fun s handle => if s = 0 then
  .bind (Access.read64 (fixtureState+8)) fun s wrongPurpose => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.receiveOwned Lemma.USB.Block.mmio 2 (handle+8192) 0 64) fun result _ => rejected result 34) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.receiveOwned Lemma.USB.Block.mmio 2 wrongPurpose 0 64) fun result _ => rejected result 40) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.receiveOwned Lemma.USB.Block.mmio 2 handle 1 64) fun result _ => rejected result 197) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.receiveOwned Lemma.USB.Block.mmio 2 handle 4088 64) fun result _ => rejected result 197) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.receiveOwned Lemma.USB.Block.mmio 1 handle 0 64) fun result _ => rejected result 197) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.receiveOwned Lemma.USB.Block.mmio 2 handle 0 65) fun result _ => rejected result 197) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.submitOwned Lemma.USB.Block.mmio 1 wrongPurpose 0 64) fun result _ => rejected result 40) fun s _ => if s = 0 then
  .bind (.bind (Lemma.USB.Controller.submitOwned Lemma.USB.Block.mmio 2 handle 0 64) fun result _ => rejected result 197) fun s _ => if s = 0 then
  .bind (Lemma.USB.Controller.read Lemma.USB.Block.mmio 88) fun s after => if s = 0 then
  .bind headCRC fun s afterCRC => if s = 0 then
  if before = after then if crc = afterCRC then
  .bind (Access.write64 fixtureState 1) fun s _ => if s = 0 then
  Lemma.Kernel.Console.record 0x465 handle wrongPurpose before crc else .done s 0
  else .done 197 0 else .done 197 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 0 else .done s 0 else .done 0 0 else .done s 0

private def serviceCompletion : Action :=
  .bind (Access.read64 fixtureState) fun s tested => if s = 0 then
  .bind (Access.read64 (Lemma.USB.Block.state+80)) fun s phase => if s = 0 then
  if tested = 0 then if phase = 2 then .done Lemma.USB.Block.pending 0 else Lemma.USB.Block.finish
  else Lemma.USB.Block.finish
  else .done s 0 else .done s 0
private def completionStep (_i _count : UInt32) (_acc _ _ _ _ : UInt64) : Action :=
  .bind ownedNegative fun s _ => if s = 0 then
  .bind serviceCompletion fun result request =>
  .bind completeIRQ fun s _ => if s = 0 then
  if result = Lemma.USB.Block.pending then
  .bind waitStep fun s _ => .done s 0
  else if result = 0 then .done Status.iterationStop request else .done result 0
  else .done s 0 else .done s 0
private def awaitCompletion : Action :=
  .boundedFoldU64 10000 completionStep 10000 0 0 0 0 0 fun s request =>
  if s = Status.iterationStop then .done 0 request else if s = 0 then .done 160 0 else .done s 0
private def transaction : Action :=
  .bind (Lemma.USB.Block.submit 4 0) fun s sequence => if s = 0 then
  .bind awaitCompletion fun s request => if s = 0 then
  if request = 5 then
  .bind (Lemma.Kernel.Console.record 0x462 sequence request 0 0) fun s _ => if s = 0 then
  .bind (Lemma.USB.Block.submit 0 0) fun s sequence => if s = 0 then
  .bind awaitCompletion fun s request => if s = 0 then
  if request = 1 then
  .bind Lemma.USB.Block.bounce fun s bounce => if s = 0 then
  .bind (Access.read64 bounce) fun s first => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x463 sequence request first bounce) fun s _ => if s = 0 then
  .bind (Access.read64 fixtureState) fun s tested => if s = 0 then
  if tested = 1 then Lemma.Kernel.Console.record 0x464 1 16 64 0 else .done 197 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done 197 0 else .done s 0 else .done s 0 else .done s 0
  else .done 197 0 else .done s 0 else .done s 0

def boot : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
  .bind Lemma.Kernel.BootInfo.validate fun s _ => if s = 0 then
  .bind (Lemma.Platform.LemmaSim.Descriptor.validateBinding 6) fun s _ => if s = 0 then
  .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x460 6 16 0 0) fun s _ => if s = 0 then
  .bind (Frames.configure 8192 8192 4) fun s _ => if s = 0 then
  .bind Frames.init fun s _ => if s = 0 then
  .bind (Frames.allocate 1 2) fun s wrongPurpose => if s = 0 then
  .bind (Access.write64 (fixtureState+8) wrongPurpose) fun s _ => if s = 0 then
  .bind (Access.write64 fixtureState 0) fun s _ => if s = 0 then
  .bind configureIRQ fun s _ => if s = 0 then
  .bind Lemma.USB.Block.initialize fun s sectors => if s = 0 then
  .bind (Lemma.Kernel.Console.record 0x461 sectors 16 64 0) fun s _ => if s = 0 then
  .bind transaction fun s _ => if s = 0 then .loop waitStep else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal

def dispatch (_frame _cause _value : UInt64) : Action := fatal
end Lemma.Platform.Silicon.Development.USBLink
