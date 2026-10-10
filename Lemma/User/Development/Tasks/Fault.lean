import Lemma.User.Console

/-! Quarantined lifecycle precondition. It checks genuinely zeroed data/BSS and
user stack before writing fresh generation-specific secrets. A successful
return enters the separate typed supervisor-CSR probe in this image's startup;
ordinary status failure must never count as an architectural fault witness. -/
namespace Lemma.User.Development.Tasks.Fault
open Lemma.Core0.Memory

def canary : UInt64 := 0x3fffc020
def bssSecret (nonce : UInt64) : UInt64 := nonce ^^^ 0x61972a5fb3e804dc
def stackSecret (nonce : UInt64) : UInt64 := nonce ^^^ 0x89e4c13572ba06df
def failure : UInt8 := 95

def main (nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 0x20008) fun s version => if s = 0 then
  if version = Lemma.User.ABI.version then
  .bind (Lemma.User.Memory.read64 0x20000) fun s data => if s = 0 then
  .bind (Lemma.User.Memory.read64 0x20010) fun s bss => if s = 0 then
  .bind (Lemma.User.Memory.read64 canary) fun s stack => if s = 0 then
  if data ||| bss ||| stack = 0 then
  .bind Lemma.User.Syscall.identity fun s id => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20010 (bssSecret nonce)) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 canary (stackSecret nonce)) fun s _ => if s = 0 then
  .bind (Lemma.User.Console.record 0xe8 id nonce bss stack) fun s _ =>
  if s = 0 then .done 0 nonce else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done failure (data ||| bss ||| stack)
  else .done s 0 else .done s 0 else .done s 0
  else .done failure version else .done s 0

end Lemma.User.Development.Tasks.Fault
