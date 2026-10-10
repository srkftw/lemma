import Lemma.User.IPC
import Lemma.User.CapabilityConsole

/-! Quarantined IPC acceptance actor. All receive/reply work uses the reusable
User IPC library and the same kernel path required by later services. The
request-selected hold/fault cases are development fixtures, not kernel policy.
-/
namespace Lemma.User.Development.IPCServer
open Lemma.Core0.Memory
open Lemma.User

def failed : Action := .done 95 0
def incoming : UInt64 := 0x20500
def outgoing : UInt64 := 0x20700

private def transformStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Memory.read8 (source + i.toUInt64)) fun s byte =>
  if s = 0 then
    .bind (Memory.write8 (target + i.toUInt64) (byte ^^^ 0xa5)) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else failed
  else failed

/-- Quarantined late-reply fixture: wait for the actual one-use capability
withdrawal. A bounded sleep only paces polling; it cannot certify retirement. -/
private def retiredStep (_ _ : UInt32) (acc handle _ _ _ : UInt64) : Action :=
  .bind (Capability.check handle CapabilityABI.replyType CapabilityABI.replyRight) fun s value =>
  if s = CapabilityABI.invalidHandle then
    if value = 0 then .done Status.iterationStop 0 else failed
  else
  if s = 0 then
    if value = 0 then
      .bind (Syscall.sleep 10000) fun s _ =>
      if s = 0 then .done 0 acc else failed
    else failed
  else failed

private def replyObserved (console id request handle length : UInt64) : Action :=
  .bind (IPC.reply handle outgoing length 0) fun status value =>
  .bind (CapabilityConsole.record console 0x222 id request status.toUInt64 value) fun s _ =>
  if s = 0 then
    if request % 256 = 4 then
      if status = CapabilityABI.invalidHandle then .done 0 0 else failed
    else if status = 0 then
      if value = 0 then
        if request % 256 = 3 then
          .bind (IPC.reply handle outgoing length 0) fun status value =>
          .bind (CapabilityConsole.record console 0x223 id request status.toUInt64 value) fun s _ =>
          if s = 0 then if status = CapabilityABI.invalidHandle then
            if value = 0 then .done 0 0 else failed else failed else failed
        else .done 0 0
      else failed
    else failed
  else failed

private def dispatch (console id kind : UInt64) : Action :=
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s request => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s handle => if s = 0 then
  .bind (IPC.field incoming IPCABI.lengthOffset) fun s length => if s = 0 then
  .bind (CapabilityConsole.record console 0x221 id request sender handle) fun s _ => if s = 0 then
  if kind = IPCABI.sendKind then .done 0 0 else
  if kind = IPCABI.callKind then
    if handle < 16 then failed else
    if request % 256 = 5 then
      .bind (Memory.read64 0x20000) fun s nonce => if s = 0 then
      .bind (Memory.write64 0x10000 nonce) fun _ _ => failed
      else failed
    else
      .boundedFoldU64 192 transformStep length.toUInt32 0
        (incoming + IPCABI.payloadOffset) outgoing 0 0 fun s count =>
      if s = 0 then if count = length then
      if request % 256 = 2 then
        .bind (IPC.reply handle 0 1 0) fun status value =>
        .bind (CapabilityConsole.record console 0x224 id request status.toUInt64 value) fun s _ =>
        if s = 0 then if status = 71 then if value = 0 then
          replyObserved console id request handle length
        else failed else failed else failed
      else if request % 256 = 4 then
        .boundedFoldU64 512 retiredStep 512 0 handle 0 0 0 fun s _ =>
        if s = Status.iterationStop then replyObserved console id request handle length else failed
      else replyObserved console id request handle length
      else failed else failed
  else failed
  else failed else failed else failed else failed else failed

private def step : Action :=
  .bind (Memory.read64 0x20100) fun s console => if s = 0 then
  .bind (Memory.read64 0x20108) fun s id => if s = 0 then
  .bind (Memory.read64 0x20110) fun s endpoint => if s = 0 then
  .bind (IPC.receive endpoint incoming IPCABI.maximumPacket 1000000) fun status bytes =>
  if status = IPCABI.timeout then .done 0 0 else
  if status = 0 then
    .bind (IPC.validate incoming bytes) fun s kind =>
    if s = 0 then dispatch console id kind else failed
  else failed
  else failed else failed else failed

def main (nonce : UInt64) : Action :=
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20100 console) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20108 id) fun s _ => if s = 0 then
  .bind (Memory.write64 0x20110 endpoint) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x220 id nonce endpoint 0) fun s _ =>
  if s = 0 then .loop step else failed
  else failed else failed else failed else failed else failed else failed else failed

end Lemma.User.Development.IPCServer
