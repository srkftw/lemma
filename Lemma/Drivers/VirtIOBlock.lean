import Lemma.Platform.LemmaSim.IO
import Lemma.Kernel.Memory.Frames

/-! Modern VirtIO-MMIO, one split queue, one outstanding sector operation.
Only one live kernel-owned frame supplies every DMA address. Its lifetime is
independent of requesting tasks. Completion or successful reset is required
before reuse. No notebook format or client-supplied physical address appears.

The driver is asynchronous: submit returns pending; finish is invoked after
notification. Neither function spins or waits for host I/O. Flush completion is
an operation result; the document service decides transaction acknowledgement.
-/
namespace Lemma.Drivers.VirtIOBlock
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def mmio : UInt64 := 0x10001000
def state : UInt64 := 0x80400a00
-- context words: handle, base, capacity, avail, used, pending, readonly, poisoned
private def get (offset : UInt64) : Action := Access.read64 (state + offset)
private def put (offset value : UInt64) : Action := Access.write64 (state + offset) value
private def reg (offset : UInt64) : Action := Lemma.Platform.LemmaSim.IO.read32 (mmio + offset)
private def set (offset value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write32 (mmio + offset) value

def unavailable : UInt8 := 160
def unsupported : UInt8 := 161
def busy : UInt8 := 162
def invalidRequest : UInt8 := 163
def ioError : UInt8 := 164
def corruptCompletion : UInt8 := 165
def readOnly : UInt8 := 166
def poisoned : UInt8 := 167
def pending : UInt8 := 168

def failed (s : UInt8) : Bool := if s = 0 then false else true

private def write16 (address value : UInt64) : Action :=
  .bind (Access.write8 address (value &&& 255)) fun s _ =>
  if s = 0 then Access.write8 (address + 1) ((value >>> 8) &&& 255) else .done s 0
private def read16 (address : UInt64) : Action :=
  .bind (Access.read8 address) fun s lo =>
  if s = 0 then .bind (Access.read8 (address + 1)) fun s hi =>
  if s = 0 then .done 0 (lo ||| (hi <<< 8)) else .done s 0 else .done s 0

/-- Descriptor length/flags/next are little-endian fields packed into word1.
Queue addresses fit the binding's RAM, hence the high MMIO words are zero. -/
private def descriptor (base index address length flags next : UInt64) : Action :=
  .bind (Access.write64 (base + index * 16) address) fun s _ =>
  if s = 0 then Access.write64 (base + index * 16 + 8)
    (length ||| (flags <<< 32) ||| (next <<< 48)) else .done s 0

private def initializeQueue (handle base capacity ro : UInt64) : Action :=
  .bind (put 0 handle) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 8 base) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 16 capacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 24 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 32 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 40 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 48 ro) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 56 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x38 8) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x80 base) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x84 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x90 (base + 128)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x94 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0xa0 (base + 256)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0xa4 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x44 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x70 15) fun s _ =>
  if failed s = true then .done s 0 else .done 0 capacity

private def allocateQueue (capacity ro : UInt64) : Action :=
  .bind (get 0) fun s previous => if s = 0 then
  .bind (if previous = 0 then Frames.allocate 1 1 else .done 0 previous) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s base =>
  if failed s = true then .done s 0 else
  -- initialize/reset has observed status0 before any old ring is cleared.
  .bind (Frames.zero base) fun s _ => if s = 0 then
  initializeQueue handle base capacity ro else .done s 0 else .done s 0

private def capacityStable (ro : UInt64) : Action :=
  .bind (reg 0xfc) fun s before =>
  if failed s = true then .done s 0 else
  .bind (reg 0x100) fun s low =>
  if failed s = true then .done s 0 else
  .bind (reg 0x104) fun s high =>
  if failed s = true then .done s 0 else
  .bind (reg 0xfc) fun s after =>
  if failed s = true then .done s 0 else
  if before = after then
    let capacity := low ||| (high <<< 32)
    if 8 < capacity then allocateQueue capacity ro else .done unsupported 0
  else .done busy 0

