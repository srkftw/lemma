import Lemma.Drivers.Multimodal
import Lemma.Multimodal.Permissions
import Lemma.Kernel.Capability
import Lemma.Kernel.Memory.UserCopy

/-! Named capability service for converter14. The notebook's local control
endpoint is the only authority; the installer, Arithmetic and tutor have none.
A grant has independent purpose bits, session, epoch, expiry and byte budget.
Payloads never use the tiny managed ByteArray path or gain archive durability. -/
namespace Lemma.Platform.LemmaSim.MultimodalService

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.User

/-- Additive syscall69 service version; legacy controller1 remains supported. -/
def version : UInt64 := 3
def state : UInt64 := 0x804e0300
private def get (offset : UInt64) : Action := Access.read64 (state + offset)
private def put (offset value : UInt64) : Action := Access.write64 (state + offset) value
private def row (stream : UInt64) : UInt64 := 64 + stream * 64
private def fatal : Action := .done 255 0
private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

def configure (key : UInt64) : Action :=
  .bind Lemma.Drivers.Multimodal.discover fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 104 clearStep 104 0 0 0 0 0 fun s _ => if mmFailed s = true then fatal else
  .bind (Frames.allocate 1 1) fun s scratch => if mmFailed s = true then .done s 0 else
  .bind (put 0 key) fun s _ => if mmFailed s = true then fatal else
  .bind (put 8 scratch) fun s _ => if mmFailed s = true then fatal else
  .bind (Frames.allocate 1 1) fun s dma => if mmFailed s = true then .done s 0 else
  .bind (put 16 dma) fun s _ => if mmFailed s = true then fatal else
  .bind (Frames.allocate 1 1) fun s ring => if mmFailed s = true then .done s 0 else put 640 ring

private def authorize (descriptor handle : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s key =>
  if mmFailed s = true then .done s 0 else
  .bind (get 0) fun s expected => if mmFailed s = true then fatal else
  if expected = 0 then .done 7 0 else if mmDifferent key expected = true then .done 7 0 else .done 0 key

private def metadata (descriptor pointer bytes : UInt64) : Action :=
  .bind (get 8) fun s scratch => if mmFailed s = true then fatal else
  .bind (UserCopy.copyFromUser descriptor pointer scratch 0 bytes) fun s _ => if mmFailed s = true then .done s 0 else
  Frames.resolvePurpose 1 scratch 1

private def now : Action := IO.read64 (Lemma.Drivers.Multimodal.base + 24)
private def faultStatus (value : UInt64) : UInt8 :=
  if 15 < value then 2 else value.toUInt8

private def grant (descriptor stream pointer : UInt64) : Action :=
  .bind (metadata descriptor pointer 64) fun s data => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 data) fun s magic => if mmFailed s = true then fatal else
  if mmDifferent magic 0x31474d4d = true then .done 2 0 else
  .bind (Access.read64 (data + 8)) fun s session => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 16)) fun s bits => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s rate => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 32)) fun s extent => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 40)) fun s expiry => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 48)) fun s previous => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 56)) fun s format => if mmFailed s = true then fatal else
  if mmDifferent format 1 = true then .done 2 0 else
  .bind now fun s ticks => if mmFailed s = true then .done s 0 else
  let error := Lemma.Multimodal.Permissions.request stream bits rate extent expiry ticks session
  if mmDifferent error 0 = true then .done error.toUInt8 0 else
  .bind (get (row stream)) fun s epoch => if mmFailed s = true then fatal else
  if mmDifferent previous epoch = true then .done 4 0 else
  let next := Lemma.Multimodal.Permissions.nextEpoch epoch
  if next = 0 then .done 14 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 80 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.command stream 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put (row stream) next) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 8) session) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 16) bits) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 24) expiry) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 32) extent) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 40) rate) fun s _ => if mmFailed s = true then fatal else
  .bind (if stream = 0 then .done 0 0 else if stream = 6 then .done 0 0 else if stream = 7 then .done 0 0 else
    .bind Lemma.Drivers.Multimodal.discover fun s _ => if mmFailed s = true then .done s 0 else
    .bind (IO.write64 (Lemma.Drivers.Multimodal.base + 56) 0) fun s _ => if mmFailed s = true then .done s 0 else
    Lemma.Drivers.Multimodal.write stream 96 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 104 expiry) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 80 next) fun s _ => .done s next

