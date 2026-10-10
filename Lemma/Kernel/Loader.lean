import Lemma.Kernel.Memory.AddressSpace

/-! Guest boot-package loading for the declared fixed user virtual profile.
Validation precedes allocation. Every copied byte and every owned mapping is
constructed by compiled Lean; no host-chosen frame or installed table is used.
The descriptor's private loader state is reserved at +2400..+2559.
-/
namespace Lemma.Kernel.Loader
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def packageBase : UInt64 := 0x80600000
def packageBytes : UInt64 := 0x100000
def packageMagic : UInt64 := 0x31474b50414d454c
def invalidPackage : UInt8 := 80
def invalidImage : UInt8 := 81
def duplicateImage : UInt8 := 82
def invalidBounds : UInt8 := 83
def invariantFailure : UInt8 := 84
def kernelStackHandleOffset : UInt64 := 2400
def kernelStackTopOffset : UInt64 := 2408
def kernelStackSecondHandleOffset : UInt64 := 2480
def kernelStackThirdHandleOffset : UInt64 := 2488
def kernelStackFourthHandleOffset : UInt64 := 2496
def kernelStackPagesOffset : UInt64 := 2504
def kernelStackBaseOffset : UInt64 := 2512
def entryOffset : UInt64 := 2416
def textBytesOffset : UInt64 := 2424
def exitCodeOffset : UInt64 := 2432
def outcomeCauseOffset : UInt64 := 2440
def argumentOffset : UInt64 := 2448
def imageIdOffset : UInt64 := 2456
def imageIndexOffset : UInt64 := 2464
def readyOffset : UInt64 := 2472
def failed (status : UInt8) : Bool := if status = 0 then false else true
private def get (address slot : UInt64) : Action := Access.read64 (address + slot)
private def put (address slot value : UInt64) : Action := Access.write64 (address + slot) value

/-- Subtraction bounds avoid accepting wrapped offset+length values. -/
def fileRange (offset length header total : UInt64) : Bool :=
  if header ≤ offset then
    if offset ≤ total then if length ≤ total - offset then true else false else false
  else false
def disjoint (a lengthA b lengthB : UInt64) : Bool :=
  if lengthA = 0 then true else if lengthB = 0 then true else
  if a + lengthA ≤ b then true else if b + lengthB ≤ a then true else false
def entryValid (entry textBytes : UInt64) : Bool :=
  if 4 ≤ textBytes then
    if textBytes ≤ 0xf000 then
      if 0x10000 ≤ entry then
        if entry - 0x10000 ≤ textBytes - 4 then
          if entry % 4 = 0 then true else false
        else false
      else false
    else false
  else false

private def validateDescriptor (record header total : UInt64) : Action :=
  .bind (get record 0) fun s id => if failed s = true then .done s 0 else
  if id = 0 then .done invalidImage 0 else
  .bind (get record 8) fun s entry => if failed s = true then .done s 0 else
  .bind (get record 16) fun s textVA => if failed s = true then .done s 0 else
  .bind Frames.runtimeCount fun s frameCount => if failed s = true then .done s 0 else
  let textBase := if frameCount = 8192 then 0x1000000 else 0x10000
  let textCapacity := if frameCount = 8192 then 0x80000 else 0xf000
  if (if textVA = textBase then false else true) = true then .done invalidImage 0 else
  .bind (get record 24) fun s textOffset => if failed s = true then .done s 0 else
  .bind (get record 32) fun s textBytes => if failed s = true then .done s 0 else
  if textBytes < 4 then .done invalidImage 0 else
  if textCapacity < textBytes then .done invalidImage 0 else
  if entry < textBase then .done invalidImage 0 else
  if textBytes - 4 < entry - textBase then .done invalidImage 0 else
  if (if entry % 4 = 0 then false else true) = true then .done invalidImage 0 else
  if fileRange textOffset textBytes header total = false then .done invalidBounds 0 else
  .bind (get record 40) fun s dataVA => if failed s = true then .done s 0 else
  if (if dataVA = 0x20000 then false else true) = true then .done invalidImage 0 else
  .bind (get record 48) fun s dataOffset => if failed s = true then .done s 0 else
  .bind (get record 56) fun s dataFileBytes => if failed s = true then .done s 0 else
  .bind (get record 64) fun s dataMemoryBytes => if failed s = true then .done s 0 else
  if (if dataMemoryBytes = 4096 then false else true) = true then .done invalidImage 0 else
  if 4096 < dataFileBytes then .done invalidBounds 0 else
  if fileRange dataOffset dataFileBytes header total = false then .done invalidBounds 0 else
  if disjoint textOffset textBytes dataOffset dataFileBytes = false then .done invalidBounds 0 else
  -- Fixed virtual segment intervals are independently checked, including the
  -- last partial text page and the stack's two surrounding unmapped pages.
  if textCapacity < ((textBytes + 4095) / 4096) * 4096 then .done invalidBounds 0 else
  if disjoint textVA (((textBytes + 4095) / 4096) * 4096) dataVA dataMemoryBytes = false then .done invalidBounds 0 else
  if 0x3fffb000 < dataVA + dataMemoryBytes then .done invalidBounds 0 else
  .bind (get record 72) fun s stackVA => if failed s = true then .done s 0 else
  if (if stackVA = 0x3fffc000 then false else true) = true then .done invalidImage 0 else
  .bind (get record 80) fun s stackPages => if failed s = true then .done s 0 else
  if (if stackPages = 2 then false else true) = true then .done invalidImage 0 else
  .bind (get record 88) fun s flags => if failed s = true then .done s 0 else
  if flags = 0 then .done 0 record else .done invalidImage 0

