import Lemma.Kernel.Memory.AddressSpace
import Lemma.Kernel.Memory.UserCopy
import Lemma.User.IPCABI

/-! Bounded copied IPC storage. Descriptor and queue addresses follow genuine
owner-1/purpose-1 generation resolution. This layer has no object, capability,
task or scheduler dependency and never retains a physical User alias. -/
namespace Lemma.Kernel.IPCStorage
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def magic : UInt64 := 0x31435049414d454c
def queueMagic : UInt64 := 0x31455551414d454c
def metadataOffset : UInt64 := 3648
def metadataBytes : UInt64 := 128
def packetOffset : UInt64 := 3776
def payloadOffset : UInt64 := 3840
def maximumPacket : UInt64 := 256
def maximumPayload : UInt64 := 192
def maxTransaction : UInt64 := 0x0fffffffffffffff
def stateIdle : UInt64 := 0
def stateReserved : UInt64 := 1
def stateWaiting : UInt64 := 2
def stateReady : UInt64 := 3
def sendOperation : UInt64 := 1
def receiveOperation : UInt64 := 2
def callOperation : UInt64 := 3
def stateOffset : UInt64 := 24
def operationOffset : UInt64 := 32
def transactionOffset : UInt64 := 40
def nextTransactionOffset : UInt64 := 48
def endpointOffset : UInt64 := 56
def replyOffset : UInt64 := 64
def userVAOffset : UInt64 := 72
def capacityOffset : UInt64 := 80
def deadlineOffset : UInt64 := 88
def resultStatusOffset : UInt64 := 96
def resultBytesOffset : UInt64 := 104
def resultSenderOffset : UInt64 := 112
def resultReplyOffset : UInt64 := 120
def queueHeaderBytes : UInt64 := 128
def queueStride : UInt64 := 320
def queueSlots : UInt64 := 4
def queueSlotStateOffset : UInt64 := 0
def queueSlotSerialOffset : UInt64 := 8
def queueSlotSenderOffset : UInt64 := 16
def queueSlotTransactionOffset : UInt64 := 24
def queueSlotReplyOffset : UInt64 := 32
def queueSlotBytesOffset : UInt64 := 40
def queueSlotPacketOffset : UInt64 := 64

def failed (status : UInt8) : Bool := if status = 0 then false else true
def fatal : Action := .done 255 0
def get (address : UInt64) : Action :=
  .bind (Access.read64 address) fun s value => if failed s = true then fatal else .done 0 value
def put (address value : UInt64) : Action :=
  .bind (Access.write64 address value) fun s _ => if failed s = true then fatal else .done 0 value
private def equalWord (address expected : UInt64) : Action :=
  .bind (get address) fun s value =>
  if failed s = true then fatal else if value = expected then .done 0 value else fatal
private def zeroStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (get (address + i.toUInt64 * 8)) fun s value =>
  if failed s = true then fatal else .done 0 (if value = 0 then acc else 0)
