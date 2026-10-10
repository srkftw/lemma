import Lemma.Kernel.Memory.Access
import Lemma.Platform.LemmaVM.Layout

/-! Runtime frame ownership over the boot-selected reserved frame pool. Records are in
kernel-owned metadata, not supplied by the host. Policy, scans and zeroing are
ordinary elaborated Lean functions lowered through checked Action CFGs. -/
namespace Lemma.Kernel.Memory.Frames
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def count : UInt64 := Lemma.Platform.LemmaVM.Layout.frameCountValue
def bytes : UInt64 := Lemma.Platform.LemmaVM.Layout.frameBytesValue
def pool : UInt64 := Lemma.Platform.LemmaVM.Layout.poolValue
/-- Boot-only configuration cells. The validated machine descriptor selects the
expanded floor before init; historical boot explicitly selects 512/32/2. There
is no syscall or capability exposing this constructor. -/
def configuration : UInt64 := 0x804006a0
def maximumCount : UInt64 := 8192
def expandedPoolLimit : UInt64 := 0x84000000
def configure (amount quota stackPages : UInt64) : Action :=
  if (if amount = 512 then if quota = 32 then if stackPages = 2 then true else false else false
      else if amount = 8192 then if 128 ≤ quota then if quota ≤ amount then if stackPages = 4 then true else false else false else false
      else false) = false then .done 39 0 else
  .bind (Access.write64 configuration amount) fun s _ =>
  if s = 0 then
    .bind (Access.write64 (configuration + 8) quota) fun s _ =>
    if s = 0 then Access.write64 (configuration + 16) stackPages else .done s 0
  else .done s 0

def runtimeCount : Action :=
  .bind (Access.read64 configuration) fun s amount =>
  if s = 0 then
    if amount = 512 then .done 0 amount else
    if amount = 8192 then .done 0 amount else .done 39 0
  else .done s 0

def runtimeQuota : Action :=
  .bind runtimeCount fun s amount =>
  if s = 0 then
    .bind (Access.read64 (configuration + 8)) fun s quota =>
    if s = 0 then
      if amount = 512 then if quota = 32 then .done 0 quota else .done 39 0
      else if 128 ≤ quota then if quota ≤ amount then .done 0 quota else .done 39 0 else .done 39 0
    else .done s 0
  else .done s 0

def runtimeStackPages : Action :=
  .bind runtimeCount fun s amount =>
  if s = 0 then
    .bind (Access.read64 (configuration + 16)) fun s pages =>
    if s = 0 then
      if amount = 512 then if pages = 2 then .done 0 pages else .done 39 0
      else if pages = 4 then .done 0 pages else .done 39 0
    else .done s 0
  else .done s 0

def records : UInt64 := Lemma.Platform.LemmaVM.Layout.metadataValue + 0x1000
def accounting : UInt64 := Lemma.Platform.LemmaVM.Layout.metadataValue + 0x100
def taskQuota : UInt64 := 32
def kernelOwner : UInt64 := 1
def kernelPurpose : UInt64 := 1
def tablePurpose : UInt64 := 2
def textPurpose : UInt64 := 3
def dataPurpose : UInt64 := 4
def stackPurpose : UInt64 := 5
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
def purposeDenied : UInt8 := 40
/-- Closed kernel-only two-handle transaction result. Copy both handles before
beginning another pair allocation; no user receives this metadata address. -/
def pairResult : UInt64 := 0x80400580

def record (index : UInt64) : UInt64 := records + index * 32
def address (index : UInt64) : UInt64 := pool + index * bytes
def indexValid (index : UInt64) : Bool := if index < count then true else false
def purposeValid (purpose : UInt64) : Bool :=
  if 1 ≤ purpose then if purpose ≤ 5 then true else false else false
def ownerValid (owner : UInt64) : Bool :=
  if 0 < owner then if owner < 0xffffffffffffffff then true else false else false
def frameAddressValid (frame : UInt64) : Bool :=
  if pool ≤ frame then
    if frame < expandedPoolLimit then
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
def remainingValid (remaining amount : UInt64) : Bool :=
  if 0 < remaining then if remaining ≤ amount then true else false else false
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
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 8192 initStep count.toUInt32 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 accounting count) fun s _ => .done s count

