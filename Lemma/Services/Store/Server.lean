import Lemma.Services.Store.Engine
import Lemma.Services.Store.Protocol
import Lemma.User.IPC
import Lemma.User.Capability
import Lemma.Courses.PackageTarget

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

private def respondAt (reply operation ns object sequence detail count : UInt64) (app : UInt8) : Action :=
  .bind (Protocol.header outgoing operation ns object sequence detail count) fun s _ => if s = 0 then
  .bind (IPC.reply reply outgoing (64 + count) app.toUInt64) fun s value =>
  if value = 0 then
    if s = 0 then .done 0 0 else
    if s = CapabilityABI.invalidHandle then .done 0 0 else
    if s = IPCABI.peerDied then .done 0 0 else
    if s = IPCABI.revoked then .done 0 0 else failed
  else failed
  else failed

private def respond (reply operation ns object detail count : UInt64) (app : UInt8) : Action :=
  .bind (Engine.field context 40) fun s sequence => if s = 0 then
  respondAt reply operation ns object sequence detail count app else failed

/-- Receipt fields128..176 are independent of the staged payload lease and
retained v1 reply handle. The full kernel sender, namespace and ticket bind
every observation. No client lifetime transition releases live block work. -/
def checkpointOwner (sender ns ticket : UInt64) : Action :=
  .bind (get 128) fun s receipt => if s = 0 then
  .bind (get 136) fun s owner => if s = 0 then
  .bind (get 144) fun s storedNs => if s = 0 then
  .bind (get 152) fun s storedTicket => if s = 0 then
  if receipt ≤ 3 then
  if receipt = 0 then .done 0 0 else
  if owner = sender then if storedNs = ns then if storedTicket = ticket then .done 0 1
  else .done 0 0 else .done 0 0 else .done 0 0
  else failed else failed else failed else failed else failed

def checkpointStatus (sender reply operation ns ticket : UInt64) : Action :=
  .bind (checkpointOwner sender ns ticket) fun s matched => if s = 0 then
  if matched = 1 then
  .bind (get 128) fun s receipt => if s = 0 then
  .bind (get 160) fun s originalSequence => if s = 0 then
  if receipt = 1 then respondAt reply operation ns 0 originalSequence 1 0 0 else
  .bind (get 168) fun s finalSequence => if s = 0 then
  .bind (get 176) fun s error => if s = 0 then
  if finalSequence = originalSequence then
    if receipt = 2 then
      if error = 0 then respondAt reply operation ns 0 finalSequence 0 0 0 else failed
    else if receipt = 3 then
      if 220 ≤ error then if error ≤ 230 then
        respondAt reply operation ns 0 finalSequence 0 0 error.toUInt8 else failed else failed
    else failed
  else failed else failed else failed else failed else failed
  else respond reply operation ns 0 0 0 Protocol.wrongOwner else failed

def checkpointBegin (sender reply ns ticket : UInt64) : Action :=
  .bind (checkpointOwner sender ns ticket) fun s matched => if s = 0 then
  if matched = 1 then checkpointStatus sender reply 12 ns ticket else
  .bind (get 128) fun s receipt => if s = 0 then
  .bind (get 48) fun s stagedOwner => if s = 0 then
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  .bind (get 24) fun s mode => if s = 0 then
  if receipt = 1 then respond reply 12 ns 0 0 0 Protocol.busy else
  if mode = 0 then respond reply 12 ns 0 0 0 Protocol.busy else
  if mode = 1 then
  if stagedOwner = 0 then if operation = 0 then
  .bind (Engine.field context 40) fun s sequence => if s = 0 then
  .bind (Engine.field context 104) fun s index => if s = 0 then
  .bind (Engine.checkpointStart context (if index = index0 then index1 else index0)) fun status _ =>
  if status = 0 then
  .bind (put 136 sender) fun s _ => if s = 0 then
  .bind (put 144 ns) fun s _ => if s = 0 then
  .bind (put 152 ticket) fun s _ => if s = 0 then
  .bind (put 160 sequence) fun s _ => if s = 0 then
  .bind (put 168 sequence) fun s _ => if s = 0 then
  .bind (put 176 0) fun s _ => if s = 0 then
  .bind (put 128 1) fun s _ => if s = 0 then
  respondAt reply 12 ns 0 sequence 1 0 0
  else failed else failed else failed else failed else failed else failed else failed
  else respond reply 12 ns 0 0 0 status else failed else failed
  else respond reply 12 ns 0 0 0 Protocol.busy
  else respond reply 12 ns 0 0 0 Protocol.busy
  else respond reply 12 ns 0 0 0 Format.readOnly
  else failed else failed else failed else failed else failed

