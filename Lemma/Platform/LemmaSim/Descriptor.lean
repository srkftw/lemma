import Lemma.Platform.LemmaSim.IO
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Memory.Frames

/-! Bounded binary descriptor consumer, v1. The actual reset DTB is validated
by BootInfo before this module runs. Unknown versions, checksum errors, geometry,
reservations or device-map differences fail closed before allocator setup.
This first binding checks RAM plus reset-DTB identity/envelope; complete DTB
peripheral-property validation remains an integration obligation. -/
namespace Lemma.Platform.LemmaSim.Descriptor
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def base : UInt64 := 0x10010400
def invalid : UInt8 := 169
def word (index : UInt64) : Action := IO.read64 (base + index * 8)
def failed (s : UInt8) : Bool := if s = 0 then false else true
private def sumStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  if i = 3 then .done 0 acc else
  .bind (word i.toUInt64) fun s v => if s = 0 then .done 0 (acc + v) else .done s 0
private def expected (index : UInt64) : UInt64 :=
  if index = 0 then 1280132179 else if index = 1 then 1 else if index = 2 then 256 else
  if index = 4 then 0x80000000 else if index = 5 then 0x08000000 else
  if index = 6 then 0x82000000 else if index = 7 then 0x02000000 else
  if index = 8 then 10000000 else if index = 9 then 0x10010000 else
  if index = 10 then 0x1000 else if index = 11 then 12 else
  if index = 12 then 0x10011000 else if index = 13 then 0x1000 else if index = 14 then 13 else
  if index = 15 then 0x10001000 else if index = 16 then 0x1000 else if index = 17 then 1 else
  if index = 22 then 0x02000000 else if index = 23 then 0x0c000000 else
  if index = 24 then 0x10000000 else if index = 25 then 0x101000 else
  if index = 28 then 0x80000000 else if index = 29 then 0x02000000 else
  if index = 30 then 0x87e00000 else if index = 31 then 0x00200000 else 0
private def fieldsStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  if i = 3 then .done 0 acc else if 18 ≤ i then if i ≤ 21 then .done 0 acc else
    if i = 26 then .done 0 acc else if i = 27 then .done 0 acc else compare i acc
  else compare i acc
where
  compare (i : UInt32) (acc : UInt64) : Action :=
    .bind (word i.toUInt64) fun s v =>
    if s = 0 then if v = expected i.toUInt64 then .done 0 acc else .done invalid 0 else .done s 0

private def geometry : Action :=
  .bind (word 18) fun s width =>
  if failed s = true then .done s 0 else
  .bind (word 19) fun s height =>
  if failed s = true then .done s 0 else
  if (if width = 1650 then if height = 2200 then true else false else
    if width = 1404 then if height = 1872 then true else false else false) = false then .done invalid 0 else
  .bind (IO.read64 0x10010020) fun s actualWidth =>
  if failed s = true then .done s 0 else
  .bind (IO.read64 0x10010028) fun s actualHeight =>
  if failed s = true then .done s 0 else
  .bind (word 20) fun s pressure =>
  if failed s = true then .done s 0 else
  .bind (IO.read64 0x10011048) fun s actualPressure =>
  if failed s = true then .done s 0 else
  if width = actualWidth then if height = actualHeight then
  if pressure = actualPressure then .done 0 width else .done invalid 0
  else .done invalid 0 else .done invalid 0

/-- Called once before the frame allocator. It never treats a host JSON profile
as guest discovery and never dereferences an unbounded borrowed pointer. -/
def validate : Action :=
  .boundedFoldU64 32 fieldsStep 32 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 32 sumStep 32 0 0 0 0 0 fun s checksum =>
  if failed s = true then .done s 0 else
  .bind (word 3) fun s actual =>
  if failed s = true then .done s 0 else
  if checksum = actual then
  .bind (word 26) fun s dtb =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 0x80400008) fun s handed =>
  if failed s = true then .done s 0 else
  if dtb = handed then
  .bind geometry fun s _ =>
  if failed s = true then .done s 0 else
  .bind (word 7) fun s bytes =>
  if failed s = true then .done s 0 else
  Frames.configure (bytes / 4096) (bytes / 4096) 4
  else .done invalid 0 else .done invalid 0

end Lemma.Platform.LemmaSim.Descriptor
