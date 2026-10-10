import Lemma.Services.Store.Engine
import Lemma.Services.Store.Protocol
import Lemma.User.IPC
import Lemma.User.Capability

/-! Separately linked document service. All serialization, transaction ordering,
checksums, indexing and recovery are compiled Lean User code. The kernel knows
only sector operations. Only this deployment receives the raw-block grant.
The document endpoint admits namespaces1/2; its Call grants are the authority
boundary. A kernel-stamped full sender owns the sole bounded staging buffer.
No host is asked to mount, parse, commit, or reconstruct a document. -/
namespace Lemma.Services.Store.Server
open Lemma.Core0.Memory
open Lemma.User

def incoming : UInt64 := 0x20300
def outgoing : UInt64 := 0x20500
def state : UInt64 := 0x20800
def context : UInt64 := 0x40000
def buffer : UInt64 := 0x41000
def index0 : UInt64 := 0x42000
def index1 : UInt64 := 0x4e000
def payload : UInt64 := 0x5a000
def failed : Action := .done 95 0
def get (offset : UInt64) : Action := Memory.read64 (state + offset)
def put (offset value : UInt64) : Action := Memory.write64 (state + offset) value

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := context + i.toUInt64 * 4096
  .bind (Syscall.allocatePage address) fun s value =>
  if s = 0 then if value = address then .done 0 (acc + 1) else failed else .done s 0

private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ =>
  if s = 0 then .done 0 (acc + 1) else failed

private def clearStage : Action :=
  .bind (put 40 0) fun s _ => if s = 0 then
  .bind (put 48 0) fun s _ => if s = 0 then
  .bind (put 56 0) fun s _ => if s = 0 then
  .bind (put 64 0) fun s _ => if s = 0 then
  .bind (put 72 0) fun s _ => if s = 0 then
  .bind (put 80 0) fun s _ => if s = 0 then
  .bind (put 88 0) fun s _ => if s = 0 then
  .bind (put 96 0) fun s _ => if s = 0 then
  .bind (put 104 0) fun s _ => if s = 0 then
  .bind (put 120 0) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else failed else failed else failed else failed else failed else failed else failed
  else failed

private def renewStage : Action :=
  .bind Syscall.time fun s now => if s = 0 then
  if now ≤ 0xffffffffffffffff - 100000000 then
  .bind (put 120 (now + 100000000)) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else failed

/-- An abandoned uncommitted staging buffer expires after ten guest seconds.
No committed record or outstanding DMA ownership is released by this lease. -/
private def expireStage : Action :=
  .bind (get 48) fun s owner => if s = 0 then
  .bind (get 40) fun s reply => if s = 0 then
  if owner = 0 then .done 0 0 else if reply = 0 then
  .bind (get 120) fun s deadline => if s = 0 then
  .bind Syscall.time fun s now => if s = 0 then
  if deadline ≤ now then clearStage else .done 0 0
  else failed else failed
  else .done 0 0 else failed else failed

private def respond (reply operation ns object detail count : UInt64) (app : UInt8) : Action :=
  .bind (Engine.field context 40) fun s sequence => if s = 0 then
  .bind (Protocol.header outgoing operation ns object sequence detail count) fun s _ => if s = 0 then
  .bind (IPC.reply reply outgoing (64 + count) app.toUInt64) fun s value =>
  if value = 0 then
    if s = 0 then .done 0 0 else
    if s = CapabilityABI.invalidHandle then .done 0 0 else
    if s = IPCABI.peerDied then .done 0 0 else
    if s = IPCABI.revoked then .done 0 0 else failed
  else failed
  else failed else failed

private def finishEngine (status : UInt8) : Action :=
  .bind (Engine.complete context status) fun s _ =>
  if s = 0 then .done 0 0 else if 220 ≤ s then if s ≤ 230 then .done 0 0 else failed else failed

private def pump : Action :=
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  if operation = 0 then .done 0 0 else
  .bind (get 0) fun s block => if s = 0 then
  .bind (get 32) fun s submitted => if s = 0 then
  if submitted = 0 then
    .bind (Engine.field context 16) fun s sector => if s = 0 then
    .bind (Syscall.call 66 block operation sector (if operation = 3 then 0 else buffer) 0) fun status _ =>
    if status = 168 then
      .bind (put 32 1) fun s _ => if s = 0 then .done 0 0 else failed
    else finishEngine status
    else failed
  else if submitted = 1 then
    .bind (Syscall.call 66 block 4 0 (if operation = 1 then buffer else 0) 0) fun status _ =>
    if status = 168 then
      .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else failed
    else
      .bind (put 32 0) fun s _ => if s = 0 then finishEngine status else failed
  else failed
  else failed else failed else failed

