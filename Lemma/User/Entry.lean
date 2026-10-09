import Lemma.Core0.Memory
import Lemma.User.ABI

/-! Independently compiled initial user entry. Gate A establishes build
separation; entering this code with U privilege is a later, separately tested gate. -/
namespace Lemma.User.Entry
open Lemma.Core0.Memory

def mix (x : UInt64) : UInt64 := (x ^^^ 0x4c454d4d41) * 17 + 3
def read (address : UInt64) : Action :=
  .platform .virtualRead64 address 0 0 0 0 0 fun s v => .done s v
def write (address value : UInt64) : Action :=
  .platform .virtualWrite64 address value 0 0 0 0 fun s v => .done s v

/-- A separately linked user entry receives an ordinary scalar boot argument.
It checks the copied initial ABI word and independently zeroed BSS, then stores
its computed result in its own data page for the caller to inspect after exit. -/
def main (argument : UInt64) : Action :=
  .bind (read 0x20000) fun s initial =>
  if s = 0 then
    if initial = 0 then
      .bind (read 0x20008) fun s version =>
      if s = 0 then
        if version = Lemma.User.ABI.version then
          .bind (read 0x20010) fun s bss =>
          if s = 0 then
            if bss = 0 then
              .bind (write 0x20000 (mix argument)) fun s _ =>
              if s = 0 then read 0x20000 else .done s 0
            else .done 43 0
          else .done s 0
        else .done 43 0
      else .done s 0
    else .done 43 0
  else .done s 0

end Lemma.User.Entry