private def current (stream epoch needed : UInt64) : Action :=
  .bind (get (row stream)) fun s actual => if mmFailed s = true then fatal else
  .bind (get (row stream + 16)) fun s bits => if mmFailed s = true then fatal else
  .bind (get (row stream + 24)) fun s expiry => if mmFailed s = true then fatal else
  .bind now fun s ticks => if mmFailed s = true then .done s 0 else
  if epoch = 0 then .done 7 0 else if mmDifferent actual epoch = true then .done 4 0 else
  if mmDifferent (bits &&& needed) (needed) = true then .done 7 0 else
  if expiry ≤ ticks then
    .bind (Lemma.Drivers.Multimodal.write stream 80 0) fun s _ => if mmFailed s = true then .done s 0 else .done 8 0
  else .done 0 bits

private def revoke (stream : UInt64) : Action :=
  .bind (Lemma.Drivers.Multimodal.write stream 80 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get (row stream)) fun s epoch => if mmFailed s = true then fatal else
  .bind (put (row stream + 16) 0) fun s _ => if mmFailed s = true then fatal else
  let next := Lemma.Multimodal.Permissions.nextEpoch epoch
  if next = 0 then .done 14 epoch else
  .bind (put (row stream) next) fun s _ => .done s next

private def configureStream (descriptor stream pointer epoch : UInt64) : Action :=
  .bind (current stream epoch (if stream = 8 then 64 else 1)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (metadata descriptor pointer 32) fun s data => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 data) fun s gain => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 8)) fun s period => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 16)) fun s exposure => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s selector => if mmFailed s = true then fatal else
  if gain = 0 then .done 3 0 else if 64 < gain then .done 3 0 else
  if period < 8 then .done 3 0 else if exposure = 0 then .done 3 0 else
  if period < exposure then .done 3 0 else
  .bind (get (row stream + 40)) fun s rate => if mmFailed s = true then fatal else
  let requiredRate := 100000000 / period + (if 100000000 % period = 0 then 0 else 1)
  if rate < requiredRate then .done 7 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 8) fun s mode => if mmFailed s = true then .done s 0 else
  if (if mode = 2 then true else if mode = 3 then true else false) = false then .done 5 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 48 gain) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 56 period) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 64 exposure) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 72 selector) fun s _ => if mmFailed s = true then .done s 0 else
  Lemma.Drivers.Multimodal.command stream 2

private def take (descriptor stream pointer epoch : UInt64) : Action :=
  .bind (get 40) fun s active => if mmFailed s = true then fatal else
  if active = stream + 1 then .done 6 0 else
  .bind (current stream epoch 3) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get (row stream + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < 64 then .done 9 0 else
  .bind (UserCopy.validateWrite descriptor pointer 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 8) fun s scratch => if mmFailed s = true then fatal else
  .bind (Lemma.Drivers.Multimodal.take stream scratch) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (UserCopy.copyToUser descriptor pointer scratch 0 64) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 32) (remaining - 64)) fun s _ => .done s sequence

private def wipeRecordStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (address + i.toUInt64 * 8) 0) fun s _ => .done s acc

private def releaseRecord : Action :=
  .bind (get 16) fun s handle => if mmFailed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address => if mmFailed s = true then fatal else
  .boundedFoldU64 8 wipeRecordStep 8 0 address 0 0 0 fun s _ => if mmFailed s = true then fatal else
  .bind (put 24 0) fun s _ => if mmFailed s = true then fatal else
  .bind (put 32 0) fun s _ => if mmFailed s = true then fatal else
  .bind (put 48 0) fun s _ => if mmFailed s = true then fatal else
  .bind (put 56 0) fun s _ => if mmFailed s = true then fatal else put 40 0

