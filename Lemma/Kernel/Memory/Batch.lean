import Lemma.Kernel.Memory.Frames

/-! Single-hart construction transaction. Kernel callers copy successful handles
out of this bounded scratch before beginning another transaction. No user gets
this pointer. Until complete, no handle is published and no mapping is installed.
Every ordinary partial-allocation failure unwinds the real owned frames. -/
namespace Lemma.Kernel.Memory.Batch
open Lemma.Core0.Memory

def handles : UInt64 := 0x80400400
def publishedCount : UInt64 := handles + 256
def capacity : UInt64 := 32
def countValid (amount : UInt64) : Bool :=
  if 0 < amount then if amount ≤ capacity then true else false else false

private def releaseStep (i _count : UInt32) (acc owner _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (handles + i.toUInt64 * 8)) fun s handle =>
  if s = 0 then
    .bind (Frames.release owner handle) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else .done Frames.invariantFailure 0
  else .done Frames.invariantFailure 0

def rollback (owner amount : UInt64) (originalStatus : UInt8) : Action :=
  if amount ≤ capacity then
    .boundedFoldU64 32 releaseStep amount.toUInt32 0 owner 0 0 0 fun s released =>
    if s = 0 then
      if released = amount then
        .bind (Access.write64 publishedCount 0) fun s _ =>
        if s = 0 then .done originalStatus 0 else .done Frames.invariantFailure 0
      else .done Frames.invariantFailure 0
    else .done Frames.invariantFailure 0
  else .done Frames.invariantFailure 0

private def allocateStep (i _count : UInt32) (acc owner purpose _ _ : UInt64) : Action :=
  .bind (Frames.allocate owner purpose) fun allocationStatus handle =>
  if allocationStatus = 0 then
    .bind (Access.write64 (handles + i.toUInt64 * 8) handle) fun storeStatus _ =>
    if storeStatus = 0 then .done 0 (acc + 1) else
      .bind (Frames.release owner handle) fun releaseStatus _ =>
      if releaseStatus = 0 then .done storeStatus acc else .done Frames.invariantFailure acc
  else .done allocationStatus acc

/-- On success, a kernel-only batch address whose live length is at
publishedCount. Any recoverable construction failure returns status/value0 after
complete rollback; an impossible cleanup failure becomes a kernel invariant error. -/
def allocate (owner purpose amount : UInt64) : Action :=
  if countValid amount = true then
    .bind (Access.write64 publishedCount 0) fun s _ =>
    if s = 0 then
      .boundedFoldU64 32 allocateStep amount.toUInt32 0 owner purpose 0 0
        fun allocationStatus acquired =>
      if allocationStatus = 0 then
        if acquired = amount then
          .bind (Access.write64 publishedCount amount) fun s _ =>
          if s = 0 then .done 0 handles else rollback owner acquired s
        else rollback owner acquired Frames.invariantFailure
      else rollback owner acquired allocationStatus
    else .done s 0
  else .done 16 0

end Lemma.Kernel.Memory.Batch
