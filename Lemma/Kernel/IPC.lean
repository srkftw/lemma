import Lemma.Kernel.Capability
import Lemma.Kernel.IPCStorage
import Lemma.Kernel.MachineServices
import Lemma.User.IPCABI

/-! Copied, capability-checked IPC. These transitions know descriptors and
bounded owned storage, never task rows or trap frames. Supervisor critical
sections are single-hart and nonpreemptible; the scheduler owns suspension.
Only explicit receive/call-wait may return the private blocked outcome254. -/
namespace Lemma.Kernel.IPC
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def blockedStatus : UInt8 := 254
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 255 0

def «initialize» (descriptor : UInt64) : Action := IPCStorage.initialize descriptor

private def put (address value : UInt64) : Action :=
  .bind (Access.write64 address value) fun s _ =>
  if failed s = true then fatal else .done 0 0

private def word (metadata offset : UInt64) : Action :=
  .bind (Access.read64 (metadata + offset)) fun s value =>
  if failed s = true then fatal else .done 0 value

private def idle (descriptor : UInt64) : Action :=
  .bind (IPCStorage.pending descriptor) fun s metadata =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.stateOffset) fun s state =>
  if failed s = true then fatal else
  if state = IPCStorage.stateIdle then .done 0 metadata
  else .done IPCABI.inFlight 0

private def capacityValid (capacity : UInt64) : Bool :=
  if IPCABI.headerBytes ≤ capacity then
    if capacity ≤ IPCABI.maximumPacket then true else false
  else false

private def payload (descriptor pointer length : UInt64) : Action :=
  if IPCABI.maximumPayload < length then .done IPCABI.invalidArgument 0 else
  UserCopy.validateRead descriptor pointer length

private def destination (descriptor pointer capacity : UInt64) : Action :=
  if capacityValid capacity = true then UserCopy.validateWrite descriptor pointer capacity
  else .done IPCABI.invalidArgument 0

private def deadline (ticks : UInt64) : Action :=
  if ticks < IPCABI.minimumTicks then .done 22 0 else
  if IPCABI.maximumTicks < ticks then .done 22 0 else
  .bind MachineServices.time fun s now =>
  if failed s = true then fatal else
  if 0xffffffffffffffff - ticks < now then .done 22 0 else .done 0 (now + ticks)

private def queueRoom (key : UInt64) : Action :=
  .bind (Objects.endpointQueue key) fun s queue =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.queueAvailable queue key) fun s available =>
  if failed s = true then .done s 0 else
  if available = 0 then .done IPCABI.queueFull 0 else
  if available ≤ IPCABI.queueCapacity then .done 0 queue else fatal

/-- Users supply payload only. Every header field is formed from the checked
operation, caller descriptor and kernel-held reply authority. -/
private def stamp (packet kind sender request reply length applicationStatus : UInt64) : Action :=
  .bind (put (packet + IPCABI.magicOffset) IPCABI.messageMagic) fun s _ =>
  if failed s = true then fatal else
  .bind (put (packet + IPCABI.kindOffset) kind) fun s _ =>
  if failed s = true then fatal else
  .bind (put (packet + IPCABI.senderOffset) sender) fun s _ =>
  if failed s = true then fatal else
  .bind (put (packet + IPCABI.requestOffset) request) fun s _ =>
  if failed s = true then fatal else
  .bind (put (packet + IPCABI.replyOffset) reply) fun s _ =>
  if failed s = true then fatal else
  .bind (put (packet + IPCABI.lengthOffset) length) fun s _ =>
  if failed s = true then fatal else
  .bind (put (packet + IPCABI.statusOffset) applicationStatus) fun s _ =>
  if failed s = true then fatal else put (packet + IPCABI.reservedOffset) 0

private def stage (descriptor transaction pointer length kind request applicationStatus : UInt64) : Action :=
  .bind (IPCStorage.stagePayload descriptor transaction pointer length) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.packet descriptor transaction) fun s packet =>
  if failed s = true then fatal else stamp packet kind descriptor request 0 length applicationStatus

