import Lemma.Drivers.Power
import Lemma.Platform.Silicon.BindingSafety

/-! Power-v2 policy and checked MMIO driver. Existing Power-v1 remains exact;
watchdog enable is explicit. Timeout units are declared machine clocks. -/
namespace Lemma.Drivers.PowerSafety
open Lemma.Core0.Memory
open Lemma.Platform.Silicon
private def read (offset : UInt64) : Action := Power.read offset
private def write (offset value : UInt64) : Action := Power.write offset value
private def result : Action :=
  .bind (read 24) fun s fault => if s = 0 then
  if fault = 0 then .done 0 0 else if fault = 1 then .done Power.busy 0 else .done Power.invalid 0
  else .done s 0

def «initialize» : Action :=
  .bind (read 0) fun s magic => if s = 0 then
  .bind (read 8) fun s version => if s = 0 then
  if magic = BindingSafety.power_magic_value then if version = 2 then
  .bind Power.resetCause fun s cause => if s = 0 then
  if 1 ≤ cause then if cause ≤ 6 then .done 0 cause else .done Power.invalid 0 else .done Power.invalid 0
  else .done s 0 else .done Power.invalid 0 else .done Power.invalid 0 else .done s 0 else .done s 0

def remaining : Action := read BindingSafety.power_watchdog_remaining_offset
def resetEpoch : Action := read BindingSafety.power_reset_epoch_offset
def supplyStatus : Action := read BindingSafety.power_supply_status_offset
private def command (value : UInt64) : Action :=
  .bind «initialize» fun s _ => if s = 0 then
  .bind (write 88 1) fun s _ => if s = 0 then
  .bind (write BindingSafety.power_watchdog_command_offset value) fun s _ => if s = 0 then
  result else .done s 0 else .done s 0 else .done s 0

def arm (timeout : UInt64) : Action :=
  if 8 ≤ timeout then if timeout ≤ 0xffffffff then
  .bind «initialize» fun s _ => if s = 0 then
  .bind (write 88 1) fun s _ => if s = 0 then
  .bind (write BindingSafety.power_watchdog_timeout_offset timeout) fun s _ => if s = 0 then
  .bind result fun s _ => if s = 0 then command 1 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done Power.invalid 0 else .done Power.invalid 0

def heartbeat : Action := command 2
def disarm : Action := command 3
end Lemma.Drivers.PowerSafety
