import Lemma.Core0

open Lemma.Core0.Memory

def continuation : UInt8 → UInt64 → Action := fun status value =>
  Action.done status value

def root : Action :=
  Action.uartReadStatus continuation

#core0_check_v0_5 root
