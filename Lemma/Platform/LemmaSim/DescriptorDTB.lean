import Lemma.Kernel.BootInfo
import Lemma.Platform.LemmaSim.IO
import Lemma.Platform.LemmaSim.DeviceABI

/-! Binding-specific guest validation of the actual handed FDT. BootInfo retains
its historical memory/envelope semantics; this bounded second pass verifies
device identities, IRQ parents, fixed ranges and geometry before allocation.
Scratch [0x80400d00,0x80400f00) is reserved boot metadata. No host manifest is
consulted and no borrowed FDT span is followed before BootInfo validates it. -/
namespace Lemma.Platform.LemmaSim.DescriptorDTB
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory

def scratch : UInt64 := 0x80400d00
def invalid : UInt8 := 169
private def failed (s : UInt8) : Bool := if s = 0 then false else true
private def get (offset : UInt64) : Action := Access.read64 (scratch + offset)
private def put (offset value : UInt64) : Action := Access.write64 (scratch + offset) value

-- Exact bounded ASCII literals, including termination and compatible lists.
private def literalLength (code : UInt64) : UInt64 :=
  if code = 1 then 1 else
  if code = 2 then 5 else
  if code = 3 then 4 else
  if code = 4 then 21 else
  if code = 5 then 19 else
  if code = 6 then 21 else
  if code = 7 then 29 else
  if code = 8 then 14 else
  if code = 9 then 16 else
  if code = 10 then 11 else
  if code = 11 then 21 else
  if code = 12 then 21 else
  if code = 13 then 21 else
  if code = 14 then 21 else
  if code = 15 then 21 else
  if code = 16 then 21 else
  if code = 17 then 21 else
  if code = 32 then 11 else
  if code = 33 then 4 else
  if code = 34 then 11 else
  if code = 35 then 17 else
  if code = 36 then 8 else
  if code = 37 then 19 else
  if code = 38 then 18 else
  if code = 39 then 12 else
  if code = 40 then 13 else
  if code = 41 then 12 else
  if code = 42 then 12 else
  if code = 43 then 19 else
  if code = 44 then 17 else
  if code = 45 then 15 else
  if code = 46 then 12 else
  if code = 47 then 17 else
  if code = 48 then 11 else
  if code = 49 then 21 else
  if code = 50 then 20 else
  if code = 51 then 16 else
  if code = 52 then 7 else
  if code = 64 then 15 else
  if code = 65 then 13 else
  if code = 66 then 12 else
  if code = 67 then 30 else
  if code = 68 then 27 else
  if code = 69 then 9 else
  if code = 70 then 20 else
  if code = 71 then 11 else
  0
