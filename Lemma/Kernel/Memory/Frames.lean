import Lemma.Kernel.Memory.Access
import Lemma.Platform.LemmaVM.Layout

/-! Runtime frame ownership over the reserved 512-page pool. Records are in
kernel-owned metadata, not supplied by the host. Policy, scans and zeroing are
ordinary elaborated Lean functions lowered through checked Action CFGs. -/
namespace Lemma.Kernel.Memory.Frames
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def count : UInt64 := Lemma.Platform.LemmaVM.Layout.frameCountValue
def bytes : UInt64 := Lemma.Platform.LemmaVM.Layout.frameBytesValue
def pool : UInt64 := Lemma.Platform.LemmaVM.Layout.poolValue
def records : UInt64 := Lemma.Platform.LemmaVM.Layout.metadataValue + 0x1000
def accounting : UInt64 := Lemma.Platform.LemmaVM.Layout.metadataValue + 0x100
def taskQuota : UInt64 := 32
def kernelOwner : UInt64 := 1
def maxGeneration : UInt64 := 0x007fffffffffffff
def retiredOwner : UInt64 := 0xffffffffffffffff

def badOwner : UInt8 := 32
def exhausted : UInt8 := 33
def notOwned : UInt8 := 34
def mapped : UInt8 := 35
def invalidFrame : UInt8 := 36
def generationExhausted : UInt8 := 37
def quotaExceeded : UInt8 := 38
def invariantFailure : UInt8 := 39

def record (index : UInt64) : UInt64 := records + index * 32
def address (index : UInt64) : UInt64 := pool + index * bytes
def indexValid (index : UInt64) : Bool := if index < count then true else false
def purposeValid (purpose : UInt64) : Bool :=
  if 1 ≤ purpose then if purpose ≤ 5 then true else false else false
def ownerValid (owner : UInt64) : Bool :=
  if 0 < owner then if owner < 0xffffffffffffffff then true else false else false
def frameAddressValid (frame : UInt64) : Bool :=
  if pool ≤ frame then
    if frame < pool + count * bytes then
      if (frame - pool) % bytes = 0 then true else false
    else false
  else false
def handleIndex (handle : UInt64) : UInt64 := handle % count
def handleGeneration (handle : UInt64) : UInt64 := handle / count
def handleValid (handle : UInt64) : Bool :=
  if 0 < handleGeneration handle then true else false
def failed (status : UInt8) : Bool := if status = 0 then false else true
def quotaValid (owner owned : UInt64) : Bool :=
  if owner = kernelOwner then true else if owned < taskQuota then true else false
def grantValid (owner purpose : UInt64) : Bool :=
  if ownerValid owner = true then purposeValid purpose else false
def resolveValid (owner handle : UInt64) : Bool :=
  if ownerValid owner = true then handleValid handle else false
def remainingValid (remaining : UInt64) : Bool :=
  if 0 < remaining then if remaining ≤ count then true else false else false
def firstFree (owner acc : UInt64) : Bool :=
  if owner = 0 then if acc = 0 then true else false else false

private def initStep (i : UInt32) (_count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (record i.toUInt64) 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record i.toUInt64 + 8) 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record i.toUInt64 + 16) 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record i.toUInt64 + 24) 0) fun s _ => .done s acc

/-- Called once before publishing any task or mapping. Reinitializing a live
allocator is deliberately not exposed as a user operation. -/
def init : Action :=
  .boundedFoldU64 512 initStep 512 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 accounting count) fun s _ => .done s count

private def ownedStep (i : UInt32) (_count : UInt32) (acc owner _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (record i.toUInt64)) fun s liveOwner =>
  if failed s = true then .done s 0 else
  .done 0 (if liveOwner = owner then acc + 1 else acc)

def ownedCount (owner : UInt64) : Action :=
  .boundedFoldU64 512 ownedStep 512 0 owner 0 0 0 fun s v => .done s v

private def findStep (i : UInt32) (_count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (record i.toUInt64)) fun s owner =>
  if failed s = true then .done s 0 else
  if firstFree owner acc = true then .done 0 (i.toUInt64 + 1) else .done 0 acc

private def zeroStep (i : UInt32) (_count : UInt32) (acc frame _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (frame + i.toUInt64 * 8) 0) fun s _ => .done s acc

def zero (frame : UInt64) : Action :=
  if frameAddressValid frame = false then .done invalidFrame 0 else
  .boundedFoldU64 512 zeroStep 512 0 frame 0 0 0 fun s v => .done s v

/-- Returns generation*512+index after complete zeroing and ownership publication.
Resolve the handle before using its physical base; release requires this exact
generation, so reuse by the same owner cannot resurrect an old reference. -/
def allocate (owner purpose : UInt64) : Action :=
  if grantValid owner purpose = false then .done badOwner 0 else
  .bind (ownedCount owner) fun s owned =>
  if failed s = true then .done s 0 else
  if quotaValid owner owned = false then .done quotaExceeded 0 else
  .boundedFoldU64 512 findStep 512 0 0 0 0 0 fun s found =>
  if failed s = true then .done s 0 else
  if found = 0 then .done exhausted 0 else
  let index := found - 1
  .bind (Access.read64 (record index + 24)) fun s generation =>
  if failed s = true then .done s 0 else
  if maxGeneration ≤ generation then .done generationExhausted 0 else
  .bind (Access.read64 accounting) fun s remaining =>
  if failed s = true then .done s 0 else
  if remainingValid remaining = false then .done invariantFailure 0 else
  .bind (zero (address index)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record index + 8) purpose) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record index + 16) 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record index + 24) (generation + 1)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 accounting (remaining - 1)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record index) owner) fun s _ =>
  if failed s = true then .done s 0 else .done 0 ((generation + 1) * count + index)

def resolve (owner handle : UInt64) : Action :=
  if resolveValid owner handle = false then .done invalidFrame 0 else
  let index := handleIndex handle
  .bind (Access.read64 (record index)) fun s liveOwner =>
  if failed s = true then .done s 0 else
  if (if liveOwner = owner then false else true) = true then .done notOwned 0 else
  .bind (Access.read64 (record index + 24)) fun s generation =>
  if failed s = true then .done s 0 else
  if (if generation = handleGeneration handle then false else true) = true then .done notOwned 0 else
  .done 0 (address index)

/-- Release requires the live owner and zero installed mappings. Callers must
invalidate translations before removing the last mapping pin (Gate D). -/
def release (owner handle : UInt64) : Action :=
  if ownerValid owner = false then .done badOwner 0 else
  if handleValid handle = false then .done invalidFrame 0 else
  let index := handleIndex handle
  .bind (resolve owner handle) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (record index + 16)) fun s mappings =>
  if failed s = true then .done s 0 else
  if (if mappings = 0 then false else true) = true then .done mapped 0 else
  .bind (Access.read64 accounting) fun s remaining =>
  if failed s = true then .done s 0 else
  if count ≤ remaining then .done invariantFailure 0 else
  .bind (Access.write64 (record index + 8) 0) fun s _ =>
  if failed s = true then .done s 0 else
  let retired := if handleGeneration handle = maxGeneration then true else false
  .bind (Access.write64 (record index) (if retired = true then retiredOwner else 0)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 accounting (if retired = true then remaining else remaining + 1)) fun s _ => .done s 0

def remaining : Action := Access.read64 accounting

end Lemma.Kernel.Memory.Frames