/-- A new grant may recover a retired client's completed private transfer.
Never wipe or reuse its frame while the controller can still write a beat. -/
private def reclaimRetiredRecord : Action :=
  .bind (get 40) fun s active => if mmFailed s = true then fatal else
  if active = 0 then .done 0 0 else if 8 < active then fatal else
  let stream := active - 1
  .bind (get 48) fun s oldEpoch => if mmFailed s = true then fatal else
  .bind (get (row stream)) fun s actualEpoch => if mmFailed s = true then fatal else
  .bind (get (row stream + 16)) fun s bits => if mmFailed s = true then fatal else
  .bind (get (row stream + 24)) fun s expiry => if mmFailed s = true then fatal else
  .bind now fun s ticks => if mmFailed s = true then .done s 0 else
  if oldEpoch = actualEpoch then if mmDifferent (bits) (0) = true then if ticks < expiry then .done 6 0
    else reclaim stream else reclaim stream else reclaim stream
where
  reclaim (stream : UInt64) : Action :=
    .bind (Lemma.Drivers.Multimodal.read stream 184) fun s status => if mmFailed s = true then .done s 0 else
    if status = 1 then .done 6 0 else
    if (if status = 2 then true else if status = 3 then true else false) = false then fatal else releaseRecord

/-- The controller owns exactly one in-flight eight-word record. Its target is
an independently allocated kernel frame, never an application supplied physical
address or the metadata scratch page. Fields24..56 retain only logical request
identity; no borrowed user mapping survives the nonpreemptible syscall. -/
private def beginRecord (descriptor stream pointer epoch : UInt64) : Action :=
  if 8 ≤ stream then .done 2 0 else
  .bind (current stream epoch 3) fun s _ => if mmFailed s = true then .done s 0 else
  .bind reclaimRetiredRecord fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 16) fun s fault => if mmFailed s = true then .done s 0 else
  if mmDifferent (fault) (0) = true then .done (faultStatus fault) 0 else
  .bind (get (row stream + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < 64 then .done 9 0 else
  .bind (UserCopy.validateWrite descriptor pointer 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 144) fun s queued => if mmFailed s = true then .done s 0 else
  if queued = 0 then .done 6 0 else
  .bind (get 16) fun s handle => if mmFailed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s destination => if mmFailed s = true then fatal else
  .bind (Lemma.Drivers.Multimodal.read stream 224) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 32) fun s controllerEpoch => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 160 destination) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 168 8) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.write stream 176 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 184) fun s status => if mmFailed s = true then .done s 0 else
  if (if status = 1 then true else if status = 2 then true else false) = false then .done 5 0 else
  .bind (put 24 descriptor) fun s _ => if mmFailed s = true then fatal else
  .bind (put 32 pointer) fun s _ => if mmFailed s = true then fatal else
  .bind (put 48 epoch) fun s _ => if mmFailed s = true then fatal else
  .bind (put 56 sequence) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 48) controllerEpoch) fun s _ => if mmFailed s = true then fatal else
  .bind (put 40 (stream + 1)) fun s _ => .done s sequence

