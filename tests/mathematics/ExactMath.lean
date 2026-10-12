import Lemma.Mathematics.Exact
import Lemma.Courses.Arithmetic
import Lemma.Compiler.CFGLower
import Std.Data.HashMap

/-! Host-only independent integer oracle and execution of the actual record/UI
Actions. This is elaboration/lowering/semantic evidence, not RV64 execution. -/
namespace ExactMathFixture
open Lean Elab Command
open Lemma.Core0 Lemma.Core0.Memory Lemma.Compiler
open Lemma.Mathematics Lemma.Documents Lemma.Courses

def signed (n : Int) : UInt64 :=
  if n < 0 then n.natAbs.toUInt64 ||| 0x8000000000000000 else n.natAbs.toUInt64

def rationalProbe (a ad b bd n d budget : UInt64) : Action :=
  .done 0 (Exact.rational a ad b bd n d budget)
def polynomialProbe (a b c d p0 p1 p2 budget : UInt64) : Action :=
  .done 0 (Exact.polynomial a b c d p0 p1 p2 budget)

structure State where
  words : Std.HashMap UInt64 UInt64 := {}

def value (state : State) (address : UInt64) : UInt64 := state.words.getD address 0

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status result => pure (status, result)
  | .bind first next =>
    let (status, result) ← execute state first
    execute state (next status result)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then throw <| IO.userError "fixture fold exceeded budget"
    let mut status : UInt8 := 0
    let mut result := initial
    for i in [:count.toNat] do
      if status = 0 then
        let pair ← execute state (step i.toUInt32 count result c0 c1 c2 c3)
        status := pair.1
        result := pair.2
    execute state (next status result)
  | .platform op a b _ _ _ _ next =>
    match op with
    | .virtualRead64 => execute state (next 0 (value (← state.get) a))
    | .virtualWrite64 =>
      state.modify fun s => { words := s.words.insert a b }
      execute state (next 0 0)
    | _ => throw <| IO.userError "record fixture attempted a nonmemory effect"
  | _ => throw <| IO.userError "record fixture attempted unsupported syntax"

def must (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message

def records : IO Unit := do
  let state ← IO.mkRef ({} : State)
  let buffer : UInt64 := 0x329000
  must ((← execute state (Mathematics.create buffer 1 1)).1 = 0) "record create"
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "initial record validation"
  -- This is the same hit testing as a real pen contact on the notebook panel.
  for _ in [:5] do
    must ((← execute state (Arithmetic.press buffer (27*12) (3*20))).1 = 0) "numerator edit"
  must ((← execute state (Arithmetic.press buffer (8*12) (3*20))).1 = 0) "select denominator"
  for _ in [:5] do
    must ((← execute state (Arithmetic.press buffer (27*12) (3*20))).1 = 0) "denominator edit"
  must ((← execute state (Arithmetic.press buffer 12 (4*20))).1 = 0) "real check"
  let checked ← state.get
  must (value checked (buffer+56) = 5 && value checked (buffer+64) = 6 &&
    value checked (buffer+96) = 1 && value checked (buffer+104) = 11 &&
    value checked (buffer+144) = 1) "5/6 was not exact revision-bound Verified"
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "Verified record validation"
  must ((← execute state (Lemma.Courses.Review.summary buffer)).2 = 26) "unassisted exact attempt review reason"
  let save : UInt64 := 0x32a000
  must ((← execute state (Mathematics.copy buffer save)) = (0,1856)) "complete1856byte transaction copy"
  for i in [:232] do
    must (value (← state.get) (save+i.toUInt64*8) = value checked (buffer+i.toUInt64*8)) "transaction copy lost a word"
  must ((← execute state (Mathematics.copy (buffer+1) save)).1 = 234) "unaligned copy accepted"
  must ((← execute state (Mathematics.copy buffer 0xfffffffffffffff8)).1 = 234) "wrapping copy accepted"
  -- Editing cannot leave the earlier result applicable or erase its history.
  must ((← execute state (Arithmetic.press buffer (27*12) (3*20))).1 = 0) "edited answer"
  let edited ← state.get
  must (value edited (buffer+96) = 0 && value edited (buffer+104) = 0 &&
    value edited (buffer+256) = 11 && value edited (buffer+312) = 1) "editing evidence/history"
  must (value edited (save+96) = 1 && value edited (save+104) = 11 &&
    value edited (save+64) = 6) "editing changed immutable pending transaction copy"
  must ((← execute state (Mathematics.submit buffer)).2 = 2) "7 as denominator should be Invalid"
  must ((← execute state (Mathematics.hint buffer)).1 = 0) "hint"
  must (value (← state.get) (buffer+152) = 1) "assistance was not retained"
  -- Explicit budget failure is a distinct outcome; malformed load cannot fake Verified.
  must ((← execute state (Arithmetic.press buffer (17*12) (4*20))).1 = 0) "limit toggle"
  must ((← execute state (Mathematics.submit buffer)).2 = 5) "resource limit outcome"
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "resource history validation"
  must ((← execute state (Arithmetic.next buffer)).1 = 0) "next polynomial"
  must ((← execute state (Arithmetic.next buffer)).1 = 0) "next unsupported"
  must ((← execute state (Mathematics.submit buffer)).2 = 4) "unsupported goal outcome"
  must ((← execute state (Mathematics.validate buffer 2 1)).1 = 234) "wrong namespace accepted"
  must ((← execute state (Mathematics.validate buffer 1 2)).1 = 234) "wrong source page accepted"
  for mode in [1,2,3,4] do
    must ((← execute state (Mathematics.reviewMode buffer)).1 = 0) "manual override/disable"
    must (value (← state.get) (buffer+184) = mode && value (← state.get) (buffer+96) = 4) "override changed mathematical evidence"
  must (((← execute state (Lemma.Courses.Review.summary buffer)).2 &&& 63) = 56) "disabled recommendation"
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "ordered learner event validation"
  -- An unknown policy ID/event payload cannot silently alter the baseline.
  let valid ← state.get
  state.modify fun s => { words := s.words.insert (buffer+176) 2 }
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 234) "unknown policy accepted"
  state.set valid
  state.modify fun s => { words := s.words.insert (buffer+192) 64 }
  must ((← execute state (Mathematics.reviewMode buffer)).1 = 235 &&
    (← execute state (Mathematics.hint buffer)).1 = 235 &&
    (← execute state (Mathematics.submit buffer)).1 = 235) "event bound did not stop before mutation"
  must (value (← state.get) (buffer+184) = 4 && value (← state.get) (buffer+96) = 4 &&
    value (← state.get) (buffer+152) = 1) "exhaustion changed original evidence/policy/assistance"
  state.set valid
  -- A real version1 record keeps all answers/evidence and migrates old hints
  -- as an explicitly unanchored aggregate rather than invented hint events.
  state.modify fun s => { words := s.words.insert (buffer+8) 1 }
  for i in [:10] do state.modify fun s => { words := s.words.insert (buffer+176+i.toUInt64*8) 0 }
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "legacy validation"
  must ((← execute state (Mathematics.upgrade buffer)).2 = 1) "guest migration"
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 0) "migrated ordered event validation"
  must (value (← state.get) (buffer+96) = 4 && value (← state.get) (buffer+152) = 1 &&
    value (← state.get) (buffer+192) = 5) "migration lost actual evidence/assistance/history"
  state.modify fun s => { words := s.words.insert (buffer+96) 1 }
  must ((← execute state (Mathematics.validate buffer 1 1)).1 = 234) "forged Verified accepted"

