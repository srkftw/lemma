import Lemma.Kernel.Loader
import Lemma.Kernel.MachineServices
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
  .bind Frames.remaining fun s remaining =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (control + 24) remaining) fun s _ =>
  if failed s = true then .done s 0 else
  Lemma.Kernel.Console.record 0xd3 root translation remaining 0

def run (argument : UInt64) : Action :=
  .bind (Access.read64 control) fun s current =>
  if failed s = true then .done s 0 else
  if current = 0 then
    .bind (Access.read64 (control + 16)) fun s owner =>
    if failed s = true then .done s 0 else
    if owner < 0xfffffffffffffffe then
      .bind (Access.write64 (control + 16) (owner + 1)) fun s _ =>
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
    else .done 37 0
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

def userTrap (descriptor frame cause value pc status translation : UInt64) : Action :=
  if cause = 0x8000000000000001 then
    .bind (AddressSpace.lookup descriptor pc 4) fun s _ =>
    if failed s = true then fatal else
    .bind (Lemma.Kernel.MachineServices.rearm Lemma.Kernel.MachineServices.quantum) fun s _ =>
    if failed s = true then fatal else
    .bind (Lemma.Kernel.Console.record 0xdf cause pc status translation) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.write64 (frame + 264) 0x200000020) fun s _ =>
    if failed s = true then fatal else .done 0 frame
  else if cause = 8 then
    .bind (AddressSpace.lookup descriptor pc 4) fun s _ =>
    if failed s = true then fatal else
    .bind (Access.read64 (frame + 136)) fun s number =>
    if failed s = true then fatal else
    if number = Lemma.User.ABI.exit then
      .bind (Access.read64 (frame + 80)) fun s code =>
      if failed s = true then fatal else finish descriptor cause code pc status translation
    else
      .bind (Access.write64 (frame + 80) 17) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (frame + 88) 0) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (frame + 256) (pc + 4)) fun s _ =>
      if failed s = true then fatal else
      .bind (Access.write64 (frame + 264) 0x200000020) fun s _ =>
      if failed s = true then fatal else .done 0 frame
  else if (if cause = 2 then true else if cause = 12 then true else
    if cause = 13 then true else if cause = 15 then true else false) = true then
    .bind (Lemma.Kernel.Console.record 0xd4 cause pc value status) fun s _ =>
    if failed s = true then fatal else finish descriptor cause 44 pc status translation
  else
    .bind (Lemma.Kernel.Console.record 0xdd cause value pc status) fun _ _ => fatal

/-- Validate the owned frame address before its first dereference. Origin is
read from the hardware-saved SPP and SATP, not supplied by the UART client. -/
def dispatch (frame cause value : UInt64) : Action :=
  .bind (Access.read64 control) fun s descriptor =>
  if failed s = true then fatal else
  if descriptor = 0 then fatal else
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (AddressSpace.owner descriptor) fun s owner =>
  if failed s = true then fatal else
  .bind (Access.read64 (base + 2400)) fun s stackHandle =>
  if failed s = true then fatal else
  .bind (Frames.resolvePurpose owner stackHandle 1) fun s stackBase =>
  if failed s = true then fatal else
  .bind (Access.read64 (base + 2408)) fun s top =>
  if failed s = true then fatal else
  if (if top = stackBase + 4096 then if frame = top - 288 then true else false else false) = true then
    .bind (Access.read64 (frame + 264)) fun s status =>
    if failed s = true then fatal else
    if status &&& 0xc6742 = 0 then
      if (status >>> 32) &&& 3 = 2 then
        .bind (Access.read64 (frame + 272)) fun s translation =>
        if failed s = true then fatal else
        .bind (AddressSpace.satp descriptor) fun s expected =>
        if failed s = true then fatal else
        if translation = expected then
          .bind (Access.read64 (frame + 256)) fun s pc =>
          if failed s = true then fatal else
          if AddressSpace.addressValid pc = true then
            if pc % 4 = 0 then userTrap descriptor frame cause value pc status translation
            else fatal
          else fatal
        else fatal
      else fatal
    else fatal
  else fatal

end Lemma.Kernel.Process