private def features : Action :=
  .bind (set 0x14 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (reg 0x10) fun s high =>
  if failed s = true then .done s 0 else
  if high &&& 1 = 0 then .done unsupported 0 else
  .bind (set 0x14 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (reg 0x10) fun s low =>
  if failed s = true then .done s 0 else
  if low &&& 512 = 0 then .done unsupported 0 else
  let ro := (low >>> 5) &&& 1
  .bind (set 0x24 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x20 ((512 : UInt64) ||| (ro <<< 5))) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x24 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x20 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x70 11) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (reg 0x70) fun s status =>
  if failed s = true then .done s 0 else
  if status = 11 then
    .bind (set 0x30 0) fun s _ =>
    if failed s = true then .done s 0 else
    .bind (reg 0x34) fun s maximum =>
    if failed s = true then .done s 0 else
    if 8 ≤ maximum then capacityStable ro else .done unsupported 0
  else .done unsupported 0

/-- Reset completion must be observed before allocating/publishing DMA memory.
An absent/legacy/nonblock transport is rejected. Optional offered features are
left unnegotiated; VERSION_1 and FLUSH are mandatory for this driver contract. -/
def «initialize» : Action :=
  .bind (reg 0) fun s magic =>
  if failed s = true then .done s 0 else
  if magic = 0x74726976 then
  .bind (reg 4) fun s version =>
  if failed s = true then .done s 0 else
  if version = 2 then
  .bind (reg 8) fun s device =>
  if failed s = true then .done s 0 else
  if device = 2 then
  .bind (set 0x70 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (reg 0x70) fun s status =>
  if failed s = true then .done s 0 else
  if status = 0 then
  .bind (set 0x70 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x70 3) fun s _ =>
  if failed s = true then .done s 0 else features
  else .done busy 0 else .done unavailable 0 else .done unsupported 0 else .done unavailable 0

/-- Kernel-owned bounce buffer, never a caller-nominated DMA pointer. The caller
must copy authorized data into it before submit and out only after finish. -/
def bounce : Action :=
  .bind (get 56) fun s poison => if s = 0 then
  if poison = 0 then
  .bind (get 40) fun s outstanding => if s = 0 then
  if outstanding = 0 then
  .bind (get 0) fun s handle => if s = 0 then
  .bind (Frames.resolvePurpose 1 handle 1) fun s owned => if s = 0 then
  .bind (get 8) fun s base => if s = 0 then
  if owned = base then .done 0 (base + 0x600) else .done corruptCompletion 0
  else .done s 0 else .done s 0 else .done s 0
  else .done busy 0 else .done s 0
  else .done poisoned 0 else .done s 0

def capacity : Action := get 16

private def publish (base kind sector : UInt64) : Action :=
  .bind (Access.write64 (base + 0x400) kind) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write64 (base + 0x408) sector) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Access.write8 (base + 0x800) 255) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (descriptor base 0 (base + 0x400) 16 1 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (if kind = 4 then descriptor base 1 (base + 0x800) 1 2 0 else
    descriptor base 1 (base + 0x600) 512 (if kind = 0 then 3 else 1) 2) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (descriptor base 2 (base + 0x800) 1 2 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (get 24) fun s index =>
  if failed s = true then .done s 0 else
  .bind (write16 (base + 132 + (index % 8) * 2) 0) fun s _ =>
  if failed s = true then .done s 0 else
  let next := (index + 1) &&& 65535
  .bind (put 40 (kind + 1)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write16 (base + 130) next) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put 24 next) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (set 0x50 0) fun s _ =>
  if failed s = true then .done s 0 else .done 0 next

/-- kind 0 read, 1 write, 4 flush. At most one outstanding request; wrapping
16-bit indices does not release the chain before validated completion. -/
private def requireLive : Action :=
  .bind (reg 0x70) fun s status => if s = 0 then
  if status = 15 then .done 0 0 else
  .bind (put 56 1) fun s _ => if s = 0 then .done poisoned 0 else .done s 0
  else .done s 0

/-- Request and observe transport reset before clearing/reusing a DMA ring.
No frame is released: failure to quiesce leaves it quarantined. Reinitialization
negotiates features again and reuses this retained owned frame. -/
def quiesce : Action :=
  .bind (put 56 1) fun s _ => if s = 0 then
  .bind (set 0x70 0) fun s _ => if s = 0 then
  .bind (reg 0x70) fun s status => if s = 0 then
  if status = 0 then
  .bind (put 40 0) fun s _ => if s = 0 then .done 0 0 else .done s 0
  else .done busy 0 else .done s 0 else .done s 0 else .done s 0

def submit (kind sector : UInt64) : Action :=
  if (if kind = 0 then true else if kind = 1 then true else if kind = 4 then true else false) = false then
    .done invalidRequest 0 else
  .bind requireLive fun s _ => if s = 0 then
  .bind (get 56) fun s poison =>
  if failed s = true then .done s 0 else
  if poison = 0 then
  .bind (get 40) fun s outstanding =>
  if failed s = true then .done s 0 else
  if outstanding = 0 then
  .bind (get 48) fun s ro =>
  if failed s = true then .done s 0 else
  if kind = 1 then if ro = 1 then .done readOnly 0 else submitWritable kind sector
  else submitWritable kind sector
  else .done busy 0 else .done poisoned 0 else .done s 0
where
  submitWritable (kind sector : UInt64) : Action :=
    .bind capacity fun s sectors =>
    if failed s = true then .done s 0 else
    if kind = 4 then
      .bind (get 8) fun s base => if s = 0 then publish base kind 0 else .done s 0
    else if sector < sectors then
      .bind (get 8) fun s base => if s = 0 then publish base kind sector else .done s 0
    else .done invalidRequest 0

private def corrupt : Action :=
  .bind (put 56 1) fun s _ => if s = 0 then .done corruptCompletion 0 else .done s 0

private def usedByte (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Access.read8 (address + i.toUInt64)) fun s byte =>
  if s = 0 then .done 0 (acc ||| (byte <<< (i.toUInt64 * 8))) else .done s 0
private def readUsed (address : UInt64) : Action :=
  .boundedFoldU64 8 usedByte 8 0 address 0 0 0 fun s word => .done s word

private def complete (base index request : UInt64) : Action :=
  .bind (readUsed (base + 260 + (index % 8) * 8)) fun s entry =>
  if failed s = true then .done s 0 else
  let expectedLength := if request = 1 then 513 else 1
  if entry &&& 0xffffffff = 0 then
  if entry >>> 32 = expectedLength then
  .bind (Access.read8 (base + 0x800)) fun s result =>
  if failed s = true then .done s 0 else
  if result ≤ 2 then
    .bind (put 32 ((index + 1) &&& 65535)) fun s _ =>
    if failed s = true then .done s 0 else
    .bind (put 40 0) fun s _ =>
    if failed s = true then .done s 0 else
    if result = 0 then .done 0 request else if result = 1 then .done ioError request
    else .done unsupported request
  else corrupt else corrupt else corrupt

/-- Acknowledge the actual transport interrupt, then inspect exactly one used
entry. Bad IDs, lengths, indices or sentinel status quarantine the DMA frame.
The used element is only4-byte aligned: its two u32 fields are read as bytes.
The actual read below is assembled by readUsed to avoid a misaligned64 load. -/
def finish : Action :=
  .bind requireLive fun s _ => if s = 0 then
  .bind (reg 0x60) fun s irq =>
  if failed s = true then .done s 0 else
  .bind (set 0x64 (irq &&& 3)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (get 56) fun s poison =>
  if failed s = true then .done s 0 else
  if poison = 0 then
  .bind (get 40) fun s request =>
  if failed s = true then .done s 0 else
  if request = 0 then .done invalidRequest 0 else
  .bind (get 8) fun s base =>
  if failed s = true then .done s 0 else
  .bind (get 32) fun s index =>
  if failed s = true then .done s 0 else
  .bind (read16 (base + 258)) fun s used =>
  if failed s = true then .done s 0 else
  if used = index then .done pending 0 else
  if used = ((index + 1) &&& 65535) then complete base index request else corrupt
  else .done poisoned 0 else .done s 0

end Lemma.Drivers.VirtIOBlock