private def finishRecord (descriptor stream pointer epoch : UInt64) : Action :=
  if 8 ≤ stream then .done 2 0 else
  .bind (get 40) fun s active => if mmFailed s = true then fatal else
  if mmDifferent (active) (stream + 1) = true then .done 5 0 else
  .bind (get 24) fun s owner => if mmFailed s = true then fatal else
  .bind (get 32) fun s destination => if mmFailed s = true then fatal else
  .bind (get 48) fun s requestedEpoch => if mmFailed s = true then fatal else
  if mmDifferent (owner) (descriptor) = true then .done 7 0 else
  if mmDifferent (destination) (pointer) = true then .done 4 0 else
  if mmDifferent (requestedEpoch) (epoch) = true then .done 4 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 184) fun s status => if mmFailed s = true then .done s 0 else
  if status = 1 then .done 6 0 else
  if mmDifferent (status) (2) = true then .bind releaseRecord fun s _ => if mmFailed s = true then fatal else .done 5 0 else
  .bind (current stream epoch 3) fun s _ =>
  if mmFailed s = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 16) fun s fault =>
  if mmFailed s = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done s 0 else
  if mmDifferent (fault) (0) = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done (faultStatus fault) 0 else
  .bind (get 16) fun s handle => if mmFailed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address => if mmFailed s = true then fatal else
  .bind (get 56) fun s expectedSequence => if mmFailed s = true then fatal else
  .bind (get (row stream + 48)) fun s expectedEpoch => if mmFailed s = true then fatal else
  .bind (Access.read64 (address + 32)) fun s sequence => if mmFailed s = true then fatal else
  .bind (Access.read64 (address + 40)) fun s actualEpoch => if mmFailed s = true then fatal else
  if mmDifferent (sequence) (expectedSequence) = true then .bind releaseRecord fun _ _ => .done 4 0 else
  if mmDifferent (actualEpoch) (expectedEpoch) = true then .bind releaseRecord fun _ _ => .done 4 0 else
  .bind (UserCopy.copyToUser descriptor pointer handle 0 64) fun s _ =>
  if mmFailed s = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done s 0 else
  .bind (get (row stream + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < 64 then fatal else
  .bind (put (row stream + 32) (remaining - 64)) fun s _ => if mmFailed s = true then fatal else
  .bind releaseRecord fun s _ => .done s sequence

/-- S16_LE samples are ordinary data. A batch may be partially accepted when
its lease expires; the returned count and byte charge include only verified
controller submissions. Acceptance is not playback or audible presentation. -/
private def pcmStep (i _ : UInt32) (accepted data epoch _ _ : UInt64) : Action :=
  .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s accepted else
  .bind (Access.read8 (data + 32 + i.toUInt64 * 2)) fun s low => if mmFailed s = true then .done s accepted else
  .bind (Access.read8 (data + 33 + i.toUInt64 * 2)) fun s high => if mmFailed s = true then .done s accepted else
  .bind (Lemma.Drivers.Multimodal.read 8 240) fun s before => if mmFailed s = true then .done s accepted else
  if before = 0xffffffffffffffff then .done 14 accepted else
  .bind (Lemma.Drivers.Multimodal.write 8 112 (low + high * 256)) fun s _ => if mmFailed s = true then .done s accepted else
  .bind (Lemma.Drivers.Multimodal.read 8 240) fun s after => if mmFailed s = true then .done s accepted else
  if mmDifferent (after) (before + 1) = true then .done 6 accepted else .done 0 (accepted + 1)

private def pcmBatch (descriptor stream pointer epoch : UInt64) : Action :=
  if mmDifferent (stream) (8) = true then .done 2 0 else
  .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (metadata descriptor pointer 32) fun s data => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 data) fun s magic => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 8)) fun s format => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 16)) fun s count => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s reserved => if mmFailed s = true then fatal else
  if mmDifferent (magic) (0x31424350) = true then .done 2 0 else if mmDifferent (format) (1) = true then .done 2 0 else
  if mmDifferent (reserved) (0) = true then .done 2 0 else if count = 0 then .done 3 0 else if 16 < count then .done 3 0 else
  .bind (get (row 8 + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < count * 8 then .done 9 0 else
  .bind (Lemma.Drivers.Multimodal.read 8 144) fun s queued => if mmFailed s = true then .done s 0 else
  if 16 < queued then .done 5 0 else if 16 - queued < count then .done 6 0 else
  .bind (metadata descriptor pointer (32 + count * 2)) fun s data => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 16 pcmStep count.toUInt32 0 data epoch 0 0 fun status accepted =>
  .bind (put (row 8 + 32) (remaining - accepted * 8)) fun s _ => if mmFailed s = true then fatal else .done status accepted

/-- Controller2's playback ring has one lifetime-owned kernel frame. State640
holds its frame handle;648..704 bind descriptor, grant and controller epochs,
accepted frontier, raw counter baselines, ownership and the exact EOF frontier.
The controller may retain a read after cancellation. Neither a new owner nor a
revoked caller can free, wipe or reuse that frame until the held read retires. -/
private def ringABI : Action :=
  .bind (IO.read64 (Lemma.Drivers.Multimodal.base + 8)) fun s abi => if mmFailed s = true then .done s 0 else
  if abi = 2 then .done 0 2 else .done 2 0
private def ringRead (offset : UInt64) : Action := IO.read64 (Lemma.Drivers.Multimodal.base + offset)
private def ringWrite (offset value : UInt64) : Action := IO.write64 (Lemma.Drivers.Multimodal.base + offset) value

private def ringOwner (descriptor epoch : UInt64) : Action :=
  .bind (get 696) fun s owned => if mmFailed s = true then fatal else
  if owned = 0 then .done 5 0 else
  .bind (get 648) fun s owner => if mmFailed s = true then fatal else
  if mmDifferent owner descriptor = true then .done 7 0 else
  .bind (get 656) fun s requested => if mmFailed s = true then fatal else
  if mmDifferent requested epoch = true then .done 4 0 else .done 0 0

private def ringCurrent (descriptor epoch : UInt64) : Action :=
  .bind (ringOwner descriptor epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 688) fun s saved => if mmFailed s = true then fatal else
  .bind (Lemma.Drivers.Multimodal.read 8 32) fun s actual => if mmFailed s = true then .done s 0 else
  if mmDifferent actual saved = true then .done 4 0 else .done 0 0

private def beginRing (descriptor stream pointer epoch : UInt64) : Action :=
  if mmDifferent stream 8 = true then .done 2 0 else
  .bind ringABI fun s _ => if mmFailed s = true then .done s 0 else
  .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringRead 144) fun s status => if mmFailed s = true then .done s 0 else
  if status = 1 then .done 6 0 else
  .bind (ringRead 168) fun s held => if mmFailed s = true then .done s 0 else
  if held &&& 255 = 2 then .done 6 0 else
  .bind (metadata descriptor pointer 32) fun s data => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 data) fun s magic => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 8)) fun s format => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 16)) fun s capacity => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s reserved => if mmFailed s = true then fatal else
  if mmDifferent magic 0x32474e52 = true then .done 2 0 else
  if mmDifferent format 1 = true then .done 2 0 else
  if mmDifferent capacity 2048 = true then .done 3 0 else
  if mmDifferent reserved 0 = true then .done 2 0 else
  .bind (get 640) fun s handle => if mmFailed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s physical => if mmFailed s = true then fatal else
  .bind (Lemma.Drivers.Multimodal.read 8 32) fun s controllerEpoch => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read 8 240) fun s submitted => if mmFailed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read 8 232) fun s consumed => if mmFailed s = true then .done s 0 else
  .bind (ringWrite 104 physical) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringWrite 112 2048) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringWrite 136 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringRead 144) fun s enabled => if mmFailed s = true then .done s 0 else
  if mmDifferent enabled 1 = true then .done 6 0 else
  .bind (put 648 descriptor) fun s _ => if mmFailed s = true then fatal else
  .bind (put 656 epoch) fun s _ => if mmFailed s = true then fatal else
  .bind (put 664 0) fun s _ => if mmFailed s = true then fatal else
  .bind (put 672 submitted) fun s _ => if mmFailed s = true then fatal else
  .bind (put 680 consumed) fun s _ => if mmFailed s = true then fatal else
  .bind (put 688 controllerEpoch) fun s _ => if mmFailed s = true then fatal else
  .bind (put 704 0xffffffffffffffff) fun s _ => if mmFailed s = true then fatal else
  .bind (put 696 1) fun s _ => .done s 0

