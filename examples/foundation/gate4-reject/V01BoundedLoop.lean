import Lemma.Core0

open Lemma.Core0.Bounded

def step (index accumulator : UInt32) : UInt32 := accumulator + index
def root (count initial : UInt32) : UInt64 := boundedFoldU32 8 step count initial

#core0_check root
