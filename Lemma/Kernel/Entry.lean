import Lemma.Kernel.BootServices
import Lemma.Kernel.Operator

namespace Lemma.Kernel.Entry
open Lemma.Core0.Memory

def bootFailure (status : UInt8) : Action :=
  Lemma.Kernel.BootServices.bootFailure status

/-- Maintained kernel root, initially exercised in the explicit bootstrap-M
build stage. Its owned storage implementation is shared by later S-mode policy. -/
def bootServices : Action :=
  Lemma.Kernel.BootServices.bootServices

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
