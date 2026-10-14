import Lemma.Courses.PackageAwaitProtocol
import Lemma.Services.Store.Server

/-! Course-only mount publication waiter. This root composes the historical
course engine/settlement/staging prefix and dispatcher; it replaces none of
their definitions. Four private waiter rows retain real kernel reply grants.
No host, admission ACK, timer sleep, root candidate or pending read warrants
Ready. Recovery14/15 and historical status8 retain their own deployments.

Private state496 is a four-bit occupancy mask. Four48-byte rows at512 contain
reply/full sender/namespace/initializer/lease deadline/full Store identity.
Reset starts with zero rows; death/revocation/cancellation invalidates the
kernel reply grant. Same-backend snapshots retain both grant and waiter row.
Root generation in a reply is validated medium identity, not an authentication
or device epoch. The full Store identity binds every retained row to this
service lifetime. Waiting and cancellation perform no backing write/barrier.
-/
namespace Lemma.Services.Store.ServerAwait
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Courses

def waiterMask : UInt64 := 496
def waiterBase : UInt64 := 512
def waiterBytes : UInt64 := 48
private def bad : Action := .done 95 0
private def row (slot : UInt64) : UInt64 := Server.state + waiterBase + slot * waiterBytes
private def word (address offset : UInt64) : Action := Memory.read64 (address + offset)
private def put (address offset value : UInt64) : Action := Memory.write64 (address + offset) value

private def respond (reply ns sequence mode generation : UInt64) (status : UInt8) : Action :=
  .bind (Memory.write64 Server.outgoing Protocol.magic) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 8) PackageAwaitProtocol.version) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 16) PackageAwaitProtocol.operation) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 24) ns) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 32) 0) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 40) sequence) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 48) mode) fun s _ => if s = 0 then
  .bind (Memory.write64 (Server.outgoing + 56) generation) fun s _ => if s = 0 then
  .bind (IPC.reply reply Server.outgoing 64 status.toUInt64) fun status value =>
  if value = 0 then
    if status = 0 then .done 0 0 else
    if status = CapabilityABI.invalidHandle then .done 0 0 else
    if status = IPCABI.peerDied then .done 0 0 else
    if status = IPCABI.revoked then .done 0 0 else bad
  else bad
  else bad else bad else bad else bad else bad else bad else bad else bad

private def flushStep (i _ : UInt32) (mask mode sequence generation identity : UInt64) : Action :=
  let address := row i.toUInt64
  .bind (word address 0) fun s reply => if s = 0 then
  if reply = 0 then .done 0 mask else
  .bind (word address 8) fun s sender => if s = 0 then
  .bind (word address 16) fun s ns => if s = 0 then
  .bind (word address 24) fun s initialization => if s = 0 then
  .bind (word address 40) fun s owner => if s = 0 then
  if 16 ≤ reply then if 0 < sender then if owner = identity then
  if Protocol.namespaceValid ns = 1 then if initialization ≤ 1 then
  if mode = 2 then if initialization = 1 then .done 0 (mask ||| (1 <<< i.toUInt64)) else
    .bind (respond reply ns sequence 2 0 Format.unformatted) fun s _ => if s = 0 then
    .bind (put address 0 0) fun s _ => .done s mask else bad
  else if mode = 1 then
    .bind (respond reply ns sequence 1 generation 0) fun s _ => if s = 0 then
    .bind (put address 0 0) fun s _ => .done s mask else bad
  else if mode = 3 then
    .bind (respond reply ns sequence 3 generation Format.readOnly) fun s _ => if s = 0 then
    .bind (put address 0 0) fun s _ => .done s mask else bad
  else bad
  else bad else bad else bad else bad else bad
  else bad else bad else bad else bad
  else bad

