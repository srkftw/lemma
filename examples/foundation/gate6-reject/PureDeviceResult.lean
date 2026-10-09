import Lemma.Core0

open Lemma.Core0.Memory

def root : UInt64 :=
  match Action.uartWriteByte 0x41 (fun status => Action.done status 0) with
  | .done _ value => value
  | _ => 0

#core0_check_v0_5 root
