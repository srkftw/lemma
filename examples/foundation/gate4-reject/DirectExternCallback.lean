import Lemma.Core0

open Lemma.Core0.Bounded

@[extern "lemma_gate4_direct_forbidden"]
opaque callback (index accumulator : UInt32) : UInt32

def root (count initial : UInt32) : UInt64 :=
  boundedFoldU32 8 callback count initial

#core0_check_v0_3 root
