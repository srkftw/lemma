import Lemma.Platform.LemmaSim.IO
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Memory.Frames
import Lemma.Platform.LemmaSim.DescriptorDTB
import Lemma.Platform.Silicon.BindingFull
import Lemma.Platform.Silicon.BindingPower
import Lemma.Platform.Silicon.BindingUSB
import Lemma.Platform.Silicon.BindingProduct
import Lemma.Platform.Silicon.BindingUSBNext
import Lemma.Platform.Silicon.BindingProductNext
import Lemma.Platform.Silicon.BindingProductExecuted
import Lemma.Platform.Silicon.BindingUSBWire

/-! Bounded binary descriptor consumer, v1. The actual reset DTB is validated
by BootInfo before this module runs. Unknown versions, checksum errors, geometry,
reservations or device-map differences fail closed before allocator setup.
The subordinate bounded FDT pass checks actual peripheral properties, including
range/IRQ/identity/clock/geometry consistency, before allocator setup. -/
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
private def expectedBinding (binding index : UInt64) : UInt64 :=
  if binding = 7 then if index = 1 then 8 else
    if index = 7 then Lemma.Platform.Silicon.BindingProduct.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingProduct.power_base else expected index
  else if binding = 6 then if index = 1 then 7 else
    if index = 7 then Lemma.Platform.Silicon.BindingUSB.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingUSB.power_base else expected index
  else if binding = 5 then if index = 1 then 6 else
    if index = 7 then Lemma.Platform.Silicon.BindingPower.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingPower.power_base else expected index
  else if binding = 4 then if index = 1 then 5 else
    if index = 7 then Lemma.Platform.Silicon.BindingPower.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingPower.power_base else expected index
  else if binding = 3 then if index = 1 then 4 else
    if index = 7 then Lemma.Platform.Silicon.BindingPower.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingPower.power_base else expected index
  else if binding = 2 then if index = 1 then 3 else
    if index = 7 then Lemma.Platform.Silicon.BindingFull.frame_pool_bytes else
    if index = 25 then 0 else expected index
  else if binding = 1 then if index = 1 then 2 else
    if index = 7 then Lemma.Platform.Silicon.Binding.frame_pool_bytes else
    if index = 25 then 0 else expected index
  else expected index
private def fieldsStep (i _ : UInt32) (acc binding _ _ _ : UInt64) : Action :=
  if i = 3 then .done 0 acc else if 18 ≤ i then if i ≤ 21 then .done 0 acc else
    if i = 26 then .done 0 acc else if i = 27 then .done 0 acc else compare binding i acc
  else compare binding i acc
where
  compare (binding : UInt64) (i : UInt32) (acc : UInt64) : Action :=
    .bind (word i.toUInt64) fun s v =>
    if s = 0 then if v = expectedBinding binding i.toUInt64 then .done 0 acc else .done invalid 0 else .done s 0

private def geometry (binding : UInt64) : Action :=
  .bind (word 18) fun s width =>
  if failed s = true then .done s 0 else
  .bind (word 19) fun s height =>
  if failed s = true then .done s 0 else
  if (if binding = 1 then
      if width = Lemma.Platform.Silicon.Binding.width then
      if height = Lemma.Platform.Silicon.Binding.height then true else false else false else
    if 3 ≤ binding then
      if width = Lemma.Platform.Silicon.BindingPower.width then
      if height = Lemma.Platform.Silicon.BindingPower.height then true else false else false else
    if binding = 2 then
      if width = Lemma.Platform.Silicon.BindingFull.width then
      if height = Lemma.Platform.Silicon.BindingFull.height then true else false else false else
    if width = 1650 then if height = 2200 then true else false else
    if width = 1404 then if height = 1872 then true else false else false) = false then .done invalid 0 else
  .bind (IO.read64 0x10010020) fun s actualWidth =>
  if failed s = true then .done s 0 else
  .bind (IO.read64 0x10010028) fun s actualHeight =>
  if failed s = true then .done s 0 else
  .bind (word 20) fun s pressure =>
  if failed s = true then .done s 0 else
  .bind (word 21) fun s features =>
  if failed s = true then .done s 0 else
  if features = (if binding = 7 then 31 else if binding = 6 then 15 else if binding = 5 then 7 else 3) then
  .bind (IO.read64 0x10011048) fun s actualPressure =>
  if failed s = true then .done s 0 else
  if width = actualWidth then if height = actualHeight then
  if pressure = actualPressure then
  .bind (word 26) fun s dtb => if s = 0 then
  .bind (word 27) fun s bytes => if s = 0 then
  if binding = 7 then DescriptorDTB.validateSiliconProduct dtb bytes width height pressure
  else if binding = 6 then DescriptorDTB.validateSiliconUSB dtb bytes width height pressure
  else if binding = 5 then DescriptorDTB.validateSiliconBLE dtb bytes width height pressure
  else if binding = 4 then DescriptorDTB.validateSiliconSafety dtb bytes width height pressure
  else if binding = 3 then DescriptorDTB.validateSiliconPower dtb bytes width height pressure
  else if binding = 1 then DescriptorDTB.validateSilicon dtb bytes width height pressure
  else if binding = 2 then DescriptorDTB.validateSilicon dtb bytes width height pressure
  else DescriptorDTB.validate dtb bytes width height pressure
  else .done s 0 else .done s 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0

