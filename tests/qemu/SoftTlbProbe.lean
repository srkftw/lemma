import Lemma.Core0.Memory

/-! A narrowly scoped guest-issued Sv39 stale-data-translation probe.
All PTE construction, mutation, reads and the delay are checked Lean Actions.
No host debugger writes a PTE or substitutes a guest SFENCE. -/
namespace Lemma.Qemu.SoftTlbProbe
open Lemma.Core0.Memory

def clear (index count : UInt32) (acc root c1 c2 c3 : UInt64) : Action :=
  let ignored := count + 0
  let ignored2 := acc + c1 + c2 + c3
  .platform .physicalWrite64 (root + index.toUInt64 * 8) 0 0 0 0 0 fun status _ =>
    .done status (ignored.toUInt64 + ignored2 * 0)

def l1 (index count : UInt32) (acc root c1 c2 c3 : UInt64) : Action :=
  let ignored := count + 0
  let ignored2 := acc + c1 + c2 + c3
  .platform .physicalWrite64 (root + index.toUInt64 * 8)
    (0x20000000 + index.toUInt64 * 0x80000 + 0xcf) 0 0 0 0 fun status _ =>
    .done status (ignored.toUInt64 + ignored2 * 0)

def l0 (index count : UInt32) (acc root c1 c2 c3 : UInt64) : Action :=
  let ignored := count + 0
  let ignored2 := acc + c1 + c2 + c3
  .platform .physicalWrite64 (root + index.toUInt64 * 8)
    ((0x82000000 + index.toUInt64 * 4096) / 4 + 0xcf) 0 0 0 0 fun status _ =>
    .done status (ignored.toUInt64 + ignored2 * 0)

def delay (index count : UInt32) (acc c0 c1 c2 c3 : UInt64) : Action :=
  .platform .physicalRead64 0x82106000 0 0 0 0 0 fun status value =>
    .done status (acc + value + index.toUInt64 + count.toUInt64 * 0 + c0 * 0 + c1 * 0 + c2 * 0 + c3 * 0)

def run : Action :=
  .boundedFoldU64 512 clear 512 0 0x82100000 0 0 0 fun s _ =>
  if 0 < s then .done s 1 else
  .boundedFoldU64 512 l1 512 0 0x82101000 0 0 0 fun s _ =>
  if 0 < s then .done s 2 else
  .boundedFoldU64 512 l0 512 0 0x82102000 0 0 0 fun s _ =>
  if 0 < s then .done s 3 else
  .platform .physicalWrite64 0x82100000 0xcf 0 0 0 0 fun s _ =>
  if 0 < s then .done s 10 else
  .platform .physicalWrite64 0x82100010 0x20840401 0 0 0 0 fun s _ =>
  if 0 < s then .done s 11 else
  .platform .physicalWrite64 0x82101080 0x20840801 0 0 0 0 fun s _ =>
  if 0 < s then .done s 12 else
  .platform .physicalWrite64 0x82102280 0x20840cc7 0 0 0 0 fun s _ =>
  if 0 < s then .done s 13 else
  .platform .physicalWrite64 0x82103000 111 0 0 0 0 fun s _ =>
  if 0 < s then .done s 14 else
  .platform .physicalWrite64 0x82104000 222 0 0 0 0 fun s _ =>
  if 0 < s then .done s 15 else
  .platform .installSatp 0x8000000000082100 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 16 else
  .platform .physicalRead64 0x82050000 0 0 0 0 0 fun s initial =>
  if 0 < s then .done s 17 else
  if initial < 111 then .done 1 initial else
  if 111 < initial then .done 1 initial else
  .platform .physicalWrite64 0x82102280 0x208410c7 0 0 0 0 fun s _ =>
  if 0 < s then .done s 18 else
  .uartWriteByte 87 fun s => -- W: warmed read, then actual guest PTE mutation.
  if 0 < s then .done s 4 else
  .boundedFoldU64 1000000 delay 1000000 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 5 else
  .platform .physicalRead64 0x82050000 0 0 0 0 0 fun s stale =>
  if 0 < s then .done s 19 else
  .platform .physicalWrite64 0x82105000 stale 0 0 0 0 fun s _ =>
  if 0 < s then .done s 20 else
  .uartWriteByte (if stale = 111 then 78 else if stale = 222 then 66 else 88) fun s =>
  if 0 < s then .done s 6 else
  .platform .installSatp 0x8000000000082100 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 21 else
  .platform .physicalRead64 0x82050000 0 0 0 0 0 fun s fresh =>
  if 0 < s then .done s 22 else
  .platform .physicalWrite64 0x82105008 fresh 0 0 0 0 fun s _ =>
  if 0 < s then .done s 23 else
  .uartWriteByte (if fresh = 222 then 70 else 88) fun s =>
  if 0 < s then .done s 7 else
  .done 0 fresh
end Lemma.Qemu.SoftTlbProbe
