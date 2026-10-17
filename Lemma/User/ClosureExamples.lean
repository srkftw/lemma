namespace Lemma.User.ClosureExamples

/-! Ordinary source fixtures for the versioned closure subset. These functions
have no effects or mathematical verification authority. Their runtime behavior
is obtained only from genuine compiler IR and checked target lowering. -/
@[noinline] def plus (offset input : UInt64) : UInt64 := input + offset
@[noinline] def times (factor input : UInt64) : UInt64 := input * factor
@[noinline] def apply (function : UInt64 → UInt64) (input : UInt64) : UInt64 := function input
@[noinline] def chooseApply (selector : UInt64) (left right : UInt64 → UInt64)
    (input : UInt64) : UInt64 :=
  if selector = 0 then left input else right input

@[noinline] def selected (selector input : UInt64) : UInt64 :=
  let left := plus input
  let right := times (input + selector)
  let first := chooseApply selector left right 0xffffffffffffffff
  let second := chooseApply selector left right 0x8000000000000001
  first ^^^ (second >>> 1)

@[noinline] def four (a b c d input : UInt64) : UInt64 := (input + a) ^^^ (b*c+d)
@[noinline] def fourCaptures (a b : UInt64) : UInt64 :=
  let function := four a b (a+b) (a^^^b)
  let first := apply function 0xffffffffffffffff
  let second := apply function 0x8000000000000001
  first ^^^ (second >>> 1)

@[noinline] def lambdaSelected (selector capture : UInt64) : UInt64 → UInt64 :=
  if selector = 0 then (fun input => input + capture) else (fun input => input * capture)
@[noinline] def lambdaEntry (selector input : UInt64) : UInt64 :=
  let function := lambdaSelected selector input
  let first := apply function 0xffffffffffffffff
  let second := apply function 0x8000000000000001
  first ^^^ (second >>> 1)

@[noinline] def sharedCaptures (selector input : UInt64) : UInt64 :=
  let left := plus input
  let right := times input
  let first := chooseApply selector left right 0xffffffffffffffff
  let second := chooseApply selector left right 0x8000000000000001
  first ^^^ (second >>> 1)

end Lemma.User.ClosureExamples