private def literalWord (code index : UInt64) : UInt64 :=
  if code = 1 then
    if index = 0 then 0x0 else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 2 then
    if index = 0 then 0x73757063 else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 3 then
    if index = 0 then 0x636f73 else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 4 then
    if index = 0 then 0x61702d616d6d656c else
    if index = 1 then 0x3130303140726570 else
    if index = 2 then 0x30303030 else
    if index = 3 then 0x0 else
    0 else
  if code = 5 then
    if index = 0 then 0x65702d616d6d656c else
    if index = 1 then 0x303131303031406e else
    if index = 2 then 0x3030 else
    if index = 3 then 0x0 else
    0 else
  if code = 6 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303031 else
    if index = 3 then 0x0 else
    0 else
  if code = 7 then
    if index = 0 then 0x7075727265746e69 else
    if index = 1 then 0x6f72746e6f632d74 else
    if index = 2 then 0x3030634072656c6c else
    if index = 3 then 0x30303030 else
    0 else
  if code = 8 then
    if index = 0 then 0x303240746e696c63 else
    if index = 1 then 0x3030303030 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 9 then
    if index = 0 then 0x31406c6169726573 else
    if index = 1 then 0x30303030303030 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 10 then
    if index = 0 then 0x3031303140637472 else
    if index = 1 then 0x3030 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 11 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303032 else
    if index = 3 then 0x0 else
    0 else
  if code = 12 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303033 else
    if index = 3 then 0x0 else
    0 else
  if code = 13 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303034 else
    if index = 3 then 0x0 else
    0 else
  if code = 14 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303035 else
    if index = 3 then 0x0 else
    0 else
  if code = 15 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303036 else
    if index = 3 then 0x0 else
    0 else
  if code = 16 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303037 else
    if index = 3 then 0x0 else
    0 else
  if code = 17 then
    if index = 0 then 0x6d5f6f6974726976 else
    if index = 1 then 0x30303031406f696d else
    if index = 2 then 0x30303038 else
    if index = 3 then 0x0 else
    0 else
  if code = 32 then
    if index = 0 then 0x62697461706d6f63 else
    if index = 1 then 0x656c else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 33 then
    if index = 0 then 0x676572 else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 34 then
    if index = 0 then 0x7075727265746e69 else
    if index = 1 then 0x7374 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 35 then
    if index = 0 then 0x7075727265746e69 else
    if index = 1 then 0x746e657261702d74 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 36 then
    if index = 0 then 0x656c646e616870 else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 37 then
    if index = 0 then 0x65736162656d6974 else
    if index = 1 then 0x6e6575716572662d else
    if index = 2 then 0x7963 else
    if index = 3 then 0x0 else
    0 else
  if code = 38 then
    if index = 0 then 0x62612c616d6d656c else
    if index = 1 then 0x6f69737265762d69 else
    if index = 2 then 0x6e else
    if index = 3 then 0x0 else
    0 else
  if code = 39 then
    if index = 0 then 0x69772c616d6d656c else
    if index = 1 then 0x687464 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 40 then
    if index = 0 then 0x65682c616d6d656c else
    if index = 1 then 0x74686769 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 41 then
    if index = 0 then 0x616d2c616d6d656c else
    if index = 1 then 0x782d78 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 42 then
    if index = 0 then 0x616d2c616d6d656c else
    if index = 1 then 0x792d78 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 43 then
    if index = 0 then 0x72702c616d6d656c else
    if index = 1 then 0x6d2d657275737365 else
    if index = 2 then 0x7861 else
    if index = 3 then 0x0 else
    0 else
  if code = 44 then
    if index = 0 then 0x65642c616d6d656c else
    if index = 1 then 0x726f747069726373 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 45 then
    if index = 0 then 0x7373657264646123 else
    if index = 1 then 0x736c6c65632d else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 46 then
    if index = 0 then 0x65632d657a697323 else
    if index = 1 then 0x736c6c else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 47 then
    if index = 0 then 0x75727265746e6923 else
    if index = 1 then 0x736c6c65632d7470 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 48 then
    if index = 0 then 0x646e2c7663736972 else
    if index = 1 then 0x7665 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 49 then
    if index = 0 then 0x7075727265746e69 else
    if index = 1 then 0x6f72746e6f632d74 else
    if index = 2 then 0x72656c6c else
    if index = 3 then 0x0 else
    0 else
  if code = 50 then
    if index = 0 then 0x7075727265746e69 else
    if index = 1 then 0x6e657478652d7374 else
    if index = 2 then 0x646564 else
    if index = 3 then 0x0 else
    0 else
  if code = 51 then
    if index = 0 then 0x72662d6b636f6c63 else
    if index = 1 then 0x79636e65757165 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 52 then
    if index = 0 then 0x7365676e6172 else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 64 then
    if index = 0 then 0x61702c616d6d656c else
    if index = 1 then 0x31762d726570 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 65 then
    if index = 0 then 0x65702c616d6d656c else
    if index = 1 then 0x31762d6e else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 66 then
    if index = 0 then 0x6d2c6f6974726976 else
    if index = 1 then 0x6f696d else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 67 then
    if index = 0 then 0x702c657669666973 else
    if index = 1 then 0x2e302e312d63696c else
    if index = 2 then 0x2c76637369720030 else
    if index = 3 then 0x3063696c70 else
    0 else
  if code = 68 then
    if index = 0 then 0x632c657669666973 else
    if index = 1 then 0x69720030746e696c else
    if index = 2 then 0x6e696c632c766373 else
    if index = 3 then 0x3074 else
    0 else
  if code = 69 then
    if index = 0 then 0x613035353631736e else
    if index = 1 then 0x0 else
    if index = 2 then 0x0 else
    if index = 3 then 0x0 else
    0 else
  if code = 70 then
    if index = 0 then 0x672c656c676f6f67 else
    if index = 1 then 0x2d68736966646c6f else
    if index = 2 then 0x637472 else
    if index = 3 then 0x0 else
    0 else
  if code = 71 then
    if index = 0 then 0x622d656c706d6973 else
    if index = 1 then 0x7375 else
    0 else
  0
