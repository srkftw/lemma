import Lemma.Kernel.Memory.Access
import Lemma.Platform.LemmaVM.Layout

/-!
Guest validation of the actual QEMU-provided flattened device tree. This is a
bounded FDT token parser, not a byte-pattern witness supplied by the host. The
admitted boot profile has one hart, version 17 FDT, no firmware reserve entries,
two-cell root addresses/sizes, and exactly the pinned 128 MiB memory bank.
The pinned QEMU/libfdt-produced blob contains nonzero property-alignment bytes;
those at most three bytes have no semantic content and are skipped within the
checked structure bound. Node-name padding remains required to be zero.
Scratch is private kernel metadata at +0x800..+0x900. No borrowed DTB pointer
is followed before both its outer envelope and each inner block are checked.
-/
namespace Lemma.Kernel.BootInfo
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def scratch : UInt64 := 0x80400800
def bootRecord : UInt64 := 0x80400000
def dtbLower : UInt64 := 0x87e00000
def dtbUpper : UInt64 := 0x88000000
def ramBase : UInt64 := 0x80000000
def ramBytes : UInt64 := 0x08000000
def invalidHeader : UInt8 := 60
def invalidStructure : UInt8 := 61
def unsupported : UInt8 := 62
def resourceLimit : UInt8 := 63
def invalidMemory : UInt8 := 64

private def get (slot : UInt64) : Action := Access.read64 (scratch + slot)
private def put (slot value : UInt64) : Action := Access.write64 (scratch + slot) value

private def be32 (address : UInt64) : Action :=
  .bind (Access.read8 address) fun s a =>
  if s = 0 then .bind (Access.read8 (address + 1)) fun s b =>
  if s = 0 then .bind (Access.read8 (address + 2)) fun s c =>
  if s = 0 then .bind (Access.read8 (address + 3)) fun s d =>
  if s = 0 then .done 0 ((a <<< 24) ||| (b <<< 16) ||| (c <<< 8) ||| d)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def be64 (address : UInt64) : Action :=
  .bind (be32 address) fun s hi =>
  if s = 0 then .bind (be32 (address + 4)) fun s lo =>
  if s = 0 then .done 0 ((hi <<< 32) ||| lo) else .done s 0
  else .done s 0

private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

/-- String length, exact first sixteen bytes, termination and end offset are
recorded separately. Long unknown property names never alias short known names.
Every read is contained in its declared structure/strings/property interval. -/
private def nameStep (i _ : UInt32) (acc address limit _ _ : UInt64) : Action :=
  .bind (get 144) fun s finished =>
  if s = 0 then
    if finished = 1 then .done 0 acc else
    if address + i.toUInt64 < limit then
      .bind (Access.read8 (address + i.toUInt64)) fun s byte =>
      if s = 0 then
        if byte = 0 then
          .bind (put 144 1) fun s _ =>
          if s = 0 then .bind (put 152 (address + i.toUInt64 + 1)) fun s _ => .done s acc
          else .done s 0
        else
          .bind (put 120 (i.toUInt64 + 1)) fun s _ =>
          if s = 0 then
            if i < 8 then
              .bind (get 128) fun s packed =>
              if s = 0 then .bind (put 128 (packed ||| (byte <<< (i.toUInt64 * 8)))) fun s _ => .done s acc
              else .done s 0
            else if i < 16 then
              .bind (get 136) fun s packed =>
              if s = 0 then .bind (put 136 (packed ||| (byte <<< ((i.toUInt64 - 8) * 8)))) fun s _ => .done s acc
              else .done s 0
            else .done 0 acc
          else .done s 0
      else .done s 0
    else .done invalidStructure 0
  else .done s 0

