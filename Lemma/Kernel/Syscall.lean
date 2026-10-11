import Lemma.Kernel.Memory.UserCopy
import Lemma.Kernel.MachineServices
import Lemma.User.ABI
import Lemma.Kernel.Capability
import Lemma.Kernel.IPC
import Lemma.Kernel.Directory
import Lemma.Kernel.KernelInput

/-! ABI v1 scalar dispatcher. Caller identity is the validated owned descriptor,
never a register supplied by U. Every operation is bounded; this gate's sleep
waits on hardware in nonpreemptible S, before the task scheduler supplies blocked
task transitions. Status255 is internal fatal and must never be returned to U. -/
namespace Lemma.Kernel.Syscall
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 255 0
def arenaAddress (va : UInt64) : Bool :=
  if 0x40000 ≤ va then if va < 0x100000 then
    if va % 4096 = 0 then true else false
  else false else false
/-- Discovery selects the expanded arena; historical callers retain the exact
old limit. The machine finisher page remains excluded by AddressSpace. -/
def ownedArenaAddress (va : UInt64) : Action :=
  if 0x40000 ≤ va then
    if va % 4096 = 0 then
      if va = 0x100000 then .done 71 0 else
      .bind Frames.runtimeCount fun s amount =>
      if failed s = true then .done 255 0 else
      let limit := if amount = 8192 then 0x800000 else 0x100000
      if va < limit then .done 0 va else .done 71 0
    else .done 71 0
  else .done 71 0
def memoryStatus (s : UInt8) : UInt8 :=
  if s = 0 then 0 else if s = 33 then 33 else if s = 38 then 38 else
  if s = 71 then 71 else if s = 72 then 72 else if s = 73 then 73 else
  if s = 74 then 74 else if s = 37 then 33 else if s = 76 then 33 else 255

private def releaseProvisional (owner handle : UInt64) (status : UInt8) : Action :=
  .bind (Frames.release owner handle) fun s _ =>
  if failed s = true then fatal else .done (memoryStatus status) 0

def allocate (descriptor va count : UInt64) : Action :=
  if count = 1 then
    .bind (ownedArenaAddress va) fun s _ =>
    if s = 0 then
      .bind (AddressSpace.owner descriptor) fun s owner =>
      if failed s = true then fatal else
      .bind (Frames.allocate owner 4) fun s handle =>
      if failed s = true then .done (memoryStatus s) 0 else
      .bind (AddressSpace.mapUser descriptor va handle 3) fun s _ =>
      if failed s = true then releaseProvisional owner handle s else .done 0 va
    else .done s 0
  else .done 16 0

def release (descriptor va count : UInt64) : Action :=
  if count = 1 then
    .bind (ownedArenaAddress va) fun s _ =>
    if s = 0 then
      .bind (AddressSpace.owner descriptor) fun s owner =>
      if failed s = true then fatal else
      .bind (AddressSpace.unmap descriptor va) fun s handle =>
      if failed s = true then .done (memoryStatus s) 0 else
      .bind (Frames.resolvePurpose owner handle 4) fun s _ =>
      if failed s = true then fatal else
      .bind (Frames.release owner handle) fun s _ =>
      if failed s = true then fatal else .done 0 va
    else .done s 0
  else .done 16 0

private def freeScratch (handle : UInt64) (status : UInt8) (count : UInt64) : Action :=
  .bind (Frames.release 1 handle) fun s _ =>
  if failed s = true then fatal else .done status count

private def writeStep (i _ : UInt32) (acc physical _ _ _ : UInt64) : Action :=
  .bind (Access.read8 (physical + i.toUInt64)) fun s byte =>
  if failed s = true then fatal else
  .bind (Lemma.Platform.LemmaVM.ConsoleDevice.sendByte byte.toUInt8) fun s _ =>
  if failed s = true then .done s acc else .done 0 (acc + 1)

