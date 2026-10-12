import Lemma.Kernel.Process
import Lemma.Kernel.Capability
import Lemma.Kernel.IPC

/-! Owned fixed-capacity task storage. IDs are the checked generation-tagged
address-space descriptor handles. The registry and persistent user contexts
are supervisor-only. No user integer supplies an owner or record pointer. -/
namespace Lemma.Kernel.Task
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def capacity : UInt64 := 8
def stride : UInt64 := 512
def tableHandle : UInt64 := Process.control + 40
def cursor : UInt64 := Process.control + 48
def packetLength : UInt64 := Process.control + 88
def packetBase : UInt64 := Process.control + 128
def stateOffset : UInt64 := 8
def deadlineOffset : UInt64 := 16
def reasonOffset : UInt64 := 24
def exitOffset : UInt64 := 32
def causeOffset : UInt64 := 40
def pcOffset : UInt64 := 48
def faultOffset : UInt64 := 56
def preemptOffset : UInt64 := 64
def yieldOffset : UInt64 := 72
def dispatchOffset : UInt64 := 80
def argumentOffset : UInt64 := 88
def imageOffset : UInt64 := 96
def wakeTimeOffset : UInt64 := 104
def waitKindOffset : UInt64 := 112
def managedOffset : UInt64 := 120
def waitEpochOffset : UInt64 := 128
def waitTransactionOffset : UInt64 := 136
def free : UInt64 := 0
def building : UInt64 := 1
def runnable : UInt64 := 2
def running : UInt64 := 3
def sleeping : UInt64 := 4
def blocked : UInt64 := 5
def dying : UInt64 := 6
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

def table : Action :=
  .bind (Access.read64 tableHandle) fun s handle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address =>
  if failed s = true then fatal else
  -- Owner, generation and purpose were just resolved in this same S Action.
  -- Read pins through that exact slot, retaining the zero-pins requirement.
  .bind (Access.read64 (Frames.record ((address - Frames.pool) / Frames.bytes) + 16)) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then .done 0 address else fatal

def row (index : UInt64) : Action :=
  if index < capacity then
    .bind table fun s address =>
    if failed s = true then fatal else .done 0 (address + index * stride)
  else fatal

def init : Action :=
  .bind (Access.read64 Process.control) fun s current =>
  if failed s = true then fatal else
  if current = 0 then
    .bind (Access.read64 tableHandle) fun s existing =>
    if failed s = true then fatal else
    if existing = 0 then
    .bind (Frames.allocate 1 1) fun s handle =>
    if failed s = true then .done s 0 else
    .bind (Access.write64 tableHandle handle) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 cursor 0) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 packetLength 0) fun s _ =>
    if failed s = true then fatal else
    .bind Frames.remaining fun s remaining =>
    if failed s = true then fatal else
    .bind (Access.write64 (Process.control + 24) remaining) fun s _ =>
    if failed s = true then fatal else .done 0 handle
    else fatal
  else fatal

private def findStep (i _ : UInt32) (acc address descriptor _ _ : UInt64) : Action :=
  let record := address + i.toUInt64 * stride
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if dying < state then fatal else
  if (if runnable ≤ state then if state < dying then true else false else false) = true then
    .bind (Access.read64 record) fun s id =>
    if failed s = true then fatal else
    if id = descriptor then .done Status.iterationStop i.toUInt64 else .done 0 acc
  else .done 0 acc

private def lookupRecord (descriptor : UInt64) : Action :=
  if descriptor = 0 then .done 74 0 else
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 findStep 8 8 address descriptor 0 0 fun s index =>
  if s = Status.iterationStop then
    .done 0 (address + index * stride)
  else if s = 0 then .done 74 0 else fatal

def lookup (descriptor : UInt64) : Action :=
  .bind (lookupRecord descriptor) fun s record =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.base descriptor) fun s _ =>
  if failed s = true then fatal else .done 0 record

private def freeStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (address + i.toUInt64 * stride + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = free then .done Status.iterationStop i.toUInt64 else
  if dying < state then fatal else .done 0 acc

private def abandon (record : UInt64) (status : UInt8) : Action :=
  .bind (Access.write64 record 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + stateOffset) free) fun s _ =>
  if failed s = true then fatal else .done status 0

