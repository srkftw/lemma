import Lemma.Core0

open Lemma.Core0.Memory

@[extern "lemma_gate8_forbidden_timer"]
opaque forbidden : Action := Action.timerProbe fun status value =>
  Action.done status value

def root : Action := forbidden

#core0_check_action_v07 root
