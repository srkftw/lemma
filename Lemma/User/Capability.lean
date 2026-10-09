import Lemma.User.Syscall
import Lemma.User.CapabilityABI

/-! Shared managed-task wrappers. Results are actual checked supervisor
replies; the requested mask only attenuates authority already in this table. -/
namespace Lemma.User.Capability
open Lemma.Core0.Memory

def bootGrant (slot : UInt64) : Action := Syscall.call CapabilityABI.bootGrant slot 0 0 0 0
def info (handle : UInt64) : Action := Syscall.call CapabilityABI.info handle 0 0 0 0
def check (handle kind rights : UInt64) : Action :=
  Syscall.call CapabilityABI.check handle kind rights 0 0
def duplicate (handle rights : UInt64) : Action :=
  Syscall.call CapabilityABI.duplicate handle rights 0 0 0
def close (handle : UInt64) : Action := Syscall.call CapabilityABI.close handle 0 0 0 0
def revoke (handle : UInt64) : Action := Syscall.call CapabilityABI.revoke handle 0 0 0 0
def consoleWrite (handle pointer length : UInt64) : Action :=
  Syscall.call CapabilityABI.console handle 0 pointer length 0
def consoleRead (handle pointer length : UInt64) : Action :=
  Syscall.call CapabilityABI.console handle 1 pointer length 0
def createEndpoint (manager : UInt64) : Action :=
  Syscall.call CapabilityABI.createEndpoint manager 0 0 0 0
def transfer (manager source target rights : UInt64) : Action :=
  Syscall.call CapabilityABI.transfer manager source target rights 0
def scopedTarget (manager : UInt64) : Action := Syscall.call CapabilityABI.scopedTarget manager 0 0 0 0
def targetEntryCount (manager : UInt64) : Action := Syscall.call CapabilityABI.scopedTarget manager 1 0 0 0
def inspect (manager subject field : UInt64) : Action := Syscall.call CapabilityABI.inspect manager subject field 0 0

end Lemma.User.Capability