private def matchStep (i _ : UInt32) (acc address code _ _ : UInt64) : Action :=
  .bind (Access.read8 (address + i.toUInt64)) fun s byte =>
  if s = 0 then
    let expected := (literalWord code (i.toUInt64 / 8) >>> ((i.toUInt64 % 8) * 8)) &&& 255
    if byte = expected then .done 0 acc else .done 10 0
  else .done s 0

private def equalLiteral (address bytes code : UInt64) : Action :=
  if bytes = literalLength code then
    .boundedFoldU64 32 matchStep bytes.toUInt32 1 address code 0 0 fun s same => .done s same
  else .done 0 0

private def findStep (i _ : UInt32) (acc address bytes start _ : UInt64) : Action :=
  let code := start + i.toUInt64
  .bind (equalLiteral address bytes code) fun s same =>
  if s = 0 then if same = 1 then .done 10 code else .done 0 acc else .done s 0

private def findCode (address bytes start count : UInt64) : Action :=
  if count ≤ 21 then
    .boundedFoldU64 21 findStep count.toUInt32 0 address bytes start 0 fun s code => .done s code
  else .done invalid 0

private def leaf (role : UInt64) : UInt64 :=
  if 1 ≤ role then if role ≤ 7 then 1 else
    if 21 ≤ role then if role ≤ 27 then 1 else 0 else 0
  else 0

private def nodeRole (parent code : UInt64) : UInt64 :=
  if parent = 0 then if code = 1 then 10 else 0 else
  if parent = 10 then if code = 2 then 11 else if code = 3 then 12 else 0 else
  if parent = 12 then
    if code = 4 then 1 else if code = 5 then 2 else if code = 6 then 3 else
    if code = 7 then 4 else if code = 8 then 5 else if code = 9 then 6 else
    if code = 10 then 7 else if 11 ≤ code then if code ≤ 17 then code + 10 else 0 else 0
  else 0

private def expectedBase (role : UInt64) : UInt64 :=
  if role = 1 then 0x10010000 else if role = 2 then 0x10011000 else
  if role = 3 then 0x10001000 else if role = 4 then 0x0c000000 else
  if role = 5 then 0x02000000 else if role = 6 then 0x10000000 else
  if role = 7 then 0x00101000 else if 21 ≤ role then 0x10001000 + (role - 20) * 4096 else 0
private def expectedSpan (role : UInt64) : UInt64 :=
  if role = 4 then 0x600000 else if role = 5 then 0x10000 else if role = 6 then 0x100 else 4096
private def expectedIRQ (role : UInt64) : UInt64 :=
  if role = 1 then 12 else if role = 2 then 13 else if role = 3 then 1 else
  if role = 6 then 10 else if role = 7 then 11 else role - 19
private def compatibleCode (role : UInt64) : UInt64 :=
  if role = 1 then 64 else if role = 2 then 65 else if role = 4 then 67 else
  if role = 5 then 68 else if role = 6 then 69 else if role = 7 then 70 else 66
private def requiredFlags (role : UInt64) : UInt64 :=
  if role = 1 then 255 else if role = 2 then 255 else
  if role = 4 then 1011 else if role = 5 then 515 else if role = 6 then 31 else 15