private def clearStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (put (address + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
private def copyStep (i _ : UInt32) (acc source destination _ _ : UInt64) : Action :=
  .bind (Access.read8 (source + i.toUInt64)) fun s byte =>
  if failed s = true then fatal else
  .bind (Access.write8 (destination + i.toUInt64) byte) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
private def copyWordStep (i _ : UInt32) (acc source destination _ _ : UInt64) : Action :=
  .bind (Access.read64 (source + i.toUInt64 * 8)) fun s word =>
  if failed s = true then fatal else
  .bind (Access.write64 (destination + i.toUInt64 * 8) word) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 8)
def copyBytes (source destination length : UInt64) : Action :=
  if maximumPacket < length then fatal else
  if (source ||| destination ||| length) &&& 7 = 0 then
    .boundedFoldU64 32 copyWordStep (length / 8).toUInt32 0 source destination 0 0 fun s copied =>
    if failed s = true then fatal else if copied = length then .done 0 copied else fatal
  else
  .boundedFoldU64 256 copyStep length.toUInt32 0 source destination 0 0 fun s copied =>
  if failed s = true then fatal else if copied = length then .done 0 copied else fatal

def «initialize» (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done 80 0 else
  let address := base + metadataOffset
  .boundedFoldU64 48 zeroStep 48 1 address 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then
  .bind (put (address + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 16) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + nextTransactionOffset) 1) fun s _ =>
  if failed s = true then fatal else put address magic
  else fatal

/-- Kernel-only borrowed base. The caller has checked this descriptor in the
same nonpreemptible Action; every IPC metadata field remains freshly read.
A zero legacy tail is not an IPC row and cannot silently acquire authority. -/
def pendingAt (descriptor base : UInt64) : Action :=
  let address := base + metadataOffset
  .bind (equalWord address magic) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (address + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (address + 16) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state ≤ stateReady then
  .bind (get (address + nextTransactionOffset)) fun s next =>
  if failed s = true then fatal else
  if 0 < next then if next ≤ maxTransaction + 1 then
  .bind (get (address + transactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  if state = stateIdle then
    if transaction = 0 then .done 0 address else fatal
  else
  if 0 < transaction then if transaction ≤ maxTransaction then
  .bind (get (address + operationOffset)) fun s operation =>
  if failed s = true then fatal else
  if 0 < operation then if operation ≤ callOperation then
  .bind (get (address + endpointOffset)) fun s endpoint =>
  if failed s = true then fatal else
  if 0 < endpoint then
    if state = stateReserved then
      if transaction = next then .done 0 address else fatal
    else if transaction + 1 = next then .done 0 address else fatal
  else fatal else fatal else fatal else fatal else fatal
  else fatal else fatal
  else fatal

/-- Public entry always establishes a fresh descriptor base. -/
def pending (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done 80 0 else pendingAt descriptor base

private def transactionRow (descriptor transaction : UInt64) : Action :=
  if transaction = 0 then .done IPCABI.invalidTransaction 0 else
  .bind (pending descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + transactionOffset)) fun s actual =>
  if failed s = true then fatal else
  if actual = transaction then .done 0 address else .done IPCABI.invalidTransaction 0

def packet (descriptor transaction : UInt64) : Action :=
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else .done 0 (address + metadataBytes)

def prepare (descriptor operation endpoint userVA capacity deadline : UInt64) : Action :=
  if operation = 0 then .done IPCABI.invalidArgument 0 else
  if callOperation < operation then .done IPCABI.invalidArgument 0 else
  if endpoint = 0 then .done 80 0 else
  .bind (pending descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateIdle then
  .bind (get (address + nextTransactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  if transaction ≤ maxTransaction then
  .bind (if operation = receiveOperation then
    if capacity < IPCABI.headerBytes then .done IPCABI.invalidArgument 0 else
    if maximumPacket < capacity then .done IPCABI.invalidArgument 0 else
    UserCopy.validateWrite descriptor userVA capacity
    else if capacity = 0 then if userVA = 0 then .done 0 0 else .done IPCABI.invalidArgument 0
    else .done IPCABI.invalidArgument 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put (address + operationOffset) operation) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + transactionOffset) transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + endpointOffset) endpoint) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + userVAOffset) userVA) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + capacityOffset) capacity) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + deadlineOffset) deadline) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + stateOffset) stateReserved) fun s _ =>
  if failed s = true then fatal else .done 0 transaction
  else .done 91 0
  else .done IPCABI.inFlight 0

def stagePayload (descriptor transaction sourceVA length : UInt64) : Action :=
  if maximumPayload < length then .done IPCABI.invalidArgument 0 else
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then
    UserCopy.copyFromUser descriptor sourceVA descriptor payloadOffset length
  else .done IPCABI.inFlight 0

def setReply (descriptor transaction replyKey : UInt64) : Action :=
  if replyKey = 0 then .done 80 0 else
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (get (address + operationOffset)) fun s operation =>
  if failed s = true then fatal else
  .bind (get (address + replyOffset)) fun s previous =>
  if failed s = true then fatal else
  if state = stateReserved then if operation = callOperation then
    if previous = 0 then put (address + replyOffset) replyKey else fatal
  else fatal else .done IPCABI.inFlight 0

def setWaitBuffer (descriptor transaction userVA capacity : UInt64) : Action :=
  if capacity < IPCABI.headerBytes then .done IPCABI.invalidArgument 0 else
  if maximumPacket < capacity then .done IPCABI.invalidArgument 0 else
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + operationOffset)) fun s operation =>
  if failed s = true then fatal else
  if operation = callOperation then
  .bind (UserCopy.validateWrite descriptor userVA capacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put (address + userVAOffset) userVA) fun s _ =>
  if failed s = true then fatal else put (address + capacityOffset) capacity
  else .done IPCABI.invalidTransaction 0

