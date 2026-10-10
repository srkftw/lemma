import Lemma.Kernel.Objects

/-! Managed caller-local capability tables in the checked AS descriptor tail.
Sixteen entries, eight enrolled tasks and sixteen objects bound every scan.
Duplication reserves a destination before changing any object accounting.
Object-wide revocation removes all aliases; closing only removes one entry. -/
namespace Lemma.Kernel.Capability
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def magic : UInt64 := 0x31504143414d454c
def headerOffset : UInt64 := 2560
def entriesOffset : UInt64 := 2624
def capacity : UInt64 := 16
def stride : UInt64 := 64
def active : UInt64 := 1
def constructing : UInt64 := 2
def entryFree : UInt64 := 0
def entryReserved : UInt64 := 1
def entryLive : UInt64 := 2
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done CapabilityABI.fatal 0
def entry (base slot : UInt64) : UInt64 := base + entriesOffset + slot * stride
def handleSlot (handle : UInt64) : UInt64 := handle % capacity
def handleSerial (handle : UInt64) : UInt64 := handle / capacity
def handleValid (handle : UInt64) : Bool :=
  if 0 < handleSerial handle then if handleSerial handle ≤ Objects.maxSerial then true else false else false

private def zeroHeaderStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (Objects.get (base + headerOffset + i.toUInt64 * 8)) fun s value =>
  if failed s = true then fatal else .done 0 (if value = 0 then acc else 0)

