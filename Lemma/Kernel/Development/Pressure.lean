import Lemma.Kernel.Task

/-! Privileged, quarantined lifecycle observation. Real frames charged to the
next private construction owner force the loader's last user-stack allocation
to hit its ordinary quota. The production allocator, loader and task policy
have no fixture selector or caller-selected quota/owner.

All successful batch handles are copied into one owned kernel-purpose frame
before address-space construction overwrites Batch's transient scratch. That
frame also retains measured accounting and first/last-word sentinels. -/
namespace Lemma.Kernel.Development.Pressure
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0
def marker (nonce index : UInt64) : UInt64 := nonce ^^^ 0x96b4ef1723a58cd0 ^^^ index

private def freeStep (i _ : UInt32) (acc table _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (table + i.toUInt64 * Task.stride + Task.stateOffset)) fun s state =>
  if failed s = true then fatal else
  if Task.dying < state then fatal else
  .done 0 (if state = Task.free then acc + 1 else acc)

private def freeSlots : Action :=
  .bind Task.table fun s table =>
  if failed s = true then fatal else
  .boundedFoldU64 8 freeStep 8 0 table 0 0 0 fun s count => .done s count

private def inactive : Action :=
  .bind (Access.read64 Process.control) fun s current =>
  if failed s = true then fatal else
  if current = 0 then
    .bind (Access.read64 (Process.control + 8)) fun s root =>
    if failed s = true then fatal else
    .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
    if failed s = true then fatal else
    if root = active then .done 0 0 else fatal
  else fatal

private def storage (handle : UInt64) : Action :=
  .bind (Frames.resolvePurpose 1 handle 1) fun s address =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount 1 handle) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then .done 0 address else fatal

private def keepStep (i _ : UInt32) (acc owner handles scratch nonce : UInt64) : Action :=
  let slot := scratch + 128 + i.toUInt64 * 16
  .bind (Access.read64 (handles + i.toUInt64 * 8)) fun s handle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose owner handle 4) fun s physical =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount owner handle) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then
    let sentinel := marker nonce i.toUInt64
    .bind (Access.write64 slot handle) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (slot + 8) sentinel) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 physical sentinel) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (physical + 4088) sentinel) fun s _ =>
    if failed s = true then fatal else .done 0 (acc + 1)
  else fatal

private def sentinelStep (i _ : UInt32) (acc owner scratch _ _ : UInt64) : Action :=
  let slot := scratch + 128 + i.toUInt64 * 16
  .bind (Access.read64 slot) fun s handle =>
  if failed s = true then fatal else
  .bind (Access.read64 (slot + 8)) fun s expected =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose owner handle 4) fun s physical =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount owner handle) fun s pins =>
  if failed s = true then fatal else
  if pins = 0 then
    .bind (Access.read64 physical) fun s first =>
    if failed s = true then fatal else
    .bind (Access.read64 (physical + 4088)) fun s last =>
    if failed s = true then fatal else
    if first = expected then if last = expected then .done 0 (acc + 1) else fatal else fatal
  else fatal

private def releaseStep (i _ : UInt32) (acc owner scratch _ _ : UInt64) : Action :=
  let slot := scratch + 128 + i.toUInt64 * 16
  .bind (Access.read64 slot) fun s handle =>
  if failed s = true then fatal else
  .bind (Frames.release owner handle) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 slot 0) fun s _ =>
  if failed s = true then fatal else .done 0 (acc + 1)

private def releaseHeld (scratchHandle : UInt64) : Action :=
  .bind (storage scratchHandle) fun s scratch =>
  if failed s = true then fatal else
  .bind (Access.read64 scratch) fun s before =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 8)) fun s owner =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 16)) fun s held =>
  if failed s = true then fatal else
  .boundedFoldU64 16 releaseStep held.toUInt32 0 owner scratch 0 0 fun s released =>
  if failed s = true then fatal else
  if released = held then
    .bind (Frames.ownedCount owner) fun s owned =>
    if failed s = true then fatal else
    if owned = 0 then
      .bind (Frames.release 1 scratchHandle) fun s _ =>
      if failed s = true then fatal else
      .bind Frames.remaining fun s after =>
      if failed s = true then fatal else
      if after = before then .done 0 after else fatal
    else fatal
  else fatal