private def retainPrepared (record descriptor image argument : UInt64) : Action :=
  .bind (Access.write64 record descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + argumentOffset) argument) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + imageOffset) image) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + managedOffset) 0) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor

/-- Reserve and load an unpublished instance. A building row is excluded from
lookup and selection until activation, so trusted policy may finish grants.
The monotonic private owner allocator never accepts a user-supplied owner. -/
def prepare (image argument : UInt64) : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 freeStep 8 8 address 0 0 0 fun s index =>
  if s = Status.iterationStop then
    let record := address + index * stride
    .bind (Access.write64 (record + stateOffset) building) fun s _ =>
    if failed s = true then fatal else
    .bind Process.reserveOwner fun s owner =>
    if failed s = true then abandon record s else
    .bind (Loader.load image owner argument) fun s descriptor =>
    if failed s = true then abandon record s else
    .bind (retainPrepared record descriptor image argument) fun s id =>
    if failed s = true then
      .bind (Loader.teardown descriptor) fun _ _ => fatal
    else .done 0 id
  else if s = 0 then .done 38 0 else fatal

private def preparedStep (i _ : UInt32) (acc address descriptor _ _ : UInt64) : Action :=
  let record := address + i.toUInt64 * stride
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if dying < state then fatal else
  if state = building then
    .bind (Access.read64 record) fun s id =>
    if failed s = true then fatal else
    if id = descriptor then .done Status.iterationStop i.toUInt64 else .done 0 acc
  else .done 0 acc

/-- Trusted construction lookup; public live lookup does not admit these rows.
The descriptor must still resolve to its exact live generation and owned root. -/
def prepared (descriptor : UInt64) : Action :=
  if descriptor = 0 then .done 74 0 else
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 preparedStep 8 8 address descriptor 0 0 fun s index =>
  if s = Status.iterationStop then
    .bind (AddressSpace.base descriptor) fun s _ =>
    if failed s = true then fatal else .done 0 (address + index * stride)
  else if s = 0 then .done 74 0 else fatal

private def detachManaged (record descriptor : UInt64) : Action :=
  .bind (Access.read64 (record + managedOffset)) fun s managed =>
  if failed s = true then fatal else
  if managed = 0 then .done 0 0 else
  if managed = 1 then
    .bind (IPC.detach descriptor) fun s _ =>
    if failed s = true then fatal else
    .bind (Capability.detach descriptor) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else fatal

private def clearPreparedStep (i _ : UInt32) (acc record _ _ _ : UInt64) : Action :=
  if i = 1 then .done 0 acc else
  .bind (Access.write64 (record + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

private def inactiveDescriptor (descriptor : UInt64) : Action :=
  .bind (AddressSpace.root descriptor) fun s root =>
  if failed s = true then fatal else
  .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
  if failed s = true then fatal else
  if root = active then fatal else .done 0 0

/-- Abort only a checked unpublished instance. Detach provisional authority
before releasing its inactive address space, then make the empty slot free. -/
def abort (descriptor : UInt64) : Action :=
  .bind (prepared descriptor) fun s record =>
  if failed s = true then .done s 0 else
  .bind (inactiveDescriptor descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (detachManaged record descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Loader.teardown descriptor) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 64 clearPreparedStep 64 0 record 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 63 then
    .bind (Access.write64 (record + stateOffset) free) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else fatal

private def checkedActivation (record descriptor : UInt64) : Action :=
  .bind (Access.read64 (record + managedOffset)) fun s managed =>
  if failed s = true then fatal else
  if managed = 0 then
    .bind (Capability.managed descriptor) fun s active =>
    if failed s = true then fatal else
    if active = 0 then .done 0 0 else fatal
  else if managed = 1 then
    .bind (Capability.requireActive descriptor) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else fatal

/-- Publish last, after the loader and any managed boot policy have completed.
The generic scheduler is independent of image names and capability grants. -/
def activate (descriptor : UInt64) : Action :=
  .bind (prepared descriptor) fun s record =>
  if failed s = true then .done s 0 else
  .bind (checkedActivation record descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + argumentOffset)) fun s argument =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + imageOffset)) fun s image =>
  if failed s = true then fatal else
  .bind (AddressSpace.root descriptor) fun s root =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + stateOffset) runnable) fun s _ =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xf1 descriptor image argument root) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor

