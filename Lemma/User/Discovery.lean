import Lemma.User.Syscall

/-! Ordinary capability-checked discovery. Every result comes from syscall26;
these wrappers grant no task-management or service-restart authority. -/
namespace Lemma.User.Discovery
open Lemma.Core0.Memory

def number : UInt64 := 26
def endpoint (directory : UInt64) : Action := Syscall.call number directory 0 1 0 0
def epoch (directory : UInt64) : Action := Syscall.call number directory 1 1 0 0
def instances (directory : UInt64) : Action := Syscall.call number directory 2 0 0 0
def frames (directory : UInt64) : Action := Syscall.call number directory 3 0 0 0

end Lemma.User.Discovery
