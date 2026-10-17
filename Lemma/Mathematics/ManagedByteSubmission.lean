/-! Ordinary Lean binary submission payload. The isolated server must retain
its signed/canonical/budget/overflow preflight before calling this comparator.
No deployment or trusted execution identity selects this implementation yet.
-/
namespace Lemma.Mathematics.ManagedByteSubmission
@[noinline] def empty (capacity : UInt64) : ByteArray :=
  ByteArray.emptyWithCapacity capacity.toNat
@[noinline] def appendWord (bytes : ByteArray) (word : UInt64) : ByteArray :=
  bytes.push word.toUInt8
    |>.push (word >>> 8).toUInt8
    |>.push (word >>> 16).toUInt8
    |>.push (word >>> 24).toUInt8
    |>.push (word >>> 32).toUInt8
    |>.push (word >>> 40).toUInt8
    |>.push (word >>> 48).toUInt8
    |>.push (word >>> 56).toUInt8
@[noinline] def readWord (bytes : ByteArray) (start : UInt64) : UInt64 :=
  (bytes.get! start.toNat).toUInt64 |||
    ((bytes.get! (start + 1).toNat).toUInt64 <<< 8) |||
    ((bytes.get! (start + 2).toNat).toUInt64 <<< 16) |||
    ((bytes.get! (start + 3).toNat).toUInt64 <<< 24) |||
    ((bytes.get! (start + 4).toNat).toUInt64 <<< 32) |||
    ((bytes.get! (start + 5).toNat).toUInt64 <<< 40) |||
    ((bytes.get! (start + 6).toNat).toUInt64 <<< 48) |||
    ((bytes.get! (start + 7).toNat).toUInt64 <<< 56)
@[noinline] def payload (capacity numerator denominator : UInt64) : ByteArray :=
  appendWord (appendWord (empty capacity) numerator) denominator
@[noinline] def compareFiveSix (numerator denominator : UInt64) : UInt64 :=
  let bytes := payload 16 numerator denominator
  let n := readWord bytes 0
  let d := readWord bytes 8
  if n * 6 = d * 5 then 1 else 2
end Lemma.Mathematics.ManagedByteSubmission
