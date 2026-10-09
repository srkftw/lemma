import Lemma.Platform.LemmaVM.ConsoleDevice

/-! Bounded console operations shared by kernel diagnostics. The K1 record is
five hexadecimal words, suitable both for a terminal and exact host capture. -/
namespace Lemma.Kernel.Console
open Lemma.Core0.Memory
open Lemma.Platform.LemmaVM.ConsoleDevice

def failed (s : UInt8) : Bool := if s = 0 then false else true
def hexDigit (n : UInt64) : UInt8 :=
  if n < 10 then (n + 48).toUInt8 else (n + 87).toUInt8
def hexStep (i _count : UInt32) (acc word _ _ _ : UInt64) : Action :=
  .bind (sendByte (hexDigit ((word >>> (60 - i.toUInt64 * 4)) &&& 15))) fun s _ =>
  .done s (acc + 1)
def putWord (word : UInt64) : Action :=
  .boundedFoldU64 16 hexStep 16 0 word 0 0 0 fun s v => .done s v
def spaceWord (word : UInt64) : Action :=
  .bind (sendByte 32) fun s _ =>
  if s = 0 then putWord word else .done s 0
def record (kind a b c d : UInt64) : Action :=
  .bind (sendByte 75) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (sendByte 49) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord kind) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord a) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord b) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord c) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord d) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (sendByte 10) fun s _ => .done s 0
def readWordStep (i _count : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind receiveByte fun s byte =>
  .done s (acc ||| (byte <<< (i.toUInt64 * 8)))
def readWord : Action :=
  .boundedFoldU64 8 readWordStep 8 0 0 0 0 0 fun s v => .done s v

end Lemma.Kernel.Console
