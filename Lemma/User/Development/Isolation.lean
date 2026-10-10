import Lemma.User.Entry

/-! Quarantined U-mode isolation attempts. Each access is generated through the
ordinary checked user profile. Its address passes the compiler's virtual range
guard; the actual page-table privilege/permission check must reject it. The
normal user entry does not import this module. -/
namespace Lemma.User.Development.Isolation
open Lemma.Core0.Memory

def readMetadata : Action :=
  .platform .virtualRead64 0x30000 0 0 0 0 0 fun s v => .done s v

def writeText : Action :=
  .platform .virtualWrite64 0x10000 0 0 0 0 0 fun s v => .done s v

def readGuard : Action :=
  .platform .virtualRead64 0x3fffb000 0 0 0 0 0 fun s v => .done s v

def readForeign : Action :=
  .platform .virtualRead64 0x40000 0 0 0 0 0 fun s v => .done s v

def main (argument : UInt64) : Action :=
  if argument = 1 then readMetadata
  else if argument = 2 then writeText
  else if argument = 3 then readGuard
  else if argument = 4 then readForeign
  else Lemma.User.Entry.main argument

end Lemma.User.Development.Isolation