/-- Called once before the frame allocator. It never treats a host JSON profile
as guest discovery and never dereferences an unbounded borrowed pointer. -/
def validateBinding (binding : UInt64) : Action :=
  if 7 < binding then .done invalid 0 else
  .boundedFoldU64 32 fieldsStep 32 0 binding 0 0 0 fun s _ =>
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
  .bind (geometry binding) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (word 7) fun s bytes =>
  if failed s = true then .done s 0 else
  if binding = 1 then
    Frames.configure (bytes / 4096) Lemma.Platform.Silicon.Binding.frame_quota 4
  else Frames.configure (bytes / 4096) (bytes / 4096) 4
  else .done invalid 0 else .done invalid 0

def validate : Action := validateBinding 0

def validateSilicon : Action := validateBinding 1

/-- Versioned full-memory silicon-development profile. This still uses external
simulation memory; it makes no on-chip SRAM or physical-conformance claim. -/
def validateSiliconFull : Action := validateBinding 2

def validateSiliconPower : Action := validateBinding 3

def validateSiliconSafety : Action := validateBinding 4

/-- Opt-in manual BLE packet development binding; no Bluetooth qualification. -/
def validateSiliconBLE : Action := validateBinding 5

/-- Opt-in decoded USB packet binding; physical USB PHY conformance remains open. -/
def validateSiliconUSB : Action := validateBinding 6

def validateSiliconProduct : Action := validateBinding 7

private def expectedBindingNext (binding index : UInt64) : UInt64 :=
  if binding = 9 then if index = 1 then 10 else
    if index = 7 then Lemma.Platform.Silicon.BindingProductNext.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingProductNext.power_base else expected index
  else if binding = 8 then if index = 1 then 9 else
    if index = 7 then Lemma.Platform.Silicon.BindingUSBNext.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingUSBNext.power_base else expected index
  else 0

private def fieldsStepNext (i _ : UInt32) (acc binding _ _ _ : UInt64) : Action :=
  if i = 3 then .done 0 acc else if 18 ≤ i then if i ≤ 21 then .done 0 acc else
    if i = 26 then .done 0 acc else if i = 27 then .done 0 acc else compare binding i acc
  else compare binding i acc
where
  compare (binding : UInt64) (i : UInt32) (acc : UInt64) : Action :=
    .bind (word i.toUInt64) fun s v =>
    if s = 0 then if v = expectedBindingNext binding i.toUInt64 then .done 0 acc else .done invalid 0 else .done s 0


private def geometryNext (binding : UInt64) : Action :=
  .bind (word 18) fun s width =>
  if failed s = true then .done s 0 else
  .bind (word 19) fun s height =>
  if failed s = true then .done s 0 else
  if (if binding = 1 then
      if width = Lemma.Platform.Silicon.Binding.width then
      if height = Lemma.Platform.Silicon.Binding.height then true else false else false else
    if 3 ≤ binding then
      if width = Lemma.Platform.Silicon.BindingPower.width then
      if height = Lemma.Platform.Silicon.BindingPower.height then true else false else false else
    if binding = 2 then
      if width = Lemma.Platform.Silicon.BindingFull.width then
      if height = Lemma.Platform.Silicon.BindingFull.height then true else false else false else
    if width = 1650 then if height = 2200 then true else false else
    if width = 1404 then if height = 1872 then true else false else false) = false then .done invalid 0 else
  .bind (IO.read64 0x10010020) fun s actualWidth =>
  if failed s = true then .done s 0 else
  .bind (IO.read64 0x10010028) fun s actualHeight =>
  if failed s = true then .done s 0 else
  .bind (word 20) fun s pressure =>
  if failed s = true then .done s 0 else
  .bind (word 21) fun s features =>
  if failed s = true then .done s 0 else
  if features = (if binding = 9 then 31 else 15) then
  .bind (IO.read64 0x10011048) fun s actualPressure =>
  if failed s = true then .done s 0 else
  if width = actualWidth then if height = actualHeight then
  if pressure = actualPressure then
  .bind (word 26) fun s dtb => if s = 0 then
  .bind (word 27) fun s bytes => if s = 0 then
  if binding = 9 then DescriptorDTB.validateSiliconProductNext dtb bytes width height pressure
  else DescriptorDTB.validateSiliconUSBNext dtb bytes width height pressure
  else .done s 0 else .done s 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0


