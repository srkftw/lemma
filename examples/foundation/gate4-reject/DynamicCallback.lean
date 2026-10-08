import Lemma.Core0

open Lemma.Core0.Bounded

def root (step : UInt32 → UInt32 → UInt32) (count initial : UInt32) : UInt64 :=
  boundedFoldU32 8 step count initial

#core0_check_v0_3 root
