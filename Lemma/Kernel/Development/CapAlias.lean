import Lemma.Kernel.Task

/-! Quarantined hardware authority probe. Only trusted development construction
can map a building task's own descriptor under an S-only RW/NX low alias. The
probe is not a production address-space API and is absent from normal roots.
The mapping and capability-header observation come from checked live ownership,
not a guessed metadata PFN. Inactive address-space destruction removes this
untracked supervisor alias before the descriptor frame is released. -/
namespace Lemma.Kernel.Development.CapAlias
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def aliasPage : UInt64 := 0x31000
def attackAddress : UInt64 := 0x31a00
def failed (s : UInt8) : Bool := if s = 0 then false else true
def fatal : Action := .done 50 0

private def checkedTable (base owner index : UInt64) : Action :=
  if (if index = 0 then true else if index = 7 then true else
      if index = 8 then true else false) = true then
    .bind (Access.read64 (base + AddressSpace.tableList + index * 8)) fun s handle =>
    if failed s = true then fatal else
    .bind (Frames.resolvePurpose owner handle 2) fun s physical =>
    if failed s = true then fatal else
    .bind (Frames.mappingCount owner handle) fun s pins =>
    if failed s = true then fatal else
    if pins = 1 then .done 0 physical else fatal
  else fatal

private def checkedHeader (base descriptor : UInt64) : Action :=
  .bind (Access.read64 (base + 2560)) fun s magic =>
  if failed s = true then fatal else
  if magic = 0x31504143414d454c then
  .bind (Access.read64 (base + 2568)) fun s version =>
  if failed s = true then fatal else
  if version = 1 then
  .bind (Access.read64 (base + 2576)) fun s self =>
  if failed s = true then fatal else
  if self = descriptor then
  .bind (Access.read64 (base + 2584)) fun s state =>
  if failed s = true then fatal else
  if state = 2 then
  .bind (Access.read64 (base + 2592)) fun s capacity =>
  if failed s = true then fatal else
  if capacity = 16 then .done 0 (base + 2560) else fatal
  else fatal else fatal else fatal else fatal

/-- Install and read back one exact S-only PTE for this building instance's
actual capability header. User store to attackAddress must fault on the U bit. -/
def install (descriptor : UInt64) : Action :=
  .bind (Task.prepared descriptor) fun s record =>
  if failed s = true then fatal else
  .bind (Access.read64 (record + Task.managedOffset)) fun s managed =>
  if failed s = true then fatal else
  if managed = 1 then
  .bind (AddressSpace.base descriptor) fun s base =>
  if failed s = true then fatal else
  .bind (checkedHeader base descriptor) fun s header =>
  if failed s = true then fatal else
  .bind (Frames.mappingCount 1 descriptor) fun s descriptorPins =>
  if failed s = true then fatal else
  if descriptorPins = 0 then
  .bind (AddressSpace.owner descriptor) fun s owner =>
  if failed s = true then fatal else
  .bind (AddressSpace.root descriptor) fun s root =>
  if failed s = true then fatal else
  .bind (Access.read64 AddressSpace.activeRoot) fun s active =>
  if failed s = true then fatal else
  if root = active then fatal else
  .bind (checkedTable base owner 0) fun s top =>
  if failed s = true then fatal else
  if top = root then
  .bind (checkedTable base owner 7) fun s middle =>
  if failed s = true then fatal else
  .bind (checkedTable base owner 8) fun s low =>
  if failed s = true then fatal else
  .bind (Access.read64 (top + AddressSpace.vpn2 aliasPage * 8)) fun s first =>
  if failed s = true then fatal else
  if first = AddressSpace.tableEntry middle then
  .bind (Access.read64 (middle + AddressSpace.vpn1 aliasPage * 8)) fun s second =>
  if failed s = true then fatal else
  if second = AddressSpace.tableEntry low then
  let slot := AddressSpace.tableSlot low aliasPage
  .bind (Access.read64 slot) fun s old =>
  if failed s = true then fatal else
  if old = 0 then
  let wanted := (base >>> 12) <<< 10 ||| 0xc7
  .bind (Access.write64 slot wanted) fun s _ =>
  if failed s = true then fatal else
  .bind (Access.read64 slot) fun s actual =>
  if failed s = true then fatal else
  if actual = wanted then
    .bind AddressSpace.flushCurrent fun s _ =>
    if failed s = true then fatal else
    .bind (Lemma.Kernel.Console.record 0xb2 descriptor header actual attackAddress) fun s _ =>
    if failed s = true then fatal else .done 0 descriptor
  else fatal else fatal else fatal else fatal else fatal else fatal else fatal

end Lemma.Kernel.Development.CapAlias
