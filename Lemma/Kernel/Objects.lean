import Lemma.Kernel.Memory.AddressSpace
import Lemma.Kernel.IPCStorage
import Lemma.User.CapabilityABI

/-! Closed kernel object storage. The sole table and each endpoint's future
queue are real owner-1 purpose-1 frames. All pointer derivation follows checked
generation/purpose resolution; no user value is an object address. -/
namespace Lemma.Kernel.Objects
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

def control : UInt64 := Lemma.Platform.LemmaVM.Layout.capabilityControlValue
def magic : UInt64 := 0x314a424f414d454c
def capacity : UInt64 := 16
def endpointCapacity : UInt64 := 4
def powerEndpointCapacity : UInt64 := 5
def arithmeticEndpointCapacity : UInt64 := 6
def replyCapacity : UInt64 := 8
def arithmeticReplyCapacity : UInt64 := 7
def registryCapacity : UInt64 := 8
def rows : UInt64 := 256
def stride : UInt64 := 128
def maxGeneration : UInt64 := 0x0fffffffffffffff
def maxSerial : UInt64 := 0x0fffffffffffffff
def consoleKey : UInt64 := 16
def managementKey : UInt64 := 17
def directoryKey : UInt64 := 18
def free : UInt64 := 0
def live : UInt64 := 1
def revoking : UInt64 := 2
def retired : UInt64 := 3
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done CapabilityABI.fatal 0

/-- The volatile successor has one exact encoded budget. Legacy zero words
remain legacy; neither arbitrary versions nor arbitrary limits acquire capacity. -/
def headerAdmitted (version endpointLimit : UInt64) : Bool :=
  if version = 1 then if endpointLimit = 0 then true else false else
  if version = 2 then if endpointLimit = powerEndpointCapacity then true else false else
  if version = 3 then if endpointLimit = arithmeticEndpointCapacity then true else false else false

def endpointLimitFor (version : UInt64) : UInt64 :=
  if version = 1 then endpointCapacity else if version = 2 then powerEndpointCapacity else
  if version = 3 then arithmeticEndpointCapacity else 0

/-- Header encoding remains zero for legacy v1 and exact5/6 for v2/v3. -/
def encodedLimitFor (version : UInt64) : UInt64 :=
  if version = 2 then powerEndpointCapacity else if version = 3 then arithmeticEndpointCapacity else 0

def replyLimitFor (version : UInt64) : UInt64 :=
  if version = 1 then replyCapacity else if version = 2 then replyCapacity else
  if version = 3 then arithmeticReplyCapacity else 0

private def getGeneric (address : UInt64) : Action :=
  .bind (Access.read64 address) fun s value => if failed s = true then fatal else .done 0 value

/-- The first2MiB pool interval is admitted by every kernel execution profile.
Expose this exact aligned eight-byte interval to checked lowering. The access
still uses the same primitive and maps every error to fatal. Arbitrary, wrapped,
misaligned and expanded-pool addresses retain the original checked fallback;
this is neither a new alias nor a replacement for object/ownership validation. -/
def get (address : UInt64) : Action :=
  if 0x82000000 ≤ address then
    if address ≤ 0x82200000 - 8 then
      if address % 8 = 0 then
        .bind (Access.read64 address) fun s value => if failed s = true then fatal else .done 0 value
      else getGeneric address
    else getGeneric address
  else getGeneric address
def put (address value : UInt64) : Action :=
  .bind (Access.write64 address value) fun s _ => if failed s = true then fatal else .done 0 value
def row (base index : UInt64) : UInt64 := base + rows + index * stride
def keyIndex (key : UInt64) : UInt64 := key % capacity
def keyGeneration (key : UInt64) : UInt64 := key / capacity
def keyValid (key : UInt64) : Bool :=
  if 0 < keyGeneration key then if keyGeneration key ≤ maxGeneration then true else false else false

