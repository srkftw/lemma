import Lemma.Kernel.MachineServices

/-! Exact startup CSR observations for the separately named LemmaSim binding.
The legacy validator remains unchanged. S policy is non-nested with SIE clear;
SEIP is enabled and delegated for real PLIC delivery on entry to U. -/
namespace Lemma.Platform.LemmaSim.MachineServices

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

private def expected (i : UInt64) : UInt64 :=
  if i < 5 then Lemma.Kernel.MachineServices.expectedPmp i else
  if i = 5 then 0x030fffff else if i = 6 then 0x040005ff else 0x040043ff
private def pmpStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := if i < 5 then 0x80400020 + i.toUInt64 * 8
    else 0x80400068 + (i.toUInt64 - 5) * 8
  .bind (Access.read64 address) fun s value => if s = 0 then
  if value = expected i.toUInt64 then .done 0 acc else .done 51 0 else .done s 0

def validateFor (expectedInterrupts : UInt64) : Action :=
  .bind (Access.read64 0x80400018) fun s pmp => if s = 0 then
  if pmp = 0x1b1b1b1b1b1f1818 then
  .boundedFoldU64 8 pmpStep 8 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (Access.read64 0x80400048) fun s exceptions => if s = 0 then
  if exceptions = 0xb1ff then
  .bind (Access.read64 0x80400050) fun s interrupts => if s = 0 then
  if interrupts = expectedInterrupts then
  .bind (Access.read64 0x80400058) fun s status => if s = 0 then
  if status &&& 0x1baa = 0x800 then if (status >>> 32) &&& 15 = 10 then
  .bind (Access.read64 0x80400060) fun s translation => if s = 0 then
  if translation = 0 then
  .bind (Lemma.Kernel.MachineServices.call 3 0) fun s witness => if s = 0 then
  if witness = 0x534543414c4c0001 then .done 0 0 else .done 51 0
  else .done s 0 else .done 51 0 else .done s 0
  else .done 51 0 else .done 51 0 else .done s 0
  else .done 51 0 else .done s 0 else .done 51 0 else .done s 0
  else .done s 0 else .done 51 0 else .done s 0

def validate : Action := validateFor 0x1646
def validateSilicon : Action := validateFor 514

/-- The ninth PMP entry is an actual readback from the structured startup.
The old eight entries and machine-service witness retain their prior meaning. -/
def validateMultimodal : Action :=
  .bind validateSilicon fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 0x804e01f0) fun s address => if mmFailed s = true then .done s 0 else
  .bind (Access.read64 0x804e01f8) fun s configuration => if mmFailed s = true then .done s 0 else
  if mmDifferent address 0x040053ff = true then .done 51 0 else
  if mmDifferent configuration 0x1b = true then .done 51 0 else .done 0 0

end Lemma.Platform.LemmaSim.MachineServices