private def readName (address limit : UInt64) : Action :=
  .bind (put 120 0) fun s _ =>
  if s = 0 then .bind (put 128 0) fun s _ =>
  if s = 0 then .bind (put 136 0) fun s _ =>
  if s = 0 then .bind (put 144 0) fun s _ =>
  if s = 0 then
    .boundedFoldU64 128 nameStep 128 0 address limit 0 0 fun s _ =>
    if s = 0 then .bind (get 144) fun s doneName =>
    if s = 0 then
      if doneName = 1 then .bind (get 152) fun s endName => .done s endName
      else .done resourceLimit 0
    else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def propertyKind (length lo hi : UInt64) : UInt64 :=
  if length = 14 then
    if lo = 0x7373657264646123 then
      if hi = 0x736c6c65632d then 1 else 0
    else 0
  else if length = 11 then
    if lo = 0x65632d657a697323 then
      if hi = 0x736c6c then 2 else 0
    else if lo = 0x745f656369766564 then
      if hi = 0x657079 then 3 else 0
    else 0
  else if length = 3 then
    if lo = 0x676572 then if hi = 0 then 4 else 0 else 0
  else 0

private def memoryName (length lo hi : UInt64) : UInt64 :=
  if length = 15 then
    if lo = 0x384079726f6d656d then
      if hi = 0x30303030303030 then 1 else 0
    else 0
  else 0

/-- The narrow boot profile has no secondary reserved-memory binding. Unknown
reservations must not silently turn the owned frame pool into advertised RAM. -/
private def reservedMemoryName (length lo hi : UInt64) : UInt64 :=
  if length = 15 then
    if lo = 0x6465767265736572 then
      if hi = 0x79726f6d656d2d then 1 else 0
    else 0
  else 0

private def paddingStep (i _ : UInt32) (acc start stop _ _ : UInt64) : Action :=
  if start + i.toUInt64 < stop then
    .bind (Access.read8 (start + i.toUInt64)) fun s value =>
    if s = 0 then
      if value = 0 then .done 0 acc else .done invalidStructure 0
    else .done s 0
  else .done 0 acc

private def padding (start stop : UInt64) : Action :=
  if start ≤ stop then
    if stop - start ≤ 3 then
      .boundedFoldU64 3 paddingStep 3 0 start stop 0 0 fun s v => .done s v
    else .done invalidStructure 0
  else .done invalidStructure 0

/-- One bit per open depth records that children have begun. A fresh child
clears its own bit, preserving all ancestor bits; properties must precede them. -/
private def nodeOrder (depth : UInt64) : Action :=
  .bind (get 192) fun s flags =>
  if s = 0 then
    let parent := if depth = 0 then 0 else (1 : UInt64) <<< (depth - 1)
    let child := (1 : UInt64) <<< depth
    put 192 ((flags ||| parent) &&& (child ^^^ 0xffffffffffffffff))
  else .done s 0

private def beginNode (cursor depth limit : UInt64) : Action :=
  if depth < 16 then
    .bind (readName (cursor + 4) limit) fun s endName =>
    if s = 0 then .bind (get 120) fun s length =>
    if s = 0 then .bind (get 128) fun s lo =>
    if s = 0 then .bind (get 136) fun s hi =>
    if s = 0 then
      let next := (endName + 3) &&& 0xfffffffffffffffc
      if next ≤ limit then
        .bind (padding endName next) fun s _ =>
        if s = 0 then .bind (nodeOrder depth) fun s _ =>
        if s = 0 then
        .bind (if depth = 0 then
          .bind (get 48) fun s seen =>
          if s = 0 then
            if seen = 0 then
              if length = 0 then put 48 1 else .done invalidStructure 0
            else .done invalidStructure 0
          else .done s 0
        else if depth = 1 then
          if reservedMemoryName length lo hi = 1 then .done unsupported 0 else
          if memoryName length lo hi = 1 then
            .bind (get 112) fun s completed =>
            if s = 0 then
              if completed = 0 then
                .bind (put 88 2) fun s _ =>
                if s = 0 then .bind (put 96 0) fun s _ =>
                if s = 0 then put 104 0 else .done s 0 else .done s 0
              else .done invalidMemory 0
            else .done s 0
          else .done 0 0
        else .done 0 0) fun s _ =>
        if s = 0 then .bind (put 40 (depth + 1)) fun s _ =>
        if s = 0 then put 32 next else .done s 0 else .done s 0
        else .done s 0 else .done s 0
      else .done invalidStructure 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done resourceLimit 0

