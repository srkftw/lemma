import Lemma.Core0.Memory
import Lemma.User.ABI

/-! The only user syscall bridge. Its checked result is the actual a0 status
and a1 value returned by the supervisor; wrappers do not manufacture success. -/
namespace Lemma.User.Syscall
open Lemma.Core0.Memory

def call (number a0 a1 a2 a3 a4 : UInt64) : Action :=
  .platform .syscall number a0 a1 a2 a3 a4 fun s v => .done s v

def identity : Action := call ABI.identity 0 0 0 0 0
def consoleWrite (pointer length : UInt64) : Action :=
  call ABI.console 0 pointer length 0 0
def consoleRead (pointer length : UInt64) : Action :=
  call ABI.console 1 pointer length 0 0
def yield : Action := call ABI.yield 0 0 0 0 0
def sleep (ticks : UInt64) : Action := call ABI.sleep ticks 0 0 0 0
def time : Action := call ABI.time 0 0 0 0 0
def exit (code : UInt64) : Action := call ABI.exit code 0 0 0 0
def allocatePage (va : UInt64) : Action := call ABI.allocatePages va 1 0 0 0
def releasePage (va : UInt64) : Action := call ABI.releasePages va 1 0 0 0

end Lemma.User.Syscall