def commitWait (descriptor transaction : UInt64) : Action :=
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then
  .bind (put (address + nextTransactionOffset) (transaction + 1)) fun s _ =>
  if failed s = true then fatal else put (address + stateOffset) stateWaiting
  else .done IPCABI.inFlight 0

private def resetStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  let index := i.toUInt64
  if index < 3 then .done 0 acc else
  if index = 6 then .done 0 acc else
  .bind (put (address + index * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
private def reset (address : UInt64) : Action :=
  .bind (put (address + stateOffset) stateIdle) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 48 resetStep 48 0 address 0 0 0 fun s _ =>
  if failed s = true then fatal else .done 0 0

def abort (descriptor transaction : UInt64) : Action :=
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then reset address else .done IPCABI.inFlight 0

def complete (descriptor transaction status bytes sender replyHandle : UInt64) : Action :=
  if 255 < status then fatal else
  if maximumPacket < bytes then fatal else
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReady then .done IPCABI.alreadyCompleted 0 else
  if state = stateWaiting then
  .bind (put (address + resultStatusOffset) status) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + resultBytesOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + resultSenderOffset) sender) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + resultReplyOffset) replyHandle) fun s _ =>
  if failed s = true then fatal else put (address + stateOffset) stateReady
  else .done IPCABI.inFlight 0

