/-! Restricted exact mathematics, contract `lemma-exact/1`.

This is ordinary scalar Lean compiled by the checked Core0 path, not the Lean
proof kernel. Signed integers use canonical sign/magnitude UInt64 words. Every
public operand is bounded to one million; arithmetic intermediates fit below
2^63. No wrapping result can authorize Verified. -/
namespace Lemma.Mathematics.Exact

def unchecked : UInt64 := 0
def verified : UInt64 := 1
def invalid : UInt64 := 2
def needsClarification : UInt64 := 3
def unsupported : UInt64 := 4
def indeterminate : UInt64 := 5
def sign : UInt64 := 0x8000000000000000
def limit : UInt64 := 1000000
def checkerIdentity : UInt64 := 0x0001000000000001
def magnitude (value : UInt64) : UInt64 := value &&& 0x7fffffffffffffff
def canonical (value : UInt64) : Bool := if value = sign then false else true
def bounded (value : UInt64) : Bool := magnitude value ≤ limit

def negate (value : UInt64) : UInt64 := if value = 0 then 0 else value ^^^ sign

/-- Internal operands have the bounds established by the public callers. -/
def multiply (a b : UInt64) : UInt64 :=
  let value := magnitude a * magnitude b
  if value = 0 then 0 else value ||| ((a ^^^ b) &&& sign)

/-- Cancellation normalizes zero. The callers bound the magnitude sum to
2*10^18, strictly below the sign bit. -/
def add (a b : UInt64) : UInt64 :=
  let x := magnitude a
  let y := magnitude b
  if a &&& sign = b &&& sign then
    let value := x + y
    if value = 0 then 0 else value ||| (a &&& sign)
  else if x = y then 0 else
    if y < x then (x - y) ||| (a &&& sign) else (y - x) ||| (b &&& sign)

/-- Check a/ad + b/bd = n/d in Q. Denominators are positive, with no hidden
nonzero side condition. Resource budget is a declared count of arithmetic
steps, not wall time. -/
def rational (a ad b bd n d budget : UInt64) : UInt64 :=
  if canonical a = false then needsClarification else
  if canonical b = false then needsClarification else
  if canonical n = false then needsClarification else
  if ad = 0 then invalid else if bd = 0 then invalid else if d = 0 then invalid else
  if bounded a = false then indeterminate else if bounded b = false then indeterminate else
  if bounded n = false then indeterminate else
  if limit < ad then indeterminate else if limit < bd then indeterminate else
  if limit < d then indeterminate else if budget < 8 then indeterminate else
  let sum := add (multiply a bd) (multiply b ad)
  if multiply sum d = multiply n (ad * bd) then verified else invalid

/-- Check (a*x+b)*(c*x+d) = p2*x^2+p1*x+p0 by exact coefficient equality
over Q[x]. The represented coefficients are integers embedded in Q. This
checks all x; it does not sample floating-point values. -/
def polynomial (a b c d p0 p1 p2 budget : UInt64) : UInt64 :=
  if canonical a = false then needsClarification else if canonical b = false then needsClarification else
  if canonical c = false then needsClarification else if canonical d = false then needsClarification else
  if canonical p0 = false then needsClarification else if canonical p1 = false then needsClarification else
  if canonical p2 = false then needsClarification else
  if bounded a = false then indeterminate else if bounded b = false then indeterminate else
  if bounded c = false then indeterminate else if bounded d = false then indeterminate else
  if bounded p0 = false then indeterminate else if bounded p1 = false then indeterminate else
  if bounded p2 = false then indeterminate else if budget < 6 then indeterminate else
  if multiply b d = p0 then
    if add (multiply a d) (multiply b c) = p1 then
      if multiply a c = p2 then verified else invalid
    else invalid else invalid

/-- Applicable evidence is bound to its exact immutable package goal and the
current submission revision. Unsupported domains cannot obtain arithmetic
authority through a matching result code. -/
def applicable (outcome evidenceRevision submissionRevision goal environment : UInt64) : Bool :=
  if outcome = verified then if evidenceRevision = submissionRevision then
    if goal = 1 then environment = checkerIdentity else
    if goal = 2 then environment = checkerIdentity else false
  else false else false

end Lemma.Mathematics.Exact
