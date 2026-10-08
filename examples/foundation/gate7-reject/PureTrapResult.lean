import Lemma.Core0

open Lemma.Core0.Memory

def root : UInt64 :=
  match Action.trapEcall (fun status mask => Action.done status mask) with
  | .done _ value => value
  | _ => 0

#core0_check_action_v06 root
