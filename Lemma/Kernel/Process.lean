import Lemma.Kernel.Loader
import Lemma.Kernel.MachineServices
import Lemma.Kernel.Syscall
import Lemma.User.ABI

/-! The first process boundary: independently loaded U code, an owned trap
stack, and a suspended S caller. This is deliberately single-process until
the task/scheduler gates replace the current-process word. -/
namespace Lemma.Kernel.Process
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def control : UInt64 := 0x80400700
def resume : UInt64 := 0x80500000
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

def init : Action :=
  .bind (AddressSpace.noteActive 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.create 1) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.root descriptor) fun s root =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.satp descriptor) fun s translation =>
  if failed s = true then .done s 0 else
  .platform .installSatp translation 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.noteActive root) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 control 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (control + 8) root) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (control + 16) 2) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (control + 32) 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s remaining =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (control + 24) remaining) fun s _ =>
  if failed s = true then .done s 0 else
  Lemma.Kernel.Console.record 0xd3 root translation remaining 0

/-- Trusted construction identities never wrap or accept user-supplied owners.
The later task-table gate replaces this monotonic single-process allocator. -/
def reserveOwner : Action :=
  .bind (Access.read64 (control + 16)) fun s owner =>
  if failed s = true then .done s 0 else
  if 2 ≤ owner then
    if owner < 0xfffffffffffffffe then
      .bind (Access.write64 (control + 16) (owner + 1)) fun s _ => .done s owner
    else .done 37 0
  else .done 78 0

def run (argument : UInt64) : Action :=
  .bind (Access.read64 control) fun s current =>
  if failed s = true then .done s 0 else
  if current = 0 then
    .bind reserveOwner fun s owner =>
    if failed s = true then .done s 0 else
    .bind (Lemma.Kernel.Loader.load 0 owner argument) fun loaded descriptor =>
    if failed loaded = true then
      Lemma.Kernel.Console.record 0xde loaded.toUInt64 argument 0 0
    else
      .bind (AddressSpace.base descriptor) fun s base =>
      if failed s = true then .done s 0 else
      .bind (AddressSpace.root descriptor) fun s root =>
      if failed s = true then .done s 0 else
      .bind (Access.read64 (base + 2416)) fun s entry =>
      if failed s = true then .done s 0 else
      .bind (Access.read64 (base + 2424)) fun s textBytes =>
      if failed s = true then .done s 0 else
      .bind (Lemma.Kernel.Console.record 0xd0 descriptor root entry textBytes) fun s _ =>
      if failed s = true then .done s 0 else
      .bind (Access.write64 control descriptor) fun s _ =>
      if failed s = true then .done s 0 else
      .bind (AddressSpace.context descriptor) fun s context =>
      if failed s = true then .done s 0 else
      .bind (AddressSpace.noteActive root) fun s _ =>
      if failed s = true then .done s 0 else
      .platform .enterUser context 0 0 0 0 0 fun s code =>
      if failed s = true then .done s 0 else
      .bind (Access.read64 (base + 2432)) fun s recorded =>
      if failed s = true then .done s 0 else
      if code = recorded then
        .bind (AddressSpace.lookup descriptor 0x20000 1) fun s data =>
        if failed s = true then .done s 0 else
        .bind (Access.read64 data) fun s value =>
        if failed s = true then .done s 0 else
        .bind Frames.remaining fun s before =>
        if failed s = true then .done s 0 else
        .bind (Access.write64 control 0) fun s _ =>
        if failed s = true then .done s 0 else
        .bind (Lemma.Kernel.Loader.teardown descriptor) fun s _ =>
        if failed s = true then .done s 0 else
        .bind Frames.remaining fun s after =>
        if failed s = true then .done s 0 else
        .bind (Access.read64 (control + 24)) fun s baseline =>
        if failed s = true then .done s 0 else
        if after = baseline then Lemma.Kernel.Console.record 0xd2 code value before after
        else .done 78 0
      else .done 78 0
  else .done 78 0

/-- Select the exact trusted suspended S frame. It is restored before the
caller releases any active user resources. No mapping operation may occur
between this final bookkeeping update and the typed SATP/context restoration. -/
def finish (descriptor cause code pc status translation : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (Access.write64 (base + 2432) code) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (base + 2440) cause) fun s _ =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.Console.record (if cause = 8 then 0xd1 else 0xdc) cause pc status translation) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.read64 (control + 8)) fun s kernelRoot =>
  if failed s = true then fatal else
  .bind (Access.read64 (resume + 272)) fun s savedKernel =>
  if failed s = true then fatal else
  if savedKernel = AddressSpace.satpWord kernelRoot then
    .bind (Access.write64 (resume + 80) code) fun s _ =>
    if failed s = true then fatal else
    .bind (AddressSpace.noteActive kernelRoot) fun s _ =>
    if failed s = true then fatal else .done 0 resume
  else fatal