run_cmd do
  let mut cases : Nat := 0
  for a in [-3,0,3] do
    for b in [-2,0,2] do
      for ad in [1,3] do
        for bd in [2,3] do
          for n in [-4,0,4] do
            for d in [1,4] do
              let expected := if (a*bd+b*ad)*d = n*ad*bd then 1 else 2
              unless Exact.rational (signed a) ad.toNat.toUInt64 (signed b) bd.toNat.toUInt64
                  (signed n) d.toNat.toUInt64 8 = expected do
                throwError "signed rational algorithm differs from independent Int oracle"
              cases := cases+1
  for a in [-2,0,2] do
    for b in [-2,0,2] do
      for c in [-2,0,2] do
        for d in [-2,0,2] do
          unless Exact.polynomial (signed a) (signed b) (signed c) (signed d)
              (signed (b*d)) (signed (a*d+b*c)) (signed (a*c)) 6 = 1 do
            throwError "polynomial coefficient identity differs from independent Int oracle"
          unless Exact.polynomial (signed a) (signed b) (signed c) (signed d)
              (signed (b*d+1)) (signed (a*d+b*c)) (signed (a*c)) 6 = 2 do
            throwError "altered polynomial coefficient accepted"
          cases := cases+2
  for (a,ad,b,bd,n,d,budget,expected) in
      #[(1,0,1,3,5,6,8,2),(1,2,1,3,5,0,8,2),(1,2,1,3,5,6,7,5),
        (1000001,2,1,3,5,6,8,5),(0x8000000000000000,2,1,3,5,6,8,3),
        (1000000,1000000,1000000,1000000,2,1,8,1),
        (1000000,1000000,0x80000000000f4240,1000000,0,1000000,8,1)] do
    unless Exact.rational a ad b bd n d budget = expected do throwError "exact semantic boundary"
  unless Exact.applicable 1 11 12 1 Exact.checkerIdentity = false &&
      Exact.applicable 1 11 11 1 Exact.checkerIdentity = true &&
      Exact.applicable 1 11 11 3 Exact.checkerIdentity = false do throwError "revision applicability"
  liftIO records
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .user_v0_1
      #[``rationalProbe, ``polynomialProbe, ``Mathematics.copy, ``Mathematics.submit, ``Mathematics.validate, ``Mathematics.upgrade, ``Lemma.Courses.Review.summary, ``Arithmetic.press, ``Arithmetic.render] with
    | .ok suite => pure suite
    | .error diagnostic => throwError diagnostic.render
  match lowerActionSuiteExecution .user_v0_1 suite with
  | .ok _ => pure ()
  | .error diagnostic => throwError diagnostic
  logInfo m!"EXACT_MATH:PASS {cases} independent signed arithmetic/polynomial comparisons, semantic/resource boundaries, revision/history/namespace/UI records; genuine elaboration/lowering; guest execution separate"

end ExactMathFixture
