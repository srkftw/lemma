import Lemma.Kernel.Entry

/-! Explicit hardware-isolation development configuration. A real separately
loaded peer remains paused and owns a private mapped data frame. The ordinary
operator runs fresh attacker instances; each complete request is followed by
an observation of the paused peer's actual memory and allocator state. There
is no claim that the peer has executed user instructions. -/
namespace Lemma.Kernel.Development.IsolationEntry
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Platform.LemmaVM.ConsoleDevice

def failed (s : UInt8) : Bool := if s = 0 then false else true
def sentinel : UInt64 := 0x0123456789abcdef

def postPeerObservation : Action :=
  .bind (Access.read64 (Lemma.Kernel.Process.control + 32)) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.lookup descriptor 0x40000 1) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 physical) fun s value =>
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s remaining =>
  if failed s = true then .done s 0 else
  Lemma.Kernel.Console.record 0xd7 descriptor value remaining 0

def step : Action :=
  .bind receiveByte fun s command =>
  if s = 0 then
    .bind (Lemma.Kernel.Operator.fields command) fun s _ =>
    if s = 0 then postPeerObservation else .done s 0
  else if s = 12 then .done 0 0 else .done s 0

def boot : Action :=
  .bind Lemma.Kernel.Entry.bootServices fun s _ =>
  if failed s = true then .done s 0 else
  .bind Lemma.Kernel.Process.init fun s _ =>
  if failed s = true then .done s 0 else
  .bind Lemma.Kernel.Process.reserveOwner fun s owner =>
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Loader.load 0 owner 0) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (Frames.allocate owner 4) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose owner handle 4) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 physical sentinel) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.mapUser descriptor 0x40000 handle 3) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (AddressSpace.root descriptor) fun s root =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (Lemma.Kernel.Process.control + 32) descriptor) fun s _ =>
  if failed s = true then .done s 0 else
  .bind Frames.remaining fun s remaining =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (Lemma.Kernel.Process.control + 24) remaining) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0xd5 descriptor root 0x40000 physical) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.Kernel.Console.record 0xd6 owner sentinel remaining 0) fun s _ =>
  if failed s = true then .done s 0 else .loop step

def dispatch (frame cause value : UInt64) : Action :=
  Lemma.Kernel.Entry.dispatch frame cause value

end Lemma.Kernel.Development.IsolationEntry
