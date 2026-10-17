import Lemma.Platform.RiscV.Firmware

/-! Diagnostic wrapper records the actual M timer frame, then invokes the
unchanged compiled firmware policy. No supplied instruction/address selector. -/
namespace Lemma.Platform.RiscV.Development.WfiTimerFirmware
open Lemma.Core0.Memory
open Lemma.Platform.RiscV

def traceBase : UInt64 := 0x80101000
def write (address value : UInt64) : Action := Firmware.write address value
def read (address : UInt64) : Action := Firmware.read address

def timer (frame cause tval : UInt64) : Action :=
  .bind (read Firmware.irqCountAddress) fun s ordinal => if s = 0 then
  if ordinal < 4 then
  .bind (read (frame + 256)) fun s pc => if s = 0 then
  .bind (read (frame + 264)) fun s status => if s = 0 then
  .bind (read (frame + 272)) fun s enables => if s = 0 then
  .bind Firmware.time fun s now => if s = 0 then
  let row := traceBase + ordinal * 64
  .bind (write row cause) fun s _ => if s = 0 then
  .bind (write (row + 8) tval) fun s _ => if s = 0 then
  .bind (write (row + 16) pc) fun s _ => if s = 0 then
  .bind (write (row + 24) status) fun s _ => if s = 0 then
  .bind (write (row + 32) enables) fun s _ => if s = 0 then
  .bind (write (row + 40) now) fun s _ => if s = 0 then
  .bind (write (row + 48) ordinal) fun s _ => if s = 0 then
  .bind (Firmware.dispatch frame cause tval) fun s returned => if s = 0 then
  .bind Firmware.time fun s after => if s = 0 then
  .bind (write (row + 56) after) fun s _ => .done s returned
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done 48 0 else .done s 0

def dispatch (frame cause tval : UInt64) : Action :=
  if frame = Firmware.frameAddress then
    if cause = 0x8000000000000007 then timer frame cause tval
    else Firmware.dispatch frame cause tval
  else .done 48 0

end Lemma.Platform.RiscV.Development.WfiTimerFirmware