/-- All descriptors are already range-validated when compared. Version 1 does
not permit payload sharing between image descriptors or duplicate image IDs. -/
private def priorStep (i _ : UInt32) (acc record storageBase _ _ : UInt64) : Action :=
  let previous := storageBase + 32 + i.toUInt64 * 96
  .bind (get record 0) fun s id => if failed s = true then .done s 0 else
  .bind (get previous 0) fun s oldId => if failed s = true then .done s 0 else
  if id = oldId then .done duplicateImage 0 else
  .bind (get record 24) fun s text => if failed s = true then .done s 0 else
  .bind (get record 32) fun s textBytes => if failed s = true then .done s 0 else
  .bind (get record 48) fun s data => if failed s = true then .done s 0 else
  .bind (get record 56) fun s dataBytes => if failed s = true then .done s 0 else
  .bind (get previous 24) fun s oldText => if failed s = true then .done s 0 else
  .bind (get previous 32) fun s oldTextBytes => if failed s = true then .done s 0 else
  .bind (get previous 48) fun s oldData => if failed s = true then .done s 0 else
  .bind (get previous 56) fun s oldDataBytes => if failed s = true then .done s 0 else
  if disjoint text textBytes oldText oldTextBytes = false then .done invalidBounds 0 else
  if disjoint text textBytes oldData oldDataBytes = false then .done invalidBounds 0 else
  if disjoint data dataBytes oldText oldTextBytes = false then .done invalidBounds 0 else
  if disjoint data dataBytes oldData oldDataBytes = false then .done invalidBounds 0 else
  .done 0 acc

private def descriptorStep (i _ : UInt32) (acc header total storageBase _ : UInt64) : Action :=
  let record := storageBase + 32 + i.toUInt64 * 96
  .bind (validateDescriptor record header total) fun s _ =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 8 priorStep i 0 record storageBase 0 0 fun s _ =>
  if failed s = true then .done s 0 else .done 0 (acc + 1)

