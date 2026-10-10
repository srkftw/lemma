import Lemma.Kernel.Memory.UserCopy
import Lemma.Platform.LemmaVM.ConsoleDevice

/-! One bounded UART boundary for service configurations. Header framing is
checked; valid bodies are opaque bytes. A complete payload is retained until
its whole destination fits. The sole User reader is a boot-bound full AS
handle; no User can reset this object or read diagnostic packets. -/
namespace Lemma.Kernel.KernelInput
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def control : UInt64 := Lemma.Platform.LemmaVM.Layout.inputControlValue
def magic : UInt64 := 0x31504e49414d454c
def frameVersion : UInt64 := 1
def ringOffset : UInt64 := 128
def ringCapacity : UInt64 := 512
def pendingOffset : UInt64 := 640
def pendingCapacity : UInt64 := 168
def scratchOffset : UInt64 := 832
def diagnosticOffset : UInt64 := 1088
def diagnosticBytes : UInt64 := 40
def readerOffset : UInt64 := 32
def headOffset : UInt64 := 40
def countOffset : UInt64 := 48
def stateOffset : UInt64 := 56
def headerOffset : UInt64 := 64
def headerCountOffset : UInt64 := 72
def classOffset : UInt64 := 80
def lengthOffset : UInt64 := 88
def receivedOffset : UInt64 := 96
def diagnosticReadyOffset : UInt64 := 104
def headerState : UInt64 := 0
def bodyState : UInt64 := 1
def pendingState : UInt64 := 2
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 255 0

def get (address : UInt64) : Action :=
  .bind (Access.read64 address) fun s value =>
  if failed s = true then fatal else .done 0 value

def put (address value : UInt64) : Action :=
  .bind (Access.write64 address value) fun s _ =>
  if failed s = true then fatal else .done 0 0

private def bodyValid (packetClass length : UInt64) : Bool :=
  if packetClass = 1 then
    if 0 < length then if length ≤ pendingCapacity then true else false else false
  else if packetClass = 2 then if length = diagnosticBytes then true else false
  else false

/-- Every cached physical frame address follows full owner/purpose/generation,
zero-pin and self-handle checks. Parser bounds are validated before byte access. -/
def table : Action :=
  .bind (get control) fun s handle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s base =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount 1 handle) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then
  .bind (get base) fun s tag =>
  if failed s = true then fatal else
  .bind (get (base + 8)) fun s version =>
  if failed s = true then fatal else
  .bind (get (base + 16)) fun s selectedMode =>
  if failed s = true then fatal else
  .bind (get (base + 24)) fun s self =>
  if failed s = true then fatal else
  if tag = magic then if version = frameVersion then if self = handle then
  if (if selectedMode = 1 then true else if selectedMode = 2 then true else false) = true then
  .bind (get (base + headOffset)) fun s head =>
  if failed s = true then fatal else
  .bind (get (base + countOffset)) fun s count =>
  if failed s = true then fatal else
  .bind (get (base + stateOffset)) fun s state =>
  if failed s = true then fatal else
  .bind (get (base + headerOffset)) fun s header =>
  if failed s = true then fatal else
  .bind (get (base + headerCountOffset)) fun s headerCount =>
  if failed s = true then fatal else
  .bind (get (base + classOffset)) fun s packetClass =>
  if failed s = true then fatal else
  .bind (get (base + lengthOffset)) fun s length =>
  if failed s = true then fatal else
  .bind (get (base + receivedOffset)) fun s received =>
  if failed s = true then fatal else
  .bind (get (base + diagnosticReadyOffset)) fun s ready =>
  if failed s = true then fatal else
  .bind (get (base + 112)) fun s reserved1 =>
  if failed s = true then fatal else
  .bind (get (base + 120)) fun s reserved2 =>
  if failed s = true then fatal else
  if head < ringCapacity then if count ≤ ringCapacity then if ready ≤ 1 then
  if reserved1 ||| reserved2 = 0 then
  if state = headerState then
    if headerCount < 8 then if packetClass ||| length ||| received = 0 then
      if headerCount = 0 then if header = 0 then .done 0 base else fatal
      else if header >>> (headerCount * 8) = 0 then .done 0 base else fatal
    else fatal else fatal
  else if bodyValid packetClass length = true then
    if header ||| headerCount = 0 then
      if state = bodyState then if received < length then .done 0 base else fatal
      else if state = pendingState then if received = length then .done 0 base else fatal
      else fatal
    else fatal
  else fatal
  else fatal else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal

/-- Only an explicitly boot-cleared zero control cell selects legacy mode. -/
def mode : Action :=
  .bind (get control) fun s handle =>
  if failed s = true then fatal else
  if handle = 0 then .done 0 0 else
  .bind table fun s base =>
  if failed s = true then fatal else get (base + 16)

