import Lemma.Courses.PackageAwaitProtocol
import Lemma.Services.Store.Client

/-! Bounded completion-driven guest readiness. The caller owns disjoint outgoing
and incoming spans. Kernel handles, sender generation and transaction deadlines
remain authoritative. Reset/death/cancellation never manufactures Ready; a
snapshot simply retains the pending transaction and the Store's waiter row. -/
namespace Lemma.Courses.PackageAwaitClient
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Services.Store

private def separate (a n b m : UInt64) : UInt64 :=
  if a + n ≤ b then 1 else if b + m ≤ a then 1 else 0

def beginCall (endpoint outgoing incoming ns initialization request : UInt64) : Action :=
  if request = 0 then .done Format.malformed 0 else if Format.maximumSequence < request then .done Format.malformed 0 else
  if (outgoing ||| incoming) &&& 7 = 0 then
  if outgoing ≤ 0xffffffffffffffff - 192 then if incoming ≤ 0xffffffffffffffff - 256 then
  if separate outgoing 192 incoming 256 = 1 then
  .bind (PackageAwaitProtocol.header outgoing ns initialization) fun s _ => if s = 0 then
  IPC.callBegin endpoint outgoing 64 request PackageAwaitProtocol.maximumWaitTicks
  else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0

private def validate (incoming bytes request ns : UInt64) : Action :=
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.replyKind then if bytes = 128 then
  .bind (IPC.field incoming IPCABI.requestOffset) fun s actualRequest => if s = 0 then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field incoming IPCABI.statusOffset) fun s app => if s = 0 then
  if actualRequest = request then if 0 < sender then if reply = 0 then
  .bind (Client.responseField incoming 0) fun s magic => if s = 0 then
  .bind (Client.responseField incoming 8) fun s ver => if s = 0 then
  .bind (Client.responseField incoming 16) fun s op => if s = 0 then
  .bind (Client.responseField incoming 24) fun s actualNS => if s = 0 then
  .bind (Client.responseField incoming 32) fun s object => if s = 0 then
  .bind (Client.responseField incoming 40) fun s sequence => if s = 0 then
  .bind (Client.responseField incoming 48) fun s mode => if s = 0 then
  .bind (Client.responseField incoming 56) fun s generation => if s = 0 then
  if magic = Protocol.magic then if ver = PackageAwaitProtocol.version then
  if op = PackageAwaitProtocol.operation then if actualNS = ns then if object = 0 then
  if PackageAwaitProtocol.resultValid app mode sequence generation = 1 then .done app.toUInt8 generation
  else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done IPCABI.invalidPacket 0 else .done IPCABI.invalidPacket 0
  else .done s 0

def waitCall (transaction incoming request ns : UInt64) : Action :=
  .bind (IPC.callWait transaction incoming IPCABI.maximumPacket) fun s bytes =>
  if s = 0 then validate incoming bytes request ns else .done s 0

def pollCall (transaction incoming request ns : UInt64) : Action :=
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun s bytes =>
  if s = IPCABI.wouldBlock then if bytes = 0 then .done s 0 else .done IPCABI.invalidPacket 0
  else if s = 0 then validate incoming bytes request ns else .done s 0

def call (endpoint outgoing incoming ns initialization request : UInt64) : Action :=
  .bind (beginCall endpoint outgoing incoming ns initialization request) fun s transaction =>
  if s = 0 then waitCall transaction incoming request ns else .done s 0

/-- Cancellation consumes the terminal handle once. Even an already accepted
Ready reply is discarded; the caller must separately admit any future action. -/
def cancel (transaction incoming : UInt64) : Action :=
  .bind (IPC.cancel transaction) fun s _ =>
  if (if s = 0 then (1 : UInt64) else if s = IPCABI.alreadyCompleted then 1 else 0) = 1 then
  .bind (Syscall.call 67 transaction incoming IPCABI.maximumPacket 0 0) fun terminal _ =>
  if terminal = IPCABI.wouldBlock then .done IPCABI.invalidTransaction 0 else .done 0 terminal.toUInt64
  else .done s 0

end Lemma.Courses.PackageAwaitClient