/-- The legacy path keeps its empty authority table and original publication
record. Ordinary loader failure still returns its exact status without a task. -/
def create (image argument : UInt64) : Action :=
  .bind (prepare image argument) fun s descriptor =>
  if failed s = true then .done s 0 else activate descriptor

/-- Prepare a managed instance, but do not make it runnable. The trusted boot
policy grants authority before calling activateManaged. Attach failures are
preflight-only; a successful attachment is recorded for rollback and reaping. -/
def prepareManaged (image argument : UInt64) : Action :=
  .bind (prepare image argument) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (Capability.attach descriptor) fun status _ =>
  if status = 255 then fatal else
  if failed status = true then
    .bind (abort descriptor) fun s _ =>
    if failed s = true then fatal else .done status 0
  else
    .bind (prepared descriptor) fun s record =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + managedOffset) 1) fun s _ =>
    if failed s = true then fatal else .done 0 descriptor

def activateManaged (descriptor : UInt64) : Action :=
  .bind (prepared descriptor) fun s record =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (record + managedOffset)) fun s managed =>
  if failed s = true then fatal else
  if managed = 1 then
    .bind (Capability.activate descriptor) fun s _ =>
    if failed s = true then fatal else activate descriptor
  else fatal

def increment (record offset : UInt64) : Action :=
  .bind (Access.read64 (record + offset)) fun s value =>
  if failed s = true then fatal else
  if value = 0xffffffffffffffff then fatal else
  .bind (Access.write64 (record + offset) (value + 1)) fun s _ =>
  if failed s = true then fatal else .done 0 (value + 1)

private def pickStep (i _ : UInt32) (acc address start _ _ : UInt64) : Action :=
  let index := (start + i.toUInt64) % capacity
  .bind (Access.read64 (address + index * stride + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = runnable then .done Status.iterationStop index else
  if dying < state then fatal else .done 0 acc

/-- Equal-priority round-robin scans at most eight records; no name, image or
launch argument participates in selection. Zero means no runnable task. -/
def select : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .bind (Access.read64 cursor) fun s start =>
  if failed s = true then fatal else
  if capacity ≤ start then fatal else
  .boundedFoldU64 8 pickStep 8 8 address start 0 0 fun s index =>
  if s = Status.iterationStop then
    let record := address + index * stride
    .bind (Access.read64 record) fun s descriptor =>
    if failed s = true then fatal else
    .bind (AddressSpace.base descriptor) fun s _ =>
    if failed s = true then fatal else
    .bind (increment record dispatchOffset) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + stateOffset) running) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 cursor ((index + 1) % capacity)) fun s _ =>
    if failed s = true then fatal else .done 0 descriptor
  else if s = 0 then .done 0 0 else fatal

/-- Only checked owned contexts can be selected. User registers and fault PCs
remain user data; privilege, translation and trap-stack authority are fixed. -/
def context (descriptor : UInt64) : Action :=
  .bind (lookup descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = running then
    .bind (AddressSpace.base descriptor) fun s base =>
    if failed s = true then fatal else
    let saved := base + AddressSpace.userContextOffset
    .bind (Access.read64 (base + 72)) fun s translation =>
    if failed s = true then fatal else
    .bind (Access.read64 (saved + 272)) fun s actual =>
    if failed s = true then fatal else
    if actual = translation then
      .bind (Process.validateStackAt base) fun s top =>
      if failed s = true then fatal else
      .bind (Access.write64 saved 0) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (saved + 264) 0x200000020) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (saved + 280) top) fun s _ =>
      if failed s = true then fatal else .done 0 saved
    else fatal
  else fatal

