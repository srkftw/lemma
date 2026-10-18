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
  .bind (put 0 key) fun s _ => if mmFailed s = true then fatal else put 8 scratch

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
  .bind (current stream epoch 3) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get (row stream + 32)) fun s remaining => if mmFailed s = true then fatal else
  if remaining < 64 then .done 9 0 else
  .bind (UserCopy.validateWrite descriptor pointer 64) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (get 8) fun s scratch => if mmFailed s = true then fatal else
  .bind (Lemma.Drivers.Multimodal.take stream scratch) fun s sequence => if mmFailed s = true then .done s 0 else
  .bind (UserCopy.copyToUser descriptor pointer scratch 0 64) fun s _ => if mmFailed s = true then fatal else
  .bind (put (row stream + 32) (remaining - 64)) fun s _ => .done s sequence

/-- syscall69 cap/op/stream/pointer/epoch. 0 discover;1 status;2 bounded grant;
3 configure;4 arm+start;5 drain;6 revoke;7 take64;8 submit PCM;9 queue count;
10 clock;11 consent epoch. No arbitrary MMIO/DMA pointer operation is exposed. -/
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
  if operation = 11 then get (row stream) else .done 2 0
  else .done 2 0

end Lemma.Platform.LemmaSim.MultimodalService
