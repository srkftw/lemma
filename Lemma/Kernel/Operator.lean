import Lemma.Kernel.Process

/-! Continuous bounded serial command transport. Each request is a command
byte, seven reserved zero bytes, and four little-endian u64 words. Run command
1 forwards its scalar argument to a fresh independently loaded user process.
It does not contain page allocation, user code, or execution answers. -/
namespace Lemma.Kernel.Operator
open Lemma.Core0.Memory
open Lemma.Platform.LemmaVM.ConsoleDevice

def failed (s : UInt8) : Bool := if s = 0 then false else true
private def headerStep (i _count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind receiveByte fun s byte =>
  .done s (acc ||| (byte <<< (i.toUInt64 * 8)))
def fields (command : UInt64) : Action :=
  .boundedFoldU64 7 headerStep 7 0 0 0 0 0 fun s reserved =>
  if failed s = true then .done 15 0 else
  if reserved = 0 then
    .bind Lemma.Kernel.Console.readWord fun s a =>
    if failed s = true then .done 15 0 else
    .bind Lemma.Kernel.Console.readWord fun s b =>
    if failed s = true then .done 15 0 else
    .bind Lemma.Kernel.Console.readWord fun s c =>
    if failed s = true then .done 15 0 else
    .bind Lemma.Kernel.Console.readWord fun s d =>
    if failed s = true then .done 15 0 else
    if command = 1 then
      if b = 0 then if c = 0 then if d = 0 then Lemma.Kernel.Process.run a
      else Lemma.Kernel.Console.record 0xde 14 command a d
      else Lemma.Kernel.Console.record 0xde 14 command a c
      else Lemma.Kernel.Console.record 0xde 14 command a b
    else Lemma.Kernel.Console.record 0xde 17 command 0 0
  else Lemma.Kernel.Console.record 0xde 14 command reserved 0
def step : Action :=
  .bind receiveByte fun s command =>
  if s = 0 then fields command
  else if s = 12 then .done 0 0 else .done s 0

end Lemma.Kernel.Operator
