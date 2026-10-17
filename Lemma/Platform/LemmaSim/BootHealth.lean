import Lemma.Boot.Product
import Lemma.Kernel.Task
import Lemma.Kernel.Console
import Lemma.Platform.LemmaSim.DeviceABI

/-! Product-only confirmation after actual isolated services and a completed
canonical full refresh. This is kernel policy, not ROM auto-confirmation or a
host readiness oracle. A failed barrier stays failed and is never retried by
this health observer. Notebook journal acknowledgement remains store policy. -/
namespace Lemma.Platform.LemmaSim.BootHealth
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory

def state : UInt64 := 0x80400f80
private def get (offset : UInt64) : Action := Access.read64 (state + offset)
private def put (offset value : UInt64) : Action := Access.write64 (state + offset) value
private def fatal : Action := .done 50 0
private def paper (offset : UInt64) : Action := IO.read64 (DeviceABI.paperBase + offset)

private def liveImage (descriptor image : UInt64) : Action :=
  .bind (Task.lookup descriptor) fun s record => if s = 0 then
  .bind (Access.read64 (record + Task.imageOffset)) fun s actual => if s = 0 then
  if actual = image then .done 0 record else fatal else fatal else fatal

def configure (store notebook : UInt64) : Action :=
  .bind (liveImage store 0) fun s _ => if s = 0 then
  .bind (liveImage notebook 1) fun s _ => if s = 0 then
  .bind (Access.read64 Lemma.Boot.Product.scratch) fun s magic => if s = 0 then
  if magic = Lemma.Boot.Product.contextMagic then
  .bind (Access.read64 (Lemma.Boot.Product.scratch + 8)) fun s version => if s = 0 then
  if version = 1 then
  .bind (Access.read64 (Lemma.Boot.Product.scratch + 40)) fun s trial => if s = 0 then
  if trial < 2 then
  .bind (put 0 trial) fun s _ => if s = 0 then
  .bind (put 8 store) fun s _ => if s = 0 then
  .bind (put 16 notebook) fun s _ => if s = 0 then
  .bind (put 24 0) fun s _ => if s = 0 then put 32 0 else fatal else fatal
  else fatal else fatal else fatal
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

private def recordResult (status : UInt8) (sector sequence : UInt64) : Action :=
  .bind (put 24 status.toUInt64) fun s _ => if s = 0 then
  .bind (put 32 sequence) fun s _ => if s = 0 then
  .bind (put 0 (if status = 0 then 3 else 4)) fun s _ => if s = 0 then
  Console.record 0x473 status.toUInt64 sector sequence 0
  else fatal else fatal else fatal

private def confirm (sequence : UInt64) : Action :=
  -- Publish attempted before issuing external I/O. A failure never spins on
  -- this critical path or manufactures confirmation on a later scheduler step.
  .bind (put 0 2) fun s _ => if s = 0 then
  .bind Lemma.Boot.Product.selectedMetadata fun status selected =>
  if status = 0 then
    if selected < 2 then
      .bind (Lemma.Boot.Product.confirm selected (if selected = 0 then
        Lemma.Boot.Product.metadata0Buffer else Lemma.Boot.Product.metadata1Buffer)) fun status receipt =>
      recordResult status receipt sequence
    else recordResult Lemma.Boot.Product.wrongReceipt selected sequence
  else recordResult status selected sequence
  else fatal

private def fullRefresh (sequence : UInt64) : Action :=
  .bind (paper DeviceABI.paperSequenceOffset) fun s requested => if s = 0 then
  if requested = sequence then
  .bind (paper DeviceABI.paperStatusOffset) fun s status => if s = 0 then
  if status &&& 1 = 0 then
  .bind (paper DeviceABI.paperErrorOffset) fun s error => if s = 0 then
  if error = 0 then
  .bind (paper DeviceABI.paperRectXOffset) fun s x => if s = 0 then
  .bind (paper DeviceABI.paperRectYOffset) fun s y => if s = 0 then
  .bind (paper DeviceABI.paperRectWOffset) fun s width => if s = 0 then
  .bind (paper DeviceABI.paperRectHOffset) fun s height => if s = 0 then
  if x ||| y = 0 then if width = 1650 then if height = 2200 then
  .bind (get 8) fun s store => if s = 0 then
  .bind (liveImage store 0) fun s _ => if s = 0 then
  .bind (get 16) fun s notebook => if s = 0 then
  .bind (liveImage notebook 1) fun s _ => if s = 0 then confirm sequence
  else fatal else fatal else fatal else fatal
  else .done 0 0 else .done 0 0 else .done 0 0
  else fatal else fatal else fatal else fatal
  else .done 0 0 else fatal else .done 0 0 else fatal else .done 0 0 else fatal

def step : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  if phase = 1 then
    .bind (paper DeviceABI.paperCompletedOffset) fun s sequence => if s = 0 then
    if sequence = 0 then .done 0 0 else fullRefresh sequence
    else fatal
  else .done 0 0 else fatal

end Lemma.Platform.LemmaSim.BootHealth
