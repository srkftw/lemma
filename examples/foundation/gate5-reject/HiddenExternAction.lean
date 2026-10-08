import Lemma.Core0

open Lemma.Core0.Memory

@[extern "lemma_gate5_forbidden_action"]
opaque forbidden (region : UInt8) (offset : UInt64) : Action := Action.done 0 0

def root (region : UInt8) (offset : UInt64) : Action :=
  forbidden region offset

#core0_check_v0_4 root
