import Lemma.Radio.WiFi.Block
import Lemma.Platform.Silicon.BindingWiFiCommon
import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaSim.MachineServices
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Console

/-! Opt-in privileged owned READ512 client probe. All request construction,
fragment ownership and reply validation execute in the genuinely compiled
guest. A successful read does not imply durable commit or notebook integration.
-/
namespace Lemma.Platform.Silicon.Development.WiFiCommonReadProbe
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.Radio.WiFi
def base : UInt64 := Lemma.Platform.Silicon.BindingWiFiCommon.wifi_base
def contextCell : UInt64 := Queue.state+288
def lastTX : UInt64 := Queue.state+296
def lastRX : UInt64 := Queue.state+304
def terminal : UInt64 := Queue.state+312
def writer : UInt64 := 0x445566778899aabb
private def emit (tag a b c d : UInt64) : Action := Lemma.Kernel.Console.record tag a b c d
private def waitStep : Action :=
 .bind (Lemma.Kernel.MachineServices.rearmRelative 1000) fun s _ => if s = 0 then
 Lemma.Kernel.MachineServices.wait else .done s 0
private def fatal : Action := .done 255 0
private def configureIRQ : Action :=
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c000048 1) fun s _ => if s = 0 then
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c002080 0x40000) fun s _ => if s = 0 then
 Lemma.Platform.LemmaSim.IO.write32 0x0c201000 0 else .done s 0 else .done s 0
private def resultCRCStep (i _count : UInt32) (crc address _ _ _ : UInt64) : Action :=
 .bind (Access.read64 (address+i.toUInt64*8)) fun s value => if s = 0 then
 .done 0 (Lemma.USB.BlockProtocol.crcWord crc value) else .done s 0
private def completed (handle : UInt64) : Action :=
 .bind (Block.result handle) fun s address => if s = 0 then
 .boundedFoldU64 64 resultCRCStep 64 0 address 0 0 0 fun s crc => if s = 0 then
 .bind (Frames.ownedCount 1) fun s owned => if s = 0 then
 .bind (emit 0x494 handle address crc owned) fun s _ => if s = 0 then
 .bind (Frames.release 1 handle) fun s _ => if s = 0 then
 .bind (Frames.ownedCount 1) fun s owned => if s = 0 then
 .bind (Queue.read 24) fun s packets => if s = 0 then
 if owned = 0 then if packets = 5 then
 .bind (emit 0x496 owned packets 512 0) fun s _ => if s = 0 then Access.write64 terminal 1 else .done s 0
 else fatal else fatal else .done s 0 else .done s 0 else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def cursors (handle : UInt64) : Action :=
 .bind (Frames.resolvePurpose 1 handle 4) fun s frame => if s = 0 then
 .bind (Access.read64 (frame+16)) fun s tx => if s = 0 then
 .bind (Access.read64 (frame+24)) fun s rx => if s = 0 then
 .bind (Access.read64 lastTX) fun s oldTX => if s = 0 then
 .bind (Access.read64 lastRX) fun s oldRX => if s = 0 then
 .bind (if oldTX = tx then .done 0 0 else
   .bind (Access.write64 lastTX tx) fun s _ => if s = 0 then emit 0x492 tx handle 72 93 else .done s 0) fun s _ => if s = 0 then
 if oldRX = rx then .done 0 0 else
 .bind (Access.write64 lastRX rx) fun s _ => if s = 0 then emit 0x493 rx handle 584 127 else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def service (handle : UInt64) : Action :=
 .bind (Lemma.Platform.LemmaSim.IO.read32 0x0c201004) fun s source => if s = 0 then
 if source = 0 then
 .bind (Block.progress base handle) fun s _ => if s = Block.pending then cursors handle
 else if s = 0 then completed handle else
 .bind (emit 0x49f s.toUInt64 handle 0 0) fun _ _ => Access.write64 terminal 2
 else if source = 18 then
 .bind (Controller.events base) fun s events => if s = 0 then
 .bind (Block.progress base handle) fun s _ => if s = Block.pending then
 .bind (cursors handle) fun s _ => if s = 0 then
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c201004 source) fun s _ => if s = 0 then emit 0x495 source events 0 0 else .done s 0
 else .done s 0
 else if s = 0 then
 .bind (Lemma.Platform.LemmaSim.IO.write32 0x0c201004 source) fun s _ => if s = 0 then
 .bind (emit 0x495 source events 0 0) fun s _ => if s = 0 then completed handle else .done s 0 else .done s 0
 else .bind (emit 0x49f s.toUInt64 handle events source) fun _ _ => Access.write64 terminal 2
 else .done s 0 else fatal else .done s 0
private def progress : Action :=
 .bind (Access.read64 terminal) fun s stopped => if s = 0 then
 if stopped = 0 then
 .bind (Access.read64 contextCell) fun s handle => if s = 0 then
 .bind (service handle) fun s _ => if s = 0 then waitStep else .done s 0 else .done s 0
 else waitStep else .done s 0
def transaction : Action :=
 .bind (Controller.initialize base) fun s _ => if s = 0 then
 .bind (Frames.configure 8192 8192 4) fun s _ => if s = 0 then
 .bind Frames.init fun s _ => if s = 0 then
 .bind Queue.initialize fun s _ => if s = 0 then
 .bind Block.create fun s handle => if s = 0 then
 .bind (Access.write64 contextCell handle) fun s _ => if s = 0 then
 .bind configureIRQ fun s _ => if s = 0 then
 .bind (Block.beginRead handle writer 4096) fun s _ => if s = Block.pending then
 .bind (emit 0x491 handle writer 4096 512) fun s _ => if s = 0 then .loop progress else .done s 0
 else fatal else fatal else fatal else fatal else fatal else fatal else fatal else fatal
private def validatePmp : Action :=
 .bind (Access.read64 (Queue.state+496)) fun s address => if s = 0 then
 .bind (Access.read64 (Queue.state+504)) fun s configuration => if s = 0 then
 if address = 0x04004c7f then if configuration = 27 then .done 0 0
 else .done 51 0 else .done 51 0 else .done s 0 else .done s 0
def boot : Action :=
 .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ => if s = 0 then
 .bind Lemma.Kernel.BootInfo.validate fun s _ => if s = 0 then
 .bind validatePmp fun s _ => if s = 0 then
 .bind Lemma.Platform.LemmaSim.Descriptor.validateSiliconWiFiCommon fun s _ => if s = 0 then
 .bind Lemma.Platform.LemmaSim.MachineServices.validateSilicon fun s _ => if s = 0 then
 transaction else fatal else fatal else fatal else fatal else fatal
def dispatch (_frame _cause _value : UInt64) : Action := fatal
end Lemma.Platform.Silicon.Development.WiFiCommonReadProbe
