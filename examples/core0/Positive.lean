import Lemma.Core0

/-!
Positive ordinary-Lean source corpus for Core0 v0.1.  These are elaborated by Lean
before `#core0_check` reads their declaration bodies from the environment.
-/

namespace Lemma.Examples.Core0.Positive

def mix64 (x y : UInt64) : UInt64 :=
  let sum := x + y
  let mixed := (sum ^^^ y) * 3
  if sum < x then mixed - 1 else (mixed &&& 18446744073709551615) + 1

def entry (x y seed : UInt64) : UInt64 :=
  let narrowed : UInt32 := ((x ^^^ y) + seed).toUInt32
  let widened : UInt64 := narrowed.toUInt64
  if x ≤ y then mix64 widened seed else mix64 widened (y ^^^ seed)

def u8Path (x y : UInt8) : UInt8 :=
  let overflow := (x ||| y) + 255
  if x = y then overflow else (x &&& y) ^^^ 17

def u32Path (x y : UInt32) : UInt32 :=
  if x < y then (x * y) - 1 else (x + y) ^^^ 4294967295

def conversions (x : UInt64) : UInt64 :=
  let byte : UInt8 := x.toUInt8
  let word : UInt32 := byte.toUInt32
  word.toUInt64

def boolResult (x y : UInt64) : Bool :=
  decide (x < y)

def chooseBool (condition : Bool) (x y : UInt64) : UInt64 :=
  if condition then x else y

#core0_check entry
#core0_check u8Path
#core0_check u32Path
#core0_check conversions
#core0_check boolResult
#core0_check chooseBool

open Lean Elab Command in
run_cmd do
  let env ← getEnv
  let program ← match Lemma.Core0.checkAndLower env ``mix64 with
    | .ok program => pure program
    | .error diag => throwError diag.render
  let cases : Array (Nat × Nat × Nat) := #[
    (0, 0, 1),
    (2, 3, 19),
    (18446744073709551615, 1, 2),
    (18446744073709551615, 18446744073709551615, 2)
  ]
  for (x, y, expectedRaw) in cases do
    let expected := Lemma.Core0.Scalar.normalize .u64 expectedRaw
    match Lemma.Core0.evalProgramScalars program
        #[Lemma.Core0.Scalar.u64 x, Lemma.Core0.Scalar.u64 y] with
    | .error diag => throwError diag.render
    | .ok result =>
        unless result.ty == .u64 && result.value == expected do
          throwError m!"reference mismatch for mix64({x}, {y}): got {result.value}, expected {expected}"
  let u8Program ← match Lemma.Core0.checkAndLower env ``u8Path with
    | .ok program => pure program
    | .error diag => throwError diag.render
  for (x, y, expected) in #[(255, 1, 16), (255, 255, 254)] do
    match Lemma.Core0.evalProgramScalars u8Program
        #[Lemma.Core0.Scalar.u8 x, Lemma.Core0.Scalar.u8 y] with
    | .error diag => throwError diag.render
    | .ok result =>
        unless result.ty == .u8 && result.value == expected do
          throwError m!"reference mismatch for u8Path({x}, {y})"
  let u32Program ← match Lemma.Core0.checkAndLower env ``u32Path with
    | .ok program => pure program
    | .error diag => throwError diag.render
  for (x, y, expected) in #[(0, 1, 4294967295), (4294967295, 1, 4294967295)] do
    match Lemma.Core0.evalProgramScalars u32Program
        #[Lemma.Core0.Scalar.u32 x, Lemma.Core0.Scalar.u32 y] with
    | .error diag => throwError diag.render
    | .ok result =>
        unless result.ty == .u32 && result.value == expected do
          throwError m!"reference mismatch for u32Path({x}, {y})"
  let conversionProgram ← match Lemma.Core0.checkAndLower env ``conversions with
    | .ok program => pure program
    | .error diag => throwError diag.render
  match Lemma.Core0.evalProgramScalars conversionProgram
      #[Lemma.Core0.Scalar.u64 18446744073709551615] with
  | .error diag => throwError diag.render
  | .ok result =>
      unless result.ty == .u64 && result.value == 255 do
        throwError m!"reference conversion mismatch: {repr result}"
  let boolProgram ← match Lemma.Core0.checkAndLower env ``boolResult with
    | .ok program => pure program
    | .error diag => throwError diag.render
  match Lemma.Core0.evalProgram boolProgram
      #[.scalar (Lemma.Core0.Scalar.u64 0), .scalar (Lemma.Core0.Scalar.u64 1)] with
  | .error diag => throwError diag.render
  | .ok (.bool true) => pure ()
  | .ok result => throwError m!"reference comparison mismatch: {repr result}"
  let chooseProgram ← match Lemma.Core0.checkAndLower env ``chooseBool with
    | .ok program => pure program
    | .error diag => throwError diag.render
  match Lemma.Core0.evalProgram chooseProgram #[.bool false,
      .scalar (Lemma.Core0.Scalar.u64 11), .scalar (Lemma.Core0.Scalar.u64 29)] with
  | .error diag => throwError diag.render
  | .ok (.scalar result) =>
      unless result.ty == .u64 && result.value == 29 do
        throwError m!"reference Bool branch mismatch: {repr result}"
  | .ok result => throwError m!"reference Bool branch type mismatch: {repr result}"
  logInfo "Core0 reference evaluator: 11 genuine-frontend cases passed"

end Lemma.Examples.Core0.Positive
