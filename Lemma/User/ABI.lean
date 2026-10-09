/-! Version 1 syscall numbers. Function calls and ECALL transports have different
register conventions: a7 number, a0..a4 arguments, a0 status/a1 value on return.
The machine boundary declares the normal LP64 clobbers and preserves all other
interrupted registers. Pointer arguments never grant authority. -/
namespace Lemma.User.ABI
def version : UInt64 := 1
def identity : UInt64 := 1
def console : UInt64 := 2
def yield : UInt64 := 3
def sleep : UInt64 := 4
def time : UInt64 := 5
def exit : UInt64 := 6
def exitNumber : Nat := exit.toNat
def allocatePages : UInt64 := 7
def releasePages : UInt64 := 8
end Lemma.User.ABI