/-- Resolving the global table never relies on an arbitrary pointer or only a
magic word. Its handle, owner, purpose, pin count and bounded header all agree. -/
def table : Action :=
  .bind (get control) fun s handle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount 1 handle) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then
  .bind (get address) fun s tag =>
  if failed s = true then fatal else
  if tag = magic then
  .bind (get (address + 8)) fun s version =>
  if failed s = true then fatal else
  .bind (get (address + 24)) fun s endpointLimit =>
  if failed s = true then fatal else
  if headerAdmitted version endpointLimit = true then
  .bind (get (address + 16)) fun s serial =>
  if failed s = true then fatal else
  if 0 < serial then if serial ≤ maxSerial + 1 then
  .bind (get (address + 32)) fun s count =>
  if failed s = true then fatal else
  if count ≤ capacity then
  .bind (get (address + 40)) fun s enrolled =>
  if failed s = true then fatal else
  if enrolled ≤ registryCapacity then .done 0 address else fatal
  else fatal else fatal else fatal
  else fatal else fatal else fatal

/-- Version1 retains its four-Endpoint limit. Only the validated volatile
version2 header admits the fifth Endpoint needed by the power binding. -/
def runtimeEndpointCapacity : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .bind (get (address + 8)) fun s version =>
  if failed s = true then fatal else
  .done 0 (endpointLimitFor version)

/-- The version3 arithmetic binding admits six Endpoints and seven Replies in
the same16-row layout. Versions1/2 retain all eight Reply slots. -/
def runtimeReplyCapacity : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .bind (get (address + 8)) fun s version =>
  if failed s = true then fatal else .done 0 (replyLimitFor version)

private def initStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let index := i.toUInt64
  let address := row base index
  let kind := if index = 0 then CapabilityABI.consoleType else if index = 1 then CapabilityABI.managementType else
    if index = 2 then CapabilityABI.directoryType else 0
  .bind (put (address + 8) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 16) kind) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 48) (if index < 3 then 1 else 0)) fun s _ =>
  if failed s = true then fatal else
  .bind (put address (if index < 3 then live else free)) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

/-- Boot-only single initialization; the allocator zeroes the whole provisional
frame. Global publication follows all pinned object/header initialization. -/
private def initFor (version : UInt64) : Action :=
  if (if version = 1 then true else if version = 2 then true else if version = 3 then true else false) = false then
    .done CapabilityABI.invalidArgument 0 else
  let endpointLimit := encodedLimitFor version
  .bind (get control) fun s existing =>
  if failed s = true then fatal else
  if existing = 0 then
  .bind (Frames.allocate 1 1) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 16 initStep 16 0 address 0 0 0 fun s initialized =>
  if failed s = true then fatal else
  if initialized = capacity then
  .bind (put (address + 8) version) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 24) endpointLimit) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 16) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 32) 3) fun s _ =>
  if failed s = true then fatal else
  .bind (put address magic) fun s _ =>
  if failed s = true then fatal else
  .bind (put control handle) fun s _ =>
  if failed s = true then fatal else .done 0 handle
  else fatal
  else .done CapabilityABI.invalidArgument 0

/-- Historical boot constructor and default budgets remain unchanged. -/
def init : Action := initFor 1
/-- Boot-only successor used by the power-enabled LemmaSim binding. Object
rows, Reply budget, key generations and all User authority remain unchanged. -/
def initPower : Action := initFor 2
/-- Software authority-budget successor; hardware ISA, page pool and geometry
are unchanged. Header publication remains after all real table initialization. -/
def initArithmetic : Action := initFor 3

private def resolveState (key : UInt64) (allowRevoking : Bool) : Action :=
  if keyValid key = false then .done CapabilityABI.invalidHandle 0 else
  .bind table fun s base =>
  if failed s = true then fatal else
  let address := row base (keyIndex key)
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if (if state = live then true else if allowRevoking = true then if state = revoking then true else false else false) = true then
  .bind (get (address + 8)) fun s generation =>
  if failed s = true then fatal else
  if generation = keyGeneration key then
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if CapabilityABI.typeValid kind = true then
  .bind (get (address + 24)) fun s references =>
  if failed s = true then fatal else
  if references ≤ 128 then
  .bind (get (address + 48)) fun s pinned =>
  if failed s = true then fatal else
  if pinned ≤ 1 then .done 0 address else fatal
  else fatal else fatal else .done CapabilityABI.invalidHandle 0
  else if retired < state then fatal else .done CapabilityABI.invalidHandle 0

