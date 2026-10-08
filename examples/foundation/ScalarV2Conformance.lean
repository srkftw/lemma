import examples.foundation.ScalarV2ConformanceSupport

/-!
Ordinary elaborated Lean roots for the additive `core0-v0.2` profile.

The first thirty roots form fifteen notation/direct-identity metamorphic pairs:
complement, left shift, logical right shift, unsigned division, and unsigned
remainder at each of UInt8, UInt32, and UInt64.  The next roots force
structured conditionals returning every admitted scalar result type and carry
potentially unsafe operations through a normal helper-call boundary.  The final
nine roots retain executable coverage of every `core0-v0.1` primitive inside the
additive profile rather than treating v0.1 compatibility as a label-only claim.
-/

namespace Lemma.Examples.Foundation.ScalarV2

/-! ### UInt8 notation and exact primitive identities -/

def u8ComplementNotation (x : UInt8) : UInt8 := ~~~x

def u8ComplementDirect (x : UInt8) : UInt8 := UInt8.complement x

def u8ShlNotation (x count : UInt8) : UInt8 := x <<< count

def u8ShlDirect (x count : UInt8) : UInt8 := UInt8.shiftLeft x count

def u8ShrNotation (x count : UInt8) : UInt8 := x >>> count

def u8ShrDirect (x count : UInt8) : UInt8 := UInt8.shiftRight x count

def u8DivNotation (x divisor : UInt8) : UInt8 := x / divisor

def u8DivDirect (x divisor : UInt8) : UInt8 := UInt8.div x divisor

def u8RemNotation (x divisor : UInt8) : UInt8 := x % divisor

def u8RemDirect (x divisor : UInt8) : UInt8 := UInt8.mod x divisor

/-! ### UInt32 notation and exact primitive identities -/

def u32ComplementNotation (x : UInt32) : UInt32 := ~~~x

def u32ComplementDirect (x : UInt32) : UInt32 := UInt32.complement x

def u32ShlNotation (x count : UInt32) : UInt32 := x <<< count

def u32ShlDirect (x count : UInt32) : UInt32 := UInt32.shiftLeft x count

def u32ShrNotation (x count : UInt32) : UInt32 := x >>> count

def u32ShrDirect (x count : UInt32) : UInt32 := UInt32.shiftRight x count

def u32DivNotation (x divisor : UInt32) : UInt32 := x / divisor

def u32DivDirect (x divisor : UInt32) : UInt32 := UInt32.div x divisor

def u32RemNotation (x divisor : UInt32) : UInt32 := x % divisor

def u32RemDirect (x divisor : UInt32) : UInt32 := UInt32.mod x divisor

/-! ### UInt64 notation and exact primitive identities -/

def u64ComplementNotation (x : UInt64) : UInt64 := ~~~x

def u64ComplementDirect (x : UInt64) : UInt64 := UInt64.complement x

def u64ShlNotation (x count : UInt64) : UInt64 := x <<< count

def u64ShlDirect (x count : UInt64) : UInt64 := UInt64.shiftLeft x count

def u64ShrNotation (x count : UInt64) : UInt64 := x >>> count

def u64ShrDirect (x count : UInt64) : UInt64 := UInt64.shiftRight x count

def u64DivNotation (x divisor : UInt64) : UInt64 := x / divisor

def u64DivDirect (x divisor : UInt64) : UInt64 := UInt64.div x divisor

def u64RemNotation (x divisor : UInt64) : UInt64 := x % divisor

def u64RemDirect (x divisor : UInt64) : UInt64 := UInt64.mod x divisor

/-! ### Structured branch results and branch-dependent helper calls -/

def cfgBool (arithmetic quotient : Bool) (value divisor count : UInt8) : Bool :=
  if arithmetic then
    decide (Support.chooseU8 true quotient value divisor count = 0)
  else
    decide (Support.chooseU8 false quotient value divisor count = value)

def cfgU8 (arithmetic quotient : Bool) (value divisor count : UInt8) : UInt8 :=
  Support.chooseU8 arithmetic quotient value divisor count

def cfgU32 (arithmetic quotient : Bool) (value divisor count : UInt32) : UInt32 :=
  Support.chooseU32 arithmetic quotient value divisor count

def cfgU64 (arithmetic quotient : Bool) (value divisor count : UInt64) : UInt64 :=
  Support.chooseU64 arithmetic quotient value divisor count

def nestedHelperCall (outer arithmetic quotient : Bool)
    (value divisor count : UInt64) : UInt64 :=
  if outer then
    Support.chooseU64 arithmetic quotient value divisor count
  else
    Support.chooseU64 arithmetic quotient (~~~value) divisor count

/-! ### Retained `core0-v0.1` primitive closure -/

def u8LegacyArithmetic (x y z : UInt8) : UInt8 :=
  let sum := x + y
  let difference := sum - z
  let product := difference * y
  let masked := product &&& x
  let joined := masked ||| z
  joined ^^^ y

def u32LegacyArithmetic (x y z : UInt32) : UInt32 :=
  let sum := x + y
  let difference := sum - z
  let product := difference * y
  let masked := product &&& x
  let joined := masked ||| z
  joined ^^^ y

def u64LegacyArithmetic (x y z : UInt64) : UInt64 :=
  let sum := x + y
  let difference := sum - z
  let product := difference * y
  let masked := product &&& x
  let joined := masked ||| z
  joined ^^^ y

def u8LegacyCompare (flag expected : Bool) (x y z : UInt8) : UInt8 :=
  if flag = expected then
    if x = y then 1 else if x < y then 2 else if x ≤ z then 3 else 4
  else
    5

def u32LegacyCompare (flag expected : Bool) (x y z : UInt32) : UInt32 :=
  if flag = expected then
    if x = y then 1 else if x < y then 2 else if x ≤ z then 3 else 4
  else
    5

def u64LegacyCompare (flag expected : Bool) (x y z : UInt64) : UInt64 :=
  if flag = expected then
    if x = y then 1 else if x < y then 2 else if x ≤ z then 3 else 4
  else
    5

def u8LegacyCasts (x : UInt8) : UInt64 :=
  x.toUInt32.toUInt64 + x.toUInt64

def u32LegacyCasts (x : UInt32) : UInt64 :=
  x.toUInt8.toUInt64 + x.toUInt64

def u64LegacyCasts (x : UInt64) : UInt64 :=
  x.toUInt8.toUInt64 + x.toUInt32.toUInt64

end Lemma.Examples.Foundation.ScalarV2
