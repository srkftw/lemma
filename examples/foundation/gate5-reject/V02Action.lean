import Lemma.Core0

open Lemma.Core0.Memory

def root (region : UInt8) (offset : UInt64) : Action :=
  Action.load8 region offset fun status value => Action.done status value

#core0_check_v0_2 root