def validateBindingNext (binding : UInt64) : Action :=
  if binding = 8 then admitted binding else if binding = 9 then admitted binding else .done invalid 0
where
 admitted (binding : UInt64) : Action :=
  if 9 < binding then .done invalid 0 else
  .boundedFoldU64 32 fieldsStepNext 32 0 binding 0 0 0 fun s _ =>
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
  .bind (geometryNext binding) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (word 7) fun s bytes =>
  if failed s = true then .done s 0 else
  if binding = 1 then
    Frames.configure (bytes / 4096) Lemma.Platform.Silicon.Binding.frame_quota 4
  else Frames.configure (bytes / 4096) (bytes / 4096) 4
  else .done invalid 0 else .done invalid 0


/-- Additive Paper-v2 USB/Product hardware discovery, exact ABI9/10. -/
def validateSiliconUSBNext : Action := validateBindingNext 8
def validateSiliconProductNext : Action := validateBindingNext 9

private def expectedBindingExecuted (binding index : UInt64) : UInt64 :=
  if binding = 10 then if index = 1 then 11 else
    if index = 7 then Lemma.Platform.Silicon.BindingProductExecuted.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingProductExecuted.power_base else expected index
  else 0

private def fieldsStepExecuted (i _ : UInt32) (acc binding _ _ _ : UInt64) : Action :=
  if i = 3 then .done 0 acc else if 18 ≤ i then if i ≤ 21 then .done 0 acc else
    if i = 26 then .done 0 acc else if i = 27 then .done 0 acc else compare binding i acc
  else compare binding i acc
where
  compare (binding : UInt64) (i : UInt32) (acc : UInt64) : Action :=
    .bind (word i.toUInt64) fun s v =>
    if s = 0 then if v = expectedBindingExecuted binding i.toUInt64 then .done 0 acc else .done invalid 0 else .done s 0


private def geometryExecuted (binding : UInt64) : Action :=
  .bind (word 18) fun s width =>
  if failed s = true then .done s 0 else
  .bind (word 19) fun s height =>
  if failed s = true then .done s 0 else
  if (if binding = 1 then
      if width = Lemma.Platform.Silicon.Binding.width then
      if height = Lemma.Platform.Silicon.Binding.height then true else false else false else
    if 3 ≤ binding then
      if width = Lemma.Platform.Silicon.BindingPower.width then
      if height = Lemma.Platform.Silicon.BindingPower.height then true else false else false else
    if binding = 2 then
      if width = Lemma.Platform.Silicon.BindingFull.width then
      if height = Lemma.Platform.Silicon.BindingFull.height then true else false else false else
    if width = 1650 then if height = 2200 then true else false else
    if width = 1404 then if height = 1872 then true else false else false) = false then .done invalid 0 else
  .bind (IO.read64 0x10010020) fun s actualWidth =>
  if failed s = true then .done s 0 else
  .bind (IO.read64 0x10010028) fun s actualHeight =>
  if failed s = true then .done s 0 else
  .bind (word 20) fun s pressure =>
  if failed s = true then .done s 0 else
  .bind (word 21) fun s features =>
  if failed s = true then .done s 0 else
  if features = (if binding = 10 then 31 else 15) then
  .bind (IO.read64 0x10011048) fun s actualPressure =>
  if failed s = true then .done s 0 else
  if width = actualWidth then if height = actualHeight then
  if pressure = actualPressure then
  .bind (word 26) fun s dtb => if s = 0 then
  .bind (word 27) fun s bytes => if s = 0 then
  if binding = 10 then DescriptorDTB.validateSiliconProductExecuted dtb bytes width height pressure
  else .done invalid 0
  else .done s 0 else .done s 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0