def resolve (key : UInt64) : Action := resolveState key false
def resolveRevoking (key : UInt64) : Action := resolveState key true

def registryDescriptor (index : UInt64) : Action :=
  if index < registryCapacity then
  .bind table fun s address =>
  if failed s = true then fatal else get (address + 64 + index * 8)
  else .done CapabilityABI.invalidArgument 0

private def findRegisteredStep (i _ : UInt32) (acc base descriptor _ _ : UInt64) : Action :=
  .bind (get (base + 64 + i.toUInt64 * 8)) fun s current =>
  if failed s = true then fatal else
  if current = descriptor then .done Status.iterationStop i.toUInt64 else .done 0 acc

def registrySlot (descriptor : UInt64) : Action :=
  if descriptor = 0 then .done CapabilityABI.invalidHandle 0 else
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 8 findRegisteredStep 8 registryCapacity base descriptor 0 0 fun s index =>
  if s = Status.iterationStop then .done 0 index else
  if s = 0 then .done CapabilityABI.invalidHandle 0 else fatal

def serviceMagic : UInt64 := 0x31565253414d454c
def serviceOffset : UInt64 := 224
def serviceEpochOffset : UInt64 := 232
def serviceKeyOffset : UInt64 := 240
def serviceOwnerOffset : UInt64 := 248

/-- The legacy all-zero binding is valid but unavailable. An initialized
binding is either wholly withdrawn or names a full registered descriptor and
its exact live/revoking Endpoint. No task pointer or extra reference is held. -/
def serviceBinding : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + serviceOffset)) fun s tag =>
  if failed s = true then fatal else
  .bind (get (base + serviceEpochOffset)) fun s epoch =>
  if failed s = true then fatal else
  .bind (get (base + serviceKeyOffset)) fun s key =>
  if failed s = true then fatal else
  .bind (get (base + serviceOwnerOffset)) fun s owner =>
  if failed s = true then fatal else
  if tag = 0 then
    if epoch ||| key ||| owner = 0 then .done 0 base else fatal
  else if tag = serviceMagic then
    if key = 0 then if owner = 0 then .done 0 base else fatal else
    if epoch = 0 then fatal else
    .bind (AddressSpace.base owner) fun s _ =>
    if failed s = true then fatal else
    .bind (registrySlot owner) fun s _ =>
    if failed s = true then fatal else
    .bind (resolveRevoking key) fun s object =>
    if failed s = true then fatal else
    .bind (get (object + 16)) fun s kind =>
    if failed s = true then fatal else
    .bind (get (object + 40)) fun s actualOwner =>
    if failed s = true then fatal else
    if kind = CapabilityABI.endpointType then
      if actualOwner = owner then .done 0 base else fatal
    else fatal
  else fatal

/-- Boot-only initialization in the checked global object's reserved words. -/
def serviceInitialize : Action :=
  .bind serviceBinding fun s base =>
  if failed s = true then fatal else
  .bind (get (base + serviceOffset)) fun s tag =>
  if failed s = true then fatal else
  if tag = 0 then put (base + serviceOffset) serviceMagic
  else .done CapabilityABI.invalidArgument 0