/-- Does not require Objects.init for a genuinely zero legacy header. A partial
or constructing managed header cannot be interpreted as an unmanaged caller. -/
private def header (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (Objects.get (base + headerOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = magic then
  .bind (Objects.get (base + headerOffset + 8)) fun s version =>
  if failed s = true then fatal else
  if version = 1 then
  .bind (Objects.get (base + headerOffset + 16)) fun s self =>
  if failed s = true then fatal else
  if self = descriptor then
  .bind (Objects.get (base + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if (if state = active then true else if state = constructing then true else false) = true then
  .bind (Objects.get (base + headerOffset + 32)) fun s count =>
  if failed s = true then fatal else
  if count = capacity then
  .bind (Objects.get (base + headerOffset + 40)) fun s used =>
  if failed s = true then fatal else
  if used ≤ capacity then
  .bind (Objects.get (base + headerOffset + 48)) fun s registry =>
  if failed s = true then fatal else
  if registry < Objects.registryCapacity then
  .bind (Objects.registryDescriptor registry) fun s registered =>
  if failed s = true then fatal else
  if registered = descriptor then
  .bind (Objects.get (base + headerOffset + 56)) fun s reserved =>
  if failed s = true then fatal else
  if reserved = 0 then .done 0 base else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else if tag = 0 then .done CapabilityABI.invalidHandle 0 else fatal

def managed (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (base + headerOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = 0 then
  .boundedFoldU64 8 zeroHeaderStep 8 1 base 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then .done 0 0 else fatal
  else
  .bind (header descriptor) fun s checked =>
  if failed s = true then fatal else
  .bind (Objects.get (checked + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if state = active then .done 0 1 else fatal

def requireActive (descriptor : UInt64) : Action :=
  .bind (header descriptor) fun s base =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (base + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if state = active then .done 0 base else .done CapabilityABI.invalidHandle 0

def attach (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .boundedFoldU64 8 zeroHeaderStep 8 1 base 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then
  .bind (Objects.register descriptor) fun s registry =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.initialize descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset + 16) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset + 24) constructing) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset + 32) capacity) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset + 48) registry) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset) magic) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor
  else .done CapabilityABI.invalidArgument 0

def activate (descriptor : UInt64) : Action :=
  .bind (header descriptor) fun s base =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (base + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if state = constructing then
    .bind (Objects.put (base + headerOffset + 24) active) fun s _ =>
    if failed s = true then fatal else .done 0 descriptor
  else .done CapabilityABI.invalidArgument 0

private def countEntryStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (Objects.get (entry base i.toUInt64)) fun s state =>
  if failed s = true then fatal else
  if state = entryFree then .done 0 acc else
  if state = entryLive then .done 0 (acc + 1) else fatal

def entryCount (descriptor : UInt64) : Action :=
  .bind (header descriptor) fun s base =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 16 countEntryStep 16 0 base 0 0 0 fun s actual =>
  if failed s = true then fatal else
  .bind (Objects.get (base + headerOffset + 40)) fun s stored =>
  if failed s = true then fatal else
  if actual = stored then .done 0 actual else fatal

private def freeEntryStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (Objects.get (entry base i.toUInt64)) fun s state =>
  if failed s = true then fatal else
  if state = entryFree then .done Status.iterationStop i.toUInt64 else
  if state = entryLive then .done 0 acc else fatal

private def freeSlot (descriptor : UInt64) : Action :=
  .bind (header descriptor) fun s base =>
  if failed s = true then .done s 0 else
  .bind (entryCount descriptor) fun s count =>
  if failed s = true then fatal else
  if count < capacity then
  .boundedFoldU64 16 freeEntryStep 16 capacity base 0 0 0 fun s slot =>
  if s = Status.iterationStop then .done 0 slot else fatal
  else .done CapabilityABI.tableFull 0

private def lookupEntry (descriptor handle : UInt64) : Action :=
  if handleValid handle = false then .done CapabilityABI.invalidHandle 0 else
  .bind (requireActive descriptor) fun s base =>
  if failed s = true then .done s 0 else
  let address := entry base (handleSlot handle)
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = entryLive then
  .bind (Objects.get (address + 8)) fun s serial =>
  if failed s = true then fatal else
  if serial = handleSerial handle then
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 24)) fun s rights =>
  if failed s = true then fatal else
  if CapabilityABI.rightsValid kind rights = true then .done 0 address else fatal
  else .done CapabilityABI.invalidHandle 0
  else if state = entryFree then .done CapabilityABI.invalidHandle 0 else fatal

/-- Returns an internal checked object key, never through the User syscall
result. Object typing and requested rights are checked after local generation. -/
def lookup (descriptor handle kind rights : UInt64) : Action :=
  if CapabilityABI.typeValid kind = false then .done CapabilityABI.invalidArgument 0 else
  if CapabilityABI.rightsSubset rights CapabilityABI.knownRights = false then
    .done CapabilityABI.invalidArgument 0 else
  .bind (lookupEntry descriptor handle) fun s address =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s actualKind =>
  if failed s = true then fatal else
  if actualKind = kind then
  .bind (Objects.get (address + 24)) fun s available =>
  if failed s = true then fatal else
  if CapabilityABI.rightsSubset rights available = true then .done 0 key
  else .done CapabilityABI.denied 0
  else .done CapabilityABI.wrongType 0

private def clearEntryStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Objects.put (address + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

private def publish (descriptor key rights slot serial : UInt64) : Action :=
  .bind (header descriptor) fun s base =>
  if failed s = true then fatal else
  let address := entry base slot
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = entryFree then
  .bind (Objects.get (base + headerOffset + 40)) fun s count =>
  if failed s = true then fatal else
  if count < capacity then
  .bind (Objects.put address entryReserved) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.reference key) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 8) serial) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 16) key) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 24) rights) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 32) slot) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 40) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 48) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (address + 56) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put (base + headerOffset + 40) (count + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.put address entryLive) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.publishSerial serial) fun s _ =>
  if failed s = true then fatal else .done 0 (serial * capacity + slot)
  else fatal else fatal

private def grant (descriptor key rights : UInt64) : Action :=
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  if CapabilityABI.rightsValid kind rights = true then
  .bind (freeSlot descriptor) fun s slot =>
  if failed s = true then .done s 0 else
  .bind Objects.nextSerial fun s serial =>
  if failed s = true then .done s 0 else publish descriptor key rights slot serial
  else .done CapabilityABI.invalidArgument 0

private def discoveredStep (i _ : UInt32) (acc base key descriptor _ : UInt64) : Action :=
  let address := entry base i.toUInt64
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = entryFree then .done 0 acc else
  if state = entryLive then
  .bind (Objects.get (address + 16)) fun s current =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 24)) fun s rights =>
  if failed s = true then fatal else
  if current = key then if rights = CapabilityABI.endpointCall then
  .bind (Objects.get (address + 8)) fun s serial =>
  if failed s = true then fatal else
  let handle := serial * capacity + i.toUInt64
  .bind (lookupEntry descriptor handle) fun s checked =>
  if failed s = true then fatal else
  if checked = address then .done Status.iterationStop handle else fatal
  else .done 0 acc else .done 0 acc
  else fatal