private def mark (bit : UInt64) : Action :=
  .bind (get 64) fun s flags =>
  if s = 0 then if flags &&& bit = 0 then put 64 (flags ||| bit) else .done invalid 0 else .done s 0
private def fixedCell (data bytes expected bit : UInt64) : Action :=
  if bytes = 4 then
  .bind (BootInfo.readBE32 data) fun s value => if s = 0 then
  if value = expected then mark bit else .done invalid 0 else .done s 0
  else .done invalid 0
private def dynamicCell (data bytes slot bit : UInt64) : Action :=
  .bind (get slot) fun s expected => if s = 0 then fixedCell data bytes expected bit else .done s 0

private def parentCell (data bytes : UInt64) : Action :=
  if bytes = 4 then .bind (BootInfo.readBE32 data) fun s parent => if s = 0 then
  if 0 < parent then .bind (get 72) fun s previous => if s = 0 then
  if previous = 0 then .bind (put 72 parent) fun s _ => if s = 0 then mark 8 else .done s 0
  else if previous = parent then mark 8 else .done invalid 0
  else .done s 0 else .done invalid 0 else .done s 0 else .done invalid 0

private def interruptContext (data bytes role : UInt64) : Action :=
  if bytes = 16 then
  .bind (BootInfo.readBE32 data) fun s first => if s = 0 then
  .bind (BootInfo.readBE32 (data + 4)) fun s irq0 => if s = 0 then
  .bind (BootInfo.readBE32 (data + 8)) fun s second => if s = 0 then
  .bind (BootInfo.readBE32 (data + 12)) fun s irq1 => if s = 0 then
  .bind (get 88) fun s previous => if s = 0 then
  if 0 < first then if first = second then
  if irq0 = (if role = 4 then 11 else 3) then
  if irq1 = (if role = 4 then 9 else 7) then
  if (if previous = 0 then (1 : UInt64) else if previous = first then 1 else 0) = 1 then
  .bind (put 88 first) fun s _ => if s = 0 then mark 512 else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0

private def protectedOverlap (base bytes : UInt64) : UInt64 :=
  if bytes = 0 then 0 else if base ≤ 0xffffffffffffffff - bytes then
    if base < 0x10012000 then if 0x10010000 < base + bytes then 1 else
      if base < 0x10009000 then if 0x10000000 < base + bytes then 1 else
        if base < 0x0c600000 then if 0x0c000000 < base + bytes then 1 else
          if base < 0x02010000 then if 0x02000000 < base + bytes then 1 else
            if base < 0x00102000 then if 0x00101000 < base + bytes then 1 else 0 else 0
          else 0
        else 0
      else 0
    else 0
  else 1

private def otherRegStep (i _ : UInt32) (acc data _ _ _ : UInt64) : Action :=
  .bind (BootInfo.readBE64 (data + i.toUInt64 * 16)) fun s base => if s = 0 then
  .bind (BootInfo.readBE64 (data + i.toUInt64 * 16 + 8)) fun s bytes => if s = 0 then
  if protectedOverlap base bytes = 0 then .done 0 acc else .done invalid 0
  else .done s 0 else .done s 0
private def otherReg (data bytes : UInt64) : Action :=
  if bytes % 16 = 0 then if bytes ≤ 256 then
  .boundedFoldU64 16 otherRegStep (bytes / 16).toUInt32 0 data 0 0 0 fun s v => .done s v
  else .done invalid 0 else .done invalid 0

private def ownedReg (data bytes role : UInt64) : Action :=
  if bytes = 16 then
  .bind (BootInfo.readBE64 data) fun s base => if s = 0 then
  .bind (BootInfo.readBE64 (data + 8)) fun s span => if s = 0 then
  if base = expectedBase role then if span = expectedSpan role then mark 1 else .done invalid 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done invalid 0

