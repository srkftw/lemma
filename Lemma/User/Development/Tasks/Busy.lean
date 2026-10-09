import Lemma.User.Memory
import Lemma.User.ABI

/-! Quarantined noncooperative U workload: no syscall or yield in its genuine
reachable source closure. Timer interrupts must permit its peers to execute.
-/
namespace Lemma.User.Development.Tasks.Busy
open Lemma.Core0.Memory

def tick : Action :=
  .bind (Lemma.User.Memory.read64 0x20000) fun s nonce => if s = 0 then
  .bind (Lemma.User.Memory.read64 0x20018) fun s counter => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20018 (counter + 1)) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20020 ((counter * 7 + nonce) ^^^ 0xace13579bdf02468)) fun s _ =>
  .done s counter
  else .done s 0 else .done s 0 else .done s 0

def main (nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 0x20008) fun s version => if s = 0 then
  if version = Lemma.User.ABI.version then
  .bind (Lemma.User.Memory.read64 0x20010) fun s bss => if s = 0 then
  if bss = 0 then
  .bind (Lemma.User.Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20018 0) fun s _ =>
  if s = 0 then .loop tick else .done s 0
  else .done s 0 else .done 95 bss else .done s 0
  else .done 95 version else .done s 0

end Lemma.User.Development.Tasks.Busy
