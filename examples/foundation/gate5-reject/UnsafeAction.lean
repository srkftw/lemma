import Lemma.Core0

open Lemma.Core0.Memory

unsafe def root (value : UInt64) : Action := Action.done 0 value

#core0_check_v0_4 root