private def ringCopyStep (i _ : UInt32) (acc data destination producer _ : UInt64) : Action :=
  let offset := (producer + i.toUInt64) % 2048 * 2
  .bind (Access.read8 (data + 32 + i.toUInt64 * 2)) fun s low => if mmFailed s = true then .done s acc else
  .bind (Access.read8 (data + 33 + i.toUInt64 * 2)) fun s high => if mmFailed s = true then .done s acc else
  .bind (Access.write8 (destination + offset) low) fun s _ => if mmFailed s = true then .done s acc else
  .bind (Access.write8 (destination + offset + 1) high) fun s _ => .done s (acc + 1)

private def ringPacket (data count producer : UInt64) : Action :=
  .bind (Access.read64 data) fun s magic => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 8)) fun s format => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 16)) fun s actualCount => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s actualProducer => if mmFailed s = true then fatal else
  if mmDifferent magic 0x32424350 = true then .done 2 0 else
  if mmDifferent format 1 = true then .done 2 0 else
  if mmDifferent actualCount count = true then .done 4 0 else
  if mmDifferent actualProducer producer = true then .done 4 0 else .done 0 0

/-- A packet is admitted atomically. Unpublished bytes never grant playback;
permission and controller identity are rechecked after the bounded copy. Ring
space uses the DMA fetch frontier, not the FIFO submission or consumed counter. -/
private def enqueueRing (descriptor stream pointer epoch : UInt64) : Action :=
  if mmDifferent stream 8 = true then .done 2 0 else
  .bind ringABI fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringCurrent descriptor epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 704) fun s eof => if mmFailed s = true then fatal else
  if mmDifferent eof 0xffffffffffffffff = true then .done 5 0 else
  .bind (metadata descriptor pointer 32) fun s data => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 (data + 16)) fun s count => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s producer => if mmFailed s = true then fatal else
  if count = 0 then .done 3 0 else if 512 < count then .done 3 0 else
  .bind (ringPacket data count producer) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 664) fun s expected => if mmFailed s = true then fatal else
  if mmDifferent producer expected = true then .done 4 0 else
  if 0xffffffffffffffff - count < producer then .done 14 0 else
  .bind (ringRead 120) fun s actual => if mmFailed s = true then .done s 0 else
  if mmDifferent actual producer = true then .done 4 0 else
  .bind (ringRead 128) fun s fetched => if mmFailed s = true then .done s 0 else
  if producer < fetched then .done 4 0 else
  if 2048 < producer - fetched then .done 4 0 else
  if 2048 - (producer - fetched) < count then .done 6 0 else
  .bind (get (row 8 + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < count * 8 then .done 9 0 else
  .bind (metadata descriptor pointer (32 + count * 2)) fun s data => if mmFailed s = true then .done s 0 else
  .bind (ringPacket data count producer) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 640) fun s handle => if mmFailed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s destination => if mmFailed s = true then fatal else
  .boundedFoldU64 512 ringCopyStep count.toUInt32 0 data destination producer 0 fun s copied => if mmFailed s = true then .done s 0 else
  if mmDifferent copied count = true then fatal else
  .bind (ringCurrent descriptor epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringWrite 120 (producer + count)) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringRead 120) fun s published => if mmFailed s = true then .done s 0 else
  if mmDifferent published (producer + count) = true then .done 6 0 else
  .bind (put (row 8 + 32) (remaining - count * 8)) fun s _ => if mmFailed s = true then fatal else
  .bind (put 664 published) fun s _ => .done s published

