import Lemma.Core0

open Lemma.Core0.Bounded

def lookalike (budget : Nat) (step : UInt32 → UInt32 → UInt32)
    (count initial : UInt32) : UInt64 :=
  boundedFoldU32 budget step count initial

def step (index accumulator : UInt32) : UInt32 := accumulator + index

def root (count initial : UInt32) : UInt64 := lookalike 8 step count initial

#core0_check_v0_3 root
