import Lemma.Services.Store.Client
import Lemma.User.IPC
import Lemma.User.CapabilityConsole

/-! Quarantined ordinary User client for the LemmaSim isolation deployment.
It has document Call and console Write grants only. Each observation serializes
an actual kernel/service reply. The invalid namespace is deliberately sent as a
raw application packet, so the production Client's local shape check cannot be
mistaken for a service rejection. The final load targets a genuinely unmapped
User page; there is no privileged startup instruction or host memory mutation.
The store and production notebook remain separately linked, unchanged peers. -/
namespace Lemma.User.Development.NotebookIsolation
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Services.Store

private def failed : Action := .done 95 0
private def outgoing : UInt64 := 0x20300
private def incoming : UInt64 := 0x20500
private def faultAddress : UInt64 := 0x400000

private def observe (console identity test : UInt64) (expected actual : UInt8) (value : UInt64) : Action :=
  .bind (CapabilityConsole.record console 0x430 identity test actual.toUInt64 value) fun s _ =>
  if s = 0 then if actual = expected then .done 0 value else failed else failed

private def bad (status : UInt8) : Bool := if status = 0 then false else true

private def namespaceReply (console identity operation object bytes : UInt64) : Action :=
  if bytes = 128 then
  .bind (IPC.validate incoming bytes) fun s kind =>
  if bad s = true then failed else
  if kind = IPCABI.replyKind then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s request =>
  if bad s = true then failed else
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender =>
  if bad s = true then failed else
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply =>
  if bad s = true then failed else
  .bind (IPC.field incoming IPCABI.statusOffset) fun s application =>
  if bad s = true then failed else
  .bind (Protocol.field (incoming + 64) 0) fun s magic =>
  if bad s = true then failed else
  .bind (Protocol.field (incoming + 64) 8) fun s version =>
  if bad s = true then failed else
  .bind (Protocol.field (incoming + 64) 16) fun s observedOperation =>
  if bad s = true then failed else
  .bind (Protocol.field (incoming + 64) 24) fun s ns =>
  if bad s = true then failed else
  .bind (Protocol.field (incoming + 64) 32) fun s observedObject =>
  if bad s = true then failed else
  .bind (Protocol.field (incoming + 64) 56) fun s count =>
  if bad s = true then failed else
  if request = operation then if 0 < sender then if reply = 0 then
  if magic = Protocol.magic then if version = 1 then
  if observedOperation = operation then if ns = 3 then if observedObject = object then
  if count = 0 then if application ≤ 255 then
  observe console identity (200 + operation) 220 application.toUInt8 ns
  else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed
  else failed else failed

private def namespaceAttempt (documents console identity operation object transaction : UInt64) : Action :=
  .bind (Protocol.header outgoing operation 3 object transaction 0 0) fun s _ =>
  if bad s = true then failed else
  .bind (IPC.callBegin documents outgoing 64 operation IPCABI.maximumTicks) fun s pending =>
  if bad s = true then failed else
  .bind (IPC.callWait pending incoming IPCABI.maximumPacket) fun status bytes =>
  .bind (observe console identity (100 + operation) 0 status bytes) fun s _ =>
  if bad s = true then failed else namespaceReply console identity operation object bytes

private def waitStep (_ _ : UInt32) (acc deadline _ _ _ : UInt64) : Action :=
  .bind Syscall.time fun s now => if s = 0 then
  if deadline ≤ now then .done Status.iterationStop now else
  .bind (Syscall.sleep (if deadline - now < 1000 then 1000 else
    if 1000000 < deadline - now then 1000000 else deadline - now)) fun s _ =>
  if s = 0 then .done 0 acc else failed
  else failed

/-- Let the unchanged notebook draw and publish before the actual fault. The
bounded wait uses guest monotonic time and the existing sleeping scheduler. -/
private def waitUntil (deadline : UInt64) : Action :=
  .boundedFoldU64 600 waitStep 600 0 deadline 0 0 0 fun s now =>
  if s = Status.iterationStop then .done 0 now else failed

def main (argument : UInt64) : Action :=
  if argument = 0 then
  .bind (Capability.bootGrant 0) fun s documents =>
  if bad s = true then failed else
  .bind (Capability.bootGrant 1) fun s console =>
  if bad s = true then failed else
  .bind Syscall.identity fun s identity =>
  if bad s = true then failed else
  .bind (Memory.write64 0x20000 identity) fun s _ =>
  if bad s = true then failed else
  .bind (CapabilityConsole.record console 0x42f identity documents console argument) fun s _ =>
  if bad s = true then failed else
  .bind (Syscall.call 66 documents 0 0 0 0) fun status value =>
  .bind (observe console identity 1 72 status value) fun s _ =>
  if bad s = true then failed else
  .bind (Syscall.call 66 0 2 0 outgoing 0) fun status value =>
  .bind (observe console identity 2 80 status value) fun s _ =>
  if bad s = true then failed else
  .bind (Syscall.call 64 documents 0 0 0 0) fun status value =>
  .bind (observe console identity 3 72 status value) fun s _ =>
  if bad s = true then failed else
  .bind (Syscall.call 65 documents 1 outgoing 0 0) fun status value =>
  .bind (observe console identity 4 72 status value) fun s _ =>
  if bad s = true then failed else
  .bind (Capability.createEndpoint documents) fun status value =>
  .bind (observe console identity 5 81 status value) fun s _ =>
  if bad s = true then failed else
  .bind (Protocol.header outgoing 1 1 0 0 0 0) fun s _ =>
  if bad s = true then failed else
  .bind (IPC.callBegin 0 outgoing 64 7 IPCABI.maximumTicks) fun status value =>
  .bind (observe console identity 7 80 status value) fun s _ =>
  if bad s = true then failed else
  .bind (namespaceAttempt documents console identity 1 0 0) fun s _ =>
  if bad s = true then failed else
  .bind (namespaceAttempt documents console identity 2 0x70000001 1) fun s _ =>
  if bad s = true then failed else
  .bind (namespaceAttempt documents console identity 6 1 1) fun s _ =>
  if bad s = true then failed else
  .bind (waitUntil 202700000) fun s attemptedAt =>
  if bad s = true then failed else
  .bind (CapabilityConsole.record console 0x430 identity 299 0 attemptedAt) fun s _ =>
  if bad s = true then failed else
  .bind (Memory.write64 0x20700 0xd15ca11ed15ca11e) fun s _ =>
  if bad s = true then failed else
  .bind (Client.beginCall documents outgoing 3 1 1 1 0 8 0x20700 300) fun status transaction =>
  .bind (observe console identity 298 0 status transaction) fun s _ =>
  if bad s = true then failed else
  if transaction = 0 then failed else
  .bind (Client.waitCall transaction incoming 3 1 1 300 8) fun status value =>
  .bind (observe console identity 300 232 status value) fun s _ =>
  if bad s = true then failed else
  .bind (waitUntil 420000000) fun s now =>
  if bad s = true then failed else
  .bind (CapabilityConsole.record console 0x432 identity faultAddress now 0) fun s _ =>
  if bad s = true then failed else
  .bind (Memory.read64 faultAddress) fun status value =>
  .bind (CapabilityConsole.record console 0x435 identity status.toUInt64 value 0) fun _ _ => failed
  else failed

end Lemma.User.Development.NotebookIsolation