private def finishRing (descriptor stream producer epoch : UInt64) : Action :=
  if mmDifferent stream 8 = true then .done 2 0 else
  .bind ringABI fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringCurrent descriptor epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 664) fun s expected => if mmFailed s = true then fatal else
  if mmDifferent producer expected = true then .done 4 0 else
  .bind (get 704) fun s eof => if mmFailed s = true then fatal else
  if eof = producer then .done 0 producer else
  if mmDifferent eof 0xffffffffffffffff = true then .done 4 0 else
  .bind (ringWrite 136 2) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringRead 152) fun s actual => if mmFailed s = true then .done s 0 else
  if mmDifferent actual producer = true then .done 6 0 else
  .bind (put 704 producer) fun s _ => .done s producer

/-- Raw observations of an owned ring remain available after revocation. They
cannot submit samples, borrow another descriptor's ring, or reveal its address. -/
private def ringStatus (descriptor stream selector epoch : UInt64) : Action :=
  if mmDifferent stream 8 = true then .done 2 0 else
  .bind ringABI fun s _ => if mmFailed s = true then .done s 0 else
  .bind (ringOwner descriptor epoch) fun s _ => if mmFailed s = true then .done s 0 else
  if selector = 0 then ringRead 144 else
  if selector = 1 then ringRead 120 else
  if selector = 2 then ringRead 128 else
  if selector = 3 then Lemma.Drivers.Multimodal.read 8 240 else
  if selector = 4 then Lemma.Drivers.Multimodal.read 8 232 else
  if selector = 5 then ringRead 160 else
  if selector = 6 then ringRead 168 else
  if selector = 7 then Lemma.Drivers.Multimodal.read 8 16 else
  if selector = 8 then Lemma.Drivers.Multimodal.read 8 32 else
  if selector = 9 then ringRead 112 else .done 2 0

