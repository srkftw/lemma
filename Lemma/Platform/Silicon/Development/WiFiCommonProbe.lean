import Lemma.Radio.WiFi.Queue
import Lemma.Radio.WiFi.Codec
import Lemma.Platform.Silicon.BindingWiFiCommon
import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaSim.MachineServices
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Console

/-! Prospective Kernel8 common DATA probe. Real buffer generation, ownership
errors, queue completion and PLIC18 policy are guest-issued. Discovery selection
and whole-image admission are separately qualified before runtime. No HE/MAC. -/
namespace Lemma.Platform.Silicon.Development.WiFiCommonProbe
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.Radio.WiFi

def base : UInt64 := Lemma.Platform.Silicon.BindingWiFiCommon.wifi_base
def rxHandle : UInt64 := Queue.state+256
def received : UInt64 := Queue.state+264
def secondBatch : UInt64 := Queue.state+272
def rxArmed : UInt64 := Queue.state+280
private def fatal : Action := .done 255 0
private def emit (tag a b c d : UInt64) : Action := Lemma.Kernel.Console.record tag a b c d
private def waitStep : Action :=
 .bind (Lemma.Kernel.MachineServices.rearmRelative 1000) fun s _ => if s = 0 then
 Lemma.Kernel.MachineServices.wait else .done s 0
private def configureIRQ : Action :=
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c000048 1) fun s _ => if s = 0 then
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c002080 0x40000) fun s _ => if s = 0 then
 Lemma.Platform.LemmaSim.IO.write32 0x0c201000 0 else .done s 0 else .done s 0

private def payloadStep (index _count : UInt32) (frame sequence _ _ _ : UInt64) : Action :=
 .bind (Access.write8 (frame+index.toUInt64) ((index.toUInt64*17) ^^^ sequence)) fun s _ => .done s frame
private def payload (sequence : UInt64) : Action :=
 .bind (Frames.allocate 1 Frames.dataPurpose) fun s handle => if s = 0 then
 .bind (Frames.resolvePurpose 1 handle Frames.dataPurpose) fun s frame => if s = 0 then
 .boundedFoldU64 16 payloadStep 16 frame sequence 0 0 0 fun s _ => .done s handle
 else .done s 0 else .done s 0
private def fillStep (index _count : UInt32) (first _ _ _ _ : UInt64) : Action :=
 .bind (payload (first+index.toUInt64)) fun s handle => if s = 0 then
 .bind (Queue.enqueue 1 handle 0 16 93) fun s _ => if s = 0 then
 .bind (emit 0x481 (first+index.toUInt64) handle 16 93) fun s _ => .done s first
 else .done s 0 else .done s 0
private def fill (first : UInt64) : Action :=
 .boundedFoldU64 4 fillStep 4 first 0 0 0 0 fun s _ => .done s 4

private def fullCheck : Action :=
 .bind (payload 8) fun s handle => if s = 0 then
 .bind (Queue.enqueue 1 handle 0 16 93) fun s _ => if s = Queue.full then
 .bind (Frames.mappingCount 1 handle) fun s pins => if s = 0 then
 if pins = 0 then .bind (Frames.release 1 handle) fun s _ => .done s 0
 else .done 212 0 else .done s 0 else .done 212 0 else .done s 0
private def pinCheck : Action :=
 .bind (Queue.read 72) fun s handle => if s = 0 then
 .bind (Frames.release 1 handle) fun s _ => if s = Frames.mapped then
 emit 0x485 handle s.toUInt64 4 0 else .done 212 0 else .done s 0
private def wrongPurposeCheck : Action :=
 .bind (Frames.allocate 1 Frames.tablePurpose) fun s handle => if s = 0 then
 .bind (Queue.enqueue 1 handle 0 16 93) fun s _ => if s = Frames.purposeDenied then
 .bind (Frames.mappingCount 1 handle) fun s pins => if s = 0 then
 if pins = 0 then .bind (Frames.release 1 handle) fun s _ => .done s 0 else .done 212 0
 else .done s 0 else .done 212 0 else .done s 0

private def compareStep (index _count : UInt32) (frame _ _ _ _ : UInt64) : Action :=
 .bind (Access.read8 (frame+index.toUInt64)) fun s value => if s = 0 then
 if value = ((255 : UInt64) ^^^ (index.toUInt64*17)) then .done 0 frame else .done 213 value
 else .done s 0
private def receive : Action :=
 .bind (Access.read64 rxHandle) fun s handle => if s = 0 then
 .bind (Controller.receiveOwned base 1 handle 0) fun s length => if s = 0 then
 if length = 16 then
 .bind (Frames.resolvePurpose 1 handle Frames.dataPurpose) fun s frame => if s = 0 then
 .boundedFoldU64 16 compareStep 16 frame 0 0 0 0 fun s _ => if s = 0 then
 .bind (Controller.releaseHead base) fun s _ => if s = 0 then
 .bind (Frames.release 1 handle) fun s _ => if s = 0 then
 .bind (Access.write64 received 1) fun s _ => if s = 0 then emit 0x483 length handle 1 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done 213 length else .done s 0 else .done s 0
