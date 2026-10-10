import Lemma.Kernel.Memory.Frames
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Console
import Lemma.Kernel.MachineServices
import Lemma.Platform.LemmaVM.Layout

/-! Shared boot-only initialization. It carries no task selector or development
command policy. Historical entries use mode zero for the later console input
boundary because this cell is initialized explicitly, rather than assuming RAM
outside the linked BSS was cleared. -/
namespace Lemma.Kernel.BootServices
open Lemma.Core0.Memory

def bootFailure (status : UInt8) : Action :=
  .bind (Lemma.Kernel.Memory.Access.read64 0x80400820) fun s cursor =>
  if s = 0 then
    .bind (Lemma.Kernel.Memory.Access.read64 0x80400828) fun s depth =>
    if s = 0 then
      .bind (Lemma.Kernel.Memory.Access.read64 0x80400870) fun s memoryComplete =>
      if s = 0 then
        .bind (Lemma.Kernel.Console.record 0xe0 status.toUInt64 cursor depth memoryComplete)
          fun _ _ => .done status 0
      else .done s 0
    else .done s 0
  else .done s 0

def bootServices : Action :=
  .bind (Lemma.Kernel.Memory.Frames.configure 512 32 2) fun s _ =>
  if s = 0 then
  .bind (Lemma.Kernel.Memory.Access.write64 Lemma.Platform.LemmaVM.Layout.inputControlValue 0)
    fun s _ =>
  if s = 0 then
  .bind Lemma.Platform.LemmaVM.ConsoleDevice.initialize14 fun s _ =>
  if s = 0 then
    .bind Lemma.Kernel.BootInfo.validate fun s dtb =>
    if s = 0 then
      .bind Lemma.Kernel.Memory.Frames.init fun s frames =>
      if s = 0 then
        .bind (Lemma.Kernel.Memory.Access.read64 0x80400010) fun s stage =>
        if s = 0 then
          .bind (Lemma.Kernel.Console.record 0x0a dtb stage frames 0x82000000) fun s _ =>
          if s = 0 then
            if stage = 1 then Lemma.Kernel.MachineServices.init
            else if stage = 0 then .done 0 0 else .done 51 0
          else .done s 0
        else .done s 0
      else .done s 0
    else bootFailure s
  else .done s 0
  else .done s 0

  else .done s 0

end Lemma.Kernel.BootServices
