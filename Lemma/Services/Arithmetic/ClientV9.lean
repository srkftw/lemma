import Lemma.Services.Arithmetic.ProtocolV9
import Lemma.User.IPC

/-! One pending asynchronous call on the existing isolated arithmetic endpoint.
Every echoed field, transaction and service identity is checked; the kernel
authenticates endpoint/transaction ownership and the reply sender is nonzero. -/
namespace Lemma.Services.Arithmetic.ClientV9
open Lemma.Core0.Memory Lemma.User

def beginCall (endpoint outgoing request : UInt64) : Action :=
  .bind (Memory.read64 (outgoing+96)) fun s stored => if s = 0 then
  if request = stored then IPC.callBegin endpoint outgoing ProtocolV9.requestBytes request Protocol.deadlineTicks
  else .done 234 0 else .done s 0
private def echoStep (i _ : UInt32) (acc incoming outgoing _ _ : UInt64) : Action :=
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+i.toUInt64*8)) fun s actual => if s = 0 then
  .bind (Memory.read64 (outgoing+i.toUInt64*8)) fun s expected => if s = 0 then
  if actual = expected then .done 0 acc else .done IPCABI.invalidPacket 0 else .done s 0 else .done s 0

def validate (incoming outgoing request bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actual => if s = 0 then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s authority => if s = 0 then
  .bind (IPC.field incoming IPCABI.statusOffset) fun s status => if s = 0 then
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+168)) fun s identity => if s = 0 then
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+144)) fun s n => if s = 0 then
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+152)) fun s d => if s = 0 then
  .bind (Memory.read64 (incoming+IPCABI.headerBytes+160)) fun s outcome => if s = 0 then
  if kind = IPCABI.replyKind then
  if bytes = IPCABI.headerBytes+ProtocolV9.replyBytes then
  if actual = request then
  if (if sender = 0 then false else true) = true then
  if authority = 0 then
  if identity = ProtocolV9.serviceIdentity then
  .boundedFoldU64 18 echoStep 18 0 incoming outgoing 0 0 fun s _ => if s = 0 then
  if status = 0 then
    if (if outcome = 1 then true else outcome = 2) = true then
    if n = Lemma.Mathematics.Exact.sign then .done IPCABI.invalidPacket 0 else
    if ReductionV1.maximumMagnitude < (n &&& 0x7fffffffffffffff) then .done IPCABI.invalidPacket 0 else
    if d = 0 then .done IPCABI.invalidPacket 0 else if ReductionV1.maximumMagnitude < d then .done IPCABI.invalidPacket 0 else
    .done 0 outcome
    else .done IPCABI.invalidPacket 0
  else if (if status = 234 then true else status = 235) = true then
    if n ||| d ||| outcome = 0 then .done status.toUInt8 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done s 0
  else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0
  else .done s 0
  else .done s 0
  else .done s 0
  else .done s 0
  else .done s 0
  else .done s 0
  else .done s 0
  else .done s 0
  else .done s 0

def pollCall (transaction incoming outgoing request : UInt64) : Action :=
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun s bytes =>
  if s = IPCABI.wouldBlock then if bytes = 0 then .done s 0 else .done IPCABI.invalidPacket 0
  else if s = 0 then validate incoming outgoing request bytes else .done s 0
end Lemma.Services.Arithmetic.ClientV9