private def transmit : Action :=
 .bind (Queue.complete base) fun s handle => if s = 0 then
 .bind (Frames.release 1 handle) fun s _ => if s = 0 then
 .bind (Queue.read 24) fun s count => if s = 0 then emit 0x482 count handle 1 0
 else .done s 0 else .done s 0 else .done s 0

private def irq : Action :=
 .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c201004) fun s source => if s = 0 then
 if source = 0 then .done 0 0 else if source = 18 then
 .bind (Controller.events base) fun s events => if s = 0 then
 if events &&& (4 : UInt64) = 0 then
 .bind (if events &&& (1 : UInt64) = 1 then transmit else .done 0 0) fun s _ => if s = 0 then
 .bind (if events &&& (2 : UInt64) = 2 then receive else .done 0 0) fun s _ => if s = 0 then
 .bind (Controller.acknowledge base events) fun s _ => if s = 0 then
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c201004 source) fun s _ => if s = 0 then
 .bind (emit 0x486 source events 0 0) fun s _ => .done s source
 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done 214 events else .done s 0 else .done 214 source else .done s 0
private def finish : Action :=
 .bind (Frames.ownedCount 1) fun s owned => if s = 0 then
 .bind (Controller.read base 96) fun s transmitted => if s = 0 then
 .bind (Controller.read base 104) fun s receivedCount => if s = 0 then
 if owned = 0 then if transmitted = 8 then if receivedCount = 1 then
 .bind (emit 0x484 transmitted receivedCount owned 8) fun s _ => if s = 0 then .loop waitStep else .done s 0
 else .done 215 receivedCount else .done 215 transmitted else .done 215 owned
 else .done s 0 else .done s 0 else .done s 0
private def awaitReceive : Action :=
 .bind (Access.read64 received) fun s rx => if s = 0 then
 if rx = 1 then finish else
 .bind (Access.read64 rxArmed) fun s armed => if s = 0 then
 .bind (if armed = 0 then
   .bind (Controller.arm base 16 127) fun s _ => if s = 0 then
   .bind (Access.write64 rxArmed 1) fun s _ => if s = 0 then emit 0x487 16 127 8 0 else .done s 0
   else .done s 0
   else .done 0 0) fun s _ => if s = 0 then waitStep else .done s 0
 else .done s 0 else .done s 0
private def progress : Action :=
 .bind irq fun s _ => if s = 0 then
 .bind (Queue.read 24) fun s completed => if s = 0 then
 .bind (Access.read64 secondBatch) fun s batch => if s = 0 then
 .bind (if completed = 4 then if batch = 0 then
   .bind (fill 4) fun s _ => if s = 0 then Access.write64 secondBatch 1 else .done s 0
   else .done 0 0 else .done 0 0) fun s _ => if s = 0 then
 if completed = 8 then awaitReceive else
 .bind (Queue.kick base) fun s _ => if s = 0 then waitStep else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Transaction root used for genuine component qualification before discovery
and whole-image configuration are admitted. The compiled loop owns all policy. -/
def transaction : Action :=
 .bind (Controller.initialize base) fun s _ => if s = 0 then
 .bind (Frames.configure 8192 8192 4) fun s _ => if s = 0 then
 .bind Frames.init fun s _ => if s = 0 then
 .bind Queue.initialize fun s _ => if s = 0 then
 .bind wrongPurposeCheck fun s _ => if s = 0 then
 .bind (Frames.allocate 1 Frames.dataPurpose) fun s handle => if s = 0 then
 .bind (Access.write64 rxHandle handle) fun s _ => if s = 0 then
 .bind (fill 0) fun s _ => if s = 0 then
 .bind fullCheck fun s _ => if s = 0 then
 .bind pinCheck fun s _ => if s = 0 then
 .bind configureIRQ fun s _ => if s = 0 then
 .bind (emit 0x480 12 18 4 16) fun s _ => if s = 0 then
 .loop progress
 else fatal else fatal else fatal else fatal else fatal else fatal else fatal
 else fatal else fatal else fatal else fatal else fatal

def dispatch (_frame _cause _value : UInt64) : Action := fatal

/-- Actual M-startup CSR observations precede any WiFi MMIO or queue clear. -/
private def validatePmp : Action :=
 .bind (Access.read64 (Queue.state+496)) fun s address => if s = 0 then
 .bind (Access.read64 (Queue.state+504)) fun s configuration => if s = 0 then
 if address = 0x04004c7f then if configuration = 27 then .done 0 0
 else .done 51 0 else .done 51 0 else .done s 0 else .done s 0

/-- Full reset descriptor/DTB validation precedes ownership or device work. -/
def boot : Action :=
 .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
 .bind Lemma.Kernel.BootInfo.validate fun s _ => if s = 0 then
 .bind validatePmp fun s _ => if s = 0 then
 .bind Lemma.Platform.LemmaSim.Descriptor.validateSiliconWiFiCommon fun s _ => if s = 0 then
 .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun s _ => if s = 0 then
 transaction else fatal else fatal else fatal else fatal else fatal
end Lemma.Platform.Silicon.Development.WiFiCommonProbe