private def descriptorProperty (data bytes : UInt64) : Action :=
  if bytes = 16 then
  .bind (BootInfo.readBE64 data) fun s base => if s = 0 then
  .bind (BootInfo.readBE64 (data + 8)) fun s span => if s = 0 then
  if base = 0x10010400 then if span = 256 then mark 128 else .done invalid 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done invalid 0

private def leafProperty (data bytes code role : UInt64) : Action :=
  if code = 32 then
    .bind (equalLiteral data bytes (compatibleCode role)) fun s same => if s = 0 then
    if same = 1 then mark 2 else .done invalid 0 else .done s 0
  else if code = 33 then ownedReg data bytes role else
  if role = 4 then
    if code = 36 then
      if bytes = 4 then .bind (BootInfo.readBE32 data) fun s phandle => if s = 0 then
      if 0 < phandle then .bind (put 80 phandle) fun s _ => if s = 0 then mark 16 else .done s 0
      else .done invalid 0 else .done s 0 else .done invalid 0
    else if code = 48 then fixedCell data bytes 95 32 else
    if code = 47 then fixedCell data bytes 1 64 else
    if code = 45 then fixedCell data bytes 0 128 else
    if code = 49 then if bytes = 0 then mark 256 else .done invalid 0 else
    if code = 50 then interruptContext data bytes role else .done 0 0
  else if role = 5 then
    if code = 50 then interruptContext data bytes role else .done 0 0
  else if code = 34 then fixedCell data bytes (expectedIRQ role) 4 else
  if code = 35 then parentCell data bytes else
  if role = 1 then
    if code = 38 then fixedCell data bytes 1 16 else
    if code = 39 then dynamicCell data bytes 104 32 else
    if code = 40 then dynamicCell data bytes 112 64 else
    if code = 44 then descriptorProperty data bytes else .done 0 0
  else if role = 2 then
    if code = 38 then fixedCell data bytes 1 16 else
    if code = 41 then fixedCell data bytes 65535 32 else
    if code = 42 then fixedCell data bytes 65535 64 else
    if code = 43 then dynamicCell data bytes 120 128 else .done 0 0
  else if role = 6 then
    if code = 51 then fixedCell data bytes 3686400 16 else .done 0 0
  else .done 0 0

private def containerProperty (data bytes code role : UInt64) : Action :=
  if role = 11 then
    if code = 37 then
      .bind (get 192) fun s seen => if s = 0 then
      if seen = 0 then
        if bytes = 4 then .bind (BootInfo.readBE32 data) fun s timebase => if s = 0 then
        if timebase = 10000000 then put 192 1 else .done invalid 0 else .done s 0 else .done invalid 0
      else .done invalid 0 else .done s 0
    else .done 0 0
  else if role = 12 then
    .bind (get 184) fun s flags => if s = 0 then
    let bit := if code = 45 then (1 : UInt64) else if code = 46 then 2 else if code = 52 then 4 else if code = 32 then 8 else 0
    if bit = 0 then .done 0 0 else if flags &&& bit = 0 then
    .bind (if code = 52 then if bytes = 0 then .done 0 1 else .done invalid 0 else
      if code = 32 then equalLiteral data bytes 71 else
      if bytes = 4 then .bind (BootInfo.readBE32 data) fun s cells =>
      if s = 0 then if cells = 2 then .done 0 1 else .done invalid 0 else .done s 0
      else .done invalid 0) fun s valid =>
    if s = 0 then if valid = 1 then put 184 (flags ||| bit) else .done invalid 0 else .done s 0
    else .done invalid 0 else .done s 0
  else .done 0 0

private def unknownCompatible (data bytes : UInt64) : Action :=
  if 6 ≤ bytes then
  .bind (BootInfo.readBE32 data) fun s first => if s = 0 then
  .bind (Access.read8 (data + 4)) fun s fifth => if s = 0 then
  .bind (Access.read8 (data + 5)) fun s sixth => if s = 0 then
  if first = 0x6c656d6d then if fifth = 97 then if sixth = 44 then .done invalid 0 else .done 0 0
  else .done 0 0 else .done 0 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 0

