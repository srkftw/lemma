import Lemma.Core0

open Lemma.Core0.Bounded

partial def recursiveStep (index accumulator : UInt32) : UInt32 :=
  recursiveStep index accumulator

def root (count initial : UInt32) : UInt64 :=
  boundedFoldU32 8 recursiveStep count initial

#core0_check_v0_3 root