/-- Latch a single terminal receipt only after the actual engine completion.
Checkpoint never changes acknowledged document sequence; a mismatch fails
closed rather than publishing a receipt for another operation. -/
def settleCheckpoint : Action :=
  .bind (get 128) fun s receipt => if s = 0 then
  if receipt = 1 then
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  if operation = 0 then
  .bind (Engine.field context 32) fun s result => if s = 0 then
  .bind (Engine.field context 40) fun s sequence => if s = 0 then
  .bind (get 160) fun s originalSequence => if s = 0 then
  if sequence = originalSequence then
  if (if result = 0 then (1 : UInt64) else if 220 ≤ result then if result ≤ 230 then 1 else 0 else 0) = 1 then
  .bind (put 168 sequence) fun s _ => if s = 0 then
  .bind (put 176 result) fun s _ => if s = 0 then
  .bind (put 128 (if result = 0 then 2 else 3)) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else failed
  else failed else failed else failed else failed else failed
  else .done 0 0 else failed
  else .done 0 0 else failed

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
  .bind settleCheckpoint fun s _ => if s = 0 then
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
  else failed else failed else failed else failed else failed else failed
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

def application (sender reply bytes : UInt64) : Action :=
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
  .bind (Engine.field context 0) fun s active => if s = 0 then
  if magic = Protocol.magic then if version = Protocol.requestVersion operation then
  if Protocol.shape operation ns object transaction offset count bytes = 1 then
    if operation = 13 then checkpointStatus sender reply operation ns transaction else
    if operation = 8 then respond reply operation ns object mode 0 0 else
    if operation = 12 then checkpointBegin sender reply ns transaction
    else if 0 < active then respond reply operation ns object 0 0 Protocol.busy else
    if operation = 11 then format sender reply else
    if operation = 1 then respond reply operation ns object mode 0 (if mode = 1 then 0 else if mode = 2 then Format.unformatted else Format.readOnly)
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
  else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed
  else respond reply 0 0 0 0 0 Format.malformed

def receive (nonblocking : UInt64) : Action :=
  .bind (get 8) fun s endpoint => if s = 0 then
  .bind (if nonblocking = 1 then IPC.tryReceive endpoint incoming IPCABI.maximumPacket
    else IPC.receive endpoint incoming IPCABI.maximumPacket 1000000) fun status bytes =>
  if status = IPCABI.wouldBlock then if bytes = 0 then .done 0 0 else failed else
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

def step : Action :=
  .bind pump fun s _ => if s = 0 then
  .bind settle fun s _ => if s = 0 then
  .bind expireStage fun s _ => if s = 0 then
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  if operation = 0 then receive 0 else
  .bind (get 24) fun s mode => if s = 0 then
  .bind (get 128) fun s receipt => if s = 0 then
  if mode = 0 then receive 1 else if receipt = 1 then receive 1 else .done 0 0
  else failed else failed
  else failed else failed else failed else failed

def main (bootArgument : UInt64) : Action :=
  if bootArgument ≤ 1 then
  .bind (Capability.bootGrant 0) fun s block => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s identity => if s = 0 then
  .boundedFoldU64 34 allocateStep 34 0 0 0 0 0 fun s pages =>
  if s = 0 then if pages = 34 then
  .boundedFoldU64 24 clearStep 24 0 0 0 0 0 fun s fields =>
  if s = 0 then if fields = 24 then
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

/-! `lemma-course-store-guard/1` is opt-in. Historical main/step/application
remain unchanged. Its reserved key prefix is4350; bits32..47 are the nonzero
package identity and bits0..31 the nonzero edition. The existing namespace
grant remains the authority. All policy checks precede append/delete I/O. -/

def courseKey (object : UInt64) : UInt64 :=
  if object >>> 48 = 0x4350 then 1 else 0

private def courseKeyValid (object : UInt64) : UInt64 :=
  if (object >>> 32) &&& 0xffff = 0 then 0 else
  if object &&& 0xffffffff = 0 then 0 else 1

