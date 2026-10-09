import Lemma.Core0.Bounded
import examples.foundation.BoundedConformanceSupport

/-!
Ordinary elaborated Lean declarations for the additive `core0-v0.3` profile.
Every root takes its runtime count and initial accumulator as `UInt32` values and
returns the tagged `UInt64` bounded-fold outcome.
-/

namespace Lemma.Examples.Foundation.Bounded

open Lemma.Core0.Bounded

def sumStep (index accumulator : UInt32) : UInt32 :=
  accumulator + index

def sumChangedStep (index accumulator : UInt32) : UInt32 :=
  accumulator + index + 1

def bitMixStep (index accumulator : UInt32) : UInt32 :=
  let count := (index + 5) &&& 31
  ((accumulator ^^^ index) <<< count) + 0x6d2b79f5

def helperStep (index accumulator : UInt32) : UInt32 :=
  Support.helperMix index accumulator

def nestedOuterStep (index accumulator : UInt32) : UInt32 :=
  (boundedFoldU32 16 Support.nestedInnerStep index accumulator).toUInt32

/-- Runtime-counted triangular summation, statically capped at sixteen steps. -/
def sumFold (count initial : UInt32) : UInt64 :=
  boundedFoldU32 16 sumStep count initial

/-- Metamorphic body variant: the same loop boundary with a distinct callback. -/
def sumFoldChanged (count initial : UInt32) : UInt64 :=
  boundedFoldU32 16 sumChangedStep count initial

/-- A shift/xor/add fold using v0.2 scalar operations inside the callback. -/
def bitMixFold (count initial : UInt32) : UInt64 :=
  boundedFoldU32 64 bitMixStep count initial

/-- The outer callback itself contains a second checked bounded fold. -/
def nestedFold (count initial : UInt32) : UInt64 :=
  boundedFoldU32 16 nestedOuterStep count initial

/-- Callback work reaches an ordinary closed helper in another source module. -/
def helperFold (count initial : UInt32) : UInt64 :=
  boundedFoldU32 64 helperStep count initial

/-- Static zero budget: only runtime count zero succeeds. -/
def zeroBudgetFold (count initial : UInt32) : UInt64 :=
  boundedFoldU32 0 sumStep count initial

/-- Maximum admitted static budget, used for 255/256/257 boundary execution. -/
def maxBudgetFold (count initial : UInt32) : UInt64 :=
  boundedFoldU32 256 sumStep count initial

end Lemma.Examples.Foundation.Bounded