private def beginNode (cursor depth limit : UInt64) : Action :=
  if depth < 16 then
  .bind (BootInfo.readBoundedName (cursor + 4) limit) fun s endName => if s = 0 then
  .bind (findCode (cursor + 4) (endName - cursor - 4) 1 17) fun s code => if s = 0 then
  .bind (if depth = 0 then .done 0 0 else get (256 + (depth - 1) * 8)) fun s parent => if s = 0 then
  if leaf parent = 0 then
  let role := nodeRole parent code
  .bind (get 48) fun s seen => if s = 0 then
  if role = 0 then
    .bind (put (256 + depth * 8) 0) fun s _ => if s = 0 then
    .bind (put 32 (depth + 1)) fun s _ => if s = 0 then put 0 ((endName + 3) &&& 0xfffffffffffffffc) else .done s 0 else .done s 0
  else if seen &&& ((1 : UInt64) <<< role) = 0 then
    .bind (put 48 (seen ||| ((1 : UInt64) <<< role))) fun s _ => if s = 0 then
    .bind (put (256 + depth * 8) role) fun s _ => if s = 0 then
    .bind (if leaf role = 1 then put 64 0 else .done 0 0) fun s _ => if s = 0 then
    .bind (put 32 (depth + 1)) fun s _ => if s = 0 then put 0 ((endName + 3) &&& 0xfffffffffffffffc) else .done s 0
    else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0 else .done s 0
  else .done invalid 0 else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0

private def endNode (cursor depth : UInt64) : Action :=
  if 0 < depth then
  .bind (get (256 + (depth - 1) * 8)) fun s role => if s = 0 then
  .bind (if leaf role = 1 then
    .bind (get 64) fun s flags => if s = 0 then
    if flags = requiredFlags role then .done 0 0 else .done invalid 0 else .done s 0
  else .done 0 0) fun s _ => if s = 0 then
  .bind (put 32 (depth - 1)) fun s _ => if s = 0 then put 0 (cursor + 4) else .done s 0
  else .done s 0 else .done s 0 else .done invalid 0

private def property (cursor depth limit : UInt64) : Action :=
  if depth = 0 then .done invalid 0 else if limit < cursor + 12 then .done invalid 0 else
  .bind (BootInfo.readBE32 (cursor + 4)) fun s bytes => if failed s = true then .done s 0 else
  .bind (BootInfo.readBE32 (cursor + 8)) fun s nameOffset => if failed s = true then .done s 0 else
  .bind (get 16) fun s strings => if failed s = true then .done s 0 else
  .bind (get 24) fun s stringsEnd => if failed s = true then .done s 0 else
  if stringsEnd - strings ≤ nameOffset then .done invalid 0 else
  let data := cursor + 12
  if limit - data < bytes then .done invalid 0 else
  .bind (BootInfo.readBoundedName (strings + nameOffset) stringsEnd) fun s nameEnd => if failed s = true then .done s 0 else
  .bind (findCode (strings + nameOffset) (nameEnd - strings - nameOffset) 32 21) fun s code => if failed s = true then .done s 0 else
  .bind (get (256 + (depth - 1) * 8)) fun s role => if failed s = true then .done s 0 else
  .bind (if leaf role = 1 then leafProperty data bytes code role else
    if role = 11 then containerProperty data bytes code role else
    if role = 12 then containerProperty data bytes code role else
    if code = 33 then
      if 2 ≤ depth then if depth ≤ 3 then
        .bind (get (256 + (depth - 2) * 8)) fun s parent => if s = 0 then
        if parent = 12 then otherReg data bytes else
        if parent = 10 then otherReg data bytes else .done 0 0 else .done s 0
      else
        .bind (get 264) fun s ancestor => if s = 0 then
        if ancestor = 12 then .done invalid 0 else .done 0 0 else .done s 0
      else .done 0 0
    else if code = 32 then unknownCompatible data bytes else .done 0 0) fun s _ => if failed s = true then .done s 0 else
  let next := (data + bytes + 3) &&& 0xfffffffffffffffc
  if next ≤ limit then put 0 next else .done invalid 0

