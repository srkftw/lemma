/-!
One immutable, genuinely elaborated source program for compiler-fault detection.
Each helper contains one deliberately targeted operation. The selector root retains
the legacy three-UInt64 harness ABI while the test driver changes only the lowering.
-/

namespace Lemma.Examples.Foundation.CompilerFaults

def strictLt (x y : UInt64) : UInt64 :=
  if x < y then 0x11 else 0x22

def unsignedLt (x y : UInt64) : UInt64 :=
  if x < y then 0x33 else 0x44

def addPair (x y : UInt64) : UInt64 :=
  x + y

def widen32 (x : UInt32) : UInt64 :=
  x.toUInt64

def truncate32 (x : UInt64) : UInt32 :=
  x.toUInt32

def orderedSub (x y : UInt64) : UInt64 :=
  x - y

def callOrder (x y : UInt64) : UInt64 :=
  orderedSub x y

def entry (selector x y : UInt64) : UInt64 :=
  if selector < 1 then strictLt x y
  else if selector < 2 then unsignedLt x y
  else if selector < 3 then addPair x y
  else if selector < 4 then widen32 x.toUInt32
  else if selector < 5 then truncate32 x |>.toUInt64
  else callOrder x y

end Lemma.Examples.Foundation.CompilerFaults