def publishServiceBinding (server key epoch : UInt64) : Action :=
  .bind serviceBinding fun s base =>
  if failed s = true then fatal else
  .bind (get (base + serviceOffset)) fun s tag =>
  if failed s = true then fatal else
  .bind (get (base + serviceEpochOffset)) fun s previous =>
  if failed s = true then fatal else
  .bind (get (base + serviceKeyOffset)) fun s existing =>
  if failed s = true then fatal else
  if tag = serviceMagic then if existing = 0 then
  if previous < 0xffffffffffffffff then if epoch = previous + 1 then
  .bind (AddressSpace.base server) fun s _ =>
  if failed s = true then fatal else
  .bind (registrySlot server) fun s _ =>
  if failed s = true then fatal else
  .bind (resolve key) fun s object =>
  if failed s = true then fatal else
  .bind (get (object + 16)) fun s kind =>
  if failed s = true then fatal else
  .bind (get (object + 40)) fun s owner =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then if owner = server then
  .bind (put (base + serviceEpochOffset) epoch) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + serviceOwnerOffset) server) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + serviceKeyOffset) key) fun s _ =>
  if failed s = true then fatal else .done 0 epoch
  else fatal else fatal else fatal else fatal else fatal else fatal

/-- Both revocation and last-alias destruction call this before changing the
Endpoint or releasing its queue. Withdrawal preserves the last epoch. -/
def withdrawService (key owner : UInt64) : Action :=
  .bind serviceBinding fun s base =>
  if failed s = true then fatal else
  .bind (get (base + serviceKeyOffset)) fun s current =>
  if failed s = true then fatal else
  if current = key then
  .bind (get (base + serviceOwnerOffset)) fun s actualOwner =>
  if failed s = true then fatal else
  if actualOwner = owner then
  .bind (put (base + serviceKeyOffset) 0) fun s _ =>
  if failed s = true then fatal else put (base + serviceOwnerOffset) 0
  else fatal else .done 0 0

private def freeRegisteredStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (get (base + 64 + i.toUInt64 * 8)) fun s current =>
  if failed s = true then fatal else
  if current = 0 then .done Status.iterationStop i.toUInt64 else .done 0 acc

def register (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (registrySlot descriptor) fun s _ =>
  if s = 0 then .done CapabilityABI.invalidArgument 0 else
  if s = CapabilityABI.invalidHandle then
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 40)) fun s enrolled =>
  if failed s = true then fatal else
  if enrolled < registryCapacity then
  .boundedFoldU64 8 freeRegisteredStep 8 registryCapacity base 0 0 0 fun s index =>
  if s = Status.iterationStop then
  .bind (put (base + 64 + index * 8) descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 40) (enrolled + 1)) fun s _ =>
  if failed s = true then fatal else .done 0 index
  else fatal else .done CapabilityABI.tableFull 0
  else fatal

def unregister (descriptor index : UInt64) : Action :=
  .bind (registrySlot descriptor) fun s actual =>
  if failed s = true then fatal else
  if actual = index then
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 40)) fun s enrolled =>
  if failed s = true then fatal else
  if 0 < enrolled then
  .bind (put (base + 64 + index * 8) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 40) (enrolled - 1)) fun s _ =>
  if failed s = true then fatal else .done 0 0
  else fatal else fatal

def nextSerial : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 16)) fun s serial =>
  if failed s = true then fatal else
  if serial ≤ maxSerial then .done 0 serial else .done CapabilityABI.generationExhausted 0

/-- Called only after successful capability publication in the same bounded,
nonpreemptible transition. Recoverable failures never consume a serial. -/
def publishSerial (serial : UInt64) : Action :=
  .bind nextSerial fun s expected =>
  if failed s = true then fatal else
  if serial = expected then
  .bind table fun s base =>
  if failed s = true then fatal else put (base + 16) (serial + 1)
  else fatal

private def freeObjectStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let address := row base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if state = free then
  .bind (get (address + 8)) fun s generation =>
  if failed s = true then fatal else
  if 0 < generation then if generation ≤ maxGeneration then
    .done Status.iterationStop i.toUInt64 else fatal else fatal
  else if retired < state then fatal else .done 0 acc

private def endpointCountStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let address := row base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if (if state = live then true else if state = revoking then true else false) = true then
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if CapabilityABI.typeValid kind = true then
    .done 0 (if kind = CapabilityABI.endpointType then acc + 1 else acc)
  else fatal
  else if retired < state then fatal else .done 0 acc