/-- Boot-only one-time publication. The real allocator zeroes all parser,
queue, ring and scratch bytes before the frame handle becomes visible. -/
def init (selectedMode : UInt64) : Action :=
  if (if selectedMode = 1 then true else if selectedMode = 2 then true else false) = true then
  .bind (get control) fun s existing =>
  if failed s = true then fatal else
  if existing = 0 then
  .bind (Frames.allocate 1 1) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s base =>
  if failed s = true then fatal else
  .bind (put (base + 8) frameVersion) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 16) selectedMode) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + 24) handle) fun s _ =>
  if failed s = true then fatal else
  .bind (put base magic) fun s _ =>
  if failed s = true then fatal else
  .bind (put control handle) fun s _ =>
  if failed s = true then fatal else .done 0 handle
  else .done 16 0
  else .done 16 0

/-- Trusted boot binding is the final ordinary-failable construction step.
It can be repeated only for the identical full descriptor, never reassigned. -/
def bindReader (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s _ =>
  if failed s = true then .done 80 0 else
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + readerOffset)) fun s existing =>
  if failed s = true then fatal else
  if existing = 0 then
    .bind (put (base + readerOffset) descriptor) fun s _ =>
    if failed s = true then fatal else .done 0 descriptor
  else if existing = descriptor then .done 0 descriptor else .done 72 0

private def resetParser (base : UInt64) : Action :=
  .bind (put (base + headerOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + headerCountOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + classOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + lengthOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + receivedOffset) 0) fun s _ =>
  if failed s = true then fatal else put (base + stateOffset) headerState

private def ringPublishStep (i _ : UInt32) (acc base tail _ _ : UInt64) : Action :=
  let index := i.toUInt64
  .bind (Access.read8 (base + pendingOffset + index)) fun s byte =>
  if failed s = true then fatal else
  .bind (Access.write8 (base + ringOffset + (tail + index) % ringCapacity) byte) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

private def diagnosticPublishStep (i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  let index := i.toUInt64
  .bind (Access.read8 (base + pendingOffset + index)) fun s byte =>
  if failed s = true then fatal else
  .bind (Access.write8 (base + diagnosticOffset + index) byte) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

/-- Returns12 without consuming another UART byte when a complete bounded
payload cannot fit. Normal mode discards the whole opaque diagnostic body. -/
private def flushPending (base : UInt64) : Action :=
  .bind (get (base + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = pendingState then
  .bind (get (base + classOffset)) fun s packetClass =>
  if failed s = true then fatal else
  .bind (get (base + lengthOffset)) fun s length =>
  if failed s = true then fatal else
  if packetClass = 1 then
  .bind (get (base + headOffset)) fun s head =>
  if failed s = true then fatal else
  .bind (get (base + countOffset)) fun s count =>
  if failed s = true then fatal else
  if length ≤ ringCapacity - count then
  .boundedFoldU64 168 ringPublishStep length.toUInt32 0 base ((head + count) % ringCapacity) 0 0 fun s copied =>
  if failed s = true then fatal else
  if copied = length then
  .bind (put (base + countOffset) (count + length)) fun s _ =>
  if failed s = true then fatal else resetParser base
  else fatal
  else .done 12 0
  else if packetClass = 2 then
  .bind (get (base + 16)) fun s selectedMode =>
  if failed s = true then fatal else
  if selectedMode = 1 then resetParser base else
  if selectedMode = 2 then
  .bind (get (base + diagnosticReadyOffset)) fun s ready =>
  if failed s = true then fatal else
  if ready = 0 then
  .boundedFoldU64 40 diagnosticPublishStep 40 0 base 0 0 0 fun s copied =>
  if failed s = true then fatal else
  if copied = diagnosticBytes then
  .bind (put (base + diagnosticReadyOffset) 1) fun s _ =>
  if failed s = true then fatal else resetParser base
  else fatal
  else .done 12 0
  else fatal else fatal
  else .done 0 0

private def validHeader (word : UInt64) : Bool :=
  if word &&& 0xffffffff = 0x31494d4c then
    if (word >>> 40) &&& 255 = 0 then bodyValid ((word >>> 32) &&& 255) (word >>> 48)
    else false
  else false

private def magicByte (index : UInt64) : UInt64 :=
  (0x31494d4c >>> (index * 8)) &&& 255

private def startBody (base word : UInt64) : Action :=
  .bind (put (base + headerOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + headerCountOffset) 0) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + classOffset) ((word >>> 32) &&& 255)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + lengthOffset) (word >>> 48)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + receivedOffset) 0) fun s _ =>
  if failed s = true then fatal else put (base + stateOffset) bodyState

