import Lemma.Kernel.Task

/-! Single-hart equal-priority scheduling. Supervisor policy remains
nonpreemptible; actual M timer delivery latches SSIP, which preempts U.
Every scheduling transition returns to the fixed S continuation before
reaping or entering another task. The perpetual loop is an Action.loop in
its caller; every individual table scan and critical section is bounded. -/
namespace Lemma.Kernel.Scheduler
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0
def quantum : UInt64 := 10000 -- 1ms on the pinned 10MHz machine timer

/-- No mapping mutation may follow the final active-root update before typed
restoration. This does not reclaim anything on the outgoing owned task stack. -/
def returnKernel (descriptor reason pc : UInt64) : Action :=
  .bind MachineServices.interruptCount fun s interrupts =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xf2 descriptor reason interrupts pc) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.read64 (Process.control + 8)) fun s root =>
  if failed s = true then fatal else
  .bind (Access.read64 (Process.resume + 272)) fun s saved =>
  if failed s = true then fatal else
  if saved = AddressSpace.satpWord root then
    .bind (Access.write64 (Process.resume + 80) reason) fun s _ =>
    if failed s = true then fatal else
    .bind (AddressSpace.noteActive root) fun s _ =>
    if failed s = true then fatal else .done 0 Process.resume
  else fatal

def finish (descriptor cause code pc value : UInt64) : Action :=
  .bind (Task.terminate descriptor cause code pc value) fun s _ =>
  if failed s = true then fatal else
  returnKernel descriptor (if cause = 8 then 4 else 5) pc

def yieldTask (descriptor context pc : UInt64) : Action :=
  .bind (Process.syscallReply context pc 0 0) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.ready descriptor 2 pc) fun s _ =>
  if failed s = true then fatal else returnKernel descriptor 2 pc

def sleepTask (descriptor context pc ticks : UInt64) : Action :=
  if ticks < 1000 then Process.syscallReply context pc 22 0 else
  if 10000000 < ticks then Process.syscallReply context pc 22 0 else
  .bind MachineServices.time fun s now =>
  if failed s = true then fatal else
  if 0xffffffffffffffff - ticks < now then Process.syscallReply context pc 22 0 else
  let deadline := now + ticks
  .bind (Process.syscallReply context pc 0 deadline) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.sleep descriptor deadline pc) fun s _ =>
  if failed s = true then fatal else returnKernel descriptor 3 pc

def call (descriptor context pc : UInt64) : Action :=
  .bind (Access.read64 (context + 136)) fun s number =>
  if failed s = true then fatal else
  .bind (Access.read64 (context + 80)) fun s a =>
  if failed s = true then fatal else
  .bind (Access.read64 (context + 88)) fun s b =>
  if failed s = true then fatal else
  .bind (Access.read64 (context + 96)) fun s c =>
  if failed s = true then fatal else
  .bind (Access.read64 (context + 104)) fun s d =>
  if failed s = true then fatal else
  .bind (Access.read64 (context + 112)) fun s e =>
  if failed s = true then fatal else
  if number = Lemma.User.ABI.exit then
    if b ||| c ||| d ||| e = 0 then finish descriptor 8 a pc 0
    else Process.syscallReply context pc 16 0
  else if number = Lemma.User.ABI.yield then
    if a ||| b ||| c ||| d ||| e = 0 then yieldTask descriptor context pc
    else Process.syscallReply context pc 16 0
  else if number = Lemma.User.ABI.sleep then
    if b ||| c ||| d ||| e = 0 then sleepTask descriptor context pc a
    else Process.syscallReply context pc 16 0
  else
    .bind (Lemma.Kernel.Syscall.dispatch descriptor number a b c d e) fun status value =>
    if status = 255 then fatal else
    if status = IPC.blockedStatus then
      .bind (IPC.waitInfo descriptor value) fun s metadata =>
      if failed s = true then fatal else
      .bind (Access.read64 (metadata + IPCStorage.operationOffset)) fun s kind =>
      if failed s = true then fatal else
      .bind (Access.read64 (metadata + IPCStorage.deadlineOffset)) fun s expires =>
      if failed s = true then fatal else
      .bind (Process.syscallReply context pc 0 0) fun s _ =>
      if failed s = true then fatal else
      .bind (Task.block descriptor value kind expires pc) fun s _ =>
      if failed s = true then fatal else returnKernel descriptor 6 pc
    else Process.syscallReply context pc status value