private def settle : Action :=
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  if operation = 0 then
  .bind (Engine.field context 32) fun s result => if s = 0 then
  .bind (get 24) fun s mode => if s = 0 then
  .bind (Engine.field context 336) fun s readOnly => if s = 0 then
  let nextMode := if result = 0 then (1 : UInt64) else if result = 221 then 2 else if readOnly = 0 then 1 else 3
  .bind (put 24 nextMode) fun s _ => if s = 0 then
  .bind (get 40) fun s reply => if s = 0 then
  if reply = 0 then .done 0 mode else
  .bind (get 56) fun s request => if s = 0 then
  .bind (get 64) fun s ns => if s = 0 then
  .bind (get 72) fun s object => if s = 0 then
  .bind (get 104) fun s offeredCount => if s = 0 then
  .bind (Engine.field context 352) fun s actualCount => if s = 0 then
  if result ≤ 255 then
  let count := if result = 0 then if request = 5 then actualCount else 0 else 0
  if count ≤ offeredCount then
  .bind (respond reply request ns object nextMode count result.toUInt8) fun s _ =>
  if s = 0 then clearStage else failed
  else failed else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed
  else .done 0 0 else failed

private def stageOwner (sender ns object transaction : UInt64) : Action :=
  .bind (get 48) fun s owner => if s = 0 then
  .bind (get 64) fun s storedNs => if s = 0 then
  .bind (get 72) fun s storedObject => if s = 0 then
  .bind (get 80) fun s storedTransaction => if s = 0 then
  if owner = sender then if storedNs = ns then if storedObject = object then
  if storedTransaction = transaction then .done 0 1 else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0
  else failed else failed else failed else failed

private def begin (sender reply ns object transaction count : UInt64) : Action :=
  .bind (get 48) fun s owner => if s = 0 then
  if owner = 0 then
  .bind (put 48 sender) fun s _ => if s = 0 then
  .bind (put 64 ns) fun s _ => if s = 0 then
  .bind (put 72 object) fun s _ => if s = 0 then
  .bind (put 80 transaction) fun s _ => if s = 0 then
  .bind (put 88 0) fun s _ => if s = 0 then
  .bind (put 96 count) fun s _ => if s = 0 then
  .bind renewStage fun s _ => if s = 0 then respond reply 2 ns object 0 0 0 else failed
  else failed
  else failed else failed else failed else failed else failed
  else respond reply 2 ns object 0 0 Protocol.busy else failed

private def chunk (sender reply ns object transaction offset count : UInt64) : Action :=
  .bind (stageOwner sender ns object transaction) fun s matched => if s = 0 then
  if matched = 1 then
  .bind (get 88) fun s used => if s = 0 then
  .bind (get 96) fun s desired => if s = 0 then
  if offset = used then if used ≤ desired then if count ≤ desired - used then
  .bind (Format.copy (incoming + 128) (payload + used) count) fun s _ => if s = 0 then
  .bind (put 88 (used + count)) fun s _ => if s = 0 then
  .bind renewStage fun s _ => if s = 0 then
  respond reply 3 ns object (used + count) 0 0 else failed else failed else failed
  else respond reply 3 ns object used 0 Format.malformed
  else failed else respond reply 3 ns object used 0 Format.malformed
  else failed else failed
  else respond reply 3 ns object 0 0 Protocol.wrongOwner else failed

private def defer (sender reply operation ns object count : UInt64) : Action :=
  .bind (put 48 sender) fun s _ => if s = 0 then
  .bind (put 56 operation) fun s _ => if s = 0 then
  .bind (put 64 ns) fun s _ => if s = 0 then
  .bind (put 72 object) fun s _ => if s = 0 then
  .bind (put 104 count) fun s _ => if s = 0 then
  .bind (put 40 reply) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else failed else failed else failed else failed

private def commit (sender reply ns object transaction : UInt64) : Action :=
  .bind (stageOwner sender ns object transaction) fun s matched => if s = 0 then
  if matched = 1 then
  .bind (get 88) fun s used => if s = 0 then
  .bind (get 96) fun s desired => if s = 0 then
  if used = desired then
  .bind (Engine.appendStart context ns object transaction payload used 1) fun status _ =>
  if status = 0 then defer sender reply 4 ns object 0
  else respond reply 4 ns object used 0 status
  else respond reply 4 ns object used 0 Protocol.incomplete
  else failed else failed
  else respond reply 4 ns object 0 0 Protocol.wrongOwner else failed

private def simpleIO (sender reply operation ns object transaction offset count : UInt64) : Action :=
  .bind (get 48) fun s owner => if s = 0 then
  if owner = 0 then
    if operation = 5 then
      .bind (Engine.readStart context ns object offset count (outgoing + 64)) fun status _ =>
      if status = 0 then defer sender reply operation ns object count
      else respond reply operation ns object 0 0 status
    else if operation = 6 then
      .bind (Engine.appendStart context ns object transaction payload 0 2) fun status _ =>
      if status = 0 then defer sender reply operation ns object 0
      else respond reply operation ns object 0 0 status
    else if operation = 7 then
      .bind (Engine.field context 104) fun s index => if s = 0 then
      .bind (Engine.checkpointStart context (if index = index0 then index1 else index0)) fun status _ =>
      if status = 0 then defer sender reply operation ns object 0
      else respond reply operation ns object 0 0 status
      else failed
    else failed
  else respond reply operation ns object 0 0 Protocol.busy else failed