private def endNode (cursor depth : UInt64) : Action :=
  if depth = 0 then .done invalidStructure 0 else
  .bind (if depth = 2 then
    .bind (get 88) fun s active =>
    if s = 0 then
      if active = 2 then
        .bind (get 96) fun s typeSeen =>
        if s = 0 then .bind (get 104) fun s regSeen =>
        if s = 0 then
          if typeSeen = 1 then
            if regSeen = 1 then
              .bind (put 112 1) fun s _ =>
              if s = 0 then put 88 0 else .done s 0
            else .done invalidMemory 0
          else .done invalidMemory 0
        else .done s 0 else .done s 0
      else .done 0 0
    else .done s 0
  else if depth = 1 then put 56 1 else .done 0 0) fun s _ =>
  if s = 0 then .bind (put 40 (depth - 1)) fun s _ =>
  if s = 0 then put 32 (cursor + 4) else .done s 0 else .done s 0

private def cellsProperty (data length seenSlot : UInt64) : Action :=
  if length = 4 then
    .bind (get seenSlot) fun s seen =>
    if s = 0 then
      if seen = 0 then
        .bind (be32 data) fun s value =>
        if s = 0 then
          if value = 2 then put seenSlot 1 else .done unsupported 0
        else .done s 0
      else .done invalidStructure 0
    else .done s 0
  else .done invalidStructure 0

private def memoryType (data length : UInt64) : Action :=
  if length = 7 then
    .bind (get 96) fun s seen =>
    if s = 0 then
      if seen = 0 then
        .bind (readName data (data + length)) fun s _ =>
        if s = 0 then .bind (get 120) fun s nameLength =>
        if s = 0 then .bind (get 128) fun s packed =>
        if s = 0 then
          if nameLength = 6 then
            if packed = 0x79726f6d656d then put 96 1 else .done invalidMemory 0
          else .done invalidMemory 0
        else .done s 0 else .done s 0 else .done s 0
      else .done invalidStructure 0
    else .done s 0
  else .done invalidMemory 0

private def memoryReg (data length : UInt64) : Action :=
  if length = 16 then
    .bind (get 104) fun s seen =>
    if s = 0 then
      if seen = 0 then
        .bind (be64 data) fun s base =>
        if s = 0 then .bind (be64 (data + 8)) fun s size =>
        if s = 0 then
          if base = ramBase then
            if size = ramBytes then put 104 1 else .done invalidMemory 0
          else .done invalidMemory 0
        else .done s 0 else .done s 0
      else .done invalidStructure 0
    else .done s 0
  else .done invalidMemory 0

/-- Another root child declaring device_type=memory is an unsupported second
bank even when it uses a different node name. It cannot be silently ignored. -/
private def denyAdditionalMemoryType (data length : UInt64) : Action :=
  if length = 7 then
    .bind (readName data (data + length)) fun s _ =>
    if s = 0 then .bind (get 120) fun s nameLength =>
    if s = 0 then .bind (get 128) fun s packed =>
    if s = 0 then
      if nameLength = 6 then
        if packed = 0x79726f6d656d then .done invalidMemory 0 else .done 0 0
      else .done 0 0
    else .done s 0 else .done s 0 else .done s 0
  else .done 0 0

