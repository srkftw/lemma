import Lemma.Services.Store.Protocol
import Lemma.User.IPC

/-! Reusable document-endpoint client. Packet spans belong to the calling User
task. Nonzero status is an actual transport/application failure. No retry is
manufactured after an uncertain commit. Async begin/wait let a notebook keep
its input loop running while the store owns the disk transaction. -/
namespace Lemma.Services.Store.Client
open Lemma.Core0.Memory
open Lemma.User

def responseField (incoming offset : UInt64) : Action := Protocol.field (incoming + 64) offset
def responseData (incoming : UInt64) : UInt64 := incoming + 128

private def validate (incoming operation ns object request expectedCount bytes : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.replyKind then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actualRequest => if s = 0 then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field incoming IPCABI.statusOffset) fun s app => if s = 0 then
  if actualRequest = request then if 0 < sender then if reply = 0 then
  if 128 ≤ bytes then
  .bind (responseField incoming 0) fun s magic => if s = 0 then
  .bind (responseField incoming 8) fun s version => if s = 0 then
  .bind (responseField incoming 16) fun s observedOperation => if s = 0 then
  .bind (responseField incoming 24) fun s observedNs => if s = 0 then
  .bind (responseField incoming 32) fun s observedObject => if s = 0 then
  .bind (responseField incoming 40) fun s sequence => if s = 0 then
  .bind (responseField incoming 56) fun s count => if s = 0 then
  if magic = Protocol.magic then if version = 1 then
  if observedOperation = operation then if observedNs = ns then if observedObject = object then
  if sequence ≤ Format.maximumSequence then
  if app = 0 then
    if (if operation = 5 then if count ≤ expectedCount then (1 : UInt64) else 0 else if count = 0 then 1 else 0) = 1 then
    if bytes = 128 + count then .done 0 sequence else .done IPCABI.invalidPacket 0
    else .done IPCABI.invalidPacket 0
  else if 220 ≤ app then if app ≤ 233 then
    if count = 0 then if bytes = 128 then .done app.toUInt8 sequence else .done IPCABI.invalidPacket 0
    else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done s 0

def beginCall (endpoint outgoing operation ns object transaction offset count source request : UInt64) : Action :=
  let bytes := if operation = 3 then 64 + count else 64
  if Protocol.shape operation ns object transaction offset count bytes = 1 then
  .bind (Protocol.header outgoing operation ns object transaction offset count) fun s _ => if s = 0 then
  if operation = 3 then
    .bind (Format.copy source (outgoing + 64) count) fun s _ =>
    if s = 0 then IPC.callBegin endpoint outgoing bytes request IPCABI.maximumTicks else .done s 0
  else IPC.callBegin endpoint outgoing bytes request IPCABI.maximumTicks
  else .done s 0 else .done Format.malformed 0

def waitCall (transaction incoming operation ns object request expectedCount : UInt64) : Action :=
  .bind (IPC.callWait transaction incoming IPCABI.maximumPacket) fun s bytes =>
  if s = 0 then validate incoming operation ns object request expectedCount bytes else .done s 0

/-- Additive LemmaSim completion probe. wouldBlock leaves the transaction and
reply bytes unconsumed; the notebook returns to pen handling while flush runs.
Successful replies use exactly the same independent framing checks as wait. -/
def pollCall (transaction incoming operation ns object request expectedCount : UInt64) : Action :=
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun s bytes =>
  if s = IPCABI.wouldBlock then
    if bytes = 0 then .done s 0 else .done IPCABI.invalidPacket 0
  else if s = 0 then validate incoming operation ns object request expectedCount bytes else .done s 0

def call (endpoint outgoing incoming operation ns object transaction offset count source request : UInt64) : Action :=
  .bind (beginCall endpoint outgoing operation ns object transaction offset count source request) fun s pending =>
  if s = 0 then waitCall pending incoming operation ns object request count else .done s 0

end Lemma.Services.Store.Client