/-- Completion uses a previously captured inactive context. It validates the
same privilege, translation and owned trap-stack authority without sanitizing
or advancing any saved user register. A blocked user PC remains user data. -/
def savedContext (descriptor : UInt64) : Action :=
  .bind (lookup descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = blocked then
    .bind (AddressSpace.base descriptor) fun s base =>
    if failed s = true then fatal else
    .bind (Access.read64 (base + 64)) fun s root =>
    if failed s = true then fatal else
    .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
    if failed s = true then fatal else
    if active = root then fatal else
    let saved := base + AddressSpace.userContextOffset
    .bind (Access.read64 (base + 72)) fun s translation =>
    if failed s = true then fatal else
    .bind (Access.read64 (saved + 272)) fun s actual =>
    if failed s = true then fatal else
    if actual = translation then
    .bind (Access.read64 saved) fun s zero =>
    if failed s = true then fatal else
    if zero = 0 then
    .bind (Access.read64 (saved + 264)) fun s status =>
    if failed s = true then fatal else
    if status = 0x200000020 then
    .bind (Process.validateStackAt base) fun s top =>
    if failed s = true then fatal else
    .bind (Access.read64 (saved + 280)) fun s storedTop =>
    if failed s = true then fatal else
    if storedTop = top then .done 0 saved else fatal
    else fatal else fatal else fatal
  else fatal

/-- Only capture borrows this fresh descriptor base and owned-stack top. The
original hardware-frame validation and a second fresh descriptor validation run
before copying; that copy touches only the disjoint saved-context words. Live
task-row state and saved translation are still checked after the copy. -/
private def contextAt (descriptor base top : UInt64) : Action :=
  .bind (lookupRecord descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = running then
    let saved := base + AddressSpace.userContextOffset
    .bind (Access.read64 (base + 72)) fun s translation =>
    if failed s = true then fatal else
    .bind (Access.read64 (saved + 272)) fun s actual =>
    if failed s = true then fatal else
    if actual = translation then
      .bind (Access.write64 saved 0) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (saved + 264) 0x200000020) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (saved + 280) top) fun s _ =>
      if failed s = true then fatal else .done 0 saved
    else fatal
  else fatal

private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Access.read64 (source + i.toUInt64 * 8)) fun s value =>
  if failed s = true then fatal else
  .bind (Access.write64 (target + i.toUInt64 * 8) value) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

def capture (descriptor frame : UInt64) : Action :=
  .bind (Process.validateFrame frame) fun s actual =>
  if failed s = true then fatal else
  if actual = descriptor then
    .bind (AddressSpace.base descriptor) fun s base =>
    if failed s = true then fatal else
    let saved := base + AddressSpace.userContextOffset
    .boundedFoldU64 36 copyStep 36 0 frame saved 0 0 fun s count =>
    if failed s = true then fatal else
    if count = 36 then contextAt descriptor base (frame + 288) else fatal
  else fatal

def ready (descriptor reason pc : UInt64) : Action :=
  .bind (lookup descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = running then
    .bind (Access.write64 (record + reasonOffset) reason) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + pcOffset) pc) fun s _ =>
    if failed s = true then fatal else
    .bind (increment record (if reason = 1 then preemptOffset else yieldOffset)) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + stateOffset) runnable) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else fatal

def sleep (descriptor deadline pc : UInt64) : Action :=
  .bind (lookup descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = running then
    .bind (Access.write64 (record + deadlineOffset) deadline) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + pcOffset) pc) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + reasonOffset) 3) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + waitKindOffset) 1) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + stateOffset) sleeping) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else fatal

/-- Only a managed running task may suspend an already captured ECALL. The
caller advances its PC once before this transition. Epoch and full descriptor
generation bind later completion; publishing blocked is the final write. -/
def block (descriptor transaction kind deadline pc : UInt64) : Action :=
  if transaction = 0 then fatal else
  if (if kind = 2 then true else if kind = 3 then true else false) = false then fatal else
  if deadline = 0 then fatal else
  .bind (lookup descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = running then
    .bind (Access.read64 (record + managedOffset)) fun s managed =>
    if failed s = true then fatal else
    if managed = 1 then
    .bind (Capability.requireActive descriptor) fun s _ =>
    if failed s = true then fatal else
    .bind (increment record waitEpochOffset) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + waitTransactionOffset) transaction) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + waitKindOffset) kind) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + deadlineOffset) deadline) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + pcOffset) pc) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + reasonOffset) 6) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + stateOffset) blocked) fun s _ =>
    if failed s = true then fatal else .done 0 transaction
    else fatal
  else fatal