/-- Discovery has one fixed attenuation, Call16. Existing exact current-key
entries are returned by a read-only path even when the table/serial space is
full. Only a genuinely absent entry reaches ordinary grant publication. -/
def grantDiscovered (descriptor key : UInt64) : Action :=
  .bind (requireActive descriptor) fun s base =>
  if failed s = true then .done s 0 else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (entryCount descriptor) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 16 discoveredStep 16 0 base key descriptor 0 fun s handle =>
  if s = Status.iterationStop then .done 0 handle else
  if s = 0 then grant descriptor key CapabilityABI.endpointCall else fatal
  else .done CapabilityABI.wrongType 0

private def activeRegisteredStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Objects.registryDescriptor i.toUInt64) fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then .done 0 acc else
  .bind (header descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (base + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if state = active then .done 0 (acc + 1) else
  if state = constructing then .done 0 acc else fatal

/-- Count only full generation-checked active managed registrations. This low
module has no Task import and discloses no descriptor or pointer to User. -/
def activeRegisteredCount : Action :=
  .boundedFoldU64 8 activeRegisteredStep 8 0 0 0 0 0 fun s count =>
  if failed s = true then fatal else .done 0 count

def grantBoot (descriptor key rights : UInt64) : Action :=
  .bind (header descriptor) fun s base =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (base + headerOffset + 24)) fun s state =>
  if failed s = true then fatal else
  if state = constructing then grant descriptor key rights else .done CapabilityABI.denied 0

def duplicate (descriptor handle rights : UInt64) : Action :=
  .bind (lookupEntry descriptor handle) fun s address =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (address + 24)) fun s available =>
  if failed s = true then fatal else
  if CapabilityABI.rightsSubset CapabilityABI.duplicateRight available = true then
  if rights = 0 then .done CapabilityABI.invalidArgument 0 else
  if CapabilityABI.rightsSubset rights CapabilityABI.knownRights = false then
    .done CapabilityABI.invalidArgument 0 else
  if CapabilityABI.rightsSubset rights available = true then
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else grant descriptor key rights
  else .done CapabilityABI.denied 0
  else .done CapabilityABI.denied 0

private def drop (descriptor base address key : UInt64) : Action :=
  .bind (Objects.get (base + headerOffset + 40)) fun s count =>
  if failed s = true then fatal else
  if 0 < count then
  .bind (Objects.put address entryReserved) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 8 clearEntryStep 8 0 address 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 8 then
  .bind (Objects.put (base + headerOffset + 40) (count - 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.dereference key) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor
  else fatal else fatal

private def revokeEntryStep (i _ : UInt32) (acc base descriptor key _ : UInt64) : Action :=
  let address := entry base i.toUInt64
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = entryLive then
  .bind (Objects.get (address + 16)) fun s actual =>
  if failed s = true then fatal else
  if actual = key then
  .bind (drop descriptor base address key) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else .done 0 acc
  else if state = entryFree then .done 0 acc else fatal

private def revokeTaskStep (i _ : UInt32) (acc key _ _ _ : UInt64) : Action :=
  .bind (Objects.registryDescriptor i.toUInt64) fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then .done 0 acc else
  .bind (header descriptor) fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 revokeEntryStep 16 0 base descriptor key 0 fun s removed =>
  if failed s = true then fatal else .done 0 (acc + removed)

/-- The sole Reply grant has no Duplicate/Transfer rights. Ordinary table/serial
failure leaves its queued Call and pending reference intact for receive retry. -/
def grantReply (server key : UInt64) : Action :=
  .bind (requireActive server) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Objects.replyFields key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get object) fun s state =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 72)) fun s previous =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 80)) fun s phase =>
  if failed s = true then fatal else
  if state = Objects.live then if previous = 0 then if phase = 1 then
  .bind (grant server key CapabilityABI.replyRight) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Objects.deliverReply key server) fun s _ =>
  if failed s = true then fatal else .done 0 handle
  else .done CapabilityABI.invalidHandle 0 else .done CapabilityABI.invalidHandle 0
  else .done CapabilityABI.invalidHandle 0

