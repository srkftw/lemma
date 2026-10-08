import Lemma.Core0

open Lemma.Core0.Memory

def root : UInt64 :=
  match Action.timerReadTime (fun status value => Action.done status value) with
  | .done _ value => value
  | _ => 0

#core0_check_action_v07 root