/-- A matching latest row, including a tombstone, permanently consumes this
edition key. Do not confuse Engine.lookup's live-only notFound with absence.
No state publication, reply or backing operation occurs in this preflight. -/
def courseAbsent (ns object : UInt64) : Action :=
  if courseKey object = 1 then if courseKeyValid object = 1 then
  .bind (Engine.field context 104) fun s index => if s = 0 then
  .bind (Index.find index ns object) fun s slot => if s = 0 then
  .bind (Lemma.User.Memory.read64 (Index.row index slot)) fun s storedNs => if s = 0 then
  if storedNs = 0 then .done 0 0 else
  .bind (Lemma.User.Memory.read64 (Index.row index slot + 8)) fun s storedObject => if s = 0 then
  if storedNs = ns then if storedObject = object then .done Format.readOnly 0 else .done Format.malformed 0
  else .done Format.malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0

private def courseBegin (sender reply ns object transaction count : UInt64) : Action :=
  .bind (get 48) fun s owner => if s = 0 then
  if owner = 0 then
  if count < 128 then respond reply 2 ns object 0 0 Format.malformed else
  .bind (courseAbsent ns object) fun status _ =>
  if status = 0 then begin sender reply ns object transaction count
  else if 220 ≤ status then if status ≤ 233 then respond reply 2 ns object 0 0 status else failed else failed
  else respond reply 2 ns object 0 0 Protocol.busy else failed

private def coursePackageStatus (status : UInt8) : UInt8 :=
  if status = 0 then 0 else
  if status = Lemma.Courses.PackageFormat.unsupported then Format.unsupported else
  if status = Lemma.Courses.PackageFormat.integrityFailure then Format.checksumFailed else
  if status = Lemma.Courses.PackageFormat.resourceLimit then Format.full else Format.malformed

private def courseCommit (sender reply ns object transaction : UInt64) : Action :=
  .bind (stageOwner sender ns object transaction) fun s matched => if s = 0 then
  if matched = 1 then
  .bind (get 88) fun s used => if s = 0 then
  .bind (get 96) fun s desired => if s = 0 then
  if used = desired then
  .bind (courseAbsent ns object) fun status _ => if status = 0 then
  .bind (Lemma.Courses.PackageTarget.validate payload used) fun status _ =>
  if status = 0 then
  .bind (Lemma.User.Memory.read64 (payload + 24)) fun s identity => if s = 0 then
  .bind (Lemma.User.Memory.read64 (payload + 32)) fun s edition => if s = 0 then
  if identity = (object >>> 32) &&& 0xffff then if edition = object &&& 0xffffffff then
    commit sender reply ns object transaction
  else respond reply 4 ns object used 0 Format.malformed
  else respond reply 4 ns object used 0 Format.malformed
  else failed else failed
  else if 240 ≤ status then if status ≤ 244 then
    respond reply 4 ns object used 0 (coursePackageStatus status) else failed else failed
  else if 220 ≤ status then if status ≤ 233 then respond reply 4 ns object used 0 status else failed else failed
  else respond reply 4 ns object used 0 Protocol.incomplete
  else failed else failed
  else respond reply 4 ns object 0 0 Protocol.wrongOwner else failed

/-- The versioned entry preserves ordinary header/shape/mode/active priority.
Reserved begin/commit/delete are guarded. Other operations delegate unchanged
to the legacy dispatcher; no replacement policy applies to notebook records. -/
def courseApplication (sender reply bytes : UInt64) : Action :=
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
  .bind (Engine.field context 0) fun s active => if s = 0 then
  if magic = Protocol.magic then if version = Protocol.requestVersion operation then
  if Protocol.shape operation ns object transaction offset count bytes = 1 then
    if 0 < active then application sender reply bytes else
    if mode = 1 then if courseKey object = 1 then
      if operation = 2 then courseBegin sender reply ns object transaction count else
      if operation = 4 then courseCommit sender reply ns object transaction else
      if operation = 6 then
        .bind (get 48) fun s owner => if s = 0 then
        if owner = 0 then respond reply operation ns object 0 0 Format.readOnly
        else respond reply operation ns object 0 0 Protocol.busy else failed
      else application sender reply bytes
    else application sender reply bytes else application sender reply bytes
  else application sender reply bytes
  else application sender reply bytes
  else application sender reply bytes
  else failed else failed else failed else failed else failed else failed
  else failed else failed else failed else failed
  else application sender reply bytes

