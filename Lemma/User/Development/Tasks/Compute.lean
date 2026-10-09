import Lemma.User.Console

/-! Independent U computation. Several nonce-derived values and an accumulator
remain live across ordinary yield calls and timer preemption. The second task
uses the same virtual data and canary addresses with a different address space.
-/
namespace Lemma.User.Development.Tasks.Compute
open Lemma.Core0.Memory

def canary : UInt64 := 0x3fffc020
def failure : UInt8 := 95
def left (nonce : UInt64) : UInt64 := nonce ^^^ 0x1375a94f2468bace
def right (nonce : UInt64) : UInt64 := nonce + 0x8420feca97531bdf
def third (nonce : UInt64) : UInt64 := (nonce * (17 : UInt64)) ^^^ (nonce >>> 13)

private def churn (i _ : UInt32) (acc nonce a b c : UInt64) : Action :=
  .done 0 (((acc + a + i.toUInt64) ^^^ b) * 3 + (c ^^^ nonce))

private def chunk (_i _ : UInt32) (acc nonce a b c : UInt64) : Action :=
  .boundedFoldU64 4096 churn 4096 acc nonce a b c fun s result => .done s result

private def round (i _ : UInt32) (acc nonce id a b : UInt64) : Action :=
  let c := third nonce
  .bind Lemma.User.Syscall.yield fun s _ => if s = 0 then
  .boundedFoldU64 32 chunk 32 acc nonce a b c fun s result => if s = 0 then
  .bind (Lemma.User.Memory.read64 0x20000) fun s privateWord => if s = 0 then
  .bind (Lemma.User.Memory.read64 canary) fun s guard => if s = 0 then
  if privateWord = nonce then if guard = a then
  .bind (Lemma.User.Console.record 0xf9 id i.toUInt64 result nonce) fun s _ =>
  .done s result
  else .done failure guard else .done failure privateWord
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

def main (nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 0x20008) fun s version => if s = 0 then
  if version = Lemma.User.ABI.version then
  .bind (Lemma.User.Memory.read64 0x20010) fun s bss => if s = 0 then
  if bss = 0 then
  .bind Lemma.User.Syscall.identity fun s id => if s = 0 then
  .bind (Lemma.User.Memory.write64 0x20000 nonce) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 canary (left nonce)) fun s _ => if s = 0 then
  .bind (Lemma.User.Console.record 0xf8 id 1 nonce nonce) fun s _ => if s = 0 then
  .boundedFoldU64 8 round 8 nonce nonce id (left nonce) (right nonce) fun s result => if s = 0 then
  .bind (Lemma.User.Memory.read64 canary) fun s guard => if s = 0 then
  if guard = left nonce then
  .bind (Lemma.User.Console.record 0xfa id result guard nonce) fun s _ =>
  if s = 0 then .done 0 result else .done s 0
  else .done failure guard
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0
  else .done failure bss else .done s 0
  else .done failure version else .done s 0

end Lemma.User.Development.Tasks.Compute