/-- The only callers select either the fixed immutable boot-package region or
one revalidated owner-1 purpose-1 frame. No public raw-pointer parser is exposed.
Header extent and address overflow are checked before the first memory read. -/
private def validateView (storageBase storageBytes imageIndex : UInt64) : Action :=
  if storageBytes < 32 then .done invalidBounds 0 else
  if packageBytes < storageBytes then .done invalidBounds 0 else
  if 0xffffffffffffffff - storageBytes < storageBase then .done invalidBounds 0 else
  .bind (get storageBase 0) fun s magic => if failed s = true then .done s 0 else
  if (if magic = packageMagic then false else true) = true then .done invalidPackage 0 else
  .bind (get storageBase 8) fun s version => if failed s = true then .done s 0 else
  .bind Frames.runtimeCount fun s frameCount => if failed s = true then .done s 0 else
  let expectedVersion := if frameCount = 8192 then 2 else 1
  if (if version = expectedVersion then false else true) = true then .done invalidPackage 0 else
  .bind (get storageBase 16) fun s count => if failed s = true then .done s 0 else
  if count = 0 then .done invalidPackage 0 else
  if 8 < count then .done invalidPackage 0 else
  if count ≤ imageIndex then .done invalidImage 0 else
  .bind (get storageBase 24) fun s total => if failed s = true then .done s 0 else
  let header := 32 + count * 96
  if total < header then .done invalidBounds 0 else
  if storageBytes < total then .done invalidBounds 0 else
  .boundedFoldU64 8 descriptorStep count.toUInt32 0 header total storageBase 0 fun s checked =>
  if failed s = true then .done s 0 else
  if checked = count then .done 0 (storageBase + 32 + imageIndex * 96)
  else .done invariantFailure 0

/-- Success returns the selected immutable descriptor address. No frame is
allocated until the complete bounded package corpus and selection are valid. -/
def validate (imageIndex : UInt64) : Action :=
  validateView packageBase packageBytes imageIndex

/-- Validate the same package grammar inside an existing kernel-owned frame.
The handle is revalidated for owner, generation and purpose before reading.
This read-only API neither allocates nor executes the fixture's payload. -/
def validateFrame (kernelFrameHandle imageIndex : UInt64) : Action :=
  .bind (Frames.resolvePurpose 1 kernelFrameHandle 1) fun s storageBase =>
  if failed s = true then .done s 0 else
  validateView storageBase 4096 imageIndex

private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Access.read8 (source + i.toUInt64)) fun s byte =>
  if failed s = true then .done s 0 else
  .bind (Access.write8 (target + i.toUInt64) byte) fun s _ => .done s (acc + 1)
private def copy (source target amount : UInt64) : Action :=
  if amount ≤ 4096 then
    .boundedFoldU64 4096 copyStep amount.toUInt32 0 source target 0 0 fun s copied =>
    if failed s = true then .done s 0 else
    if copied = amount then .done 0 0 else .done invariantFailure 0
  else .done invalidBounds 0

private def releaseUnmapped (owner handle : UInt64) (original : UInt8) : Action :=
  .bind (Frames.release owner handle) fun s _ =>
  if s = 0 then .done original 0 else .done invariantFailure 0

/-- AS takes the mapping pin only on success. A failed provisional leaf is
released here, while AS removes any newly constructed bottom-level table. -/
private def page (descriptor owner va purpose permissions source amount : UInt64) : Action :=
  .bind (Frames.allocate owner purpose) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose owner handle purpose) fun s physical =>
  if failed s = true then releaseUnmapped owner handle s else
  .bind (copy source physical amount) fun s _ =>
  if failed s = true then releaseUnmapped owner handle s else
  .bind (AddressSpace.mapUser descriptor va handle permissions) fun s _ =>
  if failed s = true then releaseUnmapped owner handle s else .done 0 handle

private def textStep (i _ : UInt32) (acc descriptor owner record _ : UInt64) : Action :=
  .bind (get record 24) fun s textOffset => if failed s = true then .done s 0 else
  .bind (get record 32) fun s textBytes => if failed s = true then .done s 0 else
  let offset := i.toUInt64 * 4096
  let amount := if 4096 < textBytes - offset then 4096 else textBytes - offset
  .bind (get record 16) fun s textVA => if failed s = true then .done s 0 else
  .bind (page descriptor owner (textVA + offset) 3 5 (packageBase + textOffset + offset) amount) fun s _ =>
  if failed s = true then .done s 0 else .done 0 (acc + 1)
private def stackStep (i _ : UInt32) (acc descriptor owner _ _ : UInt64) : Action :=
  .bind (page descriptor owner (0x3fffc000 + i.toUInt64 * 4096) 5 3 0 0) fun s _ =>
  if failed s = true then .done s 0 else .done 0 (acc + 1)