def take (descriptor transaction : UInt64) : Action :=
  .bind (transactionRow descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReady then .done 0 address else .done IPCABI.wouldBlock 0

def finish (descriptor transaction : UInt64) : Action :=
  .bind (take descriptor transaction) fun s address =>
  if failed s = true then .done s 0 else reset address

private def invalidate (descriptor key field status : UInt64) : Action :=
  .bind (pending descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateWaiting then
  .bind (get (address + field)) fun s actual =>
  if failed s = true then fatal else
  if actual = key then
  .bind (get (address + transactionOffset)) fun s transaction =>
  if failed s = true then fatal else complete descriptor transaction status 0 0 0
  else .done 0 0
  else if state = stateReserved then fatal else .done 0 0
def invalidateEndpoint (descriptor key status : UInt64) : Action :=
  invalidate descriptor key endpointOffset status
def invalidateReply (descriptor key status : UInt64) : Action :=
  invalidate descriptor key replyOffset status
def waitsOnReceive (descriptor endpoint : UInt64) : Action :=
  .bind (pending descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (get (address + operationOffset)) fun s operation =>
  if failed s = true then fatal else
  .bind (get (address + endpointOffset)) fun s key =>
  if failed s = true then fatal else
  .done 0 (if state = stateWaiting then if operation = receiveOperation then
    if key = endpoint then 1 else 0 else 0 else 0)
def detach (descriptor : UInt64) : Action :=
  .bind (pending descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 48 clearStep 48 0 address 0 0 0 fun s cleared =>
  if failed s = true then fatal else if cleared = 48 then .done 0 0 else fatal

def queueSlot (base index : UInt64) : UInt64 := base + queueHeaderBytes + index * queueStride
private def queueFrame (handle : UInt64) : Action :=
  .bind (Frames.resolvePurpose 1 handle 1) fun s base =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount 1 handle) fun s pins =>
  if failed s = true then fatal else if pins = 0 then .done 0 base else fatal

private def wire (address sender replyKey : UInt64) : Action :=
  .bind (equalWord address IPCABI.messageMagic) fun s _ =>
  if failed s = true then fatal else
  .bind (get (address + IPCABI.kindOffset)) fun s kind =>
  if failed s = true then fatal else
  if (if replyKey = 0 then if kind = IPCABI.sendKind then true else false
      else if kind = IPCABI.callKind then true else false) = true then
  .bind (equalWord (address + IPCABI.senderOffset) sender) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (address + IPCABI.replyOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (get (address + IPCABI.lengthOffset)) fun s length =>
  if failed s = true then fatal else
  if length ≤ maximumPayload then
  .bind (equalWord (address + IPCABI.statusOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (address + IPCABI.reservedOffset) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (IPCABI.headerBytes + length)
  else fatal else fatal

private def uniqueSerialStep (i _ : UInt32) (acc base address serial _ : UInt64) : Action :=
  let other := queueSlot base i.toUInt64
  if other = address then .done 0 acc else
  .bind (get other) fun s state =>
  if failed s = true then fatal else
  if state = 1 then
  .bind (get (other + queueSlotSerialOffset)) fun s actual =>
  if failed s = true then fatal else if actual = serial then fatal else .done 0 acc
  else .done 0 acc
private def queueCheckStep (i _ : UInt32) (acc base next _ _ : UInt64) : Action :=
  let address := queueSlot base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if state = 0 then
  .boundedFoldU64 8 zeroStep 8 1 address 0 0 0 fun s allZero =>
  if failed s = true then fatal else if allZero = 1 then .done 0 acc else fatal
  else if state = 1 then
  .bind (get (address + queueSlotSerialOffset)) fun s serial =>
  if failed s = true then fatal else
  if 0 < serial then if serial < next then
  .boundedFoldU64 4 uniqueSerialStep 4 0 base address serial 0 fun s _ =>
  if failed s = true then fatal else
  .bind (get (address + queueSlotSenderOffset)) fun s sender =>
  if failed s = true then fatal else
  if 0 < sender then
  .bind (get (address + queueSlotTransactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  if 0 < transaction then if transaction ≤ maxTransaction then
  .bind (get (address + queueSlotReplyOffset)) fun s replyKey =>
  if failed s = true then fatal else
  .bind (wire (address + queueSlotPacketOffset) sender replyKey) fun s bytes =>
  if failed s = true then fatal else
  .bind (equalWord (address + queueSlotBytesOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (address + 48) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (address + 56) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else fatal else fatal else fatal else fatal else fatal else fatal

def queue (handle key : UInt64) : Action :=
  if key = 0 then fatal else
  .bind (queueFrame handle) fun s base =>
  if failed s = true then fatal else
  .bind (equalWord base queueMagic) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (base + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (base + 16) key) fun s _ =>
  if failed s = true then fatal else
  .bind (get (base + 24)) fun s count =>
  if failed s = true then fatal else
  if count ≤ queueSlots then
  .bind (get (base + 32)) fun s next =>
  if failed s = true then fatal else
  if 0 < next then if next ≤ maxTransaction + 1 then
  .boundedFoldU64 11 zeroStep 11 1 (base + 40) 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then
  .boundedFoldU64 4 queueCheckStep 4 0 base next 0 0 fun s actual =>
  if failed s = true then fatal else if actual = count then .done 0 base else fatal
  else fatal else fatal else fatal else fatal

def queueInitialize (handle key : UInt64) : Action :=
  if key = 0 then fatal else
  .bind (queueFrame handle) fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 176 zeroStep 176 1 base 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then
  .bind (put (base + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 16) key) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 32) 1) fun s _ =>
  if failed s = true then fatal else put base queueMagic
  else fatal

def queueAvailable (handle key : UInt64) : Action :=
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 24)) fun s count =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s next =>
  if failed s = true then fatal else
  if count = queueSlots then .done 0 0 else
  if next ≤ maxTransaction then .done 0 (queueSlots - count) else .done 91 0

private def peekStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let address := queueSlot base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if state = 1 then
    if acc = 0 then .done 0 address else
    .bind (get (address + queueSlotSerialOffset)) fun s serial =>
    if failed s = true then fatal else
    .bind (get (acc + queueSlotSerialOffset)) fun s previous =>
    if failed s = true then fatal else .done 0 (if serial < previous then address else acc)
  else .done 0 acc
def queuePeek (handle key : UInt64) : Action :=
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 4 peekStep 4 0 base 0 0 0 fun s address =>
  if failed s = true then fatal else
  if address = 0 then .done IPCABI.wouldBlock 0 else .done 0 address

private def freeSlotStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let address := queueSlot base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if state = 0 then .done Status.iterationStop address else .done 0 acc

def queueEnqueue (handle key descriptor replyKey : UInt64) : Action :=
  .bind (queueAvailable handle key) fun s available =>
  if failed s = true then .done s 0 else
  if available = 0 then .done IPCABI.queueFull 0 else
  .bind (pending descriptor) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (equalWord (metadata + endpointOffset) key) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (metadata + replyOffset) replyKey) fun s _ =>
  if failed s = true then fatal else
  .bind (get (metadata + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then
  .bind (get (metadata + transactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  .bind (wire (metadata + metadataBytes) descriptor replyKey) fun s bytes =>
  if failed s = true then fatal else
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 24)) fun s count =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s serial =>
  if failed s = true then fatal else
  .boundedFoldU64 4 freeSlotStep 4 0 base 0 0 0 fun s address =>
  if s = Status.iterationStop then
  .bind (put address 2) fun s _ =>
  if failed s = true then fatal else
  .bind (copyBytes (metadata + metadataBytes) (address + queueSlotPacketOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotSerialOffset) serial) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotSenderOffset) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotTransactionOffset) transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotReplyOffset) replyKey) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotBytesOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 32) (serial + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 24) (count + 1)) fun s _ =>
  if failed s = true then fatal else put address 1
  else fatal
  else .done IPCABI.inFlight 0

def queueCopyToUser (handle key descriptor userVA capacity localReplyHandle : UInt64) : Action :=
  if capacity < IPCABI.headerBytes then .done IPCABI.invalidArgument 0 else
  if maximumPacket < capacity then .done IPCABI.invalidArgument 0 else
  .bind (AddressSpace.base descriptor) fun s receiverBase =>
  if failed s = true then .done 80 0 else
  .bind (UserCopy.validateWrite descriptor userVA capacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (queuePeek handle key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + queueSlotBytesOffset)) fun s bytes =>
  if failed s = true then fatal else
  if capacity < bytes then .done IPCABI.bufferTooSmall 0 else
  .bind (get (address + queueSlotReplyOffset)) fun s replyKey =>
  if failed s = true then fatal else
  if (if replyKey = 0 then if localReplyHandle = 0 then true else false
      else if 0 < localReplyHandle then true else false) = true then
  .bind (copyBytes (address + queueSlotPacketOffset) (receiverBase + packetOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (put (receiverBase + packetOffset + IPCABI.replyOffset) localReplyHandle) fun s _ =>
  if failed s = true then fatal else
  UserCopy.copyToUser descriptor userVA descriptor packetOffset bytes
  else fatal

private def withdrawSlot (base address : UInt64) : Action :=
  .bind (get (base + 24)) fun s count =>
  if failed s = true then fatal else
  if 0 < count then
  .bind (put address 2) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 40 clearStep 40 0 address 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 40 then put (base + 24) (count - 1) else fatal
  else fatal
def queuePop (handle key serial : UInt64) : Action :=
  .bind (queuePeek handle key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + queueSlotSerialOffset)) fun s actual =>
  if failed s = true then fatal else
  if actual = serial then
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else withdrawSlot base address
  else .done IPCABI.invalidTransaction 0

private def cancelQueueStep (i _ : UInt32) (acc base sender replyKey transaction : UInt64) : Action :=
  let address := queueSlot base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if state = 1 then
  .bind (get (address + queueSlotSenderOffset)) fun s actualSender =>
  if failed s = true then fatal else
  .bind (get (address + queueSlotReplyOffset)) fun s actualReply =>
  if failed s = true then fatal else
  .bind (get (address + queueSlotTransactionOffset)) fun s actualTransaction =>
  if failed s = true then fatal else
  if (if sender = 0 then if actualReply = replyKey then
        if actualTransaction = transaction then true else false else false
      else if actualSender = sender then true else false) = true then
  .bind (withdrawSlot base address) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else .done 0 acc
  else .done 0 acc
def queueCancelSender (handle key descriptor : UInt64) : Action :=
  if descriptor = 0 then fatal else
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 4 cancelQueueStep 4 0 base descriptor 0 0 fun s count =>
  if failed s = true then fatal else .done 0 count
def queueCancelReply (handle key replyKey transaction : UInt64) : Action :=
  if replyKey = 0 then fatal else
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 4 cancelQueueStep 4 0 base 0 replyKey transaction fun s count =>
  if failed s = true then fatal else .done 0 count

/-! Borrowed IPC transaction helpers. A caller must obtain `base` from a fresh
successful `AddressSpace.base` in the same single-hart nonpreemptible Action.
Only IPC tail and disjoint object/queue writes may intervene; descriptor
identity/root/grants/registry, frame ownership/generation/pins and page tables
cannot change. These helpers
never retain an alias or cross a suspension boundary. Every mutable IPC field
is freshly validated by pendingAt, and ordinary UserCopy validates both pages
and the scratch handle afresh before any payload byte changes. Public legacy
entries above retain their complete descriptor validation and error order. -/

private def transactionRowAt (descriptor base transaction : UInt64) : Action :=
  if transaction = 0 then .done IPCABI.invalidTransaction 0 else
  .bind (pendingAt descriptor base) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + transactionOffset)) fun s actual =>
  if failed s = true then fatal else
  if actual = transaction then .done 0 address else .done IPCABI.invalidTransaction 0