private def ownedStep (i : UInt32) (_count : UInt32) (acc owner _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (record i.toUInt64)) fun s liveOwner =>
  if failed s = true then .done s 0 else
  .done 0 (if liveOwner = owner then acc + 1 else acc)

def ownedCount (owner : UInt64) : Action :=
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 8192 ownedStep count.toUInt32 0 owner 0 0 0 fun s v => .done s v

private def findStep (i : UInt32) (_count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (record i.toUInt64)) fun s owner =>
  if failed s = true then .done s 0 else
  if firstFree owner acc = true then .done 0 (i.toUInt64 + 1) else .done 0 acc

private def zeroStep (i : UInt32) (_count : UInt32) (acc frame _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (frame + i.toUInt64 * 8) 0) fun s _ => .done s acc

def zero (frame : UInt64) : Action :=
  if frameAddressValid frame = false then .done invalidFrame 0 else
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  if pool + count * bytes ≤ frame then .done invalidFrame 0 else
  .boundedFoldU64 512 zeroStep 512 0 frame 0 0 0 fun s v => .done s v

/-- Returns generation*configuredCount+index after complete zeroing and ownership publication.
Resolve the handle before using its physical base; release requires this exact
generation, so reuse by the same owner cannot resurrect an old reference. -/
def allocate (owner purpose : UInt64) : Action :=
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  .bind runtimeQuota fun s quota =>
  if failed s = true then .done s 0 else
  if grantValid owner purpose = false then .done badOwner 0 else
  .bind (ownedCount owner) fun s owned =>
  if failed s = true then .done s 0 else
  if (if owner = kernelOwner then true else if owned < quota then true else false) = false then .done quotaExceeded 0 else
  .boundedFoldU64 8192 findStep count.toUInt32 0 0 0 0 0 fun s found =>
  if failed s = true then .done s 0 else
  if found = 0 then .done exhausted 0 else
  let index := found - 1
  .bind (Access.read64 (record index + 24)) fun s generation =>
  if failed s = true then .done s 0 else
  if 0xffffffffffffffff / count ≤ generation then .done generationExhausted 0 else
  .bind (Access.read64 accounting) fun s remaining =>
  if failed s = true then .done s 0 else
  if remainingValid remaining count = false then .done invariantFailure 0 else
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
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  if (if ownerValid owner = true then if 0 < handle / count then true else false else false) = false then .done invalidFrame 0 else
  if resolveValid owner handle = false then .done invalidFrame 0 else
  let index := handle % count
  .bind (Access.read64 (record index)) fun s liveOwner =>
  if failed s = true then .done s 0 else
  if (if liveOwner = owner then false else true) = true then .done notOwned 0 else
  .bind (Access.read64 (record index + 24)) fun s generation =>
  if failed s = true then .done s 0 else
  if (if generation = handle / count then false else true) = true then .done notOwned 0 else
  .done 0 (address index)

/-- Purpose and generation are revalidated before exposing kernel storage. -/
def purpose (owner handle : UInt64) : Action :=
  .bind (resolve owner handle) fun s frame =>
  if failed s = true then .done s 0 else
  Access.read64 (record ((frame - pool) / bytes) + 8)

/-- Resolve the owner/generation once, then inspect its metadata through that
validated physical slot. Single-hart S policy cannot change the grant between
these reads; a redundant recursive resolve needlessly consumed trap stack. -/
def resolvePurpose (owner handle expected : UInt64) : Action :=
  .bind (resolve owner handle) fun s frame =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (record ((frame - pool) / bytes) + 8)) fun s actual =>
  if failed s = true then .done s 0 else
  if actual = expected then .done 0 frame else .done purposeDenied 0

/-- Pins count revocable owner references (user leaves and owned page-table
trees), not the trusted S management alias of the physical pool. -/
def mappingCount (owner handle : UInt64) : Action :=
  .bind (resolve owner handle) fun s frame =>
  if failed s = true then .done s 0 else
  Access.read64 (record ((frame - pool) / bytes) + 16)