private def clear (descriptor transaction : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (IPCStorage.abort descriptor transaction) fun s _ =>
  if failed s = true then fatal else .done status value

private def finish (descriptor transaction : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (IPCStorage.finish descriptor transaction) fun s _ =>
  if failed s = true then fatal else .done status value

private def publishedSend (descriptor transaction : UInt64) : Action :=
  .bind (IPCStorage.commitWait descriptor transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.complete descriptor transaction 0 0 0 0) fun s _ =>
  if failed s = true then fatal else finish descriptor transaction 0 0

def send (descriptor handle pointer length request : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointSend) fun s key =>
  if failed s = true then .done s 0 else
  .bind (payload descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (idle descriptor) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (queueRoom key) fun s queue =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.prepare descriptor IPCStorage.sendOperation key 0 0 0) fun s transaction =>
  if failed s = true then .done s 0 else
  .bind (stage descriptor transaction pointer length IPCABI.sendKind request 0) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.queueEnqueue queue key descriptor 0) fun s _ =>
  if failed s = true then fatal else publishedSend descriptor transaction

def callBegin (descriptor handle pointer length request ticks : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s key =>
  if failed s = true then .done s 0 else
  .bind (payload descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (idle descriptor) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (queueRoom key) fun s queue =>
  if failed s = true then .done s 0 else
  .bind Objects.replyAvailable fun s available =>
  if failed s = true then .done s 0 else
  if available = 0 then .done CapabilityABI.objectFull 0 else
  .bind (deadline ticks) fun s expires =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.prepare descriptor IPCStorage.callOperation key 0 0 expires) fun s transaction =>
  if failed s = true then .done s 0 else
  .bind (stage descriptor transaction pointer length IPCABI.callKind request 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.createReply descriptor key transaction expires) fun s reply =>
  if failed s = true then fatal else
  .bind (IPCStorage.setReply descriptor transaction reply) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.queueEnqueue queue key descriptor reply) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.markReplyQueued reply) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.commitWait descriptor transaction) fun s _ =>
  if failed s = true then fatal else .done 0 transaction

private def checkedTransaction (descriptor transaction : UInt64) : Action :=
  if transaction = 0 then .done IPCABI.invalidTransaction 0 else
  .bind (IPCStorage.pending descriptor) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (word metadata IPCStorage.transactionOffset) fun s actual =>
  if failed s = true then fatal else
  if actual = transaction then .done 0 metadata else .done IPCABI.invalidTransaction 0

private def copyHead (descriptor queue key slot pointer capacity localReply : UInt64) : Action :=
  .bind (word slot IPCStorage.queueSlotSerialOffset) fun s serial =>
  if failed s = true then fatal else
  .bind (IPCStorage.queueCopyToUser queue key descriptor pointer capacity localReply) fun s bytes =>
  if failed s = true then fatal else
  .bind (IPCStorage.queuePop queue key serial) fun s _ =>
  if failed s = true then fatal else .done 0 bytes