def packetAt (descriptor base transaction : UInt64) : Action :=
  .bind (transactionRowAt descriptor base transaction) fun s address =>
  if failed s = true then .done s 0 else .done 0 (address + metadataBytes)

def prepareAt (descriptor base operation endpoint userVA capacity deadline : UInt64) : Action :=
  if operation = 0 then .done IPCABI.invalidArgument 0 else
  if callOperation < operation then .done IPCABI.invalidArgument 0 else
  if endpoint = 0 then .done 80 0 else
  .bind (pendingAt descriptor base) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateIdle then
  .bind (get (address + nextTransactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  if transaction ≤ maxTransaction then
  .bind (if operation = receiveOperation then
    if capacity < IPCABI.headerBytes then .done IPCABI.invalidArgument 0 else
    if maximumPacket < capacity then .done IPCABI.invalidArgument 0 else
    UserCopy.validateWrite descriptor userVA capacity
    else if capacity = 0 then if userVA = 0 then .done 0 0 else .done IPCABI.invalidArgument 0
    else .done IPCABI.invalidArgument 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put (address + operationOffset) operation) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + transactionOffset) transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + endpointOffset) endpoint) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + userVAOffset) userVA) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + capacityOffset) capacity) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + deadlineOffset) deadline) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + stateOffset) stateReserved) fun s _ =>
  if failed s = true then fatal else .done 0 transaction
  else .done 91 0
  else .done IPCABI.inFlight 0

