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

/- Public syscall results. Status 255 is reserved for a kernel invariant
failure and must never describe an ordinary invalid user request. -/
def success : UInt8 := 0
def noByte : UInt8 := 12
def invalidArgument : UInt8 := 16
def unsupported : UInt8 := 17
def invalidDeadline : UInt8 := 22
def invalidMemory : UInt8 := 33
def quotaExceeded : UInt8 := 38
def invalidRange : UInt8 := 71
def permissionDenied : UInt8 := 72
def duplicateMapping : UInt8 := 73
def missingMapping : UInt8 := 74
def kernelFatal : UInt8 := 255
end Lemma.User.ABI