private def courseReceive (nonblocking : UInt64) : Action :=
  .bind (get 8) fun s endpoint => if s = 0 then
  .bind (if nonblocking = 1 then IPC.tryReceive endpoint incoming IPCABI.maximumPacket
    else IPC.receive endpoint incoming IPCABI.maximumPacket 1000000) fun status bytes =>
  if status = IPCABI.wouldBlock then if bytes = 0 then .done 0 0 else failed else
  if status = IPCABI.timeout then .done 0 0 else
  if status = 0 then
  .bind (IPC.validate incoming bytes) fun s kind => if s = 0 then
  if kind = IPCABI.callKind then
  .bind (IPC.field incoming IPCABI.senderOffset) fun s sender => if s = 0 then
  .bind (IPC.field incoming IPCABI.replyOffset) fun s reply => if s = 0 then
  .bind (IPC.field incoming IPCABI.lengthOffset) fun s length => if s = 0 then
  if 0 < sender then if 16 ≤ reply then courseApplication sender reply length else failed else failed
  else failed else failed else failed
  else .done 0 0 else failed else failed else failed

def courseStep : Action :=
  .bind pump fun s _ => if s = 0 then
  .bind settle fun s _ => if s = 0 then
  .bind expireStage fun s _ => if s = 0 then
  .bind (Engine.field context 0) fun s operation => if s = 0 then
  if operation = 0 then courseReceive 0 else
  .bind (get 24) fun s mode => if s = 0 then
  .bind (get 128) fun s receipt => if s = 0 then
  if mode = 0 then courseReceive 1 else if receipt = 1 then courseReceive 1 else .done 0 0
  else failed else failed
  else failed else failed else failed else failed

def courseMain (bootArgument : UInt64) : Action :=
  if bootArgument ≤ 1 then
  .bind (Capability.bootGrant 0) fun s block => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s identity => if s = 0 then
  .boundedFoldU64 34 allocateStep 34 0 0 0 0 0 fun s pages =>
  if s = 0 then if pages = 34 then
  .boundedFoldU64 24 clearStep 24 0 0 0 0 0 fun s fields =>
  if s = 0 then if fields = 24 then
  .bind (put 0 block) fun s _ => if s = 0 then
  .bind (put 8 endpoint) fun s _ => if s = 0 then
  .bind (put 16 identity) fun s _ => if s = 0 then
  .bind (put 112 bootArgument) fun s _ => if s = 0 then
  .bind (Syscall.call 66 block 0 0 0 0) fun s capacity => if s = 0 then
  .bind (Engine.mountStart context buffer index0 capacity) fun s _ =>
  if s = 0 then .loop courseStep else failed
  else failed else failed else failed else failed else failed
  else failed else failed else failed else failed
  else failed else failed else failed else failed

/-- Opt-in recovery server composes this exact ordinary pump/settle/lease
prefix with its separately versioned receive dispatcher. Historical step and
courseStep retain their own complete definitions and receive paths. -/
def courseService : Action :=
  .bind pump fun s _ => if s = 0 then
  .bind settle fun s _ => if s = 0 then expireStage else failed else failed


/-! School queue guard/1 is selected only by ServerSchool.main. The frozen
metadata prefix5351 is append-only, including tombstones. Historical course
roots and application dispatchers keep their exact definitions. -/
def schoolKey (object : UInt64) : UInt64 :=
  if object >>> 48 = 0x5351 then 1 else 0

def schoolAbsent (ns object : UInt64) : Action :=
  if ns = 2 then if schoolKey object = 1 then if 0 < (object &&& 0x0000ffffffffffff) then
  .bind (Engine.field context 104) fun s index => if s = 0 then
  .bind (Index.find index ns object) fun s slot => if s = 0 then
  .bind (Memory.read64 (Index.row index slot)) fun s storedNs => if s = 0 then
  if storedNs = 0 then .done 0 0 else
  .bind (Memory.read64 (Index.row index slot+8)) fun s storedObject => if s = 0 then
  if storedNs = ns then if storedObject = object then .done Format.readOnly 0 else .done Format.malformed 0
  else .done Format.malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.wrongNamespace 0

private def schoolBegin (sender reply ns object transaction count : UInt64) : Action :=
  .bind (get 48) fun s owner => if s = 0 then
  if owner = 0 then
  if count < 4096 then respond reply 2 ns object 0 0 Format.malformed else
  if 16384 < count then respond reply 2 ns object 0 0 Format.full else
  .bind (schoolAbsent ns object) fun status _ =>
  if status = 0 then begin sender reply ns object transaction count
  else if 220 ≤ status then if status ≤ 233 then respond reply 2 ns object 0 0 status else failed else failed
  else respond reply 2 ns object 0 0 Protocol.busy else failed

