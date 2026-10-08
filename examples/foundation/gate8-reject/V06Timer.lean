import Lemma.Core0

open Lemma.Core0.Memory

def root : Action :=
  Action.timerReadTime fun status value => Action.done status value

#core0_check_action_v06 root
