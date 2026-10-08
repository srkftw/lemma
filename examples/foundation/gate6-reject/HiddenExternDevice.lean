import Lemma.Core0

open Lemma.Core0.Memory

@[extern "lemma_gate6_forbidden_device"]
opaque forbidden : Action := Action.uartReadStatus fun status value =>
  Action.done status value

def root : Action := forbidden

#core0_check_v0_5 root
