import Lemma.Core0

open Lemma.Core0.Memory

private instance : Nonempty Action := ⟨Action.done 0 0⟩

partial def recursiveAction (value : UInt64) : Action :=
  recursiveAction value

def root (value : UInt64) : Action := recursiveAction value

#core0_check_v0_4 root