private def verifyRollback (scratchHandle : UInt64) (status : UInt8) : Action :=
  .bind (storage scratchHandle) fun s scratch =>
  if failed s = true then fatal else
  .bind (Access.read64 scratch) fun s before =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 8)) fun s owner =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 16)) fun s held =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 24)) fun s image =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 40)) fun s slotsBefore =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 48)) fun s beforeCreate =>
  if failed s = true then fatal else
  .bind (Access.read64 (Process.control + 16)) fun s nextOwner =>
  if failed s = true then fatal else
  if nextOwner = owner + 1 then
  .bind freeSlots fun s slotsAfter =>
  if failed s = true then fatal else
  if slotsAfter = slotsBefore then
  .bind (Frames.ownedCount owner) fun s ownedAfter =>
  if failed s = true then fatal else
  if ownedAfter = held then
  .bind Frames.remaining fun s afterFailure =>
  if failed s = true then fatal else
  if afterFailure = beforeCreate then
  if afterFailure = before - held - 1 then
  .boundedFoldU64 16 sentinelStep held.toUInt32 0 owner scratch 0 0 fun s checked =>
  if failed s = true then fatal else
  if checked = held then
    .bind (Lemma.Kernel.Console.record 0xe9 image status.toUInt64 before afterFailure) fun s _ =>
    if failed s = true then fatal else
    .bind (releaseHeld scratchHandle) fun s afterRelease =>
    if failed s = true then fatal else
    .bind (Lemma.Kernel.Console.record 0xea owner held ownedAfter afterRelease) fun s _ =>
    if failed s = true then fatal else .done status 0
  else fatal
  else fatal else fatal else fatal else fatal else fatal

private def attempt (scratchHandle : UInt64) : Action :=
  .bind (storage scratchHandle) fun s scratch =>
  if failed s = true then fatal else
  .bind (Access.read64 scratch) fun s before =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 16)) fun s held =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 24)) fun s image =>
  if failed s = true then fatal else
  .bind (Access.read64 (scratch + 32)) fun s argument =>
  if failed s = true then fatal else
  .bind Frames.remaining fun s beforeCreate =>
  if failed s = true then fatal else
  if beforeCreate = before - held - 1 then
    .bind (Access.write64 (scratch + 48) beforeCreate) fun s _ =>
    if failed s = true then fatal else
    .bind (Task.create image argument) fun status descriptor =>
    if status = 38 then
      if descriptor = 0 then verifyRollback scratchHandle status else fatal
    else if status = 0 then
      -- A violated fixture expectation never leaves an unexpected task live.
      .bind (Task.terminate descriptor 0x100 0x55 0 0) fun s _ =>
      if failed s = true then fatal else
      .bind Task.reap fun s _ =>
      if failed s = true then fatal else
      .bind (releaseHeld scratchHandle) fun _ _ => fatal
    else .bind (releaseHeld scratchHandle) fun _ _ => fatal
  else fatal

private def prepare (scratchHandle owner held image argument slots : UInt64) : Action :=
  .bind (storage scratchHandle) fun s scratch =>
  if failed s = true then fatal else
  .bind (Access.write64 (scratch + 8) owner) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (scratch + 16) held) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (scratch + 24) image) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (scratch + 32) argument) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (scratch + 40) slots) fun s _ =>
  if failed s = true then fatal else
  .bind (Batch.allocate owner 4 held) fun s handles =>
  if failed s = true then
    .bind (Access.read64 scratch) fun readStatus before =>
    if failed readStatus = true then fatal else
    .bind (Frames.release 1 scratchHandle) fun releaseStatus _ =>
    if failed releaseStatus = true then fatal else
    .bind Frames.remaining fun remainingStatus after =>
    if failed remainingStatus = true then fatal else
    if after = before then .done s 0 else fatal
  else
    .bind (Access.read64 Batch.publishedCount) fun s published =>
    if failed s = true then fatal else
    if published = held then
      .boundedFoldU64 16 keepStep held.toUInt32 0 owner handles scratch argument fun s kept =>
      if failed s = true then fatal else
      if kept = held then attempt scratchHandle else fatal
    else fatal

/-- The image selection and nonce arrive only through the development control
entry. The owner is read from trusted monotonic process state, never a payload.
On the expected real late quota failure, return 38 only after complete cleanup. -/
def run (image argument : UInt64) : Action :=
  .bind inactive fun s _ =>
  if failed s = true then fatal else
  .bind (Loader.validate image) fun s record =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (record + 32)) fun s textBytes =>
  if failed s = true then fatal else
  let pages := (textBytes + 4095) / 4096
  if (if 1 ≤ pages then if pages ≤ 15 then true else false else false) = true then
  let held := 17 - pages
  .bind freeSlots fun s slots =>
  if failed s = true then fatal else
  if slots = 0 then .done 38 0 else
  .bind (Access.read64 (Process.control + 16)) fun s owner =>
  if failed s = true then fatal else
  if (if 2 ≤ owner then if owner < 0xfffffffffffffffe then true else false else false) = true then
  .bind (Frames.ownedCount owner) fun s existing =>
  if failed s = true then fatal else
  if existing = 0 then
  .bind Frames.remaining fun s before =>
  if failed s = true then fatal else
  if before < 35 then .done 33 0 else
  .bind (Frames.allocate 1 1) fun s scratchHandle =>
  if failed s = true then .done s 0 else
  .bind (storage scratchHandle) fun s scratch =>
  if failed s = true then fatal else
  .bind (Access.write64 scratch before) fun s _ =>
  if failed s = true then fatal else
  prepare scratchHandle owner held image argument slots
  else fatal else fatal else fatal

end Lemma.Kernel.Development.Pressure