def createEndpoint (ownerDescriptor : UInt64) : Action :=
  .bind (AddressSpace.base ownerDescriptor) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 endpointCountStep 16 0 base 0 0 0 fun s endpoints =>
  if failed s = true then fatal else
  .bind runtimeEndpointCapacity fun s endpointLimit =>
  if failed s = true then fatal else
  if endpoints < endpointLimit then
  .boundedFoldU64 16 freeObjectStep 16 capacity base 0 0 0 fun s index =>
  if s = Status.iterationStop then
  let address := row base index
  .bind (get (address + 8)) fun s generation =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s count =>
  if failed s = true then fatal else
  if count < capacity then
  .bind (Frames.allocate 1 1) fun s queueHandle =>
  if failed s = true then .done s 0 else
  .bind (IPCStorage.queueInitialize queueHandle (generation * capacity + index)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 16) CapabilityABI.endpointType) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 32) queueHandle) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 40) ownerDescriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 32) (count + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (put address live) fun s _ =>
  if failed s = true then fatal else .done 0 (generation * capacity + index)
  else fatal else if s = 0 then .done CapabilityABI.objectFull 0 else fatal
  else if endpoints = endpointLimit then .done CapabilityABI.objectFull 0 else fatal

def reference (key : UInt64) : Action :=
  .bind (resolve key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + 24)) fun s count =>
  if failed s = true then fatal else
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.replyType then
    if count = 1 then put (address + 24) 2 else fatal
  else if count < 128 then put (address + 24) (count + 1) else fatal

def endpointQueue (key : UInt64) : Action :=
  .bind (resolveRevoking key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (get (address + 32)) fun s handle =>
  if failed s = true then fatal else
  .bind (IPCStorage.queue handle key) fun s _ =>
  if failed s = true then fatal else .done 0 handle
  else .done CapabilityABI.wrongType 0

private def replyCountStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let address := row base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if (if state = live then true else if state = revoking then true else false) = true then
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if CapabilityABI.typeValid kind = true then
    .done 0 (if kind = CapabilityABI.replyType then acc + 1 else acc)
  else fatal
  else if retired < state then fatal else .done 0 acc

/-- Pure preflight before Call storage publication. Global free capacity and
the independent eight-Reply bound are both checked before any row changes. -/
def replyAvailable : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 replyCountStep 16 0 base 0 0 0 fun s replies =>
  if failed s = true then fatal else
  .bind runtimeReplyCapacity fun s replyLimit =>
  if failed s = true then fatal else
  if replies < replyLimit then
  .bind (get (base + 32)) fun s count =>
  if failed s = true then fatal else
  if count < capacity then
  .boundedFoldU64 16 freeObjectStep 16 capacity base 0 0 0 fun s _ =>
  if s = Status.iterationStop then .done 0 (replyLimit - replies) else
    if s = 0 then .done CapabilityABI.objectFull 0 else fatal
  else .done CapabilityABI.objectFull 0
  else if replies = replyLimit then .done CapabilityABI.objectFull 0 else fatal

def createReply (caller endpoint transaction deadline : UInt64) : Action :=
  .bind (IPCStorage.pending caller) fun s metadata =>
  if failed s = true then .done s 0 else
  .bind (get (metadata + IPCStorage.stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.operationOffset)) fun s operation =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.transactionOffset)) fun s actual =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.endpointOffset)) fun s actualEndpoint =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.deadlineOffset)) fun s actualDeadline =>
  if failed s = true then fatal else
  if state = IPCStorage.stateReserved then if operation = IPCStorage.callOperation then
  if actual = transaction then if actualEndpoint = endpoint then if actualDeadline = deadline then
  .bind (endpointQueue endpoint) fun s _ =>
  if failed s = true then .done s 0 else
  .bind replyAvailable fun s _ =>
  if failed s = true then .done s 0 else
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 freeObjectStep 16 capacity base 0 0 0 fun s index =>
  if s = Status.iterationStop then
  let address := row base index
  .bind (get (address + 8)) fun s generation =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s count =>
  if failed s = true then fatal else
  .bind (put (address + 16) CapabilityABI.replyType) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 24) 1) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 40) caller) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 56) endpoint) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 64) transaction) fun s _ =>
  if failed s = true then fatal else
  .bind (put (address + 88) deadline) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 32) (count + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (put address live) fun s _ =>
  if failed s = true then fatal else .done 0 (generation * capacity + index)
  else fatal
  else fatal else fatal else fatal else fatal else fatal

/-- Reply inspection binds generation, type, caller transaction and Endpoint.
The row address is an internal result; User never receives object pointers. -/
private def replyPhase (address metadata refs : UInt64) : Action :=
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  .bind (get (address + 72)) fun s server =>
  if failed s = true then fatal else
  .bind (get (address + 80)) fun s phase =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.stateOffset)) fun s callerState =>
  if failed s = true then fatal else
  if phase = 0 then
    if state = live then if refs = 1 then if server = 0 then
      if callerState = IPCStorage.stateReserved then .done 0 address else fatal
    else fatal else fatal else fatal
  else if phase = 1 then
    if server = 0 then
    if state = live then
      if 0 < refs then
        if (if callerState = IPCStorage.stateReserved then true else
          if callerState = IPCStorage.stateWaiting then true else false) = true then .done 0 address else fatal
      else fatal
    else if (if callerState = IPCStorage.stateWaiting then true else
      if callerState = IPCStorage.stateReady then true else false) = true then .done 0 address else fatal
    else fatal
  else if phase = 2 then
    if 0 < server then
    .bind (AddressSpace.base server) fun s _ =>
    if failed s = true then fatal else
    .bind (registrySlot server) fun s _ =>
    if failed s = true then fatal else
    if (if callerState = IPCStorage.stateWaiting then true else
      if callerState = IPCStorage.stateReady then true else false) = true then
      if state = live then if refs = 2 then .done 0 address else fatal else .done 0 address
    else fatal else fatal
  else fatal

