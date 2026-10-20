import Lemma.Mathematics.Exact
import Lemma.User.Memory

/-! Bounded local rational calculator; its result is not checking evidence. -/
namespace Lemma.Services.Arithmetic.ReductionV1
open Lemma.Core0.Memory

def maximumMagnitude : UInt64 := 1000000
def requiredBudget : UInt64 := 34
private def gcdStep (_ _ : UInt32) (packed _ _ _ _ : UInt64) : Action :=
  let a := packed >>> 32
  let b := packed &&& 0xffffffff
  if b = 0 then .done 0 packed else .done 0 ((b <<< 32) ||| (a % b))

/-- Status234: malformed/undefined fraction.235: declared numerical resource.
On success only, result encodes canonical magnitude in bits32..62, original
sign in bit63, positive denominator in bits0..31. No Verified is produced. -/
def calculate (numerator denominator budget : UInt64) : Action :=
  if numerator = Lemma.Mathematics.Exact.sign then .done 234 0 else
  if denominator = 0 then .done 234 0 else
  let magnitude := numerator &&& 0x7fffffffffffffff
  if maximumMagnitude < magnitude then .done 235 0 else
  if maximumMagnitude < denominator then .done 235 0 else
  if budget < requiredBudget then .done 235 0 else
  .boundedFoldU64 32 gcdStep 32 ((magnitude <<< 32) ||| denominator) 0 0 0 0 fun status packed =>
  if status = 0 then
    if packed &&& 0xffffffff = 0 then
    let gcd := packed >>> 32
    if gcd = 0 then .done 234 0 else
    let n := magnitude / gcd
    let d := denominator / gcd
    .done 0 ((n <<< 32) ||| d ||| (numerator &&& Lemma.Mathematics.Exact.sign))
    else .done 235 0
  else .done status 0
end Lemma.Services.Arithmetic.ReductionV1