private def acceptHeaderByte (base byte : UInt64) : Action :=
  .bind (get (base + headerCountOffset)) fun s count =>
  if failed s = true then fatal else
  .bind (get (base + headerOffset)) fun s header =>
  if failed s = true then fatal else
  if count < 4 then
    if byte = magicByte count then
      .bind (put (base + headerOffset) (header ||| (byte <<< (count * 8)))) fun s _ =>
      if failed s = true then fatal else put (base + headerCountOffset) (count + 1)
    else if byte = magicByte 0 then
      .bind (put (base + headerOffset) byte) fun s _ =>
      if failed s = true then fatal else put (base + headerCountOffset) 1
    else resetParser base
  else
    let next := header ||| (byte <<< (count * 8))
    if count = 7 then
      if validHeader next = true then startBody base next else resetParser base
    else
      .bind (put (base + headerOffset) next) fun s _ =>
      if failed s = true then fatal else put (base + headerCountOffset) (count + 1)

private def acceptByte (base byte : UInt64) : Action :=
  .bind (get (base + stateOffset)) fun s state =>
  if failed s = true then fatal else
  if state = headerState then acceptHeaderByte base byte else
  if state = bodyState then
  .bind (get (base + receivedOffset)) fun s received =>
  if failed s = true then fatal else
  .bind (get (base + lengthOffset)) fun s length =>
  if failed s = true then fatal else
  if received < length then
  .bind (Access.write8 (base + pendingOffset + received) byte) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + receivedOffset) (received + 1)) fun s _ =>
  if failed s = true then fatal else
  if received + 1 = length then put (base + stateOffset) pendingState else .done 0 0
  else fatal else fatal

private def pollStep (_i _ : UInt32) (acc base _ _ _ : UInt64) : Action :=
  .bind (flushPending base) fun s _ =>
  if s = 12 then .done Status.iterationStop acc else
  if failed s = true then fatal else
  .bind (Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep 0 0 0 0 0 0 0) fun s byte =>
  if s = Status.iterationStop then
    .bind (acceptByte base byte) fun s _ =>
    if failed s = true then fatal else .done 0 (acc + 1)
  else if s = 0 then .done Status.iterationStop acc else .done s acc

/-- No more than64 actual single receive polls. Internal iterationStop means
an observed byte even when it is00; it is never exposed as ordinary success. -/
def poll : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .boundedFoldU64 64 pollStep 64 0 base 0 0 0 fun s consumed =>
  if (if s = 0 then true else if s = Status.iterationStop then true else false) = true then
    .bind (flushPending base) fun s _ =>
    if (if s = 0 then true else if s = 12 then true else false) = true then .done 0 consumed
    else fatal
  else .done s consumed

private def snapshotStep (i _ : UInt32) (acc base head _ _ : UInt64) : Action :=
  let index := i.toUInt64
  .bind (Access.read8 (base + ringOffset + (head + index) % ringCapacity)) fun s byte =>
  if failed s = true then fatal else
  .bind (Access.write8 (base + scratchOffset + index) byte) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

/-- Complete offered User range preflight precedes even empty reads. Snapshot
copy and exact copied==count precede advancing the ring; invalid User buffers
leave every queued byte available for retry. No physical User alias persists. -/
def read (descriptor pointer length : UInt64) : Action :=
  .bind (UserCopy.validateWrite descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + readerOffset)) fun s reader =>
  if failed s = true then fatal else
  if reader = descriptor then
  if length = 0 then .done 0 0 else
  .bind (get (base + countOffset)) fun s available =>
  if failed s = true then fatal else
  if available = 0 then .done 12 0 else
  let count := if length ≤ available then length else available
  .bind (get (base + headOffset)) fun s head =>
  if failed s = true then fatal else
  .boundedFoldU64 256 snapshotStep count.toUInt32 0 base head 0 0 fun s copied =>
  if failed s = true then fatal else
  if copied = count then
  .bind (get (base + 24)) fun s handle =>
  if failed s = true then fatal else
  .bind (UserCopy.copyToUser descriptor pointer handle scratchOffset count) fun s copied =>
  if failed s = true then .done s 0 else
  if copied = count then
  .bind (put (base + headOffset) ((head + count) % ringCapacity)) fun s _ =>
  if failed s = true then fatal else
  .bind (put (base + countOffset) (available - count)) fun s _ =>
  if failed s = true then fatal else .done 0 count
  else fatal else fatal
  else .done 72 0

/-- Trusted development Entry only. The normal closure has no dispatcher; its
poller discards a whole validated class2 body without inspecting command words. -/
def diagnosticPacket : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 16)) fun s selectedMode =>
  if failed s = true then fatal else
  if selectedMode = 2 then
  .bind (get (base + diagnosticReadyOffset)) fun s ready =>
  if failed s = true then fatal else
  if ready = 1 then .done 0 (base + diagnosticOffset) else .done 12 0
  else .done 72 0

def consumeDiagnostic : Action :=
  .bind table fun s base =>
  if failed s = true then fatal else
  .bind (get (base + 16)) fun s selectedMode =>
  if failed s = true then fatal else
  if selectedMode = 2 then
  .bind (get (base + diagnosticReadyOffset)) fun s ready =>
  if failed s = true then fatal else
  if ready = 1 then put (base + diagnosticReadyOffset) 0 else .done 16 0
  else .done 72 0

end Lemma.Kernel.KernelInput