def replyFields (key : UInt64) : Action :=
  .bind (resolveRevoking key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.replyType then
  .bind (get (address + 24)) fun s refs =>
  if failed s = true then fatal else
  if refs ≤ 2 then
  .bind (get (address + 32)) fun s payload =>
  if failed s = true then fatal else
  .bind (get (address + 48)) fun s pin =>
  if failed s = true then fatal else
  if payload = 0 then if pin = 0 then
  .bind (get (address + 40)) fun s caller =>
  if failed s = true then fatal else
  .bind (IPCStorage.pending caller) fun s metadata =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.operationOffset)) fun s operation =>
  if failed s = true then fatal else
  if operation = IPCStorage.callOperation then
  .bind (get (address + 64)) fun s transaction =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.transactionOffset)) fun s actual =>
  if failed s = true then fatal else
  if actual = transaction then
  .bind (get (address + 56)) fun s endpoint =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.endpointOffset)) fun s actualEndpoint =>
  if failed s = true then fatal else
  if actualEndpoint = endpoint then
  .bind (get (metadata + IPCStorage.replyOffset)) fun s actualReply =>
  if failed s = true then fatal else
  if actualReply = key then
  .bind (get (address + 88)) fun s deadline =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.deadlineOffset)) fun s actualDeadline =>
  if failed s = true then fatal else
  if actualDeadline = deadline then replyPhase address metadata refs else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal
  else .done CapabilityABI.wrongType 0

def markReplyQueued (key : UInt64) : Action :=
  .bind (replyFields key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + 80)) fun s phase =>
  if failed s = true then fatal else
  if phase = 0 then put (address + 80) 1 else fatal