def syscallReply (frame pc : UInt64) (result : UInt8) (output : UInt64) : Action :=
  .bind (Access.write64 (frame + 80) result.toUInt64) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (frame + 88) output) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (frame + 256) (pc + 4)) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.write64 (frame + 264) 0x200000020) fun s _ =>
  if failed s = true then fatal else .done 0 frame

def userTrap (descriptor frame cause value pc status translation : UInt64) : Action :=
  if cause = 0x8000000000000001 then
    -- An interrupt may precede a precise fetch fault at a user-selected PC.
    -- Origin, stack ownership and SATP are already validated. Restoring that
    -- U context cannot confer S authority; let hardware report the fetch fault.
    .bind (Lemma.Kernel.MachineServices.rearm Lemma.Kernel.MachineServices.quantum) fun s _ =>
    if failed s = true then fatal else
    .bind (Lemma.Kernel.Console.record 0xdf cause pc status translation) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (frame + 264) 0x200000020) fun s _ =>
    if failed s = true then fatal else .done 0 frame
  else if cause = 8 then
    if pc % 4 = 0 then
      .bind (AddressSpace.lookup descriptor pc 4) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.read64 (frame + 136)) fun s number =>
      if failed s = true then fatal else
      .bind (Access.read64 (frame + 80)) fun s a =>
      if failed s = true then fatal else
      .bind (Access.read64 (frame + 88)) fun s b =>
      if failed s = true then fatal else
      .bind (Access.read64 (frame + 96)) fun s c =>
      if failed s = true then fatal else
      .bind (Access.read64 (frame + 104)) fun s d =>
      if failed s = true then fatal else
      .bind (Access.read64 (frame + 112)) fun s e =>
      if failed s = true then fatal else
      if number = Lemma.User.ABI.exit then
        if b ||| c ||| d ||| e = 0 then finish descriptor cause a pc status translation
        else syscallReply frame pc 16 0
      else
        .bind (Lemma.Kernel.Syscall.dispatch descriptor number a b c d e) fun result output =>
        if result = 255 then fatal else
        if result = IPC.blockedStatus then fatal else
        syscallReply frame pc result output
    -- The owned U origin is already established. A hardware ECALL at a
    -- halfword site is outside this generated ABI, but its user-selected PC
    -- cannot establish a kernel integrity failure. Terminate that instance.
    else finish descriptor cause 44 pc status translation
  else if (if cause ≤ 7 then true else if cause = 12 then true else
    if cause = 13 then true else if cause = 15 then true else false) = true then
    .bind (Lemma.Kernel.Console.record 0xd4 cause pc value status) fun s _ =>
    if failed s = true then fatal else finish descriptor cause 44 pc status translation
  else
    .bind (Lemma.Kernel.Console.record 0xdd cause value pc status) fun _ _ => fatal

/-- The owned stack pair is checked independently of any supplied frame. -/
def validateStack (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (AddressSpace.owner descriptor) fun s owner =>
  if failed s = true then fatal else
  .bind (Access.read64 (base + 2400)) fun s stackHandle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose owner stackHandle 1) fun s stackBase =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount owner stackHandle) fun s pins =>
  if failed s = true then fatal else
  .bind (Access.read64 (base + 2480)) fun s secondHandle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose owner secondHandle 1) fun s secondBase =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount owner secondHandle) fun s secondPins =>
  if failed s = true then fatal else
  .bind (Access.read64 (base + 2408)) fun s top =>
  if failed s = true then fatal else
  if (if pins ||| secondPins = 0 then if secondBase = stackBase + Frames.bytes then
    if top = stackBase + Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue then true
    else false else false else false) = true then .done 0 top else fatal

/-- Validate the owned frame address before its first dereference. Origin is
read from the hardware-saved SPP and SATP, not supplied by the UART client.
The scheduler uses this same boundary; legacy single-process policy is separate. -/
def validateFrame (frame : UInt64) : Action :=
  .bind (Access.read64 control) fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then fatal else
  .bind (validateStack descriptor) fun s top =>
  if failed s = true then fatal else
  if frame = top - 288 then
    .bind (Access.read64 (frame + 264)) fun s status =>
    if failed s = true then fatal else
    if status &&& 0xc6742 = 0 then
      if (status >>> 32) &&& 3 = 2 then
        .bind (Access.read64 (frame + 272)) fun s translation =>
        if failed s = true then fatal else
        .bind (AddressSpace.satp descriptor) fun s expected =>
        if failed s = true then fatal else
        if translation = expected then .done 0 descriptor
        else fatal
      else fatal
    else fatal
  else fatal

def dispatch (frame cause value : UInt64) : Action :=
  .bind (validateFrame frame) fun s descriptor =>
  if failed s = true then fatal else
  .bind (Access.read64 (frame + 264)) fun s status =>
  if failed s = true then fatal else
  .bind (Access.read64 (frame + 272)) fun s translation =>
  if failed s = true then fatal else
  .bind (Access.read64 (frame + 256)) fun s pc =>
  if failed s = true then fatal else
  userTrap descriptor frame cause value pc status translation

end Lemma.Kernel.Process