/-- A zero value means an expired head was withdrawn. A delivered wire packet
is at least64 bytes. All User access and packet-size checks precede publication
of a receiver's one-use Reply capability. -/
private def receiveHead (descriptor transaction pointer capacity : UInt64) : Action :=
  .bind (checkedTransaction descriptor transaction) fun s metadata =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.endpointOffset) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.endpointQueue key) fun s queue =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.queuePeek queue key) fun s slot =>
  if failed s = true then .done s 0 else
  .bind (word slot IPCStorage.queueSlotBytesOffset) fun s bytes =>
  if failed s = true then fatal else
  if capacity < bytes then .done IPCABI.bufferTooSmall 0 else
  .bind (destination descriptor pointer capacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (word slot IPCStorage.queueSlotReplyOffset) fun s reply =>
  if failed s = true then fatal else
  if reply = 0 then copyHead descriptor queue key slot pointer capacity 0 else
  .bind (Objects.replyFields reply) fun s fields =>
  if failed s = true then fatal else
  .bind (word fields 80) fun s phase =>
  if failed s = true then fatal else
  if phase = 1 then
  .bind (word fields 88) fun s expires =>
  if failed s = true then fatal else
  .bind MachineServices.time fun s now =>
  if failed s = true then fatal else
  if expires ≤ now then
    .bind (Capability.retireReply reply IPCABI.timeout.toUInt64) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else
    .bind (Capability.grantReply descriptor reply) fun s localReply =>
    if failed s = true then .done s 0 else
    copyHead descriptor queue key slot pointer capacity localReply
  else fatal

private def receiveStep (_ _ : UInt32) (acc descriptor transaction pointer capacity : UInt64) : Action :=
  .bind (receiveHead descriptor transaction pointer capacity) fun s bytes =>
  if failed s = true then .done s 0 else
  if bytes = 0 then .done 0 acc else .done Status.iterationStop bytes

private def receivePacket (descriptor transaction pointer capacity : UInt64) : Action :=
  .boundedFoldU64 4 receiveStep 4 0 descriptor transaction pointer capacity fun s bytes =>
  if s = Status.iterationStop then .done 0 bytes else
  if failed s = true then .done s 0 else .done IPCABI.wouldBlock 0

private def receiveResult (descriptor transaction bytes : UInt64) : Action :=
  .bind (IPCStorage.packet descriptor transaction) fun s packet =>
  if failed s = true then fatal else
  .bind (word packet IPCABI.senderOffset) fun s sender =>
  if failed s = true then fatal else
  .bind (word packet IPCABI.replyOffset) fun s replyHandle =>
  if failed s = true then fatal else
  IPCStorage.complete descriptor transaction 0 bytes sender replyHandle

private def beginReceive (descriptor key pointer capacity expires mode : UInt64) : Action :=
  .bind (IPCStorage.prepare descriptor IPCStorage.receiveOperation key pointer capacity expires) fun s transaction =>
  if failed s = true then .done s 0 else
  .bind (receivePacket descriptor transaction pointer capacity) fun status bytes =>
  if status = 0 then
    .bind (IPCStorage.commitWait descriptor transaction) fun s _ =>
    if failed s = true then fatal else
    .bind (receiveResult descriptor transaction bytes) fun s _ =>
    if failed s = true then fatal else finish descriptor transaction 0 bytes
  else if status = IPCABI.wouldBlock then
    if mode = IPCABI.nonblocking then clear descriptor transaction status 0 else
    .bind (IPCStorage.commitWait descriptor transaction) fun s _ =>
    if failed s = true then fatal else .done blockedStatus transaction
  else if status = 255 then fatal else clear descriptor transaction status 0

def receive (descriptor handle pointer capacity ticks mode : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointReceive) fun s key =>
  if failed s = true then .done s 0 else
  .bind (destination descriptor pointer capacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (idle descriptor) fun s _ =>
  if failed s = true then .done s 0 else
  if mode = IPCABI.nonblocking then
    if ticks = 0 then beginReceive descriptor key pointer capacity 0 mode
    else .done IPCABI.invalidArgument 0
  else if mode = IPCABI.blocking then
    .bind (deadline ticks) fun s expires =>
    if failed s = true then .done s 0 else beginReceive descriptor key pointer capacity expires mode
  else .done IPCABI.invalidArgument 0

/-- Internal suspension information is a checked metadata address, never a
User-visible result. The scheduler binds its own epoch and full descriptor. -/
def waitInfo (descriptor transaction : UInt64) : Action :=
  .bind (checkedTransaction descriptor transaction) fun s metadata =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.stateOffset) fun s state =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.operationOffset) fun s operation =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.deadlineOffset) fun s expires =>
  if failed s = true then fatal else
  if state = IPCStorage.stateWaiting then
    if (if operation = IPCStorage.receiveOperation then true else if operation = IPCStorage.callOperation then true else false) = true then
      if 0 < expires then .done 0 metadata else fatal
    else fatal
  else fatal

private def completeError (descriptor transaction : UInt64) (status : UInt8) : Action :=
  .bind (IPCStorage.complete descriptor transaction status.toUInt64 0 0 0) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.take descriptor transaction) fun s metadata =>
  if failed s = true then fatal else .done 0 metadata

private def expireCall (descriptor transaction metadata : UInt64) : Action :=
  .bind (word metadata IPCStorage.replyOffset) fun s reply =>
  if failed s = true then fatal else
  if reply = 0 then fatal else
  .bind (Capability.retireReply reply IPCABI.timeout.toUInt64) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.take descriptor transaction) fun s ready =>
  if failed s = true then fatal else .done 0 ready

private def pollWaiting (descriptor transaction metadata : UInt64) : Action :=
  .bind (word metadata IPCStorage.operationOffset) fun s operation =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.deadlineOffset) fun s expires =>
  if failed s = true then fatal else
  .bind MachineServices.time fun s now =>
  if failed s = true then fatal else
  if (if expires = 0 then false else if expires ≤ now then true else false) = true then
    if operation = IPCStorage.callOperation then expireCall descriptor transaction metadata
    else if operation = IPCStorage.receiveOperation then completeError descriptor transaction IPCABI.timeout else fatal
  else if operation = IPCStorage.callOperation then .done IPCABI.wouldBlock 0
  else if operation = IPCStorage.receiveOperation then
    .bind (word metadata IPCStorage.userVAOffset) fun s pointer =>
    if failed s = true then fatal else
    .bind (word metadata IPCStorage.capacityOffset) fun s capacity =>
    if failed s = true then fatal else
    .bind (receivePacket descriptor transaction pointer capacity) fun status bytes =>
    if status = 0 then
      .bind (receiveResult descriptor transaction bytes) fun s _ =>
      if failed s = true then fatal else IPCStorage.take descriptor transaction
    else if status = IPCABI.wouldBlock then .done status 0
    else if status = 255 then fatal else completeError descriptor transaction status
  else fatal

