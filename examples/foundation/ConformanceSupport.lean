/-!
Cross-module scalar helpers for the Gate 2 Core0 conformance corpus.

These declarations intentionally remain ordinary safe, first-order Lean.  In
particular, the ABI helper has ten explicit scalar parameters so a dedicated
no-inline test build can inspect both register- and stack-passed arguments.
-/

namespace Lemma.Examples.Foundation.Conformance.Support

def mixedLeaf (gate : Bool) (byte : UInt8) (word : UInt32) (wide : UInt64) : UInt64 :=
  let byteWide : UInt64 := byte.toUInt64
  let wordWide : UInt64 := word.toUInt64
  if gate then (wide + byteWide) ^^^ wordWide else (wide - byteWide) ||| wordWide

def sharedLeaf (x y : UInt64) : UInt64 :=
  (x * 3) ^^^ y

def sharedLeft (x y : UInt64) : UInt64 :=
  sharedLeaf (x + y) y

def sharedRight (x y : UInt64) : UInt64 :=
  sharedLeaf (x ^^^ y) x

def extractedStep (x y : UInt64) : UInt64 :=
  (x + y) ^^^ y

def abiNoInlineCallee
    (a0 : UInt64) (a1 : UInt8) (a2 : UInt32) (a3 : Bool)
    (a4 : UInt64) (a5 : UInt8) (a6 : UInt32) (a7 : Bool)
    (a8 : UInt8) (a9 : UInt32) : UInt64 :=
  let narrow : UInt64 :=
    a1.toUInt64 + a2.toUInt64 + a5.toUInt64 + a6.toUInt64 +
      a8.toUInt64 + a9.toUInt64
  let selected : UInt64 := if a3 then a0 else a4
  let mixed : UInt64 := if a7 then selected + a8.toUInt64 else selected ^^^ a9.toUInt64
  narrow + mixed

end Lemma.Examples.Foundation.Conformance.Support