private def tokenStep (_ _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (get 40) fun s ended => if s = 0 then if ended = 1 then .done 0 acc else
  .bind (get 0) fun s cursor => if s = 0 then
  .bind (get 8) fun s limit => if s = 0 then
  .bind (get 32) fun s depth => if s = 0 then
  if cursor + 4 ≤ limit then
  .bind (BootInfo.readBE32 cursor) fun s token => if s = 0 then
  if token = 1 then beginNode cursor depth limit else if token = 2 then endNode cursor depth else
  if token = 3 then property cursor depth limit else if token = 4 then put 0 (cursor + 4) else
  if token = 9 then if depth = 0 then if cursor + 4 = limit then put 40 1 else .done invalid 0 else .done invalid 0
  else .done invalid 0
  else .done s 0 else .done invalid 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0

private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

private def actualDevices : Action :=
  .bind (IO.read32 0x10001000) fun s magic => if s = 0 then
  .bind (IO.read32 0x10001004) fun s version => if s = 0 then
  .bind (IO.read32 0x10001008) fun s device => if s = 0 then
  .bind (IO.read64 0x10010000) fun s paper => if s = 0 then
  .bind (IO.read64 0x10010008) fun s paperVersion => if s = 0 then
  .bind (IO.read64 0x10011000) fun s pen => if s = 0 then
  .bind (IO.read64 0x10011008) fun s penVersion => if s = 0 then
  if magic = 0x74726976 then if version = 2 then if device = 2 then
  if paper = DeviceABI.paperMagic then if paperVersion = 1 then
  if pen = DeviceABI.penMagic then if penVersion = 1 then .done 0 1 else .done invalid 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Descriptor consistency with the actual reset DTB. The complete historical
FDT envelope/memory parser runs first; peripheral checks are additive for this
binding only. Successful output is the actual validated pointer. -/
def validate (pointer expectedBytes width height pressure : UInt64) : Action :=
  .bind BootInfo.validate fun s actual => if s = 0 then if actual = pointer then
  .bind (BootInfo.readBE32 (pointer + 4)) fun s bytes => if s = 0 then
  if bytes = expectedBytes then
  .bind (BootInfo.readBE32 (pointer + 8)) fun s structureOffset => if s = 0 then
  .bind (BootInfo.readBE32 (pointer + 12)) fun s stringsOffset => if s = 0 then
  .bind (BootInfo.readBE32 (pointer + 32)) fun s stringsBytes => if s = 0 then
  .bind (BootInfo.readBE32 (pointer + 36)) fun s structureBytes => if s = 0 then
  .boundedFoldU64 64 clearStep 64 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (put 0 (pointer + structureOffset)) fun s _ => if s = 0 then
  .bind (put 8 (pointer + structureOffset + structureBytes)) fun s _ => if s = 0 then
  .bind (put 16 (pointer + stringsOffset)) fun s _ => if s = 0 then
  .bind (put 24 (pointer + stringsOffset + stringsBytes)) fun s _ => if s = 0 then
  .bind (put 104 width) fun s _ => if s = 0 then
  .bind (put 112 height) fun s _ => if s = 0 then
  .bind (put 120 pressure) fun s _ => if s = 0 then
  .boundedFoldU64 4096 tokenStep 4096 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (get 40) fun s ended => if s = 0 then
  .bind (get 48) fun s seen => if s = 0 then
  .bind (get 72) fun s parent => if s = 0 then
  .bind (get 80) fun s plic => if s = 0 then
  .bind (get 184) fun s socFlags => if s = 0 then
  .bind (get 192) fun s timebase => if s = 0 then
  if ended = 1 then if seen = 0x0fe01cfe then if parent = plic then if 0 < plic then
  if socFlags = 15 then if timebase = 1 then
  .bind actualDevices fun s _ => .done s pointer
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done invalid 0 else .done s 0 else .done invalid 0 else .done s 0

end Lemma.Platform.LemmaSim.DescriptorDTB
