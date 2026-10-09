import Lemma.Core0

open Lemma.Core0.Bounded

def polymorphicStep {alpha : Type} [Add alpha] (index accumulator : alpha) : alpha :=
  accumulator + index

def root (count initial : UInt32) : UInt64 :=
  boundedFoldU32 8 (polymorphicStep (alpha := UInt32)) count initial

#core0_check_v0_3 root
