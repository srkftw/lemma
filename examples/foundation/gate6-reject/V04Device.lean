import Lemma.Core0

open Lemma.Core0.Memory

def root : Action :=
  Action.uartReadStatus fun status value => Action.done status value

#core0_check_v0_4 root
