import Lemma.User.CapabilityConsole

/-! A prior numeric handle is untrusted runtime input. The checked denial is
followed by an actual U store into the S-only alias of this task's cap header.
No syscall or successful exit can substitute for the architectural fault. -/
namespace Lemma.User.Development.CapabilitiesTamper
open Lemma.Core0.Memory
open Lemma.User

def main (oldHandle : UInt64) : Action :=
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind Syscall.identity fun s id => if s = 0 then
  .bind (Memory.write64 0x20000 oldHandle) fun s _ => if s = 0 then
  .bind (Capability.check oldHandle CapabilityABI.consoleType CapabilityABI.consoleWrite) fun status value =>
  .bind (CapabilityConsole.record console 0x160 id oldHandle status.toUInt64 value) fun s _ => if s = 0 then
  if status = CapabilityABI.invalidHandle then
    .bind (Memory.write64 0x31a00 oldHandle) fun s value => .done s value
  else .done 95 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

end Lemma.User.Development.CapabilitiesTamper