def pin (owner handle : UInt64) : Action :=
  .bind (resolve owner handle) fun s frame =>
  if failed s = true then .done s 0 else
  let slot := record ((frame - pool) / bytes) + 16
  .bind (Access.read64 slot) fun s mappings =>
  if failed s = true then .done s 0 else
  if mappings = 0xffffffffffffffff then .done invariantFailure 0 else
  .bind (Access.write64 slot (mappings + 1)) fun s _ => .done s (mappings + 1)

def unpin (owner handle : UInt64) : Action :=
  .bind (resolve owner handle) fun s frame =>
  if failed s = true then .done s 0 else
  let slot := record ((frame - pool) / bytes) + 16
  .bind (Access.read64 slot) fun s mappings =>
  if failed s = true then .done s 0 else
  if mappings = 0 then .done invariantFailure 0 else
  .bind (Access.write64 slot (mappings - 1)) fun s _ => .done s (mappings - 1)

/-- Release requires the live owner and zero revocable mapping/tree references.
Callers invalidate translations before removing the last pin. The permanent
trusted S management alias neither grants U authority nor pins a live owner. -/
def release (owner handle : UInt64) : Action :=
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  if ownerValid owner = false then .done badOwner 0 else
  if handleValid handle = false then .done invalidFrame 0 else
  let index := handle % count
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
  let retired := if handle / count = 0xffffffffffffffff / count then true else false
  .bind (Access.write64 (record index) (if retired = true then retiredOwner else 0)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 accounting (if retired = true then remaining else remaining + 1)) fun s _ => .done s 0

def remaining : Action := Access.read64 accounting

private def pairStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  if acc = 0 then
    let index := i.toUInt64
    .bind (Access.read64 (record index)) fun s firstOwner =>
    if s = 0 then
      if firstOwner = 0 then
        .bind (Access.read64 (record (index + 1))) fun s secondOwner =>
        if s = 0 then .done 0 (if secondOwner = 0 then index + 1 else 0)
        else .done s 0
      else .done 0 0
    else .done s 0
  else .done 0 acc

private def freeGeneration (index : UInt64) : Action :=
  .bind (Access.read64 (record index)) fun s owner =>
  if s = 0 then
    if owner = 0 then
      .bind (Access.read64 (record index + 8)) fun s purpose =>
      if s = 0 then
        if purpose = 0 then
          .bind (Access.read64 (record index + 16)) fun s pins =>
          if s = 0 then
            if pins = 0 then Access.read64 (record index + 24)
            else .done invariantFailure 0
          else .done s 0
        else .done invariantFailure 0
      else .done s 0
    else .done invariantFailure 0
  else .done s 0

private def preparePairRecord (index purpose generation : UInt64) : Action :=
  .bind (Access.write64 (record index + 8) purpose) fun s _ =>
  if s = 0 then
    .bind (Access.write64 (record index + 16) 0) fun s _ =>
    if s = 0 then Access.write64 (record index + 24) (generation + 1)
    else .done s 0
  else .done s 0

private def restoreFreeRecord (index generation : UInt64) : Action :=
  .bind (Access.write64 (record index) 0) fun s _ =>
  if s = 0 then
    .bind (Access.write64 (record index + 8) 0) fun s _ =>
    if s = 0 then
      .bind (Access.write64 (record index + 16) 0) fun s _ =>
      if s = 0 then Access.write64 (record index + 24) generation
      else .done s 0
    else .done s 0
  else .done s 0

/-- Only an unpublished transaction may restore its old generations. Neither
handle has been returned with success, so no live reference can observe them.
A failed metadata write is an invariant failure even when cleanup succeeds. -/
private def rollbackPair (index available firstGeneration secondGeneration : UInt64) : Action :=
  .bind (restoreFreeRecord index firstGeneration) fun _ _ =>
  .bind (restoreFreeRecord (index + 1) secondGeneration) fun _ _ =>
  .bind (Access.write64 accounting available) fun _ _ =>
  .bind (Access.write64 pairResult 0) fun _ _ =>
  .bind (Access.write64 (pairResult + 8) 0) fun _ _ =>
  .done invariantFailure 0

