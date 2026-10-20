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

/-- Additive syscall69 service version; converter hardware discovery stays1. -/
def version : UInt64 := 2
def state : UInt64 := 0x804e0300
private def get (offset : UInt64) : Action := Access.read64 (state + offset)
private def put (offset value : UInt64) : Action := Access.write64 (state + offset) value
private def row (stream : UInt64) : UInt64 := 64 + stream * 64
private def fatal : Action := .done 255 0
private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

def configure (key : UInt64) : Action :=
  .bind Lemma.Drivers.Multimodal.discover fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if mmFailed s = true then fatal else
  .bind (Frames.allocate 1 1) fun s scratch => if mmFailed s = true then .done s 0 else
  .bind (put 0 key) fun s _ => if mmFailed s = true then fatal else
  .bind (put 8 scratch) fun s _ => if mmFailed s = true then fatal else
  .bind (Frames.allocate 1 1) fun s dma => if mmFailed s = true then .done s 0 else put 16 dma

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
  if oldEpoch = actualEpoch then if bits ≠ 0 then if ticks < expiry then .done 6 0
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
  if fault ≠ 0 then .done (faultStatus fault) 0 else
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
  if active ≠ stream + 1 then .done 5 0 else
  .bind (get 24) fun s owner => if mmFailed s = true then fatal else
  .bind (get 32) fun s destination => if mmFailed s = true then fatal else
  .bind (get 48) fun s requestedEpoch => if mmFailed s = true then fatal else
  if owner ≠ descriptor then .done 7 0 else
  if destination ≠ pointer then .done 4 0 else
  if requestedEpoch ≠ epoch then .done 4 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 184) fun s status => if mmFailed s = true then .done s 0 else
  if status = 1 then .done 6 0 else
  if status ≠ 2 then .bind releaseRecord fun s _ => if mmFailed s = true then fatal else .done 5 0 else
  .bind (current stream epoch 3) fun s _ =>
  if mmFailed s = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done s 0 else
  .bind (Lemma.Drivers.Multimodal.read stream 16) fun s fault =>
  if mmFailed s = true then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done s 0 else
  if fault ≠ 0 then .bind releaseRecord fun cleanup _ => if mmFailed cleanup = true then fatal else .done (faultStatus fault) 0 else
  .bind (get 16) fun s handle => if mmFailed s = true then fatal else
  .bind (Frames.resolvePurpose 1 handle 1) fun s address => if mmFailed s = true then fatal else
  .bind (get 56) fun s expectedSequence => if mmFailed s = true then fatal else
  .bind (get (row stream + 48)) fun s expectedEpoch => if mmFailed s = true then fatal else
  .bind (Access.read64 (address + 32)) fun s sequence => if mmFailed s = true then fatal else
  .bind (Access.read64 (address + 40)) fun s actualEpoch => if mmFailed s = true then fatal else
  if sequence ≠ expectedSequence then .bind releaseRecord fun _ _ => .done 4 0 else
  if actualEpoch ≠ expectedEpoch then .bind releaseRecord fun _ _ => .done 4 0 else
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
  if after ≠ before + 1 then .done 6 accepted else .done 0 (accepted + 1)

private def pcmBatch (descriptor stream pointer epoch : UInt64) : Action :=
  if stream ≠ 8 then .done 2 0 else
  .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (metadata descriptor pointer 32) fun s data => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 data) fun s magic => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 8)) fun s format => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 16)) fun s count => if mmFailed s = true then fatal else
  .bind (Access.read64 (data + 24)) fun s reserved => if mmFailed s = true then fatal else
  if magic ≠ 0x31424350 then .done 2 0 else if format ≠ 1 then .done 2 0 else
  if reserved ≠ 0 then .done 2 0 else if count = 0 then .done 3 0 else if 16 < count then .done 3 0 else
  .bind (get (row 8 + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < count * 8 then .done 9 0 else
  .bind (Lemma.Drivers.Multimodal.read 8 144) fun s queued => if mmFailed s = true then .done s 0 else
  if 16 < queued then .done 5 0 else if 16 - queued < count then .done 6 0 else
  .bind (metadata descriptor pointer (32 + count * 2)) fun s data => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 16 pcmStep count.toUInt32 0 data epoch 0 0 fun status accepted =>
  .bind (put (row 8 + 32) (remaining - accepted * 8)) fun s _ => if mmFailed s = true then fatal else .done status accepted

/-- syscall69 cap/op/stream/pointer/epoch. 0 discover;1 status;2 bounded grant;
3 configure;4 arm+start;5 drain;6 revoke;7 take64;8 submit PCM;9 queue count;
10 clock;11 consent epoch;12 begin owned record-DMA;13 finish/copy record;
14 bounded S16_LE PCM batch;15 raw monotonic consumed PCM counter;
16 arm PCM without starting;17 start prefilled PCM;18 service
version. Counter15 has no packet, grant or presentation authority. Legacy operations retain
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
    if stream ≠ 8 then .done 2 0 else
    .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else Lemma.Drivers.Multimodal.command 8 3
  else if operation = 17 then
    if stream ≠ 8 then .done 2 0 else
    .bind (current 8 epoch 64) fun s _ => if mmFailed s = true then .done s 0 else Lemma.Drivers.Multimodal.command 8 4
  else if operation = 18 then .done 0 version else .done 2 0
  else .done 2 0

end Lemma.Platform.LemmaSim.MultimodalService
