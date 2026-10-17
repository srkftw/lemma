import Lemma.Services.Arithmetic.Protocol
import Lemma.Services.Arithmetic.ProtocolV6
import Lemma.Mathematics.ManagedStringSubmissionAction
import Lemma.User.IPC
import Lemma.User.CapabilityConsole

/-! Independently linked arithmetic process. Its only grants are a receive
endpoint and console. It has no ink, storage, panel or tutor authority. -/
namespace Lemma.Services.Arithmetic.ServerV6
open Lemma.Core0.Memory Lemma.User

def incoming : UInt64 := 0x20300
def outgoing : UInt64 := 0x20500
private def state : UInt64 := 0x20800
private def get (offset : UInt64) : Action := Memory.read64 (state + offset)
private def put (offset value : UInt64) : Action := Memory.write64 (state + offset) value

private def respondV6 (authority request ns page revision goal budget outcome : UInt64) (status : UInt8) : Action :=
  .bind (ProtocolV6.reply outgoing ns page revision goal (if status = 0 then outcome else 0) budget request) fun s _ =>
  if s = 0 then IPC.reply authority outgoing ProtocolV6.replyBytes status.toUInt64 else .done s 0

private def delayedStep (_ _ : UInt32) (_ _ _ _ _ : UInt64) : Action :=
  .bind (Syscall.sleep 100000) fun s _ => .done s 0
/-- Laboratory delay is at least twenty seconds, beyond the unchanged one-second
caller deadline. It then attempts a real reply using its possibly retired
authority; it never invents a cancellation outcome. -/
private def delayed : Action :=
  .boundedFoldU64 2000 delayedStep 2000 0 0 0 0 0 fun s _ => .done s 0

private def processV6 (authority request : UInt64) : Action :=
  let payload := incoming + IPCABI.headerBytes
  .bind (Protocol.field payload 0) fun s magic => if s = 0 then
  .bind (Protocol.field payload 8) fun s version => if s = 0 then
  .bind (Protocol.field payload 16) fun s checker => if s = 0 then
  .bind (Protocol.field payload 24) fun s ns => if s = 0 then
  .bind (Protocol.field payload 32) fun s page => if s = 0 then
  .bind (Protocol.field payload 40) fun s revision => if s = 0 then
  .bind (Protocol.field payload 48) fun s goal => if s = 0 then
  .bind (Protocol.field payload 56) fun s n => if s = 0 then
  .bind (Protocol.field payload 64) fun s d => if s = 0 then
  .bind (Protocol.field payload 72) fun s p0 => if s = 0 then
  .bind (Protocol.field payload 80) fun s p1 => if s = 0 then
  .bind (Protocol.field payload 88) fun s p2 => if s = 0 then
  .bind (Protocol.field payload 96) fun s budget => if s = 0 then
  .bind (Protocol.field payload 104) fun s requested => if s = 0 then
  if magic = Protocol.magic then if version = ProtocolV6.version then
  if checker = Lemma.Mathematics.Exact.checkerIdentity then if requested = request then
  if Protocol.validIdentity ns page revision goal budget request = true then
  .bind (ProtocolV6.validateRequest payload) fun s _ => if s = 0 then
  .bind (get 16) fun s mode => if s = 0 then
  .bind (if mode = 3 then
    .bind (get 8) fun s console => if s = 0 then
    CapabilityConsole.record console 0x45b request revision mode goal else .done s 0
    else .done 0 0) fun s _ => if s = 0 then
  .bind (if mode = 2 then Memory.read64 0x500000 else if mode = 3 then delayed else .done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Mathematics.ManagedStringSubmissionAction.check goal n d p0 p1 p2 budget) fun status outcome =>
  .bind (get 8) fun s console => if s = 0 then
  .bind (CapabilityConsole.record console 0x455 request revision status.toUInt64 outcome) fun s _ => if s = 0 then
  .bind (respondV6 authority request ns page revision goal budget outcome status) fun actual _ =>
  .bind (CapabilityConsole.record console 0x45a request revision actual.toUInt64 mode) fun s _ =>
  if s = 0 then .done actual 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else respondV6 authority request ns page revision goal budget 0 234
  else respondV6 authority request ns page revision goal budget 0 234
  else respondV6 authority request ns page revision goal budget 0 234
  else respondV6 authority request ns page revision goal budget 0 234
  else respondV6 authority request ns page revision goal budget 0 234
  else respondV6 authority request ns page revision goal budget 0 234
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0

private def step : Action :=
  .bind (get 0) fun s endpoint => if s = 0 then
  .bind (IPC.receive endpoint incoming IPCABI.maximumPacket IPCABI.maximumTicks) fun s bytes =>
  if s = IPCABI.timeout then .done 0 0 else if s = 0 then
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s authority => if s = 0 then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s request => if s = 0 then
  if authority = 0 then .done IPCABI.invalidPacket 0 else
  if bytes = IPCABI.headerBytes + ProtocolV6.requestBytes then
  .bind (processV6 authority request) fun s _ =>
  if (if s = 0 then true else if s = IPCABI.canceled then true else if s = IPCABI.timeout then true
      else if s = IPCABI.peerDied then true else if s = IPCABI.invalidTransaction then true
      else if s = CapabilityABI.invalidHandle then true else if s = CapabilityABI.revoked then true else false) = true then
    .done 0 0 else .done s 0
  else respondV6 authority request 0 0 0 0 0 0 234
  else .done s 0 else .done s 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0

private def pressureStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Runtime.Arena.newBox i.toUInt64) fun s _ => if s = 0 then .done 0 (acc + 1) else .done s 0

/-- Only exact Laboratory deployments supply modes1/2/3. Mode1 fills real
owned objects, mode2 faults at an unmapped User address on the first request,
mode3 delays past the caller deadline and then attempts a real late reply. No
fixture manufactures a mathematical result or modifies the notebook's page. -/
def main (mode : UInt64) : Action :=
  if 3 < mode then .done 16 0 else
  .bind (Capability.bootGrant 0) fun s endpoint => if s = 0 then
  .bind (Capability.bootGrant 1) fun s console => if s = 0 then
  .bind (put 0 endpoint) fun s _ => if s = 0 then
  .bind (put 8 console) fun s _ => if s = 0 then
  .bind (put 16 mode) fun s _ => if s = 0 then
  .bind (if mode = 1 then
    .bind Lemma.User.Runtime.Arena.ensure fun s _ => if s = 0 then
    .boundedFoldU64 31 pressureStep 31 0 0 0 0 0 fun s count => if s = 0 then
      if count = 31 then .done 0 count else .done 239 0 else .done s 0 else .done s 0
    else .done 0 0) fun s held => if s = 0 then
  .bind (CapabilityConsole.record console 0x456 mode held ProtocolV6.version Protocol.deadlineTicks) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x45c ProtocolV6.implementation ProtocolV6.lowering ProtocolV6.runtime ProtocolV6.resources) fun s _ => if s = 0 then
  .loop step else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

end Lemma.Services.Arithmetic.ServerV6
