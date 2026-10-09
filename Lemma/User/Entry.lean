import Lemma.Core0.Memory

/-! Independently compiled initial user entry. Gate A establishes build
separation; entering this code with U privilege is a later, separately tested gate. -/
namespace Lemma.User.Entry
open Lemma.Core0.Memory

def mix (x : UInt64) : UInt64 := (x ^^^ 0x4c454d4d41) * 17 + 3
def main : Action := .done 0 (mix 7)

end Lemma.User.Entry
