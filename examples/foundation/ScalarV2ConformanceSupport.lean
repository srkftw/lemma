/-!
Cross-module helpers for the `core0-v0.2` scalar/CFG conformance corpus.

Every dangerous LLVM operation remains beneath an ordinary Lean conditional.
The Gate 3 lowering must therefore preserve branch choice across this direct-call
boundary; it may not eagerly evaluate the unchosen division, remainder, or shift.
-/

namespace Lemma.Examples.Foundation.ScalarV2.Support

def chooseU8 (arithmetic quotient : Bool) (value divisor count : UInt8) : UInt8 :=
  if arithmetic then
    if quotient then value / divisor else value % divisor
  else
    if quotient then value <<< count else value >>> count

def chooseU32 (arithmetic quotient : Bool) (value divisor count : UInt32) : UInt32 :=
  if arithmetic then
    if quotient then value / divisor else value % divisor
  else
    if quotient then value <<< count else value >>> count

def chooseU64 (arithmetic quotient : Bool) (value divisor count : UInt64) : UInt64 :=
  if arithmetic then
    if quotient then value / divisor else value % divisor
  else
    if quotient then value <<< count else value >>> count

end Lemma.Examples.Foundation.ScalarV2.Support
