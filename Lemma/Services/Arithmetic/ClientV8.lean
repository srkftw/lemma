import Lemma.Services.Arithmetic.ProtocolV8
import Lemma.User.IPC

/-! Async independent parameterized checking. A completed reply must echo the
complete immutable task/submission/assistance/session context. Applicability to
current document state is a separate caller check before showing any evidence. -/
namespace Lemma.Services.Arithmetic.ClientV8
open Lemma.Core0.Memory Lemma.User

def beginCall (endpoint outgoing request : UInt64) : Action :=
  .bind (Memory.read64 (outgoing+144)) fun s submission => if s = 0 then
  if submission = request then IPC.callBegin endpoint outgoing ProtocolV8.requestBytes request Protocol.deadlineTicks
  else .done 234 0 else .done s 0
private def sameStep (i _ : UInt32) (acc source expected _ _ : UInt64) : Action :=
  .bind (Memory.read64 (source+i.toUInt64*8)) fun s a => if s = 0 then
  .bind (Memory.read64 (expected+i.toUInt64*8)) fun s b => if s = 0 then
  if a = b then .done 0 acc else .done IPCABI.invalidPacket 0 else .done s 0 else .done s 0
private def validate (incoming outgoing request bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.replyKind then if bytes = IPCABI.headerBytes+ProtocolV8.replyBytes then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actual => if s = 0 then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s authority => if s = 0 then
  .bind (IPC.field incoming IPCABI.statusOffset) fun s status => if s = 0 then
  if actual = request then if 0 < sender then if authority = 0 then
  .boundedFoldU64 22 sameStep 22 0 (incoming+IPCABI.headerBytes) outgoing 0 0 fun s _ => if s = 0 then
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+176)) fun s outcome => if s = 0 then
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+184)) fun s checker => if s = 0 then
  if checker = ProtocolV8.checkerIdentity then
  if status = 0 then if 0 < outcome then if outcome ≤ 5 then .done 0 outcome
    else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else if status = 234 then if outcome = 0 then .done 234 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done s 0

def pollCall (transaction incoming outgoing request : UInt64) : Action :=
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun s bytes =>
  if s = IPCABI.wouldBlock then if bytes = 0 then .done s 0 else .done IPCABI.invalidPacket 0 else
  if s = 0 then validate incoming outgoing request bytes else .done s 0

def waitCall (transaction incoming outgoing request : UInt64) : Action :=
  .bind (IPC.callWait transaction incoming IPCABI.maximumPacket) fun s bytes =>
  if s = 0 then validate incoming outgoing request bytes else .done s 0
end Lemma.Services.Arithmetic.ClientV8
