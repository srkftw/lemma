import Lemma.Core0

open Lemma.Core0.Bounded

def root (count initial : UInt32) : UInt64 :=
  boundedFoldU32 8 (fun index accumulator => accumulator + index + initial) count initial

#core0_check_v0_3 root
