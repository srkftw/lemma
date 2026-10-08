import Lemma.Core0

open Lemma.Core0.Memory

def storedContinuation (status : UInt8) (value : UInt64) : Action :=
  Action.done status value

def root (region : UInt8) (offset : UInt64) : Action :=
  Action.load8 region offset storedContinuation

#core0_check_v0_4 root