/-- Range rejection has no device effects. A device error after transmission
returns its status and the actual prefix count; UART output is irreversible. -/
def consoleWrite (descriptor pointer length : UInt64) : Action :=
  if 256 < length then .done 16 0 else
  .bind (UserCopy.validateRead descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  if length = 0 then .done 0 0 else
  .bind (Frames.allocate 1 1) fun s handle =>
  if failed s = true then .done (memoryStatus s) 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s physical =>
  if failed s = true then freeScratch handle 255 0 else
  .bind (UserCopy.copyFromUser descriptor pointer handle 0 length) fun s _ =>
  if failed s = true then freeScratch handle s 0 else
  .boundedFoldU64 256 writeStep length.toUInt32 0 physical 0 0 0 fun s sent =>
  freeScratch handle s sent

private def readStep (i _ : UInt32) (acc physical _ _ _ : UInt64) : Action :=
  .bind (Lemma.Platform.LemmaVM.ConsoleDevice.receivePollStep 0 0 0 0 0 0 0) fun s byte =>
  if s = Status.iterationStop then
    .bind (Access.write8 (physical + i.toUInt64) byte) fun s _ =>
    if failed s = true then fatal else .done 0 (acc + 1)
  else if s = 0 then .done Status.iterationStop acc else .done s acc

/-- Preflight the complete destination before consuming a single UART byte.
Read is nonblocking: no available byte returns12/0, otherwise a short count.
No borrowed user pointer persists after this bounded critical section. -/
def consoleRead (descriptor pointer length : UInt64) : Action :=
  if 256 < length then .done 16 0 else
  .bind (UserCopy.validateWrite descriptor pointer length) fun s _ =>
  if failed s = true then .done s 0 else
  if length = 0 then .done 0 0 else
  .bind (Frames.allocate 1 1) fun s handle =>
  if failed s = true then .done (memoryStatus s) 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s physical =>
  if failed s = true then freeScratch handle 255 0 else
  .boundedFoldU64 256 readStep length.toUInt32 0 physical 0 0 0 fun s count =>
  if (if s = 0 then true else if s = Status.iterationStop then true else false) = true then
    if count = 0 then freeScratch handle 12 0 else
    .bind (UserCopy.copyToUser descriptor pointer handle 0 count) fun s copied =>
    freeScratch handle s copied
  else if count = 0 then freeScratch handle s 0 else
    .bind (UserCopy.copyToUser descriptor pointer handle 0 count) fun copiedStatus copied =>
    if failed copiedStatus = true then freeScratch handle copiedStatus 0
    else freeScratch handle s copied

/-- The boot-cleared zero control retains every earlier raw-UART profile.
A service frame selects copied buffered input without any raw fallback. -/
def selectedConsoleRead (descriptor pointer length : UInt64) : Action :=
  .bind KernelInput.mode fun s selectedMode =>
  if failed s = true then fatal else
  if selectedMode = 0 then consoleRead descriptor pointer length else
  if (if selectedMode = 1 then true else if selectedMode = 2 then true else false) = true then
    KernelInput.read descriptor pointer length
  else fatal

def sleep (ticks : UInt64) : Action :=
  .bind (Lemma.Kernel.MachineServices.rearmRelative ticks) fun s deadline =>
  if failed s = true then .done s 0 else
  .bind Lemma.Kernel.MachineServices.awaitNotification fun s _ =>
  if failed s = true then fatal else
  .bind (Lemma.Kernel.MachineServices.rearmRelative Lemma.Kernel.MachineServices.quantum) fun s _ =>
  if failed s = true then fatal else .done 0 deadline

/-- Exit is selected by trap policy; all other unknown numbers return17.
Unused argument registers do not convey additional authority. -/
def dispatchLegacy (descriptor number a b c d e : UInt64) : Action :=
  if d ||| e = 0 then
  if number = Lemma.User.ABI.identity then
    if a ||| b ||| c = 0 then
    .bind (AddressSpace.base descriptor) fun s _ =>
    if failed s = true then fatal else .done 0 descriptor
    else .done 16 0
  else if number = Lemma.User.ABI.console then
    if a = 0 then consoleWrite descriptor b c
    else if a = 1 then consoleRead descriptor b c else .done 17 0
  else if number = Lemma.User.ABI.yield then
    if a ||| b ||| c = 0 then .done 0 0 else .done 16 0
  else if number = Lemma.User.ABI.sleep then
    if b ||| c = 0 then sleep a else .done 16 0
  else if number = Lemma.User.ABI.time then
    if a ||| b ||| c = 0 then Lemma.Kernel.MachineServices.time else .done 16 0
  else if number = Lemma.User.ABI.allocatePages then
    if c = 0 then allocate descriptor a b else .done 16 0
  else if number = Lemma.User.ABI.releasePages then
    if c = 0 then release descriptor a b else .done 16 0
  else .done 17 0
  else .done 16 0

/-- A managed task cannot reach the permission-free legacy UART path. The
caller-local Console capability is checked before either range copy or MMIO. -/
def capConsole (descriptor handle operation pointer length : UInt64) : Action :=
  if operation = 0 then
    .bind (Capability.lookup descriptor handle Lemma.User.CapabilityABI.consoleType
      Lemma.User.CapabilityABI.consoleWrite) fun s _ =>
    if s = 0 then consoleWrite descriptor pointer length else .done s 0
  else if operation = 1 then
    .bind (Capability.lookup descriptor handle Lemma.User.CapabilityABI.consoleType
      Lemma.User.CapabilityABI.consoleRead) fun s _ =>
    if s = 0 then selectedConsoleRead descriptor pointer length else .done s 0
  else .done 17 0

/-- The deadline ceiling is deployment policy, never a User argument. The
historical dispatcher below retains the original one-second ceiling. -/
def dispatchManagedWithIPCLimit (maximum descriptor number a b c d e : UInt64) : Action :=
  if number = 26 then
    if d ||| e = 0 then Directory.discover descriptor a b c else .done 16 0
  else
  if (if Lemma.User.IPCABI.send ≤ number then if number ≤ Lemma.User.IPCABI.cancel then true else false else false) = true then
    IPC.dispatchWithLimit maximum descriptor number a b c d e
  else if number = Lemma.User.ABI.console then .done 72 0 else
  if number = Lemma.User.CapabilityABI.bootGrant then
    if b ||| c ||| d ||| e = 0 then Capability.bootGrant descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.info then
    if b ||| c ||| d ||| e = 0 then Capability.info descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.check then
    if d ||| e = 0 then Capability.check descriptor a b c else .done 16 0
  else if number = Lemma.User.CapabilityABI.duplicate then
    if c ||| d ||| e = 0 then Capability.duplicate descriptor a b else .done 16 0
  else if number = Lemma.User.CapabilityABI.close then
    if b ||| c ||| d ||| e = 0 then Capability.close descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.revoke then
    if b ||| c ||| d ||| e = 0 then Capability.revoke descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.console then
    if e = 0 then capConsole descriptor a b c d else .done 16 0
  else if number = Lemma.User.CapabilityABI.createEndpoint then
    if b ||| c ||| d ||| e = 0 then Capability.createEndpoint descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.transfer then
    if e = 0 then Capability.transfer descriptor a b c d else .done 16 0
  else if number = Lemma.User.CapabilityABI.scopedTarget then
    if c ||| d ||| e = 0 then Capability.scopedTarget descriptor a b else .done 16 0
  else if number = Lemma.User.CapabilityABI.inspect then
    if d ||| e = 0 then Capability.inspect descriptor a b c else .done 16 0
  else dispatchLegacy descriptor number a b c d e

def dispatchManaged (descriptor number a b c d e : UInt64) : Action :=
  if number = 26 then
    if d ||| e = 0 then Directory.discover descriptor a b c else .done 16 0
  else
  if (if Lemma.User.IPCABI.send ≤ number then if number ≤ Lemma.User.IPCABI.cancel then true else false else false) = true then
    IPC.dispatch descriptor number a b c d e
  else if number = Lemma.User.ABI.console then .done 72 0 else
  if number = Lemma.User.CapabilityABI.bootGrant then
    if b ||| c ||| d ||| e = 0 then Capability.bootGrant descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.info then
    if b ||| c ||| d ||| e = 0 then Capability.info descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.check then
    if d ||| e = 0 then Capability.check descriptor a b c else .done 16 0
  else if number = Lemma.User.CapabilityABI.duplicate then
    if c ||| d ||| e = 0 then Capability.duplicate descriptor a b else .done 16 0
  else if number = Lemma.User.CapabilityABI.close then
    if b ||| c ||| d ||| e = 0 then Capability.close descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.revoke then
    if b ||| c ||| d ||| e = 0 then Capability.revoke descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.console then
    if e = 0 then capConsole descriptor a b c d else .done 16 0
  else if number = Lemma.User.CapabilityABI.createEndpoint then
    if b ||| c ||| d ||| e = 0 then Capability.createEndpoint descriptor a else .done 16 0
  else if number = Lemma.User.CapabilityABI.transfer then
    if e = 0 then Capability.transfer descriptor a b c d else .done 16 0
  else if number = Lemma.User.CapabilityABI.scopedTarget then
    if c ||| d ||| e = 0 then Capability.scopedTarget descriptor a b else .done 16 0
  else if number = Lemma.User.CapabilityABI.inspect then
    if d ||| e = 0 then Capability.inspect descriptor a b c else .done 16 0
  else dispatchLegacy descriptor number a b c d e

def dispatchWithIPCLimit (maximum descriptor number a b c d e : UInt64) : Action :=
  .bind (Capability.managed descriptor) fun s managed =>
  if s = 0 then
    if managed = 1 then dispatchManagedWithIPCLimit maximum descriptor number a b c d e
    else if managed = 0 then dispatchLegacy descriptor number a b c d e else fatal
  else fatal

def dispatch (descriptor number a b c d e : UInt64) : Action :=
  .bind (Capability.managed descriptor) fun s managed =>
  if s = 0 then
    if managed = 1 then dispatchManaged descriptor number a b c d e
    else if managed = 0 then dispatchLegacy descriptor number a b c d e else fatal
  else fatal

end Lemma.Kernel.Syscall