/-- Withdrawal precedes alias removal. The caller's already committed packet
is immutable even when server death, timeout or endpoint revoke races later. -/
def retireReply (key status : UInt64) : Action :=
  if (if status = 0 then true else if status = IPCABI.timeout.toUInt64 then true else
    if status = IPCABI.canceled.toUInt64 then true else if status = IPCABI.peerDied.toUInt64 then true else
    if status = IPCABI.revoked.toUInt64 then true else false) = false then fatal else
  .bind (Objects.replyFields key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 40)) fun s caller =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 56)) fun s endpoint =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 64)) fun s transaction =>
  if failed s = true then fatal else
  .bind (IPCStorage.pending caller) fun s metadata =>
  if failed s = true then fatal else
  .bind (Objects.get (metadata + IPCStorage.stateOffset)) fun s callerState =>
  if failed s = true then fatal else
  if (if status = 0 then if callerState = IPCStorage.stateReady then true else false else true) = true then
  .bind (Objects.beginReplyRevoke key) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.endpointQueue endpoint) fun s queueHandle =>
  if failed s = true then fatal else
  .bind (IPCStorage.queueCancelReply queueHandle endpoint key transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.invalidateReply caller key status) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 8 revokeTaskStep 8 0 key 0 0 0 fun s removed =>
  if failed s = true then fatal else
  if removed ≤ 1 then
  .bind (Objects.resolveRevoking key) fun s current =>
  if failed s = true then fatal else
  .bind (Objects.get (current + 24)) fun s refs =>
  if failed s = true then fatal else
  if refs = 1 then
  .bind (Objects.dereference key) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.destroyReply key) fun s _ =>
  if failed s = true then fatal else .done 0 0
  else fatal else fatal
  else fatal

private def cancelReplyStep (i _ : UInt32) (acc base endpoint descriptor status : UInt64) : Action :=
  let object := Objects.row base i.toUInt64
  .bind (Objects.get object) fun s state =>
  if failed s = true then fatal else
  if state = Objects.live then
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.replyType then
  .bind (Objects.get (object + 40)) fun s caller =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 56)) fun s actualEndpoint =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 72)) fun s server =>
  if failed s = true then fatal else
  .bind (Objects.resolveRevoking actualEndpoint) fun s endpointObject =>
  if failed s = true then fatal else
  .bind (Objects.get (endpointObject + 40)) fun s endpointOwner =>
  if failed s = true then fatal else
  if (if descriptor = 0 then if actualEndpoint = endpoint then true else false else
    if caller = descriptor then true else if server = descriptor then true else
    if endpointOwner = descriptor then true else false) = true then
  .bind (Objects.get (object + 8)) fun s generation =>
  if failed s = true then fatal else
  .bind (retireReply (generation * Objects.capacity + i.toUInt64) status) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else .done 0 acc
  else .done 0 acc
  else if state = Objects.free then .done 0 acc else
    if state = Objects.retired then .done 0 acc else fatal

def cancelEndpointReplies (endpoint status : UInt64) : Action :=
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 cancelReplyStep 16 0 base endpoint 0 status fun s count =>
  if failed s = true then fatal else .done 0 count

def cancelDescriptorReplies (descriptor status : UInt64) : Action :=
  if descriptor = 0 then fatal else
  .bind Objects.table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 cancelReplyStep 16 0 base 0 descriptor status fun s count =>
  if failed s = true then fatal else .done 0 count

def close (descriptor handle : UInt64) : Action :=
  .bind (lookupEntry descriptor handle) fun s address =>
  if failed s = true then .done s 0 else
  .bind (requireActive descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.replyType then retireReply key IPCABI.canceled.toUInt64 else
  .bind (Objects.get (object + 24)) fun s refs =>
  if failed s = true then fatal else
  .bind (if kind = CapabilityABI.endpointType then
    if refs = 1 then cancelEndpointReplies key IPCABI.revoked.toUInt64 else .done 0 0
    else .done 0 0) fun s _ =>
  if failed s = true then fatal else
  .bind (drop descriptor base address key) fun s _ =>
  if failed s = true then fatal else .done 0 0

private def revokeKey (key : UInt64) : Action :=
  .bind (cancelEndpointReplies key IPCABI.revoked.toUInt64) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.beginRevoke key) fun s _ =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 8 revokeTaskStep 8 0 key 0 0 0 fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.destroy key) fun s _ =>
  if failed s = true then fatal else .done 0 0

