import Lemma.Core0

open Lemma.Core0.Memory

def budget : Nat := 8

def step (_index _count : UInt32) (accumulator _ctx0 _ctx1 _ctx2 _ctx3 : UInt64) :
    Action :=
  Action.done 0 accumulator

def root (count : UInt32) : Action :=
  Action.boundedFoldU64 budget step count 0 0 0 0 0 fun status value =>
    Action.done status value

#core0_check_v0_4 root