private def publishPair (owner purpose index available firstGeneration secondGeneration : UInt64) : Action :=
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  .bind (preparePairRecord index purpose firstGeneration) fun s _ =>
  if s = 0 then
    .bind (preparePairRecord (index + 1) purpose secondGeneration) fun s _ =>
    if s = 0 then
      .bind (Access.write64 accounting (available - 2)) fun s _ =>
      if s = 0 then
        .bind (Access.write64 (record index) owner) fun s _ =>
        if s = 0 then
          .bind (Access.write64 (record (index + 1)) owner) fun s _ =>
          if s = 0 then
            .bind (Access.write64 pairResult ((firstGeneration + 1) * count + index)) fun s _ =>
            if s = 0 then
              .bind (Access.write64 (pairResult + 8) ((secondGeneration + 1) * count + index + 1)) fun s _ =>
              if s = 0 then .done 0 pairResult
              else rollbackPair index available firstGeneration secondGeneration
            else rollbackPair index available firstGeneration secondGeneration
          else rollbackPair index available firstGeneration secondGeneration
        else rollbackPair index available firstGeneration secondGeneration
      else rollbackPair index available firstGeneration secondGeneration
    else rollbackPair index available firstGeneration secondGeneration
  else rollbackPair index available firstGeneration secondGeneration

/-- Two physically adjacent independently versioned frames. Quota, free-pair,
global accounting and both generations are checked before zeroing or ownership
changes. Both pages are zeroed before any grant is published. This single-hart
construction transaction returns only the closed pair-result metadata address.
No page-table mapping is installed and ordinary rejection acquires no frames. -/
def allocateContiguous2 (owner purpose : UInt64) : Action :=
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  .bind runtimeQuota fun s quota =>
  if failed s = true then .done s 0 else
  if grantValid owner purpose = false then .done badOwner 0 else
  .bind (Access.write64 pairResult 0) fun s _ =>
  if s = 0 then
    .bind (Access.write64 (pairResult + 8) 0) fun s _ =>
    if s = 0 then
      .bind (ownedCount owner) fun s owned =>
      if s = 0 then
        if (if owner = kernelOwner then true else if owned ≤ quota - 2 then true else false) = true then
          .bind (Access.read64 accounting) fun s available =>
          if s = 0 then
            if count < available then .done invariantFailure 0 else
            if available < 2 then .done exhausted 0 else
            .boundedFoldU64 8191 pairStep (count - 1).toUInt32 0 0 0 0 0 fun s found =>
            if s = 0 then
              if found = 0 then .done exhausted 0 else
              let index := found - 1
              .bind (freeGeneration index) fun s firstGeneration =>
              if s = 0 then
                .bind (freeGeneration (index + 1)) fun s secondGeneration =>
                if s = 0 then
                  if 0xffffffffffffffff / count ≤ firstGeneration then .done generationExhausted 0 else
                  if 0xffffffffffffffff / count ≤ secondGeneration then .done generationExhausted 0 else
                  .bind (zero (address index)) fun s _ =>
                  if s = 0 then
                    .bind (zero (address (index + 1))) fun s _ =>
                    if s = 0 then publishPair owner purpose index available firstGeneration secondGeneration
                    else .done invariantFailure 0
                  else .done invariantFailure 0
                else .done invariantFailure 0
              else .done invariantFailure 0
            else .done invariantFailure 0
          else .done invariantFailure 0
        else .done quotaExceeded 0
      else .done invariantFailure 0
    else .done invariantFailure 0
  else .done invariantFailure 0

/-- Closed four-handle construction scratch; not a user buffer or DMA span. -/
def quadResult : UInt64 := 0x804005a0
private def quadGenerations : UInt64 := quadResult + 32

private def quadFindStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  if acc = 0 then
    let index := i.toUInt64
    .bind (Access.read64 (record index)) fun s a =>
    if failed s = true then .done s 0 else
    .bind (Access.read64 (record (index + 1))) fun s b =>
    if failed s = true then .done s 0 else
    .bind (Access.read64 (record (index + 2))) fun s c =>
    if failed s = true then .done s 0 else
    .bind (Access.read64 (record (index + 3))) fun s d =>
    if failed s = true then .done s 0 else
    .done 0 (if a ||| b ||| c ||| d = 0 then index + 1 else 0)
  else .done 0 acc

