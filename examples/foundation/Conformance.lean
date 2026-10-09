import examples.foundation.ConformanceSupport
import examples.foundation.ConformanceMovedA
import examples.foundation.ConformanceMovedB
import examples.foundation.ConformanceImportBase
import examples.foundation.ConformanceImportExtra

/-!
Typed ordinary-Lean roots for Gate 2 source/model/RV64 conformance.

The corpus covers every primitive in Core0 v0.1, every admitted conversion,
all four scalar result types, direct and cross-module calls, shared dependency
graphs, an empty-argument root, a ten-argument ABI call, and five explicitly
paired source-preserving metamorphic forms.
-/

namespace Lemma.Examples.Foundation.Conformance

/-! ### Empty-argument and Boolean roots -/

def constantU64 : UInt64 :=
  0x0123456789abcdef

def boolEq (x y : Bool) : Bool :=
  decide (x = y)

def boolSelect (condition : Bool) (onTrue onFalse : UInt64) : UInt64 :=
  if condition then onTrue else onFalse

/-! ### Exhaustive UInt8 primitive anchors -/

def u8Add (x y : UInt8) : UInt8 := x + y

def u8Sub (x y : UInt8) : UInt8 := x - y

def u8Mul (x y : UInt8) : UInt8 := x * y

def u8And (x y : UInt8) : UInt8 := x &&& y

def u8Or (x y : UInt8) : UInt8 := x ||| y

def u8Xor (x y : UInt8) : UInt8 := x ^^^ y

def u8Eq (x y : UInt8) : Bool := decide (x = y)

def u8Lt (x y : UInt8) : Bool := decide (x < y)

def u8Le (x y : UInt8) : Bool := decide (x ≤ y)

/-! ### UInt32 primitive coverage -/

def u32Arithmetic (x y z : UInt32) : UInt32 :=
  let sum := x + y
  let product := sum * z
  product - y

def u32Bits (x y z : UInt32) : UInt32 :=
  ((x &&& y) ||| z) ^^^ x

def u32Comparisons (x y z : UInt32) : UInt32 :=
  if x = y then 1 else if x < y then 2 else if x ≤ z then 3 else 4

/-! ### UInt64 primitive coverage -/

def u64Arithmetic (x y z : UInt64) : UInt64 :=
  let sum := x + y
  let product := sum * z
  product - y

def u64Bits (x y z : UInt64) : UInt64 :=
  ((x &&& y) ||| z) ^^^ x

def u64Comparisons (x y z : UInt64) : UInt64 :=
  if x = y then 1 else if x < y then 2 else if x ≤ z then 3 else 4

/-! ### Every admitted widening and truncation -/

def u8ToU32 (x : UInt8) : UInt32 := x.toUInt32

def u8ToU64 (x : UInt8) : UInt64 := x.toUInt64

def u32ToU8 (x : UInt32) : UInt8 := x.toUInt8

def u32ToU64 (x : UInt32) : UInt64 := x.toUInt64

def u64ToU8 (x : UInt64) : UInt8 := x.toUInt8

def u64ToU32 (x : UInt64) : UInt32 := x.toUInt32

/-! ### Calls, mixed-width signatures, shared dependencies, and ABI shape -/

def mixedWidthCall (gate : Bool) (byte : UInt8) (word : UInt32)
    (wide : UInt64) : UInt64 :=
  Support.mixedLeaf gate byte word wide

def sharedDiamond (x y : UInt64) : UInt64 :=
  let left := Support.sharedLeft x y
  let right := Support.sharedRight x y
  left + right

def abiNoInlineRoot
    (a0 : UInt64) (a1 : UInt8) (a2 : UInt32) (a3 : Bool)
    (a4 : UInt64) (a5 : UInt8) (a6 : UInt32) (a7 : Bool)
    (a8 : UInt8) (a9 : UInt32) : UInt64 :=
  Support.abiNoInlineCallee a0 a1 a2 a3 a4 a5 a6 a7 a8 a9

/-! ### Metamorphic pair 1: alpha-renaming -/

def metamorphicAlphaOriginal (x y : UInt64) : UInt64 :=
  let sum := x + y
  let mixed := sum ^^^ y
  mixed * 3

def metamorphicAlphaRenamed (left right : UInt64) : UInt64 :=
  let total := left + right
  let scrambled := total ^^^ right
  scrambled * 3

/-! ### Metamorphic pair 2: inline expression / extracted helper -/

def metamorphicInline (x y : UInt64) : UInt64 :=
  (x + y) ^^^ y

def metamorphicExtracted (x y : UInt64) : UInt64 :=
  Support.extractedStep x y

/-! ### Metamorphic pair 3: direct expression / equivalent let nesting -/

def metamorphicLetFlat (x y z : UInt64) : UInt64 :=
  ((x + y) ^^^ z) * 3

def metamorphicLetNested (x y z : UInt64) : UInt64 :=
  let sum := x + y
  let mixed := sum ^^^ z
  mixed * 3

/-!
Pairs 4 and 5 are the `metamorphicModule` roots in `MovedA`/`MovedB` and
the `metamorphicImport` roots in `ImportBase`/`ImportExtra`, respectively.
-/

end Lemma.Examples.Foundation.Conformance
