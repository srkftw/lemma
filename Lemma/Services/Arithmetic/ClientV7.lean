import Lemma.Services.Arithmetic.ProtocolV7
import Lemma.Documents.Mathematics
import Lemma.User.IPC

/-! Protocol7 asynchronous exact-check client. The immutable copied request
binds semantic and closed execution identities before any evidence can change.
Protocol1 Client remains separately maintained with its historical semantics. -/
namespace Lemma.Services.Arithmetic.ClientV7
open Lemma.Core0.Memory Lemma.User

def beginCall (endpoint outgoing document request : UInt64) : Action :=
  .bind (Lemma.Documents.Mathematics.eventCapacity document) fun s _ => if s = 0 then
  .bind (Protocol.field document 24) fun s ns => if s = 0 then
  .bind (Protocol.field document 32) fun s page => if s = 0 then
  .bind (Protocol.field document 40) fun s revision => if s = 0 then
  .bind (Protocol.field document 48) fun s goal => if s = 0 then
  .bind (Protocol.field document 56) fun s n => if s = 0 then
  .bind (Protocol.field document 64) fun s d => if s = 0 then
  .bind (Protocol.field document 72) fun s p0 => if s = 0 then
  .bind (Protocol.field document 80) fun s p1 => if s = 0 then
  .bind (Protocol.field document 88) fun s p2 => if s = 0 then
  .bind (Protocol.field document 136) fun s budget => if s = 0 then
  .bind (Protocol.field document 120) fun s domain => if s = 0 then
  .bind (Protocol.field document 128) fun s assumptions => if s = 0 then
  .bind (ProtocolV7.request outgoing ns page revision goal n d p0 p1 p2 budget request domain assumptions) fun s _ => if s = 0 then
  IPC.callBegin endpoint outgoing ProtocolV7.requestBytes request Protocol.deadlineTicks
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def same (incoming outgoing replyOffset requestOffset : UInt64) : Action :=
  .bind (Protocol.field (incoming + IPCABI.headerBytes) replyOffset) fun s actual => if s = 0 then
  .bind (Protocol.field outgoing requestOffset) fun s expected => if s = 0 then
  if actual = expected then .done 0 0 else .done IPCABI.invalidPacket 0 else .done s 0 else .done s 0

private def validate (incoming outgoing request bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.replyKind then if bytes = IPCABI.headerBytes + ProtocolV7.replyBytes then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actual => if s = 0 then
  if actual = request then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  if sender = 0 then .done IPCABI.invalidPacket 0 else
  .bind (IPC.field incoming IPCABI.replyOffset) fun s authority => if s = 0 then
  if authority = 0 then
  .bind (same incoming outgoing 0 0) fun s _ => if s = 0 then
  .bind (same incoming outgoing 8 8) fun s _ => if s = 0 then
  .bind (same incoming outgoing 16 16) fun s _ => if s = 0 then
  .bind (same incoming outgoing 24 24) fun s _ => if s = 0 then
  .bind (same incoming outgoing 32 32) fun s _ => if s = 0 then
  .bind (same incoming outgoing 40 40) fun s _ => if s = 0 then
  .bind (same incoming outgoing 48 48) fun s _ => if s = 0 then
  .bind (same incoming outgoing 64 96) fun s _ => if s = 0 then
  .bind (same incoming outgoing 72 104) fun s _ => if s = 0 then
  .bind (same incoming outgoing 80 112) fun s _ => if s = 0 then
  .bind (same incoming outgoing 88 120) fun s _ => if s = 0 then
  .bind (same incoming outgoing 96 128) fun s _ => if s = 0 then
  .bind (same incoming outgoing 104 136) fun s _ => if s = 0 then
  .bind (same incoming outgoing 112 144) fun s _ => if s = 0 then
  .bind (same incoming outgoing 120 152) fun s _ => if s = 0 then
  .bind (IPC.field incoming IPCABI.statusOffset) fun s status => if s = 0 then
  .bind (Protocol.field (incoming + IPCABI.headerBytes) 56) fun s outcome => if s = 0 then
  if status = 0 then if outcome = 0 then .done IPCABI.invalidPacket 0 else
    if outcome ≤ 5 then .done 0 outcome else .done IPCABI.invalidPacket 0
  else if outcome = 0 then if (if status = 33 then true else if status = 38 then true else if 236 ≤ status then if status ≤ 239 then true else false else false) = true then
    .done status.toUInt8 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done s 0

def pollCall (transaction incoming outgoing request : UInt64) : Action :=
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun s bytes =>
  if s = IPCABI.wouldBlock then if bytes = 0 then .done s 0 else .done IPCABI.invalidPacket 0
  else if s = 0 then validate incoming outgoing request bytes else .done s 0

end Lemma.Services.Arithmetic.ClientV7
