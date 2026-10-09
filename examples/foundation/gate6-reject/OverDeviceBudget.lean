import Lemma.Core0

open Lemma.Core0.Memory

def step (_index _count : UInt32) (accumulator _ctx0 _ctx1 _ctx2 _ctx3 : UInt64) :
    Action :=
  Action.uartWriteByte accumulator.toUInt8 fun status =>
    Action.done status accumulator

def root (count : UInt32) : Action :=
  Action.boundedFoldU64 1000001 step count 0 0 0 0 0 fun status value =>
    Action.done status value

#core0_check_v0_5 root
