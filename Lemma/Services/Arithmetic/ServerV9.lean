import Lemma.Services.Arithmetic.ServerV8
import Lemma.Services.Arithmetic.ProtocolV9

/-! Additive local rational-tool service. Historical checking remains: historical160byte Protocol7 requests
and parameterized192byte task envelopes. No Store, pen, paper, sensor, tutor or
assessment grants. Arbitrary fresh operands still use the existing exact Q/Q[x]
checker and its bounded sign/magnitude semantics, never model confidence. -/
namespace Lemma.Services.Arithmetic.ServerV9
open Lemma.Core0.Memory Lemma.User
private def state : UInt64 := 0x20800
private def get (offset : UInt64) : Action := Memory.read64 (state+offset)
private def put (offset value : UInt64) : Action := Memory.write64 (state+offset) value

def processCopied (authority request : UInt64) : Action :=
  let payload := ServerV7.incoming+IPCABI.headerBytes
  .bind (Memory.read64 (payload+96)) fun s submission => if s = 0 then
  .bind (if submission = request then ProtocolV9.evaluate payload else .done 234 0) fun status packed =>
  .bind (ProtocolV9.reply payload ServerV7.outgoing packed status.toUInt64) fun s _ => if s = 0 then
  .bind (get 8) fun s console => if s = 0 then
  .bind (CapabilityConsole.record console 0x73a request status.toUInt64 packed ProtocolV9.serviceIdentity) fun s _ => if s = 0 then
  IPC.reply authority ServerV7.outgoing ProtocolV9.replyBytes status.toUInt64 else .done s 0 else .done s 0 else .done s 0
  else .done s 0
private def step : Action :=
  .bind (get 0) fun s endpoint => if s = 0 then
  .bind (IPC.receive endpoint ServerV7.incoming IPCABI.maximumPacket IPCABI.maximumTicks) fun s bytes =>
  if s = IPCABI.timeout then .done 0 0 else if s = 0 then
  .bind (IPC.validate ServerV7.incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field ServerV7.incoming IPCABI.replyOffset) fun s authority => if s = 0 then
  .bind (IPC.field ServerV7.incoming IPCABI.requestOffset) fun s request => if s = 0 then
  if authority = 0 then .done IPCABI.invalidPacket 0 else
  .bind (if bytes = IPCABI.headerBytes+ProtocolV9.requestBytes then processCopied authority request else
    if bytes = IPCABI.headerBytes+ProtocolV8.requestBytes then ServerV8.processCopied authority request else
    if bytes = IPCABI.headerBytes+ProtocolV7.requestBytes then ServerV7.processCopied authority request else
    IPC.reply authority ServerV7.outgoing 0 234) fun s _ =>
  if (if s = 0 then true else if s = IPCABI.canceled then true else if s = IPCABI.timeout then true else
    if s = IPCABI.peerDied then true else if s = IPCABI.invalidTransaction then true else
    if s = CapabilityABI.invalidHandle then true else if s = CapabilityABI.revoked then true else false) = true then .done 0 0 else .done s 0
  else .done s 0 else .done s 0 else .done IPCABI.invalidPacket 0 else .done s 0
  else .done s 0 else .done s 0
/-- New production root admits mode0 only. Legacy pressure/fault/delay modes keep
ServerV7's historical roots, deployments, budgets and independent evidence. -/
def main (mode : UInt64) : Action :=
  if mode = 0 then
  .bind (Capability.bootGrant 0) fun s endpoint => if s = 0 then
  .bind (Capability.bootGrant 1) fun s console => if s = 0 then
  .bind (put 0 endpoint) fun s _ => if s = 0 then
  .bind (put 8 console) fun s _ => if s = 0 then
  .bind (put 16 0) fun s _ => if s = 0 then
  .bind Lemma.User.Runtime.Arena.ensure fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x739 ProtocolV9.version ProtocolV9.serviceIdentity ProtocolV9.requestBytes ProtocolV9.replyBytes) fun s _ =>
  if s = 0 then .loop step else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 16 0
end Lemma.Services.Arithmetic.ServerV9