def revoke (descriptor handle : UInt64) : Action :=
  .bind (lookup descriptor handle CapabilityABI.endpointType CapabilityABI.revokeRight) fun s key =>
  if failed s = true then .done s 0 else revokeKey key

private def ownedObjectStep (i _ : UInt32) (acc base descriptor _ _ : UInt64) : Action :=
  let address := Objects.row base i.toUInt64
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = Objects.live then
  .bind (Objects.get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (Objects.get (address + 40)) fun s owner =>
  if failed s = true then fatal else
  if owner = descriptor then
  .bind (Objects.get (address + 8)) fun s generation =>
  if failed s = true then fatal else
  .bind (revokeKey (generation * Objects.capacity + i.toUInt64)) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else .done 0 acc else .done 0 acc
  else if state = Objects.free then .done 0 acc else
    if state = Objects.retired then .done 0 acc else fatal

private def detachEntryStep (i _ : UInt32) (acc base descriptor _ _ : UInt64) : Action :=
  let address := entry base i.toUInt64
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = entryLive then
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 24)) fun s refs =>
  if failed s = true then fatal else
  .bind (if kind = CapabilityABI.endpointType then
    if refs = 1 then cancelEndpointReplies key IPCABI.peerDied.toUInt64 else .done 0 0
    else if kind = CapabilityABI.replyType then fatal else .done 0 0) fun s _ =>
  if failed s = true then fatal else
  .bind (drop descriptor base address key) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else if state = entryFree then .done 0 acc else fatal

