import Lemma.Platform.LemmaSim.IO
import Lemma.Platform.Silicon.BindingPower

/-! Power-v1 register driver. Hardware owns admission, button epochs and wake
causes; guest policy decides whether to dispatch tasks. No storage barrier is
implicit in either command. -/
namespace Lemma.Drivers.Power
open Lemma.Core0.Memory
open Lemma.Platform.Silicon

def busy : UInt8 := 196
def invalid : UInt8 := 197
def read (offset : UInt64) : Action :=
  Lemma.Platform.LemmaSim.IO.read64 (BindingPower.power_base + offset)
def write (offset value : UInt64) : Action :=
  Lemma.Platform.LemmaSim.IO.write64 (BindingPower.power_base + offset) value
def state : Action := read BindingPower.power_state_offset
def events : Action := read BindingPower.power_events_offset
def epoch : Action := read BindingPower.power_epoch_offset
def resetCause : Action := read BindingPower.power_reset_cause_offset
def buttonLevel : Action := read BindingPower.power_button_level_offset
def wakeCause : Action := read BindingPower.power_wake_cause_offset
def ack (mask : UInt64) : Action :=
  if mask ≤ 3 then write BindingPower.power_ack_offset mask else .done invalid 0

def «initialize» : Action :=
  .bind (read BindingPower.power_magic_offset) fun s magic => if s = 0 then
  .bind (read BindingPower.power_version_offset) fun s version => if s = 0 then
  if magic = BindingPower.power_magic_value then if version = 1 then
  .bind resetCause fun s cause => if s = 0 then
  if 1 ≤ cause then if cause ≤ 3 then .done 0 cause else .done invalid 0 else .done invalid 0
  else .done s 0 else .done invalid 0 else .done invalid 0 else .done s 0 else .done s 0

def command (value : UInt64) : Action :=
  if (if value = 1 then true else if value = 2 then true else false) = true then
  .bind (write BindingPower.power_clear_error_offset 1) fun s _ => if s = 0 then
  .bind (write BindingPower.power_command_offset value) fun s _ => if s = 0 then
  .bind (read BindingPower.power_error_offset) fun s fault => if s = 0 then
  if fault = 0 then state else if fault = 1 then .done busy 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done invalid 0

end Lemma.Drivers.Power