def terminate (descriptor cause code pc value : UInt64) : Action :=
  .bind (lookup descriptor) fun s record =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = dying then .done 74 0 else
  .bind (Access.write64 (record + exitOffset) code) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + causeOffset) cause) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + pcOffset) pc) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + faultOffset) value) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (record + stateOffset) dying) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor

private def wakeStep (i _ : UInt32) (acc address now _ _ : UInt64) : Action :=
  let record := address + i.toUInt64 * stride
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = sleeping then
    .bind (Access.read64 (record + deadlineOffset)) fun s deadline =>
    if failed s = true then fatal else
    if deadline ≤ now then
      .bind (Access.write64 (record + wakeTimeOffset) now) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (record + waitKindOffset) 0) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (record + stateOffset) runnable) fun s _ =>
      if failed s = true then fatal else .done 0 (acc + 1)
    else .done 0 acc
  else if dying < state then fatal else .done 0 acc

def wakeDue (now : UInt64) : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 wakeStep 8 0 address now 0 0 fun s count => .done s count

private def completeBlocked (record descriptor epoch transaction now : UInt64) : Action :=
  .bind (savedContext descriptor) fun s context =>
  if failed s = true then fatal else
  .bind (IPC.completeWait descriptor transaction) fun status value =>
  if status = 255 then fatal else
  if status = IPC.blockedStatus then fatal else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + waitEpochOffset)) fun s actualEpoch =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + waitTransactionOffset)) fun s actualTransaction =>
  if failed s = true then fatal else
  .bind (Access.read64 record) fun s actualDescriptor =>
  if failed s = true then fatal else
  if state = blocked then if actualEpoch = epoch then
  if actualTransaction = transaction then if actualDescriptor = descriptor then
    .bind (Access.write64 (context + 80) status.toUInt64) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (context + 88) value) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + deadlineOffset) 0) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + waitKindOffset) 0) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + waitTransactionOffset) 0) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + wakeTimeOffset) now) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (record + stateOffset) runnable) fun s _ =>
    if failed s = true then fatal else .done 0 1
  else fatal else fatal else fatal else fatal

private def pollIPCStep (i _ : UInt32) (acc address now _ _ : UInt64) : Action :=
  let record := address + i.toUInt64 * stride
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if dying < state then fatal else
  if (if runnable ≤ state then if state < dying then true else false else false) = true then
    .bind (Access.read64 (record + managedOffset)) fun s managed =>
    if failed s = true then fatal else
    if managed = 0 then .done 0 acc else
    if managed = 1 then
      .bind (Access.read64 record) fun s descriptor =>
      if failed s = true then fatal else
      .bind (lookup descriptor) fun s checked =>
      if failed s = true then fatal else
      if checked = record then
      .bind (Access.read64 (record + waitEpochOffset)) fun s epoch =>
      if failed s = true then fatal else
      .bind (Access.read64 (record + waitTransactionOffset)) fun s transaction =>
      if failed s = true then fatal else
      .bind (IPC.poll descriptor) fun status _ =>
      if status = Lemma.User.IPCABI.wouldBlock then .done 0 acc else
      if status = 0 then
        if state = blocked then
          if transaction = 0 then fatal else
          .bind (completeBlocked record descriptor epoch transaction now) fun s woke =>
          if failed s = true then fatal else .done 0 (acc + woke)
        else .done 0 acc
      else fatal
      else fatal
    else fatal
  else .done 0 acc

/-- Progress outstanding calls even before CallWait. Only a blocked task has
saved registers completed here; Ready packets for a runnable caller stay held. -/
def pollIPC (now : UInt64) : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 pollIPCStep 8 0 address now 0 0 fun s woke =>
  if failed s = true then fatal else .done 0 woke