/-- Called after the actual engine/settlement prefix. Pending mounts do not
walk the waiter rows or perform another IPC call. No per-sector100ms sleep is
introduced. Publication requires idle Engine, writable mode, no read-only
latch and a positive generation produced by the complete ordinary mount. -/
def settleWaiters : Action :=
  .bind (Server.get waiterMask) fun s mask => if s = 0 then
  if mask = 0 then .done 0 0 else if 15 < mask then bad else
  .bind (Server.get 24) fun s mode => if s = 0 then
  if mode = 0 then .done 0 0 else
  .bind (Engine.field Server.context 0) fun s active => if s = 0 then
  if active = 0 then
  .bind (Engine.field Server.context 40) fun s sequence => if s = 0 then
  .bind (Engine.field Server.context 56) fun s generation => if s = 0 then
  .bind (Engine.field Server.context 336) fun s readonly => if s = 0 then
  .bind (Server.get 16) fun s identity => if s = 0 then
  if (if mode = 1 then if readonly = 0 then if 0 < generation then (1 : UInt64) else 0 else 0
      else if mode = 2 then 1 else if mode = 3 then 1 else 0) = 1 then
  .boundedFoldU64 4 flushStep 4 0 mode sequence generation identity fun s remaining =>
  if s = 0 then Server.put waiterMask remaining else bad
  else bad else bad else bad else bad else bad
  else .done 0 0 else bad else bad else bad

private def freeStep (i _ : UInt32) (acc now _ _ _ : UInt64) : Action :=
  let address := row i.toUInt64
  .bind (word address 0) fun s reply => if s = 0 then
  if reply = 0 then .done Status.iterationStop i.toUInt64 else
  .bind (word address 32) fun s deadline => if s = 0 then
  if deadline ≤ now then
    .bind (word address 16) fun s ns => if s = 0 then
    .bind (respond reply ns 0 0 0 IPCABI.timeout) fun s _ => if s = 0 then
    .bind (put address 0 0) fun s _ => if s = 0 then .done Status.iterationStop i.toUInt64 else bad
    else bad else bad
  else .done 0 acc else bad else bad

private def retain (sender reply ns initialization : UInt64) : Action :=
  .bind Syscall.time fun s now => if s = 0 then
  if now ≤ 0xffffffffffffffff - PackageAwaitProtocol.maximumWaitTicks then
  .boundedFoldU64 4 freeStep 4 4 now 0 0 0 fun s slot =>
  if s = Status.iterationStop then if slot < 4 then
  .bind (Server.get 16) fun s identity => if s = 0 then
  .bind (Server.get waiterMask) fun s mask => if s = 0 then
  if 15 < mask then bad else
  let address := row slot
  .bind (put address 8 sender) fun s _ => if s = 0 then
  .bind (put address 16 ns) fun s _ => if s = 0 then
  .bind (put address 24 initialization) fun s _ => if s = 0 then
  .bind (put address 32 (now + PackageAwaitProtocol.maximumWaitTicks)) fun s _ => if s = 0 then
  .bind (put address 40 identity) fun s _ => if s = 0 then
  .bind (put address 0 reply) fun s _ => if s = 0 then
  Server.put waiterMask (mask ||| (1 <<< slot))
  else bad else bad else bad else bad else bad else bad
  else bad else bad
  else bad else if s = 0 then respond reply ns 0 0 0 Protocol.busy else bad
  else respond reply ns 0 0 0 IPCABI.timeout else bad

def awaitApplication (sender reply bytes : UInt64) : Action :=
  .bind (Protocol.field (Server.incoming + 64) 0) fun s magic => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 8) fun s ver => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 16) fun s op => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 24) fun s ns => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 32) fun s object => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 40) fun s initialization => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 48) fun s offset => if s = 0 then
  .bind (Protocol.field (Server.incoming + 64) 56) fun s count => if s = 0 then
  if PackageAwaitProtocol.shape magic ver op ns object initialization offset count bytes = 1 then
  if 0 < sender then if 16 ≤ reply then
  .bind (Server.get 112) fun s bootInitialization => if s = 0 then
  if initialization ≤ bootInitialization then
  .bind (Server.get 24) fun s mode => if s = 0 then
  if mode = 0 then retain sender reply ns initialization else
  .bind (Engine.field Server.context 0) fun s active => if s = 0 then
  if active = 0 then
  .bind (Engine.field Server.context 40) fun s sequence => if s = 0 then
  .bind (Engine.field Server.context 56) fun s generation => if s = 0 then
  .bind (Engine.field Server.context 336) fun s readonly => if s = 0 then
  if mode = 1 then if readonly = 0 then if 0 < generation then
    respond reply ns sequence 1 generation 0 else bad else bad
  else if mode = 2 then if initialization = 1 then retain sender reply ns initialization else
    respond reply ns sequence 2 0 Format.unformatted
  else if mode = 3 then respond reply ns sequence 3 generation Format.readOnly else bad
  else bad else bad else bad
  else retain sender reply ns initialization else bad else bad
  else respond reply ns 0 0 0 Format.malformed else bad
  else bad else bad
  else if magic = Protocol.magic then if ver = PackageAwaitProtocol.version then
    respond reply ns 0 0 0 Format.malformed else respond reply ns 0 0 0 Format.unsupported
  else respond reply ns 0 0 0 Format.malformed
  else bad else bad else bad else bad else bad else bad else bad else bad