private def clearHeaderStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (Objects.put (base + headerOffset + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

private def cancelSenderStep (i _ : UInt32) (acc base descriptor _ _ : UInt64) : Action :=
  let object := Objects.row base i.toUInt64
  .bind (Objects.get object) fun s state =>
  if failed s = true then fatal else
  if state = Objects.live then
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (Objects.get (object + 8)) fun s generation =>
  if failed s = true then fatal else
  let key := generation * Objects.capacity + i.toUInt64
  .bind (Objects.endpointQueue key) fun s handle =>
  if failed s = true then fatal else
  .bind (IPCStorage.queueCancelSender handle key descriptor) fun s count =>
  if failed s = true then fatal else
  .bind (Objects.get (object + 40)) fun s owner =>
  if failed s = true then fatal else
  .bind (if owner = descriptor then Objects.invalidateEndpointWaits key IPCABI.peerDied.toUInt64
    else .done 0 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + count)
  else .done 0 acc
  else if state = Objects.free then .done 0 acc else
    if state = Objects.retired then .done 0 acc else fatal

/-- Called before Loader.teardown while the descriptor is still live and its
root inactive. First revoke every owned endpoint, then close other entries and
withdraw enrollment. An unreferenced provisional endpoint is also reclaimed. -/
def detach (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (Objects.get (base + headerOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = 0 then
  .boundedFoldU64 8 zeroHeaderStep 8 1 base 0 0 0 fun s allZero =>
  if failed s = true then fatal else
  if allZero = 1 then .done 0 0 else fatal
  else
  .bind (header descriptor) fun s checked =>
  if failed s = true then fatal else
  .bind (Objects.table) fun s objects =>
  if failed s = true then fatal else
  .bind (cancelDescriptorReplies descriptor IPCABI.peerDied.toUInt64) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 16 cancelSenderStep 16 0 objects descriptor 0 0 fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 16 ownedObjectStep 16 0 objects descriptor 0 0 fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 16 detachEntryStep 16 0 checked descriptor 0 0 fun s _ =>
  if failed s = true then fatal else
  .bind (entryCount descriptor) fun s remaining =>
  if failed s = true then fatal else
  if remaining = 0 then
  .bind (Objects.get (checked + headerOffset + 48)) fun s registry =>
  if failed s = true then fatal else
  .bind (Objects.clearManagement descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (IPCStorage.detach descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Objects.unregister descriptor registry) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 8 clearHeaderStep 8 0 checked 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 8 then .done 0 0 else fatal
  else fatal

def bootGrant (descriptor slot : UInt64) : Action :=
  if slot < capacity then
  .bind (requireActive descriptor) fun s base =>
  if failed s = true then .done s 0 else
  let address := entry base slot
  .bind (Objects.get address) fun s state =>
  if failed s = true then fatal else
  if state = entryLive then
  .bind (Objects.get (address + 8)) fun s serial =>
  if failed s = true then fatal else
  let handle := serial * capacity + slot
  .bind (lookupEntry descriptor handle) fun s _ =>
  if failed s = true then .done s 0 else .done 0 handle
  else if state = entryFree then .done CapabilityABI.invalidHandle 0 else fatal
  else .done CapabilityABI.invalidArgument 0

def info (descriptor handle : UInt64) : Action :=
  .bind (lookupEntry descriptor handle) fun s address =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  .bind (Objects.get (address + 24)) fun s rights =>
  if failed s = true then fatal else .done 0 (kind ||| (rights <<< 8))

def check (descriptor handle kind rights : UInt64) : Action :=
  .bind (lookup descriptor handle kind rights) fun s _ => .done s 0

private def management (descriptor handle rights : UInt64) : Action :=
  .bind (lookup descriptor handle CapabilityABI.managementType rights) fun s key =>
  if failed s = true then .done s 0 else
  .bind (Objects.resolve key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (address + 40)) fun s owner =>
  if failed s = true then fatal else
  if owner = descriptor then .done 0 address else .done CapabilityABI.denied 0

def scopedTarget (descriptor handle mode : UInt64) : Action :=
  if 1 < mode then .done CapabilityABI.invalidArgument 0 else
  .bind (management descriptor handle CapabilityABI.managementInspect) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 56)) fun s target =>
  if failed s = true then fatal else
  .bind (requireActive target) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  if mode = 0 then .done 0 target else entryCount target

def transfer (descriptor managerHandle sourceHandle target rights : UInt64) : Action :=
  .bind (management descriptor managerHandle CapabilityABI.managementGrant) fun s object =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (object + 56)) fun s allowedTarget =>
  if failed s = true then fatal else
  if target = allowedTarget then
  .bind (requireActive target) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (lookupEntry descriptor sourceHandle) fun s address =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (address + 24)) fun s available =>
  if failed s = true then fatal else
  if CapabilityABI.rightsSubset CapabilityABI.duplicateRight available = true then
  if rights = 0 then .done CapabilityABI.invalidArgument 0 else
  if CapabilityABI.rightsSubset rights CapabilityABI.knownRights = false then
    .done CapabilityABI.invalidArgument 0 else
  if CapabilityABI.rightsSubset rights available = true then
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else grant target key rights
  else .done CapabilityABI.denied 0 else .done CapabilityABI.denied 0
  else .done CapabilityABI.denied 0

def createEndpoint (descriptor managerHandle : UInt64) : Action :=
  .bind (management descriptor managerHandle CapabilityABI.managementCreate) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (freeSlot descriptor) fun s slot =>
  if failed s = true then .done s 0 else
  .bind Objects.nextSerial fun s serial =>
  if failed s = true then .done s 0 else
  .bind (Objects.createEndpoint descriptor) fun s key =>
  if failed s = true then .done s 0 else
  publish descriptor key CapabilityABI.endpointMask slot serial

def inspect (descriptor managerHandle subject field : UInt64) : Action :=
  .bind (management descriptor managerHandle CapabilityABI.managementInspect) fun s manager =>
  if failed s = true then .done s 0 else
  if field = 0 then
  .bind (lookupEntry descriptor subject) fun s address =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (address + 16)) fun s key =>
  if failed s = true then fatal else
  .bind (Objects.resolve key) fun s object =>
  if failed s = true then .done s 0 else Objects.get (object + 24)
  else if field = 5 then
  .bind (lookup descriptor subject CapabilityABI.endpointType 0) fun s key =>
  if failed s = true then .done s 0 else
  .bind (Objects.get (manager + 56)) fun s target =>
  if failed s = true then fatal else
  .bind (requireActive target) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  IPCStorage.waitsOnReceive target key
  else if subject = 0 then
    if field = 1 then Objects.liveCount else
    if field = 2 then Frames.remaining else
    if field = 3 then Objects.retiredCount else .done CapabilityABI.invalidArgument 0
  else .done CapabilityABI.invalidArgument 0

end Lemma.Kernel.Capability
