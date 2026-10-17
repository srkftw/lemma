import Lemma.Boot.DevelopmentRecovery
import Lemma.Drivers.PowerSafety

/-! Version1 trial-only boot supervision. The existing authenticated selection,
attempt barriers and recovery protocol are reused unchanged. A newly selected
trial gets20s at100MHz after validation/loading; confirmed fallback is unarmed.
Only a matching new kernel health policy may disarm after durable confirmation.
This is public-development-key policy, not production identity or antirollback.
-/
namespace Lemma.Boot.TrialWatchdog
open Lemma.Core0.Memory
open Lemma.Kernel.Memory.Access

def policyMagic : UInt64 := 0x31574454414d454c
def contextPolicy : UInt64 := ProductExecuted.scratch + 48
def contextTimeout : UInt64 := ProductExecuted.scratch + 56
def timeoutClocks : UInt64 := 2000000000
def invalidContext : UInt8 := 241

private def clearPolicy : Action :=
  .bind (write64 contextPolicy 0) fun s _ => if s = 0 then
  write64 contextTimeout 0 else .done s 0

private def armTrial : Action :=
  .bind (read64 ProductExecuted.scratch) fun s magic => if s = 0 then
  .bind (read64 (ProductExecuted.scratch + 8)) fun s version => if s = 0 then
  .bind (read64 (ProductExecuted.scratch + 40)) fun s trial => if s = 0 then
  if magic = ProductExecuted.contextMagic then if version = 1 then
  if trial = 0 then .done 0 0 else if trial = 1 then
    .bind (write64 contextPolicy policyMagic) fun s _ => if s = 0 then
    .bind (write64 contextTimeout timeoutClocks) fun s _ => if s = 0 then
    Lemma.Drivers.PowerSafety.arm timeoutClocks else .done s 0 else .done s 0
  else .done invalidContext 0
  else .done invalidContext 0 else .done invalidContext 0
  else .done s 0 else .done s 0 else .done s 0

def entry : Action :=
  .bind clearPolicy fun s _ => if s = 0 then
  .bind DevelopmentRecovery.entry fun s entry => if s = 0 then
  .bind armTrial fun s _ => if s = 0 then .done 0 entry else .done s 0
  else .done s 0 else .done s 0

end Lemma.Boot.TrialWatchdog