private def application (sender reply bytes : UInt64) : Action :=
  if 64 ≤ bytes then
  .bind (Protocol.field (Server.incoming + 64) 16) fun s op => if s = 0 then
  if op = PackageAwaitProtocol.operation then awaitApplication sender reply bytes
  else Server.courseApplication sender reply bytes
  else bad else Server.courseApplication sender reply bytes

private def receive (nonblocking : UInt64) : Action :=
  .bind (Server.get 8) fun s endpoint => if s = 0 then
  .bind (if nonblocking = 1 then IPC.tryReceive endpoint Server.incoming IPCABI.maximumPacket
    else IPC.receive endpoint Server.incoming IPCABI.maximumPacket 1000000) fun status bytes =>
  if status = IPCABI.wouldBlock then if bytes = 0 then .done 0 0 else bad else
  if status = IPCABI.timeout then .done 0 0 else
  if status = 0 then
  .bind (IPC.validate Server.incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field Server.incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field Server.incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field Server.incoming IPCABI.lengthOffset) fun s length => if s = 0 then
  if 0 < sender then if 16 ≤ reply then application sender reply length else bad else bad
  else bad else bad else bad
  else .done 0 0 else bad else bad else bad

def step : Action :=
  .bind Server.courseService fun s _ => if s = 0 then
  .bind settleWaiters fun s _ => if s = 0 then
  .bind (Engine.field Server.context 0) fun s operation => if s = 0 then
  if operation = 0 then receive 0 else
  .bind (Server.get 24) fun s mode => if s = 0 then
  .bind (Server.get 128) fun s receipt => if s = 0 then
  if mode = 0 then receive 1 else if receipt = 1 then receive 1 else .done 0 0
  else bad else bad else bad else bad else bad

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := Server.context + i.toUInt64 * 4096
  .bind (Syscall.allocatePage address) fun s actual => if s = 0 then
  if actual = address then .done 0 (acc + 1) else bad else .done s 0

private def clearStateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Server.put (i.toUInt64 * 8) 0) fun s _ => if s = 0 then .done 0 (acc + 1) else bad

def main (bootArgument : UInt64) : Action :=
  if bootArgument ≤ 1 then
  .bind (Capability.bootGrant 0) fun s block => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s identity => if s = 0 then
  .boundedFoldU64 34 allocateStep 34 0 0 0 0 0 fun s pages => if s = 0 then if pages = 34 then
  .boundedFoldU64 88 clearStateStep 88 0 0 0 0 0 fun s fields => if s = 0 then if fields = 88 then
  .bind (Server.put 0 block) fun s _ => if s = 0 then
  .bind (Server.put 8 endpoint) fun s _ => if s = 0 then
  .bind (Server.put 16 identity) fun s _ => if s = 0 then
  .bind (Server.put 112 bootArgument) fun s _ => if s = 0 then
  .bind (Syscall.call 66 block 0 0 0 0) fun s capacity => if s = 0 then
  .bind (Engine.mountStart Server.context Server.buffer Server.index0 capacity) fun s _ =>
  if s = 0 then .loop step else bad
  else bad else bad else bad else bad else bad
  else bad else bad else bad else bad
  else bad else bad else bad else bad

end Lemma.Services.Store.ServerAwait