private def schoolMetadataShape (ns object bytes : UInt64) : Action :=
  .bind (Memory.read64 payload) fun s tag => if s = 0 then
  .bind (Memory.read64 (payload+8)) fun s version => if s = 0 then
  .bind (Memory.read64 (payload+16)) fun s total => if s = 0 then
  .bind (Memory.read64 (payload+24)) fun s queue => if s = 0 then
  .bind (Memory.read64 (payload+32)) fun s frontier => if s = 0 then
  .bind (Memory.read64 (payload+40)) fun s actualNs => if s = 0 then
  .bind (Memory.read64 (payload+232)) fun s header => if s = 0 then
  .bind (Memory.read64 (payload+240)) fun s workspace => if s = 0 then
  .bind (Memory.read64 (payload+248)) fun s index => if s = 0 then
  if tag = 0x31425553534d454c then if version = 1 then
  if frontier < 0x0000fffffffffffe then if queue = (0x5351000000000000 ||| (frontier+1)) then
  if queue = object then if ns = 2 then if Protocol.namespaceValid actualNs = 1 then if header = 256 then if workspace = 3712 then
  if 128 ≤ index then if index%8 = 0 then if index ≤ 8512 then
  if bytes = header+workspace+index then if bytes ≤ total then if total ≤ 262144 then .done 0 0
  else .done Format.full 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0 else .done Format.malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def schoolCommit (sender reply ns object transaction : UInt64) : Action :=
  .bind (stageOwner sender ns object transaction) fun s matched => if s = 0 then
  if matched = 1 then
  .bind (get 88) fun s used => if s = 0 then
  .bind (get 96) fun s desired => if s = 0 then
  if used = desired then
  .bind (schoolAbsent ns object) fun status _ => if status = 0 then
  .bind (schoolMetadataShape ns object used) fun status _ => if status = 0 then
  commit sender reply ns object transaction
  else if 220 ≤ status then if status ≤ 233 then respond reply 4 ns object used 0 status else failed else failed
  else if 220 ≤ status then if status ≤ 233 then respond reply 4 ns object used 0 status else failed else failed
  else respond reply 4 ns object used 0 Protocol.incomplete
  else failed else failed
  else respond reply 4 ns object 0 0 Protocol.wrongOwner else failed

/-- New prefix handling follows the same framing/mode/active precedence, then
uses the original stage owner and engine Commit. No other object is retargeted. -/
def schoolApplication (sender reply bytes : UInt64) : Action :=
  if 64 ≤ bytes then
  .bind (Protocol.field (incoming+64) 0) fun s magic => if s = 0 then
  .bind (Protocol.field (incoming+64) 8) fun s version => if s = 0 then
  .bind (Protocol.field (incoming+64) 16) fun s operation => if s = 0 then
  .bind (Protocol.field (incoming+64) 24) fun s ns => if s = 0 then
  .bind (Protocol.field (incoming+64) 32) fun s object => if s = 0 then
  .bind (Protocol.field (incoming+64) 40) fun s transaction => if s = 0 then
  .bind (Protocol.field (incoming+64) 48) fun s offset => if s = 0 then
  .bind (Protocol.field (incoming+64) 56) fun s count => if s = 0 then
  .bind (get 24) fun s mode => if s = 0 then
  .bind (Engine.field context 0) fun s active => if s = 0 then
  if magic = Protocol.magic then if version = Protocol.requestVersion operation then
  if Protocol.shape operation ns object transaction offset count bytes = 1 then
  if mode = 1 then if active = 0 then if schoolKey object = 1 then
    if operation = 2 then schoolBegin sender reply ns object transaction count else
    if operation = 4 then schoolCommit sender reply ns object transaction else
    if operation = 6 then respond reply operation ns object 0 0 Format.readOnly
    else courseApplication sender reply bytes
  else courseApplication sender reply bytes else courseApplication sender reply bytes else courseApplication sender reply bytes
  else courseApplication sender reply bytes else courseApplication sender reply bytes else courseApplication sender reply bytes
  else failed else failed else failed else failed else failed
  else failed else failed else failed else failed else failed
  else courseApplication sender reply bytes

end Lemma.Services.Store.Server