private def property (cursor depth limit : UInt64) : Action :=
  if depth = 0 then .done invalidStructure 0 else
  if cursor + 12 ≤ limit then
    .bind (be32 (cursor + 4)) fun s length =>
    if s = 0 then .bind (be32 (cursor + 8)) fun s nameOffset =>
    if s = 0 then
      let data := cursor + 12
      if length ≤ limit - data then
        let next := (data + length + 3) &&& 0xfffffffffffffffc
        if next ≤ limit then
          .bind (get 16) fun s strings =>
          if s = 0 then .bind (get 24) fun s stringsLimit =>
          if s = 0 then
            if nameOffset < stringsLimit - strings then
              .bind (readName (strings + nameOffset) stringsLimit) fun s _ =>
              if s = 0 then .bind (get 120) fun s nameLength =>
              if s = 0 then .bind (get 128) fun s lo =>
              if s = 0 then .bind (get 136) fun s hi =>
              if s = 0 then
                if nameLength = 0 then .done invalidStructure 0 else
                let kind := propertyKind nameLength lo hi
                .bind (if depth = 1 then
                  if kind = 1 then cellsProperty data length 72
                  else if kind = 2 then cellsProperty data length 80
                  else .done 0 0
                else if depth = 2 then
                  .bind (get 88) fun s active =>
                  if s = 0 then
                    if active = 2 then
                      if kind = 3 then memoryType data length
                      else if kind = 4 then memoryReg data length
                      else .done 0 0
                    else if kind = 3 then denyAdditionalMemoryType data length
                    else .done 0 0
                  else .done s 0
                else .done 0 0) fun s _ =>
                if s = 0 then
                  if next - (data + length) ≤ 3 then put 32 next
                  else .done invalidStructure 0
                else .done s 0
              else .done s 0 else .done s 0 else .done s 0 else .done s 0
            else .done invalidStructure 0
          else .done s 0 else .done s 0
        else .done invalidStructure 0
      else .done invalidStructure 0
    else .done s 0 else .done s 0
  else .done invalidStructure 0

private def orderedProperty (cursor depth limit : UInt64) : Action :=
  if depth = 0 then .done invalidStructure 0 else
  .bind (get 192) fun s flags =>
  if s = 0 then
    if flags &&& ((1 : UInt64) <<< (depth - 1)) = 0 then property cursor depth limit
    else .done invalidStructure 0
  else .done s 0

private def finishTree (cursor depth limit : UInt64) : Action :=
  if depth = 0 then
    if cursor + 4 = limit then
      .bind (get 48) fun s rootSeen =>
      if s = 0 then .bind (get 56) fun s rootClosed =>
      if s = 0 then .bind (get 72) fun s addressCells =>
      if s = 0 then .bind (get 80) fun s sizeCells =>
      if s = 0 then .bind (get 112) fun s memorySeen =>
      if s = 0 then
        if rootSeen = 1 then
          if rootClosed = 1 then
            if addressCells = 1 then
              if sizeCells = 1 then
                if memorySeen = 1 then put 64 1 else .done invalidMemory 0
              else .done unsupported 0
            else .done unsupported 0
          else .done invalidStructure 0
        else .done invalidStructure 0
      else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else .done invalidStructure 0
  else .done invalidStructure 0

