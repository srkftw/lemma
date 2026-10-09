import Lemma.Kernel.Memory.Frames
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Console
import Lemma.Kernel.MachineServices
import Lemma.Kernel.Operator

namespace Lemma.Kernel.Entry
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

/-- Maintained kernel root, initially exercised in the explicit bootstrap-M
build stage. Its owned storage implementation is shared by later S-mode policy. -/
def bootServices : Action :=
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
  else
    bootFailure s

/-- Until user loading is implemented, every supervisor trap is a distinct
kernel-fatal outcome; there is no permissive resume stub. -/
def boot : Action :=
  .bind bootServices fun s _ =>
  if s = 0 then
    .bind (Lemma.Kernel.Memory.Access.read64 0x80400010) fun s stage =>
    if s = 0 then
      if stage = 1 then
        .bind Lemma.Kernel.Process.init fun s _ =>
        if s = 0 then .loop Lemma.Kernel.Operator.step else .done s 0
      else .done 0 0
    else .done s 0
  else .done s 0

def dispatch (frame cause value : UInt64) : Action :=
  Lemma.Kernel.Process.dispatch frame cause value

end Lemma.Kernel.Entry