/-- Ready completion wins subsequent deadline/cancellation events. Waiting
transactions sample hardware time here; an earlier scheduler timestamp is not
used to decide Reply publication or timeout. Idle is an ordinary no-work result. -/
def poll (descriptor : UInt64) : Action :=
  .bind (IPCStorage.pending descriptor) fun s metadata =>
  if failed s = true then fatal else
  .bind (word metadata IPCStorage.stateOffset) fun s state =>
  if failed s = true then fatal else
  if state = IPCStorage.stateIdle then .done IPCABI.wouldBlock 0 else
  .bind (word metadata IPCStorage.transactionOffset) fun s transaction =>
  if failed s = true then fatal else
  if state = IPCStorage.stateReady then .done 0 metadata else
  if state = IPCStorage.stateWaiting then pollWaiting descriptor transaction metadata else fatal

/-- Consume only after successful copy-out. A bad destination or insufficient
capacity leaves a committed Call Reply intact so the caller can retry. Receive
already copied before FIFO withdrawal, so its completion needs no second copy. -/
def completeWait (descriptor transaction : UInt64) : Action :=
  .bind (IPCStorage.take descriptor transaction) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (word metadata IPCStorage.resultStatusOffset) fun s status =>
  if failed s = true then fatal else
  if 255 < status then fatal else
  if status = 0 then
    .bind (word metadata IPCStorage.resultBytesOffset) fun s bytes =>
    if failed s = true then fatal else
    .bind (word metadata IPCStorage.operationOffset) fun s operation =>
    if failed s = true then fatal else
    if operation = IPCStorage.callOperation then
      .bind (word metadata IPCStorage.userVAOffset) fun s pointer =>
      if failed s = true then fatal else
      .bind (word metadata IPCStorage.capacityOffset) fun s capacity =>
      if failed s = true then fatal else
      if capacity < bytes then .done IPCABI.bufferTooSmall 0 else
      .bind (UserCopy.copyToUser descriptor pointer descriptor IPCStorage.packetOffset bytes) fun s _ =>
      if failed s = true then .done s 0 else finish descriptor transaction 0 bytes
    else if operation = IPCStorage.receiveOperation then finish descriptor transaction 0 bytes else fatal
  else finish descriptor transaction status.toUInt8 0

def callWait (descriptor transaction pointer capacity : UInt64) : Action :=
  .bind (checkedTransaction descriptor transaction) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (word metadata IPCStorage.operationOffset) fun s operation =>
  if failed s = true then fatal else
  if operation = IPCStorage.callOperation then
    .bind (IPCStorage.setWaitBuffer descriptor transaction pointer capacity) fun s _ =>
    if failed s = true then .done s 0 else
    .bind (poll descriptor) fun status _ =>
    if status = 0 then completeWait descriptor transaction else
    if status = IPCABI.wouldBlock then .done blockedStatus transaction else fatal
  else .done IPCABI.invalidTransaction 0

private def replyCaller (key server : UInt64) : Action :=
  .bind (Objects.replyFields key) fun s fields =>
  if failed s = true then .done s 0 else
  .bind (word fields 72) fun s actualServer =>
  if failed s = true then fatal else
  .bind (word fields 80) fun s phase =>
  if failed s = true then fatal else
  if actualServer = server then if phase = 2 then .done 0 fields else fatal
  else .done CapabilityABI.denied 0

private def commitReply (server serverTransaction key fields caller transaction bytes : UInt64) : Action :=
  .bind (word fields 88) fun s expires =>
  if failed s = true then fatal else
  .bind MachineServices.time fun s now =>
  if failed s = true then fatal else
  if expires ≤ now then
    .bind (Capability.retireReply key IPCABI.timeout.toUInt64) fun s _ =>
    if failed s = true then fatal else clear server serverTransaction CapabilityABI.invalidHandle 0
  else
    .bind (IPCStorage.complete caller transaction 0 bytes server 0) fun s _ =>
    if failed s = true then fatal else
    .bind (Capability.retireReply key 0) fun s _ =>
    if failed s = true then fatal else clear server serverTransaction 0 0