private def tokenStep (_ _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (get 64) fun s ended =>
  if s = 0 then
    if ended = 1 then .done 0 acc else
    .bind (get 32) fun s cursor =>
    if s = 0 then .bind (get 8) fun s limit =>
    if s = 0 then .bind (get 40) fun s depth =>
    if s = 0 then
      if cursor + 4 ≤ limit then
        .bind (be32 cursor) fun s token =>
        if s = 0 then
          if token = 1 then beginNode cursor depth limit
          else if token = 2 then endNode cursor depth
          else if token = 3 then orderedProperty cursor depth limit
          else if token = 4 then put 32 (cursor + 4)
          else if token = 9 then finishTree cursor depth limit
          else .done invalidStructure 0
        else .done s 0
      else .done invalidStructure 0
    else .done s 0 else .done s 0 else .done s 0
  else .done s 0

private def parseTree : Action :=
  .boundedFoldU64 4096 tokenStep 4096 0 0 0 0 0 fun s _ =>
  if s = 0 then .bind (get 64) fun s ended =>
  if s = 0 then
    if ended = 1 then .bind (get 184) fun s pointer => .done s pointer
    else .done resourceLimit 0
  else .done s 0 else .done s 0

private def header (pointer : UInt64) : Action :=
  .bind (be32 pointer) fun s magic =>
  if s = 0 then
    if magic = 0xd00dfeed then
      .bind (be32 (pointer + 4)) fun s total =>
      if s = 0 then
        if 40 ≤ total then
          if total ≤ dtbUpper - pointer then
            .bind (be32 (pointer + 8)) fun s structureOffset =>
            if s = 0 then .bind (be32 (pointer + 12)) fun s stringsOffset =>
            if s = 0 then .bind (be32 (pointer + 16)) fun s reservesOffset =>
            if s = 0 then .bind (be32 (pointer + 20)) fun s version =>
            if s = 0 then .bind (be32 (pointer + 24)) fun s compatible =>
            if s = 0 then .bind (be32 (pointer + 28)) fun s bootCpu =>
            if s = 0 then .bind (be32 (pointer + 32)) fun s stringsSize =>
            if s = 0 then .bind (be32 (pointer + 36)) fun s structureSize =>
            if s = 0 then
              if version = 17 then
              if compatible = 16 then
              if bootCpu = 0 then
              if 40 ≤ reservesOffset then
              if reservesOffset % 8 = 0 then
              if reservesOffset + 16 ≤ structureOffset then
              if structureOffset % 4 = 0 then
              if 12 ≤ structureSize then
              if structureSize % 4 = 0 then
              if structureOffset + structureSize ≤ stringsOffset then
              if 0 < stringsSize then
              if stringsOffset + stringsSize ≤ total then
                .bind (be64 (pointer + reservesOffset)) fun s reserveAddress =>
                if s = 0 then .bind (be64 (pointer + reservesOffset + 8)) fun s reserveSize =>
                if s = 0 then
                  if reserveAddress = 0 then
                  if reserveSize = 0 then
                    .bind (put 0 (pointer + structureOffset)) fun s _ =>
                    if s = 0 then .bind (put 8 (pointer + structureOffset + structureSize)) fun s _ =>
                    if s = 0 then .bind (put 16 (pointer + stringsOffset)) fun s _ =>
                    if s = 0 then .bind (put 24 (pointer + stringsOffset + stringsSize)) fun s _ =>
                    if s = 0 then .bind (put 32 (pointer + structureOffset)) fun s _ =>
                    if s = 0 then .bind (put 184 pointer) fun s _ =>
                    if s = 0 then parseTree else .done s 0
                    else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
                  else .done unsupported 0 else .done unsupported 0
                else .done s 0 else .done s 0
              else .done invalidHeader 0 else .done invalidHeader 0
              else .done invalidHeader 0 else .done invalidHeader 0
              else .done invalidHeader 0 else .done invalidHeader 0
              else .done invalidHeader 0 else .done invalidHeader 0
              else .done invalidHeader 0 else .done unsupported 0
              else .done unsupported 0 else .done unsupported 0
            else .done s 0 else .done s 0 else .done s 0 else .done s 0
            else .done s 0 else .done s 0 else .done s 0 else .done s 0
          else .done invalidHeader 0
        else .done invalidHeader 0
      else .done s 0
    else .done invalidHeader 0
  else .done s 0

/-- Validates the actual boot hart and DTB pointer, then a supported FDT tree.
The successful value is the validated DTB pointer; RAM size was read from reg.
An invalid or unsupported blob cannot be credited as usable allocator input. -/
def validate : Action :=
  .bind (Access.read64 bootRecord) fun s hart =>
  if s = 0 then
    if hart = 0 then
      .bind (Access.read64 (bootRecord + 16)) fun s stage =>
      if s = 0 then
      if stage ≤ 1 then
      .bind (Access.read64 (bootRecord + 8)) fun s pointer =>
      if s = 0 then
        if dtbLower ≤ pointer then
          if pointer ≤ dtbUpper - 40 then
            if pointer % 8 = 0 then
              .boundedFoldU64 32 clearStep 32 0 0 0 0 0 fun s _ =>
              if s = 0 then header pointer else .done s 0
            else .done invalidHeader 0
          else .done invalidHeader 0
        else .done invalidHeader 0
      else .done s 0
      else .done unsupported 0 else .done s 0
    else .done unsupported 0
  else .done s 0

end Lemma.Kernel.BootInfo
