import Lemma.Core0

open Lemma.Core0.Memory

def root
    (step : UInt32 → UInt32 → UInt64 → UInt64 → UInt64 → UInt64 → UInt64 → Action)
    (count : UInt32) : Action :=
  Action.boundedFoldU64 8 step count 0 0 0 0 0 fun status value =>
    Action.done status value

#core0_check_v0_4 root
