import Lemma.Platform.LemmaSim.Descriptor
import Lemma.Platform.LemmaVM.ConsoleDevice
import Lemma.Drivers.VirtIOBlock
import Lemma.Drivers.Paper
import Lemma.Drivers.Pen
import Lemma.Drivers.PLIC
import Lemma.Kernel.Scheduler

/-! First integrated device binding over the existing kernel, loader and scheduler.
This bring-up configuration is a runnable checkpoint, not notebook completion.
PLIC notification is delivered by the real S trap while an isolated U task runs;
IRQ handler work is constant bounded claim/latch/complete. Device service work
runs on the reserved supervisor continuation before the next task entry.
No page, stroke, document or recovery policy lives in this module. -/
namespace Lemma.Platform.LemmaSim.Entry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Kernel

def state : UInt64 := 0x80400b00
private def get (offset : UInt64) : Action := Access.read64 (state + offset)
private def put (offset value : UInt64) : Action := Access.write64 (state + offset) value
private def failed (s : UInt8) : Bool := if s = 0 then false else true
private def fatal : Action := .done 50 0

private def observeBlock : Action :=
  .bind Lemma.Drivers.VirtIOBlock.finish fun s request =>
  if s = Lemma.Drivers.VirtIOBlock.pending then .done 0 0 else
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0x401 request 0 0 0) fun s _ =>
  if failed s = true then fatal else
  if request = 1 then Lemma.Drivers.VirtIOBlock.submit 4 0 else
  if request = 5 then put 16 1 else fatal

private def observePen : Action :=
  .bind (get 8) fun s handle => if failed s = true then fatal else
  .bind (Lemma.Drivers.Pen.take handle) fun status sequence =>
  if status = Lemma.Drivers.Pen.empty then .done 0 0 else
  if status = Lemma.Drivers.Pen.lost then
    Lemma.Kernel.Console.record 0x403 status.toUInt64 sequence 0 0
  else if status = 0 then
    .bind (Frames.resolvePurpose 1 handle 1) fun s buffer => if failed s = true then fatal else
    .bind (Access.read64 (buffer + 16)) fun s x => if failed s = true then fatal else
    .bind (Access.read64 (buffer + 24)) fun s y => if failed s = true then fatal else
    Lemma.Kernel.Console.record 0x402 sequence x y 0
  else .done status 0

private def devices : Action :=
  .bind (get 0) fun s flags => if failed s = true then fatal else
  .bind (put 0 0) fun s _ => if failed s = true then fatal else
  .bind (if flags &&& 2 = 2 then observeBlock else .done 0 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (if flags &&& 4096 = 4096 then Lemma.Drivers.Paper.completion else .done 0 0) fun s _ =>
  if failed s = true then .done s 0 else
  if flags &&& 8192 = 8192 then observePen else .done 0 0

def step : Action :=
  .bind devices fun s _ => if failed s = true then .done s 0 else
  .bind (get 16) fun s doneIO => if failed s = true then fatal else
  .bind (get 24) fun s reported => if failed s = true then fatal else
  .bind (if doneIO = 1 then if reported = 0 then
    .bind (put 24 1) fun s _ => if failed s = true then fatal else
    .bind Frames.remaining fun s remaining => if failed s = true then fatal else
    .bind Frames.runtimeCount fun s amount => if failed s = true then fatal else
    Lemma.Kernel.Console.record 0x404 remaining 4 amount 0
    else .done 0 0 else .done 0 0) fun s _ =>
  if failed s = true then fatal else Scheduler.step

def start : Action :=
  .bind (put 0 0) fun s _ => if failed s = true then fatal else
  .bind (put 16 0) fun s _ => if failed s = true then fatal else
  .bind (put 24 0) fun s _ => if failed s = true then fatal else
  .bind (Frames.allocate 1 1) fun s handle => if failed s = true then .done s 0 else
  .bind (put 8 handle) fun s _ => if failed s = true then fatal else
  .bind Process.init fun s _ => if failed s = true then .done s 0 else
  .bind Task.init fun s _ => if failed s = true then .done s 0 else
  .bind (Task.create 0 0) fun s descriptor => if failed s = true then .done s 0 else
  .bind Frames.runtimeCount fun s amount => if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0x400 descriptor amount 4 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Lemma.Drivers.VirtIOBlock.submit 0 0) fun s _ =>
  if failed s = true then .done s 0 else .loop step

def initializeBinding (binding : UInt64) : Action :=
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ =>
  if failed s = true then .done s 0 else
  .bind Lemma.Kernel.BootInfo.validate fun s _ => if failed s = true then .done s 0 else
  .bind (if binding = 1 then Descriptor.validateSilicon else Descriptor.validate) fun s _ => if failed s = true then .done s 0 else
  .bind Frames.init fun s _ => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.VirtIOBlock.initialize fun s capacity => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.Paper.initialize fun s geometry => if failed s = true then .done s 0 else
  .bind Lemma.Drivers.Pen.initialize fun s epoch => if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0x405 capacity geometry epoch 0) fun s _ =>
  if failed s = true then fatal else
  Lemma.Drivers.PLIC.initialize

def boot : Action :=
  .bind (initializeBinding 0) fun s _ => if failed s = true then .done s 0 else start

/-- Real SEIP handling. A client cannot manufacture the trap frame, IRQ number,
or DMA pointers. Expensive device handling is deferred until returnKernel. -/
def dispatch (frame cause value : UInt64) : Action :=
  if cause = 0x8000000000000009 then
    .bind (Access.read64 Process.control) fun s descriptor => if failed s = true then fatal else
    .bind (Task.capture descriptor frame) fun s context => if failed s = true then fatal else
    .bind (Access.read64 (context + 256)) fun s pc => if failed s = true then fatal else
    .bind Lemma.Drivers.PLIC.claim fun s source => if failed s = true then fatal else
    if (if source = 1 then true else if source = 12 then true else if source = 13 then true else false) = true then
      .bind (get 0) fun s flags => if failed s = true then fatal else
      .bind (put 0 (flags ||| ((1 : UInt64) <<< source))) fun s _ => if failed s = true then fatal else
      .bind (Lemma.Drivers.PLIC.complete source) fun s _ => if failed s = true then fatal else
      .bind (Lemma.Kernel.Console.record 0x406 source cause descriptor pc) fun s _ =>
      if failed s = true then fatal else
      .bind (Task.ready descriptor 1 pc) fun s _ => if failed s = true then fatal else
      Scheduler.returnKernel descriptor 1 pc
    else fatal
  else Scheduler.dispatch frame cause value

end Lemma.Platform.LemmaSim.Entry