private def stageReply (server key fields pointer length applicationStatus : UInt64) : Action :=
  .bind (word fields 40) fun s caller =>
  if failed s = true then fatal else
  .bind (word fields 56) fun s endpoint =>
  if failed s = true then fatal else
  .bind (word fields 64) fun s transaction =>
  if failed s = true then fatal else
  .bind (IPCStorage.packet caller transaction) fun s callerPacket =>
  if failed s = true then fatal else
  .bind (word callerPacket IPCABI.requestOffset) fun s request =>
  if failed s = true then fatal else
  .bind (IPCStorage.prepare server IPCStorage.sendOperation endpoint 0 0 0) fun s serverTransaction =>
  if failed s = true then .done s 0 else
  .bind (stage server serverTransaction pointer length IPCABI.replyKind request applicationStatus) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.packet server serverTransaction) fun s serverPacket =>
  if failed s = true then fatal else
  .bind (IPCStorage.copyBytes serverPacket callerPacket (IPCABI.headerBytes + length)) fun s _ =>
  if failed s = true then fatal else
  commitReply server serverTransaction key fields caller transaction (IPCABI.headerBytes + length)

def reply (descriptor handle pointer length applicationStatus : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.replyType CapabilityABI.replyRight) fun s key =>
  if failed s = true then .done s 0 else
  .bind (replyCaller key descriptor) fun s fields =>
  if failed s = true then .done s 0 else
  if 255 < applicationStatus then .done IPCABI.invalidArgument 0 else
  .bind (payload descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (idle descriptor) fun s _ =>
  if failed s = true then .done s 0 else stageReply descriptor key fields pointer length applicationStatus

def cancel (descriptor transaction : UInt64) : Action :=
  .bind (checkedTransaction descriptor transaction) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (word metadata IPCStorage.operationOffset) fun s operation =>
  if failed s = true then fatal else
  if operation = IPCStorage.callOperation then
  .bind (word metadata IPCStorage.stateOffset) fun s state =>
  if failed s = true then fatal else
  if state = IPCStorage.stateReady then .done IPCABI.alreadyCompleted 0 else
  if state = IPCStorage.stateWaiting then
    .bind (word metadata IPCStorage.replyOffset) fun s key =>
    if failed s = true then fatal else
    .bind (Capability.retireReply key IPCABI.canceled.toUInt64) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else fatal
  else .done IPCABI.invalidTransaction 0

private def detachEndpointStep (i _ : UInt32) (acc base descriptor _ _ : UInt64) : Action :=
  let object := Objects.row base i.toUInt64
  .bind (word object 0) fun s state =>
  if failed s = true then fatal else
  if (if state = Objects.live then true else if state = Objects.revoking then true else false) = true then
    .bind (word object 16) fun s kind =>
    if failed s = true then fatal else
    if kind = CapabilityABI.endpointType then
      .bind (word object 8) fun s generation =>
      if failed s = true then fatal else
      let key := generation * Objects.capacity + i.toUInt64
      .bind (word object 40) fun s owner =>
      if failed s = true then fatal else
      .bind (if owner = descriptor then Objects.invalidateEndpointWaits key IPCABI.peerDied.toUInt64 else .done 0 0) fun s _ =>
      if failed s = true then fatal else
      .bind (Objects.endpointQueue key) fun s queue =>
      if failed s = true then fatal else
      .bind (IPCStorage.queueCancelSender queue key descriptor) fun s _ =>
      if failed s = true then fatal else .done 0 (acc + 1)
    else .done 0 acc
  else .done 0 acc

/-- Withdrawal precedes capability detach and inactive address-space teardown.
The lower capability detach clears initialized storage only after all enrolled
descriptor/object scans finish. Ready replies are preserved until caller death. -/
def detach (descriptor : UInt64) : Action :=
  .bind (Capability.cancelDescriptorReplies descriptor IPCABI.peerDied.toUInt64) fun s _ =>
  if failed s = true then fatal else
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 detachEndpointStep 16 0 base descriptor 0 0 fun s _ =>
  if failed s = true then fatal else .done 0 0

def dispatch (descriptor number a b c d e : UInt64) : Action :=
  if number = IPCABI.send then
    if e = 0 then send descriptor a b c d else .done IPCABI.invalidArgument 0
  else if number = IPCABI.receive then receive descriptor a b c d e
  else if number = IPCABI.callBegin then callBegin descriptor a b c d e
  else if number = IPCABI.callWait then
    if d ||| e = 0 then callWait descriptor a b c else .done IPCABI.invalidArgument 0
  else if number = IPCABI.reply then
    if e = 0 then reply descriptor a b c d else .done IPCABI.invalidArgument 0
  else if number = IPCABI.cancel then
    if b ||| c ||| d ||| e = 0 then cancel descriptor a else .done IPCABI.invalidArgument 0
  else .done Lemma.User.ABI.unsupported 0

end Lemma.Kernel.IPC
