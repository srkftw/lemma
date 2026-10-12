import Lemma.User.Syscall

/-! Named power endpoint operations. Handles confer authority only when the
kernel resolves the exact boot-granted endpoint; an arbitrary handle is denied. -/
namespace Lemma.User.Power
open Lemma.Core0.Memory
def state (handle : UInt64) : Action := Syscall.call 68 handle 0 0 0 0
def suspend (handle : UInt64) : Action := Syscall.call 68 handle 1 0 0 0
def resume (handle : UInt64) : Action := Syscall.call 68 handle 2 0 0 0
def resetCause (handle : UInt64) : Action := Syscall.call 68 handle 3 0 0 0
end Lemma.User.Power