private def quadPreflightStep (i _ : UInt32) (acc index amount _ _ : UInt64) : Action :=
  .bind (freeGeneration (index + i.toUInt64)) fun s generation =>
  if failed s = true then .done s 0 else
  if 0xffffffffffffffff / amount ≤ generation then .done generationExhausted 0 else
  .bind (Access.write64 (quadGenerations + i.toUInt64 * 8) generation) fun s _ =>
  if failed s = true then .done s 0 else .done 0 (acc + 1)

private def quadZeroStep (i _ : UInt32) (acc index _ _ _ : UInt64) : Action :=
  .bind (zero (address (index + i.toUInt64))) fun s _ =>
  if failed s = true then .done s 0 else .done 0 (acc + 1)

private def quadClearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (quadResult + i.toUInt64 * 8) 0) fun s _ => .done s acc

private def quadPublishStep (i _ : UInt32) (acc index owner purpose amount : UInt64) : Action :=
  let slot := index + i.toUInt64
  .bind (Access.read64 (quadGenerations + i.toUInt64 * 8)) fun s generation =>
  if failed s = true then .done s 0 else
  .bind (preparePairRecord slot purpose generation) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (record slot) owner) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (quadResult + i.toUInt64 * 8) ((generation + 1) * amount + slot)) fun s _ =>
  if failed s = true then .done s 0 else .done 0 (acc + 1)

private def quadRollbackStep (i _ : UInt32) (acc index _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (quadGenerations + i.toUInt64 * 8)) fun s generation =>
  if failed s = true then .done invariantFailure 0 else
  .bind (restoreFreeRecord (index + i.toUInt64) generation) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Access.write64 (quadResult + i.toUInt64 * 8) 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else .done 0 (acc + 1)

private def quadRollback (index available : UInt64) : Action :=
  .boundedFoldU64 4 quadRollbackStep 4 0 index 0 0 0 fun _ _ =>
  .bind (Access.write64 accounting available) fun _ _ => .done invariantFailure 0

/-- Four owned, physically contiguous and independently versioned pages. All
free records, quota, generations and accounting are checked before zeroing.
Ownership publication occurs only after zeroing every page. A failed publication
restores all unexposed records and accounting; no handle escapes on failure. -/
def allocateContiguous4 (owner purpose : UInt64) : Action :=
  .boundedFoldU64 4 quadClearStep 4 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind runtimeCount fun s amount =>
  if failed s = true then .done s 0 else
  .bind runtimeQuota fun s quota =>
  if failed s = true then .done s 0 else
  if grantValid owner purpose = false then .done badOwner 0 else
  .bind (ownedCount owner) fun s owned =>
  if failed s = true then .done s 0 else
  if (if owner = kernelOwner then true else if owned ≤ quota - 4 then true else false) = false then
    .done quotaExceeded 0 else
  .bind remaining fun s available =>
  if failed s = true then .done s 0 else
  if amount < available then .done invariantFailure 0 else
  if available < 4 then .done exhausted 0 else
  .boundedFoldU64 8189 quadFindStep (amount - 3).toUInt32 0 0 0 0 0 fun s found =>
  if failed s = true then .done s 0 else
  if found = 0 then .done exhausted 0 else
  let index := found - 1
  .boundedFoldU64 4 quadPreflightStep 4 0 index amount 0 0 fun s checked =>
  if failed s = true then .done s 0 else
  if checked = 4 then
    .boundedFoldU64 4 quadZeroStep 4 0 index 0 0 0 fun s cleared =>
    if failed s = true then .done invariantFailure 0 else
    if cleared = 4 then
      .boundedFoldU64 4 quadPublishStep 4 0 index owner purpose amount fun s published =>
      if failed s = true then quadRollback index available else
      if published = 4 then
        .bind (Access.write64 accounting (available - 4)) fun s _ =>
        if failed s = true then quadRollback index available else .done 0 quadResult
      else quadRollback index available
    else .done invariantFailure 0
  else .done invariantFailure 0

end Lemma.Kernel.Memory.Frames
