import Lemma.Drivers.Multimodal
import Lemma.Kernel.Memory.Access
import Lemma.Boot.RecoveryExecuted

/-! Actual compiled bounded converter workload, shared by native fast/RTL.
Stimuli enter external converter ports, never from these guest records. This
component tests controller operation; it is not the whole notebook workflow. -/
namespace Lemma.Multimodal.ControllerProbe
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
private def failed (s : UInt8) : Bool := if s = 0 then false else true
private def different (a b : UInt64) : Bool := if a = b then false else true

def result : UInt64 := 0x80410000
private def store (offset value : UInt64) : Action := Access.write64 (result + offset) value
private def reg (stream offset value : UInt64) : Action := Lemma.Drivers.Multimodal.write stream offset value
private def read (stream offset : UInt64) : Action := Lemma.Drivers.Multimodal.read stream offset

private def prepareStep (i _ : UInt32) (acc expiry _ _ _ : UInt64) : Action :=
  let stream := i.toUInt64
  .bind (Lemma.Drivers.Multimodal.command stream 1) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 48 2) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 56 1000000) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 64 3) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 72 1) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 80 1) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 96 1) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 104 expiry) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.command stream 2) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.command stream 3) fun s _ => if failed s = true then .done s 0 else
  .bind (if stream = 8 then .done 0 0 else Lemma.Drivers.Multimodal.command stream 4) fun s _ => .done s (acc + 1)

private def readyStep (_ _ : UInt32) (acc stream _ _ _ : UInt64) : Action :=
  .bind (read stream 144) fun s queued => if failed s = true then .done s 0 else
  if queued = 0 then .done 0 acc else .done Status.iterationStop queued

private def offset (word : UInt64) : UInt64 :=
  if word = 0 then 112 else if word = 1 then 120 else if word = 2 then 128 else
  if word = 3 then 136 else if word = 4 then 224 else if word = 5 then 32 else
  if word = 6 then 192 else 72

private def copyStep (i _ : UInt32) (acc stream _ _ _ : UInt64) : Action :=
  .bind (read stream (offset i.toUInt64)) fun s value => if failed s = true then .done s 0 else
  .bind (store (128 + stream * 64 + i.toUInt64 * 8) value) fun s _ => .done s acc

private def observeStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let stream := i.toUInt64
  .boundedFoldU64 200000 readyStep 200000 0 stream 0 0 0 fun s queued =>
  if (if s = 0 then false else if s = Status.iterationStop then false else true) = true then .done s 0 else if queued = 0 then .done 8 0 else
  .boundedFoldU64 8 copyStep 8 0 stream 0 0 0 fun s _ => if failed s = true then .done s 0 else
  .bind (read stream 224) fun s sequence => if failed s = true then .done s 0 else
  .bind (reg stream 152 1) fun s _ => if failed s = true then .done s 0 else
  .bind (reg stream 80 0) fun s _ => .done s (acc + 1)

private def work : Action :=
  .bind Lemma.Drivers.Multimodal.discover fun s features => if failed s = true then .done s 0 else
  .bind (store 8 features) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Platform.LemmaSim.IO.write64 (Lemma.Drivers.Multimodal.base + 56) 0) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Platform.LemmaSim.IO.read64 (Lemma.Drivers.Multimodal.base + 24)) fun s tick => if failed s = true then .done s 0 else
  .bind (store 16 tick) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 9 prepareStep 9 0 (tick + 100000000) 0 0 0 fun s _ => if failed s = true then .done s 0 else
  .bind (reg 8 112 0x1020304050607080) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Drivers.Multimodal.command 8 4) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 8 observeStep 8 0 0 0 0 0 fun s count => if failed s = true then .done s 0 else
  .bind (store 24 count) fun s _ => if failed s = true then .done s 0 else
  .bind (read 8 232) fun s consumed => if failed s = true then .done s 0 else
  .bind (store 32 consumed) fun s _ => if failed s = true then .done s 0 else
  .bind (reg 8 80 0) fun s _ => if failed s = true then .done s 0 else
  .bind (read 8 144) fun s remaining => if failed s = true then .done s 0 else
  .bind (store 40 remaining) fun s _ => if failed s = true then .done s 0 else
  if different consumed 1 = true then .done 10 0 else .done 0 count

def entry : Action :=
  .uartEnableAndResetFifo fun s => if failed s = true then .done s 0 else
  .bind (store 0 0) fun s _ => if failed s = true then .done s 0 else
  .bind work fun status count =>
  .bind (store 48 status.toUInt64) fun s _ => if failed s = true then .done s 0 else
  .bind (store 56 count) fun s _ => if failed s = true then .done s 0 else
  .bind (store 0 0x4c4d4d50) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Boot.RecoveryExecuted.transmitByte 76) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Boot.RecoveryExecuted.transmitByte 77) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Boot.RecoveryExecuted.transmitByte 77) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Boot.RecoveryExecuted.transmitByte 80) fun s _ => .done s count

end Lemma.Multimodal.ControllerProbe
