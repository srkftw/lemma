import Lemma.Core0

open Lemma.Core0.Memory

def continuation : UInt8 → UInt64 → Action := fun status mask =>
  Action.done status mask

def root : Action :=
  Action.trapBreakpoint continuation

#core0_check_action_v06 root
