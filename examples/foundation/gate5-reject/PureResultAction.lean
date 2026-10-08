import Lemma.Core0

open Lemma.Core0.Memory

def root (region : UInt8) (offset : UInt64) : UInt64 :=
  match Action.store8 region offset 1 (fun status => Action.done status 0) with
  | .done _ value => value
  | _ => 0

#core0_check_v0_4 root