def stagePayloadAt (descriptor base transaction sourceVA length : UInt64) : Action :=
  if maximumPayload < length then .done IPCABI.invalidArgument 0 else
  .bind (transactionRowAt descriptor base transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then
    UserCopy.copyFromUser descriptor sourceVA descriptor payloadOffset length
  else .done IPCABI.inFlight 0

def setReplyAt (descriptor base transaction replyKey : UInt64) : Action :=
  if replyKey = 0 then .done 80 0 else
  .bind (transactionRowAt descriptor base transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (get (address + operationOffset)) fun s operation =>
  if failed s = true then fatal else
  .bind (get (address + replyOffset)) fun s previous =>
  if failed s = true then fatal else
  if state = stateReserved then if operation = callOperation then
    if previous = 0 then put (address + replyOffset) replyKey else fatal
  else fatal else .done IPCABI.inFlight 0

def commitWaitAt (descriptor base transaction : UInt64) : Action :=
  .bind (transactionRowAt descriptor base transaction) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then
  .bind (put (address + nextTransactionOffset) (transaction + 1)) fun s _ =>
  if failed s = true then fatal else put (address + stateOffset) stateWaiting
  else .done IPCABI.inFlight 0

def queueEnqueueAt (handle key descriptor descriptorBase replyKey : UInt64) : Action :=
  .bind (queueAvailable handle key) fun s available =>
  if failed s = true then .done s 0 else
  if available = 0 then .done IPCABI.queueFull 0 else
  .bind (pendingAt descriptor descriptorBase) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (equalWord (metadata + endpointOffset) key) fun s _ =>
  if failed s = true then fatal else
  .bind (equalWord (metadata + replyOffset) replyKey) fun s _ =>
  if failed s = true then fatal else
  .bind (get (metadata + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = stateReserved then
  .bind (get (metadata + transactionOffset)) fun s transaction =>
  if failed s = true then fatal else
  .bind (wire (metadata + metadataBytes) descriptor replyKey) fun s bytes =>
  if failed s = true then fatal else
  .bind (queue handle key) fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 24)) fun s count =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s serial =>
  if failed s = true then fatal else
  .boundedFoldU64 4 freeSlotStep 4 0 base 0 0 0 fun s address =>
  if s = Status.iterationStop then
  .bind (put address 2) fun s _ =>
  if failed s = true then fatal else
  .bind (copyBytes (metadata + metadataBytes) (address + queueSlotPacketOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotSerialOffset) serial) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotSenderOffset) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotTransactionOffset) transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotReplyOffset) replyKey) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + queueSlotBytesOffset) bytes) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 32) (serial + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 24) (count + 1)) fun s _ =>
  if failed s = true then fatal else put address 1
  else fatal
  else .done IPCABI.inFlight 0

end Lemma.Kernel.IPCStorage
