/-! Ordinary closed Lean source for full-width hexadecimal UTF-8 submission
roundtrips. This module carries no deployment/checker identity by itself. The
isolated service must keep its original domain/overflow/revision preflight. -/
namespace Lemma.Mathematics.ManagedStringSubmission
@[noinline] def empty (capacity : UInt64) : ByteArray :=
  ByteArray.emptyWithCapacity capacity.toNat
@[noinline] def digit (value : UInt64) : UInt8 :=
  let n := value &&& 15
  (if n < 10 then n + 48 else n + 87).toUInt8
@[noinline] def encoded (capacity word : UInt64) : ByteArray :=
  (empty capacity).push (digit (word >>> 60))
    |>.push (digit (word >>> 56)) |>.push (digit (word >>> 52))
    |>.push (digit (word >>> 48)) |>.push (digit (word >>> 44))
    |>.push (digit (word >>> 40)) |>.push (digit (word >>> 36))
    |>.push (digit (word >>> 32)) |>.push (digit (word >>> 28))
    |>.push (digit (word >>> 24)) |>.push (digit (word >>> 20))
    |>.push (digit (word >>> 16)) |>.push (digit (word >>> 12))
    |>.push (digit (word >>> 8)) |>.push (digit (word >>> 4))
    |>.push (digit word)
@[noinline] def parse (bytes : ByteArray) : Option String := String.fromUTF8? bytes
@[noinline] def nibble (byte : UInt8) : UInt64 :=
  let value := byte.toUInt64
  if value < 58 then value - 48 else value - 87
@[noinline] def decoded (bytes : ByteArray) : UInt64 :=
  (nibble (bytes.get! 0) <<< 60) ||| (nibble (bytes.get! 1) <<< 56) |||
  (nibble (bytes.get! 2) <<< 52) ||| (nibble (bytes.get! 3) <<< 48) |||
  (nibble (bytes.get! 4) <<< 44) ||| (nibble (bytes.get! 5) <<< 40) |||
  (nibble (bytes.get! 6) <<< 36) ||| (nibble (bytes.get! 7) <<< 32) |||
  (nibble (bytes.get! 8) <<< 28) ||| (nibble (bytes.get! 9) <<< 24) |||
  (nibble (bytes.get! 10) <<< 20) ||| (nibble (bytes.get! 11) <<< 16) |||
  (nibble (bytes.get! 12) <<< 12) ||| (nibble (bytes.get! 13) <<< 8) |||
  (nibble (bytes.get! 14) <<< 4) ||| nibble (bytes.get! 15)
@[noinline] def decode (text : String) : UInt64 := decoded text.toByteArray
@[noinline] def roundtrip (word other : UInt64) : UInt64 :=
  match parse (encoded 16 word) with
  | none => 0
  | some text => decode text ^^^ other
@[noinline] def compareFiveSix (numerator denominator : UInt64) : UInt64 :=
  match parse (encoded 16 numerator) with
  | none => 0
  | some n =>
    match parse (encoded 16 denominator) with
    | none => 0
    | some d => if decode n * 6 = decode d * 5 then 1 else 2
end Lemma.Mathematics.ManagedStringSubmission
