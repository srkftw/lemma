import Lemma.Core0

open Lemma.Core0.Memory

def root (count : UInt32) (extra : UInt64) : Action :=
  Action.boundedFoldU64 8
    (fun _index _count accumulator _ctx0 _ctx1 _ctx2 _ctx3 =>
      Action.done 0 (accumulator + extra))
    count 0 0 0 0 0 fun status value => Action.done status value

#core0_check_v0_4 root
