import Lemma.User.ClosureExamples
import Lemma.User.Runtime.ManagedClosure

/-! Quarantined isolated-process qualification only. Every ordinary closure is
compiled through managedClosure2. Resource observation uses actual user memory
and the real owned arena, then tears down its syscall-owned page before exit. -/
namespace Lemma.User.Development.ClosureProcess
open Lemma.Core0.Memory Lemma.User.Runtime

private def finish (status : UInt8) (value : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (Arena.control+16)) fun s count => if s = 0 then
  if count = 0 then
  .bind Arena.destroy fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20000 value) fun s _ => if s = 0 then .done status 0 else .done s 0
  else .done s 0 else .done Arena.lifetime 0 else .done s 0

private def pressureStep (i _ : UInt32) (count _ _ _ _ : UInt64) : Action :=
  .bind (Arena.newBox i.toUInt64) fun s box => if s = 0 then
  .bind (Lemma.User.Memory.write64 (0x20100+i.toUInt64*8) box) fun s _ => .done s (count+1)
  else .done s 0
private def releaseStep (i _ : UInt32) (count _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (0x20100+i.toUInt64*8)) fun s box => if s = 0 then
  .bind (Arena.release box) fun s _ => .done s (count+1) else .done s 0

private def failedPressure (status : UInt8) (expected : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 (Arena.control+16)) fun s count => if s = 0 then
  if count = expected then
  .boundedFoldU64 31 releaseStep expected.toUInt32 0 0 0 0 0 fun s released => if s = 0 then
  if released = expected then finish status 0 else .done Arena.lifetime 0
  else .done s 0 else .done Arena.lifetime 0 else .done s 0

def entry (case : UInt64) : Action :=
  .bind Arena.ensure fun s _ => if s = 0 then
  if case = 4 then
    .boundedFoldU64 31 pressureStep 29 0 0 0 0 0 fun s count => if s = 0 then
    if count = 29 then
    .managedClosure2 Lemma.User.ClosureExamples.selected 0 1 fun s _ =>
      if s = Arena.exhausted then failedPressure s 29 else .done Arena.lifetime 0
    else .done Arena.lifetime 0 else .done s 0
  else if case = 5 then
    .boundedFoldU64 31 pressureStep 27 0 0 0 0 0 fun s count => if s = 0 then
    if count = 27 then
    .managedClosure2 Lemma.User.ClosureExamples.fourCaptures 1 2 fun s _ =>
      if s = Arena.exhausted then failedPressure s 27 else .done Arena.lifetime 0
    else .done Arena.lifetime 0 else .done s 0
  else if 8 ≤ case then
    .managedClosure2 Lemma.User.ClosureExamples.sharedCaptures (if case = 8 then 0 else 1)
      0x8000000000000001 fun s value => if s = 0 then finish s value else .done s 0
  else if 6 ≤ case then
    .managedClosure2 Lemma.User.ClosureExamples.lambdaEntry (if case = 6 then 0 else 2)
      0x8000000000000001 fun s value => if s = 0 then finish s value else .done s 0
  else if case = 2 then
    .managedClosure2 Lemma.User.ClosureExamples.fourCaptures 0xffffffffffffffff 0x8000000000000001
      fun s value => if s = 0 then finish s value else .done s 0
  else
    .managedClosure2 Lemma.User.ClosureExamples.selected
      (if case = 0 then 0 else if case = 1 then 2 else 0xffffffffffffffff)
      (if case = 0 then 0xffffffffffffffff else 0x8000000000000001)
      fun s value => if s = 0 then finish s value else .done s 0
  else .done s 0
end Lemma.User.Development.ClosureProcess