/-- syscall69 cap/op/stream/pointer/epoch. 0 discover;1 status;2 bounded grant;
3 configure;4 arm+start;5 drain;6 revoke;7 take64;8 submit PCM;9 queue count;
10 clock;11 consent epoch;12 begin owned record-DMA;13 finish/copy record;
14 bounded S16_LE PCM batch;15 raw monotonic consumed PCM counter;
16 arm PCM without starting;17 start prefilled PCM;18 service
version;19 begin owned controller2 ring;20 enqueue1..512 S16 samples atomically;
21 exact EOF frontier;22 raw owned ring counters. Counter15 has no packet, grant or presentation authority. Legacy operations retain
their meanings; no arbitrary application MMIO/DMA address is exposed. -/
def call (descriptor handle operation stream pointer epoch : UInt64) : Action :=
  .bind (authorize descriptor handle) fun s _ => if mmFailed s = true then .done s 0 else
  if stream < 9 then
  if operation = 0 then Lemma.Drivers.Multimodal.discover else
  if operation = 1 then Lemma.Drivers.Multimodal.read stream 8 else
  if operation = 2 then grant descriptor stream pointer else
  if operation = 3 then configureStream descriptor stream pointer epoch else
  if operation = 4 then
    .bind (current stream epoch (if stream = 8 then 64 else 1)) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (Lemma.Drivers.Multimodal.command stream 3) fun s _ => if mmFailed s = true then .done s 0 else Lemma.Drivers.Multimodal.command stream 4
  else if operation = 5 then Lemma.Drivers.Multimodal.command stream 5 else
  if operation = 6 then revoke stream else
  if operation = 7 then take descriptor stream pointer epoch else
  if operation = 8 then
    if mmDifferent stream 8 = true then .done 2 0 else
    .bind (current stream epoch 64) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (get (row stream + 32)) fun s remaining => if mmFailed s = true then fatal else
    if remaining < 8 then .done 9 0 else
    .bind (Lemma.Drivers.Multimodal.read stream 240) fun s before => if mmFailed s = true then .done s 0 else
    if before = 0xffffffffffffffff then .done 14 0 else
    .bind (Lemma.Drivers.Multimodal.write stream 112 pointer) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (Lemma.Drivers.Multimodal.read stream 240) fun s after => if mmFailed s = true then .done s 0 else
    if mmDifferent (after) (before + 1) = true then .done 6 0 else
    .bind (put (row stream + 32) (remaining - 8)) fun s _ => .done s after
  else if operation = 9 then Lemma.Drivers.Multimodal.read stream 144 else
  if operation = 10 then now else
  if operation = 11 then get (row stream) else
  if operation = 12 then beginRecord descriptor stream pointer epoch else
  if operation = 13 then finishRecord descriptor stream pointer epoch else
  if operation = 14 then pcmBatch descriptor stream pointer epoch else
  if operation = 15 then if stream = 8 then Lemma.Drivers.Multimodal.read 8 232 else .done 2 0 else
  if operation = 16 then
    if mmDifferent (stream) (8) = true then .done 2 0 else
    .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else Lemma.Drivers.Multimodal.command 8 3
  else if operation = 17 then
    if mmDifferent (stream) (8) = true then .done 2 0 else
    .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else Lemma.Drivers.Multimodal.command 8 4
  else if operation = 18 then
    .bind (IO.read64 (Lemma.Drivers.Multimodal.base + 8)) fun s abi => if mmFailed s = true then .done s 0 else
    .done 0 (if abi = 2 then version else 2)
  else if operation = 19 then beginRing descriptor stream pointer epoch else
  if operation = 20 then enqueueRing descriptor stream pointer epoch else
  if operation = 21 then finishRing descriptor stream pointer epoch else
  if operation = 22 then ringStatus descriptor stream pointer epoch else .done 2 0
  else .done 2 0

end Lemma.Platform.LemmaSim.MultimodalService