def validateBindingExecuted (binding : UInt64) : Action :=
  if binding = 10 then admitted binding else .done invalid 0
where
 admitted (binding : UInt64) : Action :=
  if 10 < binding then .done invalid 0 else
  .boundedFoldU64 32 fieldsStepExecuted 32 0 binding 0 0 0 fun s _ =>
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
  .bind (geometryExecuted binding) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (word 7) fun s bytes =>
  if failed s = true then .done s 0 else
  if binding = 1 then
    Frames.configure (bytes / 4096) Lemma.Platform.Silicon.Binding.frame_quota 4
  else Frames.configure (bytes / 4096) (bytes / 4096) 4
  else .done invalid 0 else .done invalid 0


def validateSiliconProductExecuted : Action := validateBindingExecuted 10

private def expectedBindingWire (binding index : UInt64) : UInt64 :=
  if binding = 11 then if index = 1 then 12 else
    if index = 7 then Lemma.Platform.Silicon.BindingUSBWire.frame_pool_bytes else
    if index = 25 then Lemma.Platform.Silicon.BindingUSBWire.power_base else expected index
  else 0

private def fieldsStepWire (i _ : UInt32) (acc binding _ _ _ : UInt64) : Action :=
  if i = 3 then .done 0 acc else if 18 ≤ i then if i ≤ 21 then .done 0 acc else
    if i = 26 then .done 0 acc else if i = 27 then .done 0 acc else compare binding i acc
  else compare binding i acc
where
  compare (binding : UInt64) (i : UInt32) (acc : UInt64) : Action :=
    .bind (word i.toUInt64) fun s v =>
    if s = 0 then if v = expectedBindingWire binding i.toUInt64 then .done 0 acc else .done invalid 0 else .done s 0


private def geometryWire (binding : UInt64) : Action :=
  .bind (word 18) fun s width =>
  if failed s = true then .done s 0 else
  .bind (word 19) fun s height =>
  if failed s = true then .done s 0 else
  if (if binding = 1 then
      if width = Lemma.Platform.Silicon.Binding.width then
      if height = Lemma.Platform.Silicon.Binding.height then true else false else false else
    if 3 ≤ binding then
      if width = Lemma.Platform.Silicon.BindingPower.width then
      if height = Lemma.Platform.Silicon.BindingPower.height then true else false else false else
    if binding = 2 then
      if width = Lemma.Platform.Silicon.BindingFull.width then
      if height = Lemma.Platform.Silicon.BindingFull.height then true else false else false else
    if width = 1650 then if height = 2200 then true else false else
    if width = 1404 then if height = 1872 then true else false else false) = false then .done invalid 0 else
  .bind (IO.read64 0x10010020) fun s actualWidth =>
  if failed s = true then .done s 0 else
  .bind (IO.read64 0x10010028) fun s actualHeight =>
  if failed s = true then .done s 0 else
  .bind (word 20) fun s pressure =>
  if failed s = true then .done s 0 else
  .bind (word 21) fun s features =>
  if failed s = true then .done s 0 else
  if features = (15) then
  .bind (IO.read64 0x10011048) fun s actualPressure =>
  if failed s = true then .done s 0 else
  if width = actualWidth then if height = actualHeight then
  if pressure = actualPressure then
  .bind (word 26) fun s dtb => if s = 0 then
  .bind (word 27) fun s bytes => if s = 0 then
  if binding = 11 then DescriptorDTB.validateSiliconUSBWire dtb bytes width height pressure
  else .done invalid 0
  else .done s 0 else .done s 0 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0


def validateBindingWire (binding : UInt64) : Action :=
  if binding = 11 then admitted binding else .done invalid 0
where
 admitted (binding : UInt64) : Action :=
  if 11 < binding then .done invalid 0 else
  .boundedFoldU64 32 fieldsStepWire 32 0 binding 0 0 0 fun s _ =>
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
  .bind (geometryWire binding) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (word 7) fun s bytes =>
  if failed s = true then .done s 0 else
  if binding = 1 then
    Frames.configure (bytes / 4096) Lemma.Platform.Silicon.Binding.frame_quota 4
  else Frames.configure (bytes / 4096) (bytes / 4096) 4
  else .done invalid 0 else .done invalid 0


def validateSiliconUSBWire : Action := validateBindingWire 11


end Lemma.Platform.LemmaSim.Descriptor