private def format (sender reply : UInt64) : Action :=
  .bind (get 112) fun s allowed => if s = 0 then
  .bind (get 24) fun s mode => if s = 0 then
  if allowed = 1 then if mode = 2 then
  .bind (Engine.field context 48) fun s capacity => if s = 0 then
  .bind (Engine.formatStart context buffer index0 capacity) fun status _ =>
  if status = 0 then defer sender reply 11 0 0 0 else respond reply 11 0 0 3 0 status
  else failed else respond reply 11 0 0 mode 0 Format.readOnly
  else respond reply 11 0 0 mode 0 Format.readOnly else failed else failed

private def application (sender reply bytes : UInt64) : Action :=
  if 64 ≤ bytes then
  .bind (Protocol.field (incoming + 64) 0) fun s magic => if s = 0 then
  .bind (Protocol.field (incoming + 64) 8) fun s version => if s = 0 then
  .bind (Protocol.field (incoming + 64) 16) fun s operation => if s = 0 then
  .bind (Protocol.field (incoming + 64) 24) fun s ns => if s = 0 then
  .bind (Protocol.field (incoming + 64) 32) fun s object => if s = 0 then
  .bind (Protocol.field (incoming + 64) 40) fun s transaction => if s = 0 then
  .bind (Protocol.field (incoming + 64) 48) fun s offset => if s = 0 then
  .bind (Protocol.field (incoming + 64) 56) fun s count => if s = 0 then
  .bind (get 24) fun s mode => if s = 0 then
  if magic = Protocol.magic then if version = 1 then
  if Protocol.shape operation ns object transaction offset count bytes = 1 then
    if operation = 11 then format sender reply else
    if operation = 1 then respond reply operation ns object mode 0 (if mode = 1 then 0 else if mode = 2 then Format.unformatted else Format.readOnly)
    else if operation = 8 then respond reply operation ns object mode 0 0
    else if mode = 1 then
      if operation = 2 then begin sender reply ns object transaction count else
      if operation = 3 then chunk sender reply ns object transaction offset count else
      if operation = 4 then commit sender reply ns object transaction else
      if operation = 5 then simpleIO sender reply operation ns object transaction offset count else
      if operation = 6 then simpleIO sender reply operation ns object transaction offset count else
      if operation = 7 then simpleIO sender reply operation ns object transaction offset count else
      if operation = 9 then
        .bind (stageOwner sender ns object transaction) fun s matched => if s = 0 then
        if matched = 1 then .bind clearStage fun s _ =>
          if s = 0 then respond reply operation ns object 0 0 0 else failed
        else respond reply operation ns object 0 0 Protocol.wrongOwner else failed
      else if operation = 10 then
        .bind (get 48) fun s owner => if s = 0 then
        if owner = 0 then respond reply operation ns object 0 0 0
        else respond reply operation ns object 0 0 Protocol.busy else failed
      else respond reply operation ns object 0 0 Format.unsupported
    else respond reply operation ns object mode 0 Format.readOnly
  else respond reply operation ns object 0 0 Format.malformed
  else respond reply operation ns object 0 0 Format.unsupported
  else respond reply operation ns object 0 0 Format.malformed
  else failed else failed else failed else failed else failed
  else failed else failed else failed else failed
  else respond reply 0 0 0 0 0 Format.malformed

private def receive : Action :=
  .bind (get 8) fun s endpoint => if s = 0 then
  .bind (IPC.receive endpoint incoming IPCABI.maximumPacket 1000000) fun status bytes =>
  if status = IPCABI.timeout then .done 0 0 else
  if status = 0 then
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field incoming IPCABI.lengthOffset) fun s length => if s = 0 then
  if 0 < sender then if 16 ≤ reply then application sender reply length else failed else failed
  else failed else failed else failed
  else .done 0 0 else failed else failed else failed

private def step : Action :=
  .bind pump fun s _ => if s = 0 then
  .bind settle fun s _ => if s = 0 then
  .bind expireStage fun s _ => if s = 0 then
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  if operation = 0 then receive else .done 0 0
  else failed else failed else failed else failed

def main (bootArgument : UInt64) : Action :=
  if bootArgument ≤ 1 then
  .bind (Capability.bootGrant 0) fun s block => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s identity => if s = 0 then
  .boundedFoldU64 34 allocateStep 34 0 0 0 0 0 fun s pages =>
  if s = 0 then if pages = 34 then
  .boundedFoldU64 16 clearStep 16 0 0 0 0 0 fun s fields =>
  if s = 0 then if fields = 16 then
  .bind (put 0 block) fun s _ => if s = 0 then
  .bind (put 8 endpoint) fun s _ => if s = 0 then
  .bind (put 16 identity) fun s _ => if s = 0 then
  .bind (put 112 bootArgument) fun s _ => if s = 0 then
  .bind (Syscall.call 66 block 0 0 0 0) fun s capacity => if s = 0 then
  .bind (Engine.mountStart context buffer index0 capacity) fun s _ =>
  if s = 0 then .loop step else failed
  else failed else failed else failed else failed else failed
  else failed else failed else failed else failed
  else failed else failed else failed else failed

end Lemma.Services.Store.Server
