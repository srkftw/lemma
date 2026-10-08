import Lemma.Core0

open Lemma.Core0.Memory

@[extern "lemma_gate7_forbidden_trap"]
opaque forbidden : Action := Action.trapEcall fun status mask =>
  Action.done status mask

def root : Action := forbidden

#core0_check_action_v06 root