private def intervalStep (i _ : UInt32) (acc address now _ _ : UInt64) : Action :=
  .bind (Access.read64 (address + i.toUInt64 * stride + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if (if state = sleeping then true else if state = blocked then true else false) = true then
    .bind (Access.read64 (address + i.toUInt64 * stride + deadlineOffset)) fun s deadline =>
    if failed s = true then fatal else
    let remaining := if deadline ≤ now then 1000 else deadline - now
    let bounded := if remaining < 1000 then 1000 else remaining
    .done 0 (if bounded < acc then bounded else acc)
  else if dying < state then fatal else .done 0 acc

def interval (now quantum : UInt64) : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 intervalStep 8 quantum address now 0 0 fun s ticks => .done s ticks

private def clearStep (i _ : UInt32) (acc record _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (record + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

private def reapOne (record : UInt64) : Action :=
  .bind (Access.read64 record) fun s descriptor =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + exitOffset)) fun s code =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + causeOffset)) fun s cause =>
  if failed s = true then fatal else
  .bind (AddressSpace.lookup descriptor 0x20000 1) fun s physical =>
  if failed s = true then fatal else
  .bind (Access.read64 physical) fun s data =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xf4 descriptor code data cause) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + preemptOffset)) fun s preemptions =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + yieldOffset)) fun s yields =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + dispatchOffset)) fun s dispatches =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xf5 descriptor preemptions yields dispatches) fun s _ =>
  if failed s = true then fatal else
  .bind Frames.remaining fun s before =>
  if failed s = true then fatal else
  .bind (detachManaged record descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (Loader.teardown descriptor) fun s _ =>
  if failed s = true then fatal else
  .boundedFoldU64 64 clearStep 64 0 record 0 0 0 fun s cleared =>
  if failed s = true then fatal else
  if cleared = 64 then
    .bind Frames.remaining fun s after =>
    if failed s = true then fatal else
    Lemma.Kernel.Console.record 0xf6 descriptor before after 0
  else fatal

private def reapStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  let record := address + i.toUInt64 * stride
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = dying then
    .bind (reapOne record) fun s _ =>
    if failed s = true then fatal else .done 0 (acc + 1)
  else if dying < state then fatal else .done 0 acc

/-- This API is called only after typed restoration onto the boot stack. The
old task root and both owned trap-stack pages remain live until that boundary. -/
def reap : Action :=
  .bind (Access.read64 Process.control) fun s current =>
  if failed s = true then fatal else
  if current = 0 then
    .bind (Access.read64 (Process.control + 8)) fun s root =>
    if failed s = true then fatal else
    .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
    if failed s = true then fatal else
    if root = active then
      .bind table fun s address =>
      if failed s = true then fatal else
      .boundedFoldU64 8 reapStep 8 0 address 0 0 0 fun s count => .done s count
    else fatal
  else fatal

def query (descriptor : UInt64) : Action :=
  .bind (lookup descriptor) fun s record =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (record + stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (AddressSpace.lookup descriptor 0x20000 1) fun s physical =>
  if failed s = true then fatal else
  .bind (Access.read64 physical) fun s data =>
  if failed s = true then fatal else
  .bind (Access.read64 (physical + 24)) fun s counter =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xfc descriptor state data counter) fun s _ =>
  if failed s = true then fatal else .done 0 descriptor

private def queryStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (address + i.toUInt64 * stride + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if dying < state then fatal else
  if (if runnable ≤ state then if state < dying then true else false else false) = true then
    .bind (Access.read64 (address + i.toUInt64 * stride)) fun s id =>
    if failed s = true then fatal else
    .bind (query id) fun s _ =>
    if failed s = true then fatal else .done 0 (acc + 1)
  else .done 0 acc

def queryAll : Action :=
  .bind table fun s address =>
  if failed s = true then fatal else
  .boundedFoldU64 8 queryStep 8 0 address 0 0 0 fun s count => .done s count

end Lemma.Kernel.Task