def deliverReply (key server : UInt64) : Action :=
  .bind (AddressSpace.base server) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (registrySlot server) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (replyFields key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  .bind (get (address + 72)) fun s previous =>
  if failed s = true then fatal else
  .bind (get (address + 80)) fun s phase =>
  if failed s = true then fatal else
  .bind (get (address + 24)) fun s refs =>
  if failed s = true then fatal else
  if state = live then if previous = 0 then if phase = 1 then if refs = 2 then
  .bind (put (address + 72) server) fun s _ =>
  if failed s = true then fatal else put (address + 80) 2
  else fatal else fatal else fatal else .done CapabilityABI.invalidHandle 0

def beginReplyRevoke (key : UInt64) : Action :=
  .bind (replyFields key) fun s address =>
  if failed s = true then .done s 0 else put address revoking

private def endpointRepliesStep (i _ : UInt32) (acc base endpoint _ _ : UInt64) : Action :=
  let address := row base i.toUInt64
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if (if state = live then true else if state = revoking then true else false) = true then
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.replyType then
  .bind (get (address + 56)) fun s actual =>
  if failed s = true then fatal else .done 0 (if actual = endpoint then acc + 1 else acc)
  else .done 0 acc
  else if retired < state then fatal else .done 0 acc

private def invalidateEndpointStep (i _ : UInt32) (acc key status _ _ : UInt64) : Action :=
  .bind (registryDescriptor i.toUInt64) fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then .done 0 acc else
  .bind (IPCStorage.invalidateEndpoint descriptor key status) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

def invalidateEndpointWaits (key status : UInt64) : Action :=
  .boundedFoldU64 8 invalidateEndpointStep 8 0 key status 0 0 fun s count =>
  if failed s = true then fatal else .done 0 count

private def clearObjectStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (put (address + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

/-- Only unpinned endpoints can be destroyed. Refcount zero precedes releasing
the genuine queue frame; generation advancement/retirement precedes reuse. -/
def destroy (key : UInt64) : Action :=
  .bind (resolveRevoking key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (get (address + 48)) fun s pinned =>
  if failed s = true then fatal else
  if pinned = 0 then
  .bind (get (address + 24)) fun s refs =>
  if failed s = true then fatal else
  if refs = 0 then
  .bind (get (address + 32)) fun s handle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s _ =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount 1 handle) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 endpointRepliesStep 16 0 base key 0 0 fun s replies =>
  if failed s = true then fatal else
  if replies = 0 then
  .bind (get (address + 40)) fun s owner =>
  if failed s = true then fatal else
  .bind (withdrawService key owner) fun s _ =>
  if failed s = true then fatal else
  .bind (invalidateEndpointWaits key IPCABI.revoked.toUInt64) fun s _ =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s count =>
  if failed s = true then fatal else
  if 3 < count then
  .bind (Frames.release 1 handle) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 16 clearObjectStep 16 0 address 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 16 then
  let generation := keyGeneration key
  .bind (put (address + 8) (if generation = maxGeneration then generation else generation + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (put address (if generation = maxGeneration then retired else free)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 32) (count - 1)) fun s _ =>
  if failed s = true then fatal else .done 0 0
  else fatal else fatal else fatal else fatal
  else fatal else .done CapabilityABI.denied 0 else .done CapabilityABI.denied 0

def dereference (key : UInt64) : Action :=
  .bind (resolveRevoking key) fun s address =>
  if failed s = true then fatal else
  .bind (get (address + 24)) fun s count =>
  if failed s = true then fatal else
  if 0 < count then
  .bind (put (address + 24) (count - 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  .bind (get (address + 48)) fun s pinned =>
  if failed s = true then fatal else
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if count = 1 then if pinned = 0 then if state = live then
    if kind = CapabilityABI.endpointType then destroy key else fatal
    else .done 0 0
    else .done 0 0 else .done 0 0
  else fatal

private def invalidateReplyBindingStep (i _ : UInt32) (acc key caller transaction _ : UInt64) : Action :=
  .bind (registryDescriptor i.toUInt64) fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then .done 0 acc else
  .bind (IPCStorage.pending descriptor) fun s metadata =>
  if failed s = true then fatal else
  .bind (get (metadata + IPCStorage.replyOffset)) fun s actual =>
  if failed s = true then fatal else
  if actual = key then
  if descriptor = caller then
  .bind (get (metadata + IPCStorage.transactionOffset)) fun s actualTransaction =>
  if failed s = true then fatal else
  if actualTransaction = transaction then
  .bind (get (metadata + IPCStorage.stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = IPCStorage.stateReady then
  .bind (IPCStorage.invalidateReply descriptor key IPCABI.canceled.toUInt64) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)
  else fatal else fatal else fatal
  else .done 0 acc

def destroyReply (key : UInt64) : Action :=
  .bind (replyFields key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get address) fun s state =>
  if failed s = true then fatal else
  if state = revoking then
  .bind (get (address + 24)) fun s refs =>
  if failed s = true then fatal else
  if refs = 0 then
  .bind (get (address + 40)) fun s caller =>
  if failed s = true then fatal else
  .bind (get (address + 64)) fun s transaction =>
  if failed s = true then fatal else
  .boundedFoldU64 8 invalidateReplyBindingStep 8 0 key caller transaction 0 fun s matched =>
  if failed s = true then fatal else
  if matched = 1 then
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 32)) fun s count =>
  if failed s = true then fatal else
  if 3 < count then
  .boundedFoldU64 16 clearObjectStep 16 0 address 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 16 then
  let generation := keyGeneration key
  .bind (put (address + 8) (if generation = maxGeneration then generation else generation + 1)) fun s _ =>
  if failed s = true then fatal else
  .bind (put address (if generation = maxGeneration then retired else free)) fun s _ =>
  if failed s = true then fatal else put (base + 32) (count - 1)
  else fatal else fatal else fatal else fatal else fatal

def beginRevoke (key : UInt64) : Action :=
  .bind (resolve key) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get (address + 16)) fun s kind =>
  if failed s = true then fatal else
  if kind = CapabilityABI.endpointType then
  .bind (get (address + 40)) fun s owner =>
  if failed s = true then fatal else
  .bind (withdrawService key owner) fun s _ =>
  if failed s = true then fatal else put address revoking
  else .done CapabilityABI.denied 0

def configureManagement (ownerDescriptor targetDescriptor : UInt64) : Action :=
  .bind (AddressSpace.base ownerDescriptor) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (AddressSpace.base targetDescriptor) fun s _ =>
  if failed s = true then .done CapabilityABI.invalidHandle 0 else
  .bind (registrySlot ownerDescriptor) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (registrySlot targetDescriptor) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (resolve managementKey) fun s address =>
  if failed s = true then fatal else
  .bind (get (address + 40)) fun s oldOwner =>
  if failed s = true then fatal else
  .bind (get (address + 56)) fun s oldTarget =>
  if failed s = true then fatal else
  if oldTarget = 0 then
  if (if oldOwner = 0 then true else if oldOwner = ownerDescriptor then true else false) = true then
  .bind (put (address + 40) ownerDescriptor) fun s _ =>
  if failed s = true then fatal else put (address + 56) targetDescriptor
  else .done CapabilityABI.denied 0 else .done CapabilityABI.invalidArgument 0

def clearManagement (descriptor : UInt64) : Action :=
  .bind (resolve managementKey) fun s address =>
  if failed s = true then fatal else
  .bind (get (address + 40)) fun s owner =>
  if failed s = true then fatal else
  .bind (get (address + 56)) fun s target =>
  if failed s = true then fatal else
  if owner = descriptor then
  .bind (put (address + 40) 0) fun s _ =>
  if failed s = true then fatal else put (address + 56) 0
  else if target = descriptor then put (address + 56) 0 else .done 0 0

def liveCount : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else get (base + 32)

private def retiredStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (get (row base i.toUInt64)) fun s state =>
  if failed s = true then fatal else
  if retired < state then fatal else .done 0 (if state = retired then acc + 1 else acc)

def retiredCount : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 16 retiredStep 16 0 base 0 0 0 fun s count =>
  if failed s = true then fatal else .done 0 count

end Lemma.Kernel.Objects
