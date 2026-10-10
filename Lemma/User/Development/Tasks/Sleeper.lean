import Lemma.User.Console

/-! Independently linked U sleeper with a private word/canary at the same VAs
as Compute. Deadline observations are real user time syscalls after wakeup.
-/
namespace Lemma.User.Development.Tasks.Sleeper
open Lemma.Core0.Memory

def canary : UInt64 := 0x3fffc020
def failure : UInt8 := 95
def guardValue (nonce : UInt64) : UInt64 := nonce ^^^ 0xe6b1c0387294a5df

private def wake (i _ : UInt32) (acc nonce id _ _ : UInt64) : Action :=
  .bind (Lemma.User.Syscall.sleep (2000000 + i.toUInt64 * 300000)) fun s deadline => if s = 0 then
  .bind Lemma.User.Syscall.time fun s now => if s = 0 then
  if deadline ≤ now then
  .bind (Lemma.User.Memory.read64 0x20000) fun s privateWord => if s = 0 then
  .bind (Lemma.User.Memory.read64 canary) fun s guard => if s = 0 then
  if privateWord = nonce then if guard = guardValue nonce then
  .bind (Lemma.User.Console.record 0xfb id deadline now nonce) fun s _ =>
  .done s ((acc * 5 + nonce) ^^^ (i.toUInt64 + 0xabcdef0123456789))
  else .done failure guard else .done failure privateWord
  else .done s 0 else .done s 0
  else .done failure now else .done s 0 else .done s 0

def main (nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 0x20008) fun s version => if s = 0 then
  if version = Lemma.User.ABI.version then
  .bind (Lemma.User.Memory.read64 0x20010) fun s bss => if s = 0 then
  if bss = 0 then
  .bind Lemma.User.Syscall.identity fun s id => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 canary (guardValue nonce)) fun s _ => if s = 0 then
  .bind (Lemma.User.Console.record 0xf8 id 2 nonce nonce) fun s _ => if s = 0 then
  .boundedFoldU64 4 wake 4 nonce nonce id 0 0 fun s result => if s = 0 then
  .bind (Lemma.User.Memory.read64 canary) fun s guard => if s = 0 then
  if guard = guardValue nonce then
  .bind (Lemma.User.Console.record 0xfa id result guard nonce) fun s _ =>
  if s = 0 then .done 0 result else .done s 0
  else .done failure guard
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0
  else .done failure bss else .done s 0
  else .done failure version else .done s 0

end Lemma.User.Development.Tasks.Sleeper
