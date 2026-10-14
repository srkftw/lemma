import Lemma.Kernel.BootServices
import Lemma.Kernel.Process

/-! Isolated closure qualification. The existing checked loader and single
U-process supervisor own every page, trap and teardown. The kernel observes
exit/data results without implementing or interpreting closure semantics. -/
namespace Lemma.Kernel.Development.ClosureKernel
open Lemma.Core0.Memory
private def step (i _ : UInt32) (count _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.Kernel.Process.run i.toUInt64) fun s _ => .done s (count+1)
def boot : Action :=
  .bind Lemma.Kernel.BootServices.bootServices fun s _ => if s = 0 then
  .bind (Lemma.Kernel.Memory.Frames.configure 1024 128 4) fun s _ => if s = 0 then
  .bind Lemma.Kernel.Memory.Frames.init fun s _ => if s = 0 then
  .bind Lemma.Kernel.Process.init fun s _ => if s = 0 then
  .boundedFoldU64 10 step 10 0 0 0 0 0 fun s count => if s = 0 then
  Lemma.Kernel.Console.record 0xc7 count 0 0 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
def dispatch (frame cause value : UInt64) : Action :=
  Lemma.Kernel.Process.dispatch frame cause value
end Lemma.Kernel.Development.ClosureKernel
