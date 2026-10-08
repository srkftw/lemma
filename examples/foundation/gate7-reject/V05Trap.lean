import Lemma.Core0

open Lemma.Core0.Memory

def root : Action :=
  Action.trapEcall fun status mask => Action.done status mask

#core0_check_v0_5 root