private def clearContextStep (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (Access.write64 (context + i.toUInt64 * 8) 0) fun s _ => .done s (acc + 1)

private def initializeContext (descriptor address record argument : UInt64) : Action :=
  .bind (AddressSpace.context descriptor) fun s context => if failed s = true then .done s 0 else
  .boundedFoldU64 36 clearContextStep 36 0 context 0 0 0 fun s cleared =>
  if failed s = true then .done s 0 else
  if (if cleared = 36 then false else true) = true then .done invariantFailure 0 else
  .bind (get record 8) fun s entry => if failed s = true then .done s 0 else
  .bind (get address kernelStackTopOffset) fun s kernelTop => if failed s = true then .done s 0 else
  .bind (AddressSpace.satp descriptor) fun s translation => if failed s = true then .done s 0 else
  .bind (put context 16 0x3fffe000) fun s _ => if failed s = true then .done s 0 else
  .bind (put context 80 argument) fun s _ => if failed s = true then .done s 0 else
  .bind (put context 256 entry) fun s _ => if failed s = true then .done s 0 else
  .bind (put context 264 0x200000020) fun s _ => if failed s = true then .done s 0 else
  .bind (put context 272 translation) fun s _ => if failed s = true then .done s 0 else
  put context 280 kernelTop

private def initializeState (address record imageIndex argument : UInt64) : Action :=
  .bind (get record 0) fun s id => if failed s = true then .done s 0 else
  .bind (get record 8) fun s entry => if failed s = true then .done s 0 else
  .bind (get record 32) fun s textBytes => if failed s = true then .done s 0 else
  .bind (put address kernelStackHandleOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address kernelStackSecondHandleOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address kernelStackTopOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address kernelStackThirdHandleOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address kernelStackFourthHandleOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address kernelStackBaseOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind Frames.runtimeStackPages fun s pages => if failed s = true then .done s 0 else
  .bind (put address kernelStackPagesOffset pages) fun s _ => if failed s = true then .done s 0 else
  .bind (put address entryOffset entry) fun s _ => if failed s = true then .done s 0 else
  .bind (put address textBytesOffset textBytes) fun s _ => if failed s = true then .done s 0 else
  .bind (put address exitCodeOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address outcomeCauseOffset 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put address argumentOffset argument) fun s _ => if failed s = true then .done s 0 else
  .bind (put address imageIdOffset id) fun s _ => if failed s = true then .done s 0 else
  .bind (put address imageIndexOffset imageIndex) fun s _ => if failed s = true then .done s 0 else
  put address readyOffset 0

private def stackFrame (owner handle : UInt64) : Action :=
  .bind (Frames.resolvePurpose owner handle 1) fun s physical =>
  if s = 0 then
    .bind (Frames.mappingCount owner handle) fun s pins =>
    if s = 0 then
      if pins = 0 then .done 0 physical else .done invariantFailure 0
    else .done invariantFailure 0
  else .done invariantFailure 0

private def stackPair (owner first second : UInt64) : Action :=
  .bind (stackFrame owner first) fun s physical =>
  if s = 0 then
    .bind (stackFrame owner second) fun s next =>
    if s = 0 then
      if next = physical + 4096 then .done 0 physical else .done invariantFailure 0
    else .done invariantFailure 0
  else .done invariantFailure 0

/-- A failed constructor can hold no stack, one published handle, or both.
A cleared handle is never resolved again. A surviving handle must still name
its owned, unmapped purpose-1 frame. Both live handles must be contiguous before
either is released; top zero denotes an unpublished partial constructor. -/
private def storedStack (owner first second top : UInt64) : Action :=
  if first = 0 then
    if second = 0 then
      if top = 0 then .done 0 0 else .done invariantFailure 0
    else
      .bind (stackFrame owner second) fun s physical =>
      if s = 0 then
        if top = 0 then .done 0 0 else
        if top = physical + 4096 then .done 0 0 else .done invariantFailure 0
      else .done invariantFailure 0
  else if second = 0 then
    .bind (stackFrame owner first) fun s physical =>
    if s = 0 then
      if top = 0 then .done 0 0 else
      if top = physical + Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue then .done 0 0
      else .done invariantFailure 0
    else .done invariantFailure 0
  else
    .bind (stackPair owner first second) fun s physical =>
    if s = 0 then
      if top = 0 then .done 0 0 else
      if top = physical + Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue then .done 0 0
      else .done invariantFailure 0
    else .done invariantFailure 0

private def releaseStackHandle (address owner slot handle : UInt64) : Action :=
  if handle = 0 then .done 0 0 else
  .bind (Frames.release owner handle) fun s _ =>
  if s = 0 then
    .bind (put address slot 0) fun s _ =>
    if s = 0 then .done 0 0 else .done invariantFailure 0
  else .done invariantFailure 0

private def releaseUnpublishedPair (owner first second : UInt64) (original : UInt8) : Action :=
  .bind (Frames.release owner first) fun firstStatus _ =>
  .bind (Frames.release owner second) fun secondStatus _ =>
  if firstStatus = 0 then
    if secondStatus = 0 then .done original 0 else .done invariantFailure 0
  else .done invariantFailure 0

private def installStackPair (address owner first second : UInt64) : Action :=
  .bind (stackPair owner first second) fun s physical =>
  if s = 0 then
    .bind (put address kernelStackHandleOffset first) fun s _ =>
    if s = 0 then
      .bind (put address kernelStackSecondHandleOffset second) fun s _ =>
      if s = 0 then
        .bind (put address kernelStackTopOffset (physical + Lemma.Platform.LemmaVM.Layout.taskKernelStackBytesValue)) fun s _ =>
        if s = 0 then .done 0 0 else .done invariantFailure 0
      else
        .bind (put address kernelStackHandleOffset 0) fun cleared _ =>
        .bind (releaseUnpublishedPair owner first second invariantFailure) fun result _ =>
        if cleared = 0 then .done result 0 else .done invariantFailure 0
    else releaseUnpublishedPair owner first second invariantFailure
  else releaseUnpublishedPair owner first second s


private def quadFrame (owner handle physical : UInt64) : Action :=
  if handle = 0 then .done 0 0 else
  .bind (stackFrame owner handle) fun s actual =>
  if s = 0 then if actual = physical then .done 0 actual else .done invariantFailure 0
  else .done invariantFailure 0

private def storedQuad (owner first second third fourth physical top : UInt64) : Action :=
  if Frames.frameAddressValid physical = false then .done invariantFailure 0 else
  .bind (quadFrame owner first physical) fun s _ => if s = 0 then
  .bind (quadFrame owner second (physical + 4096)) fun s _ => if s = 0 then
  .bind (quadFrame owner third (physical + 8192)) fun s _ => if s = 0 then
  .bind (quadFrame owner fourth (physical + 12288)) fun s _ => if s = 0 then
  if top = 0 then .done 0 physical else
  if first = 0 then .done invariantFailure 0 else
  if second = 0 then .done invariantFailure 0 else
  if third = 0 then .done invariantFailure 0 else
  if fourth = 0 then .done invariantFailure 0 else
  if top = physical + 16368 then .done 0 physical else .done invariantFailure 0
  else .done invariantFailure 0 else .done invariantFailure 0
  else .done invariantFailure 0 else .done invariantFailure 0

/-- Expanded-stack canaries detect overwrites; these are not unmapped guards.
The existing S direct map cannot provide a per-task unmapped physical guard.
S traps keep SIE clear, so the selected audit accounts one vector and no nested
S interrupt vector. M entry uses the separate firmware-private stack. -/
def stackCanary : UInt64 := 0x4c4d535441434b34

def validateExpandedStack (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s address => if s = 0 then
  .bind (AddressSpace.owner descriptor) fun s owner => if s = 0 then
  .bind (get address kernelStackHandleOffset) fun s first => if s = 0 then
  .bind (get address kernelStackSecondHandleOffset) fun s second => if s = 0 then
  .bind (get address kernelStackThirdHandleOffset) fun s third => if s = 0 then
  .bind (get address kernelStackFourthHandleOffset) fun s fourth => if s = 0 then
  .bind (get address kernelStackBaseOffset) fun s physical => if s = 0 then
  .bind (get address kernelStackTopOffset) fun s top => if s = 0 then
  if top = 0 then .done invariantFailure 0 else
  .bind (storedQuad owner first second third fourth physical top) fun s _ => if s = 0 then
  .bind (Access.read64 physical) fun s low => if s = 0 then
  .bind (Access.read64 (physical + 16376)) fun s high => if s = 0 then
  if low = stackCanary then if high = stackCanary then .done 0 top else .done invariantFailure 0
  else .done invariantFailure 0
  else .done invariantFailure 0 else .done invariantFailure 0 else .done invariantFailure 0
  else .done invariantFailure 0 else .done invariantFailure 0 else .done invariantFailure 0
  else .done invariantFailure 0 else .done invariantFailure 0 else .done invariantFailure 0
  else .done invariantFailure 0 else .done invariantFailure 0

private def abortQuad (address owner first second third fourth : UInt64) : Action :=
  .bind (put address kernelStackTopOffset 0) fun _ _ =>
  .bind (releaseStackHandle address owner kernelStackHandleOffset first) fun a _ =>
  .bind (releaseStackHandle address owner kernelStackSecondHandleOffset second) fun b _ =>
  .bind (releaseStackHandle address owner kernelStackThirdHandleOffset third) fun c _ =>
  .bind (releaseStackHandle address owner kernelStackFourthHandleOffset fourth) fun d _ =>
  if a ||| b ||| c ||| d = 0 then .done invariantFailure 0 else .done invariantFailure 0

private def installStackQuad (address owner first second third fourth : UInt64) : Action :=
  .bind (stackFrame owner first) fun s physical =>
  if s = 0 then
    .bind (storedQuad owner first second third fourth physical 0) fun s _ =>
    if s = 0 then
      .bind (put address kernelStackBaseOffset physical) fun s _ => if s = 0 then
      .bind (put address kernelStackHandleOffset first) fun s _ => if s = 0 then
      .bind (put address kernelStackSecondHandleOffset second) fun s _ => if s = 0 then
      .bind (put address kernelStackThirdHandleOffset third) fun s _ => if s = 0 then
      .bind (put address kernelStackFourthHandleOffset fourth) fun s _ => if s = 0 then
      .bind (Access.write64 physical stackCanary) fun s _ => if s = 0 then
      .bind (Access.write64 (physical + 16376) stackCanary) fun s _ => if s = 0 then
      .bind (put address kernelStackTopOffset (physical + 16368)) fun s _ =>
      if s = 0 then .done 0 0 else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
      else abortQuad address owner first second third fourth
    else abortQuad address owner first second third fourth
  else abortQuad address owner first second third fourth

private def allocateStackQuad (address owner : UInt64) : Action :=
  .bind (Frames.allocateContiguous4 owner 1) fun s result => if s = 0 then
  if result = Frames.quadResult then
    .bind (Access.read64 result) fun s first => if s = 0 then
    .bind (Access.read64 (result + 8)) fun s second => if s = 0 then
    .bind (Access.read64 (result + 16)) fun s third => if s = 0 then
    .bind (Access.read64 (result + 24)) fun s fourth => if s = 0 then
    installStackQuad address owner first second third fourth
    else .done invariantFailure 0 else .done invariantFailure 0
    else .done invariantFailure 0 else .done invariantFailure 0
  else .done invariantFailure 0 else .done s 0

private def allocateStack (address owner : UInt64) : Action :=
  .bind (get address kernelStackPagesOffset) fun s pages =>
  if s = 0 then
  if pages = 4 then allocateStackQuad address owner else
  if pages = 2 then
  .bind (Frames.allocateContiguous2 owner 1) fun s result =>
  if s = 0 then
    if result = Frames.pairResult then
      .bind (Access.read64 Frames.pairResult) fun s first =>
      if s = 0 then
        .bind (Access.read64 (Frames.pairResult + 8)) fun s second =>
        if s = 0 then installStackPair address owner first second else .done invariantFailure 0
      else .done invariantFailure 0
    else .done invariantFailure 0
  else .done s 0
  else .done invariantFailure 0
  else .done s 0

/-- Inactive-only teardown runs on the restored supervisor boot/reaper stack.
Both live stack handles are validated before release. Each is cleared immediately
after its release so partial teardown cannot double-free it. AS then invalidates
and releases all owned leaves and tables. -/
def teardown (descriptor : UInt64) : Action :=
  .bind (AddressSpace.base descriptor) fun s address => if failed s = true then .done s 0 else
  .bind (AddressSpace.owner descriptor) fun s owner => if failed s = true then .done s 0 else
  .bind (AddressSpace.root descriptor) fun s root => if failed s = true then .done s 0 else
  .bind (Access.read64 AddressSpace.activeRoot) fun s active => if failed s = true then .done s 0 else
  if root = active then .done AddressSpace.activeAddressSpace 0 else
  .bind (get address kernelStackHandleOffset) fun s first => if failed s = true then .done s 0 else
  .bind (get address kernelStackSecondHandleOffset) fun s second => if failed s = true then .done s 0 else
  .bind (get address kernelStackTopOffset) fun s top => if failed s = true then .done s 0 else
  .bind (get address kernelStackPagesOffset) fun s pages => if failed s = true then .done s 0 else
  .bind (get address kernelStackThirdHandleOffset) fun s third => if failed s = true then .done s 0 else
  .bind (get address kernelStackFourthHandleOffset) fun s fourth => if failed s = true then .done s 0 else
  .bind (get address kernelStackBaseOffset) fun s physical => if failed s = true then .done s 0 else
  .bind (if pages = 2 then storedStack owner first second top else
    if pages = 4 then storedQuad owner first second third fourth physical top else .done invariantFailure 0)
    fun s _ => if failed s = true then .done s 0 else
  -- Inactive and fully validated: withdraw the stack top before the first
  -- release, so retries contain only zero or separately owned live handles.
  .bind (put address kernelStackTopOffset 0) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (releaseStackHandle address owner kernelStackHandleOffset first) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (releaseStackHandle address owner kernelStackSecondHandleOffset second) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (releaseStackHandle address owner kernelStackThirdHandleOffset third) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (releaseStackHandle address owner kernelStackFourthHandleOffset fourth) fun s _ =>
  if failed s = true then .done s 0 else
  AddressSpace.destroy descriptor

private def abortLoad (descriptor : UInt64) (original : UInt8) : Action :=
  .bind (teardown descriptor) fun s _ =>
  if s = 0 then .done original 0 else .done invariantFailure 0

private def build (descriptor address record owner imageIndex argument : UInt64) : Action :=
  .bind (initializeState address record imageIndex argument) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (allocateStack address owner) fun s _ => if failed s = true then .done s 0 else
  .bind (get record 32) fun s textBytes => if failed s = true then .done s 0 else
  let pages := (textBytes + 4095) / 4096
  .boundedFoldU64 128 textStep pages.toUInt32 0 descriptor owner record 0 fun s copiedPages =>
  if failed s = true then .done s 0 else
  if (if copiedPages = pages then false else true) = true then .done invariantFailure 0 else
  .bind (get record 48) fun s dataOffset => if failed s = true then .done s 0 else
  .bind (get record 56) fun s dataBytes => if failed s = true then .done s 0 else
  .bind (page descriptor owner 0x20000 4 3 (packageBase + dataOffset) dataBytes) fun s _ =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 2 stackStep 2 0 descriptor owner 0 0 fun s stacks =>
  if failed s = true then .done s 0 else
  if (if stacks = 2 then false else true) = true then .done invariantFailure 0 else
  .bind (initializeContext descriptor address record argument) fun s _ => if failed s = true then .done s 0 else
  .platform .fenceInstruction 0 0 0 0 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put address readyOffset 1) fun s _ => .done s descriptor

/-- Allocate, copy, zero, map and publish one independent U-mode instance.
Success returns its generation descriptor handle; ordinary partial failures
return their original status only after complete inactive teardown. -/
def load (imageIndex owner argument : UInt64) : Action :=
  if Frames.ownerValid owner = false then .done Frames.badOwner 0 else
  if owner = 1 then .done Frames.badOwner 0 else
  .bind (validate imageIndex) fun s record => if failed s = true then .done s 0 else
  .bind (AddressSpace.create owner) fun s descriptor => if failed s = true then .done s 0 else
  .bind (AddressSpace.base descriptor) fun s address =>
  if failed s = true then abortLoad descriptor s else
  .bind (build descriptor address record owner imageIndex argument) fun s _ =>
  if failed s = true then abortLoad descriptor s else .done 0 descriptor

end Lemma.Kernel.Loader
