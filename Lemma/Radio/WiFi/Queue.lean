import Lemma.Radio.WiFi.Controller

/-! Kernel-owned four-slot CommonOFDM packet queue. Queue/RX policy is Lean;
RTL alone performs the actual DATA coding/sample work. Completion is an IRQ
observation, distinct from enqueue or submit. Failed mutations quarantine state. -/
namespace Lemma.Radio.WiFi.Queue
open Lemma.Core0.Memory Lemma.Kernel.Memory

def state : UInt64 := 0x804e0000
def magic : UInt64 := 0x3151455546495751
def full : UInt8 := 210
def quarantined : UInt8 := 211
def read (offset : UInt64) : Action := Access.read64 (state+offset)
def write (offset value : UInt64) : Action := Access.write64 (state+offset) value
def slot (index : UInt64) : UInt64 := 64+(index%4)*40

def valid : Action :=
 .bind (read 56) fun s m => if s = 0 then
 .bind (read 48) fun s poison => if s = 0 then
 .bind (read 0) fun s head => if s = 0 then
 .bind (read 8) fun s count => if s = 0 then
 .bind (read 16) fun s active => if s = 0 then
 if m = magic then if poison = 0 then if head < 4 then if count ≤ 4 then if active ≤ 1 then
 if active = 1 then if 0 < count then .done 0 count else .done quarantined 0
 else .done 0 count
 else .done quarantined 0 else .done quarantined 0 else .done quarantined 0
 else .done quarantined 0 else .done quarantined 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def clearStep (index _count : UInt32) (_ _ _ _ _ : UInt64) : Action :=
 .bind (write (index.toUInt64*8) 0) fun s _ => .done s 0

/-- Boot-only initialization. A recognized nonempty/active/quarantined queue
cannot be erased and lose its retained ownership pins. -/
def «initialize» : Action :=
 .bind (read 56) fun s m => if s = 0 then
 .bind (if m = 0 then .done 0 0 else valid) fun s count => if s = 0 then
 if count = 0 then
 .boundedFoldU64 64 clearStep 64 0 0 0 0 0 fun s _ => if s = 0 then write 56 magic
 else .done s 0
 else .done Controller.busy 0 else .done s 0 else .done s 0

private def poison (status : UInt8) : Action :=
 .bind (write 48 1) fun _ _ => .done status 0

private def install (position owner handle offset length seed : UInt64) : Action :=
 .bind (write position owner) fun s _ => if s = 0 then
 .bind (write (position+8) handle) fun s _ => if s = 0 then
 .bind (write (position+16) offset) fun s _ => if s = 0 then
 .bind (write (position+24) length) fun s _ => if s = 0 then
 write (position+32) seed else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Ownership transfers to this trusted queue only on successful commit.
No User owner is admitted; live purpose/generation and an initial zero pin count
are validated before the retained queue pin and entry are installed. -/
def enqueue (owner handle offset length seed : UInt64) : Action :=
 if owner = Frames.kernelOwner then if Controller.descriptorValid offset length seed = true then
 .bind valid fun s count => if s = 0 then
 if count < 4 then
 .bind (Frames.resolvePurpose owner handle Frames.dataPurpose) fun s _ => if s = 0 then
 .bind (Frames.mappingCount owner handle) fun s pins => if s = 0 then
 if pins = 0 then
 .bind (read 0) fun s head => if s = 0 then
 .bind (Frames.pin owner handle) fun s _ => if s = 0 then
 .bind (install (slot (head+count)) owner handle offset length seed) fun s _ => if s = 0 then
 .bind (write 8 (count+1)) fun s _ => if s = 0 then .done 0 handle else poison s
 else poison s else .done s 0 else .done s 0
 else .done Controller.busy 0 else .done s 0 else .done s 0
 else .done full 0 else .done s 0 else .done Controller.invalid 0 else .done Controller.invalid 0

def kick (base : UInt64) : Action :=
 .bind valid fun s count => if s = 0 then
 if count = 0 then .done 0 0 else
 .bind (read 16) fun s active => if s = 0 then
 if active = 1 then .done 0 1 else
 .bind (read 0) fun s head => if s = 0 then
 let position := slot head
 .bind (read position) fun s owner => if s = 0 then
 .bind (read (position+8)) fun s handle => if s = 0 then
 .bind (read (position+16)) fun s offset => if s = 0 then
 .bind (read (position+24)) fun s length => if s = 0 then
 .bind (read (position+32)) fun s seed => if s = 0 then
 .bind (Controller.submitPinned base owner handle offset length seed) fun s _ => if s = 0 then
 .bind (write 16 1) fun s _ => if s = 0 then .done 0 handle else poison s
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def finish (owner handle head count : UInt64) : Action :=
 .bind (Frames.unpin owner handle) fun s _ => if s = 0 then
 .bind (write 8 (count-1)) fun s _ => if s = 0 then
 .bind (write 0 ((head+1)%4)) fun s _ => if s = 0 then
 .bind (write 16 0) fun s _ => if s = 0 then
 .bind (read 24) fun s completed => if s = 0 then
 .bind (write 24 (completed+1)) fun s _ => if s = 0 then .done 0 handle else poison s
 else poison s else poison s else poison s else poison s else .done s 0

/-- A caller holding real PLIC source18 may complete only the actually active
head after TXevent1 and inactive hardware TX. Clear/completion of the PLIC is
outside this routine and follows successful buffer/queue publication. -/
def complete (base : UInt64) : Action :=
 .bind valid fun s count => if s = 0 then
 if 0 < count then
 .bind (read 16) fun s active => if s = 0 then
 if active = 1 then
 .bind (Controller.events base) fun s events => if s = 0 then
 if events &&& (1 : UInt64) = 1 then
 .bind (Controller.read base 16) fun s hardware => if s = 0 then
 if hardware &&& (1 : UInt64) = 0 then
 .bind (read 0) fun s head => if s = 0 then
 .bind (read (slot head)) fun s owner => if s = 0 then
 .bind (read (slot head+8)) fun s handle => if s = 0 then
 finish owner handle head count
 else .done s 0 else .done s 0 else .done s 0
 else .done Controller.busy 0 else .done s 0
 else .done Controller.busy 0 else .done s 0
 else .done Controller.busy 0 else .done s 0
 else .done Controller.busy 0 else .done s 0
end Lemma.Radio.WiFi.Queue
