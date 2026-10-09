import Lemma.Kernel.Memory.Frames
import Lemma.Kernel.BootInfo
import Lemma.Kernel.Console

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
def boot : Action :=
  .bind Lemma.Kernel.BootInfo.validate fun s dtb =>
  if s = 0 then
    .bind Lemma.Kernel.Memory.Frames.init fun s frames =>
    if s = 0 then
      .bind (Lemma.Kernel.Memory.Access.read64 0x80400010) fun s stage =>
      if s = 0 then Lemma.Kernel.Console.record 0x0a dtb stage frames 0x82000000
      else .done s 0
    else .done s 0
  else
    bootFailure s

/-- Until user loading is implemented, every supervisor trap is a distinct
kernel-fatal outcome; there is no permissive resume stub. -/
def dispatch (_frame _cause _value : UInt64) : Action := .done 50 0

end Lemma.Kernel.Entry