/-- Called only after capture has validated the original owned hardware frame.
Task.context sanitizes the separate saved context; that word cannot describe
the actual trap. Read the original frame on the fault path before termination. -/
private def reportFault (descriptor frame cause value pc : UInt64) : Action :=
  .bind (Access.read64 (frame + 264)) fun s status =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xd4 cause pc value status) fun s _ =>
  if failed s = true then fatal else finish descriptor cause 44 pc value

def dispatch (frame cause value : UInt64) : Action :=
  .bind (Access.read64 Process.control) fun s descriptor =>
  if failed s = true then fatal else
  .bind (Task.capture descriptor frame) fun s context =>
  if failed s = true then fatal else
  .bind (Access.read64 (context + 256)) fun s pc =>
  if failed s = true then fatal else
  if cause = 0x8000000000000001 then
    .bind (Task.ready descriptor 1 pc) fun s _ =>
    if failed s = true then fatal else returnKernel descriptor 1 pc
  else if cause = 8 then
    if pc % 4 = 0 then
      .bind (AddressSpace.lookup descriptor pc 4) fun s _ =>
      if failed s = true then fatal else call descriptor context pc
    else reportFault descriptor frame cause value pc
  else if (if cause ≤ 7 then true else if cause = 12 then true else
      if cause = 13 then true else if cause = 15 then true else false) = true then
    reportFault descriptor frame cause value pc
  else fatal

/-- Relative arming avoids a stale absolute minimum deadline. The earliest
sleep deadline can shorten either the runnable quantum or the idle maximum;
a subminimum interval is rounded up, so wakeup is never early. M IRQ counts
are read, never synthesized here. -/
private def armInterval (now maxTicks : UInt64) : Action :=
  .bind (Task.interval now maxTicks) fun s ticks =>
  if failed s = true then fatal else
  .bind (MachineServices.rearmRelative ticks) fun s deadline =>
  if failed s = true then fatal else .done 0 deadline

def arm (now : UInt64) : Action := armInterval now quantum

private def idle (now : UInt64) : Action :=
  .bind (armInterval now MachineServices.quantum) fun s deadline =>
  if failed s = true then fatal else
  .bind MachineServices.pending fun s pending =>
  if failed s = true then fatal else
  if pending = 0 then
    .bind MachineServices.wait fun s _ =>
    if failed s = true then fatal else
    .bind MachineServices.pending fun s observed =>
    if failed s = true then fatal else
    .bind MachineServices.interruptCount fun s count =>
    if failed s = true then fatal else
    .bind (Lemma.Kernel.Console.record 0xfd now count observed deadline) fun s _ =>
    if failed s = true then fatal else .done 0 0
  else if pending = 1 then .done 0 0 else fatal

private def enter (descriptor now : UInt64) : Action :=
  .bind (Task.context descriptor) fun s context =>
  if failed s = true then fatal else
  .bind (AddressSpace.root descriptor) fun s root =>
  if failed s = true then fatal else
  .bind (Task.lookup descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + Task.dispatchOffset)) fun s dispatches =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record 0xf3 descriptor root dispatches now) fun s _ =>
  if failed s = true then fatal else
  .bind (arm now) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 Process.control descriptor) fun s _ =>
  if failed s = true then fatal else
  .bind (AddressSpace.noteActive root) fun s _ =>
  if failed s = true then fatal else
  .platform .enterUser context 0 0 0 0 0 fun s reason =>
  if failed s = true then fatal else
  if (if 1 ≤ reason then if reason ≤ 6 then true else false else false) = true then
    .bind (Access.read64 Process.control) fun s current =>
    if failed s = true then fatal else
    if current = descriptor then
      .bind (Access.read64 (Process.control + 8)) fun s kernelRoot =>
      if failed s = true then fatal else
      .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
      if failed s = true then fatal else
      if active = kernelRoot then
        .bind (Access.write64 Process.control 0) fun s _ =>
        if failed s = true then fatal else
        .bind Task.reap fun s _ =>
        if failed s = true then fatal else .done 0 reason
      else fatal
    else fatal
  else fatal

/-- Run on the stable supervisor boot/reaper stack. A missing runnable task is
an idle state, not termination. Spurious WFI returns simply repeat the caller's
nonrecursive Action.loop; no fixed lifetime or simulated tick budget is used. -/
def step : Action :=
  .bind Task.reap fun s _ =>
  if failed s = true then fatal else
  .bind MachineServices.time fun s now =>
  if failed s = true then fatal else
  .bind (Task.wakeDue now) fun s _ =>
  if failed s = true then fatal else
  .bind (Task.pollIPC now) fun s _ =>
  if failed s = true then fatal else
  .bind Task.select fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then idle now else enter descriptor now

end Lemma.Kernel.Scheduler
