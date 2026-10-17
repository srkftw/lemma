import tests.qemu.SoftTlbProbe

/-! Executable translations use ordinary genuinely lowered Lean functions.
The linker assigns valueA's VMA to the tested alias and its load address to
page A. Page B holds valueB's independently compiled leaf. The guest changes
only its PTE; no host writes an instruction, PTE or result into the machine. -/
namespace Lemma.Qemu.SoftTlbExecProbe
open Lemma.Core0.Memory

def valueA (x : UInt64) : UInt64 := x + 111
def valueB (x : UInt64) : UInt64 := x + 222

def run : Action :=
  .boundedFoldU64 512 SoftTlbProbe.clear 512 0 0x82100000 0 0 0 fun s _ =>
  if 0 < s then .done s 1 else
  .boundedFoldU64 512 SoftTlbProbe.l1 512 0 0x82101000 0 0 0 fun s _ =>
  if 0 < s then .done s 2 else
  .boundedFoldU64 512 SoftTlbProbe.l0 512 0 0x82102000 0 0 0 fun s _ =>
  if 0 < s then .done s 3 else
  .platform .physicalWrite64 0x82100000 0xcf 0 0 0 0 fun s _ =>
  if 0 < s then .done s 10 else
  .platform .physicalWrite64 0x82100010 0x20840401 0 0 0 0 fun s _ =>
  if 0 < s then .done s 11 else
  .platform .physicalWrite64 0x82101080 0x20840801 0 0 0 0 fun s _ =>
  if 0 < s then .done s 12 else
  .platform .physicalWrite64 0x82102280 0x20840ccf 0 0 0 0 fun s _ =>
  if 0 < s then .done s 13 else
  .platform .physicalWrite64 0x82106000 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 14 else
  .platform .installSatp 0x8000000000082100 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 16 else
  .platform .physicalRead64 0x82106000 0 0 0 0 0 fun s seed =>
  if 0 < s then .done s 17 else
  let second := valueB seed
  let initial := valueA seed
  if second = 222 then
  if initial = 111 then
  .platform .physicalWrite64 0x82102280 0x208410cf 0 0 0 0 fun s _ =>
  if 0 < s then .done s 18 else
  .uartWriteByte 87 fun s =>
  if 0 < s then .done s 4 else
  .boundedFoldU64 1000000 SoftTlbProbe.delay 1000000 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 5 else
  .platform .physicalRead64 0x82106000 0 0 0 0 0 fun s seed =>
  if 0 < s then .done s 19 else
  let stale := valueA seed
  .platform .physicalWrite64 0x82105000 stale 0 0 0 0 fun s _ =>
  if 0 < s then .done s 20 else
  .uartWriteByte (if stale = 111 then 78 else if stale = 222 then 66 else 88) fun s =>
  if 0 < s then .done s 6 else
  .platform .installSatp 0x8000000000082100 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 21 else
  .platform .physicalRead64 0x82106000 0 0 0 0 0 fun s seed =>
  if 0 < s then .done s 22 else
  let fresh := valueA seed
  .platform .physicalWrite64 0x82105008 fresh 0 0 0 0 fun s _ =>
  if 0 < s then .done s 23 else
  .uartWriteByte (if fresh = 222 then 70 else 88) fun s =>
  if 0 < s then .done s 7 else
  -- Copy the actual compiler-produced pageA leaf into pageB. No instruction
  -- encoding is authored by this program or supplied by the host observer.
  .platform .physicalRead64 0x82103000 0 0 0 0 0 fun s compiledA =>
  if 0 < s then .done s 24 else
  .platform .physicalWrite64 0x82104000 compiledA 0 0 0 0 fun s _ =>
  if 0 < s then .done s 25 else
  .uartWriteByte 77 fun s =>
  if 0 < s then .done s 26 else
  .boundedFoldU64 1000000 SoftTlbProbe.delay 1000000 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 27 else
  .platform .physicalRead64 0x82106000 0 0 0 0 0 fun s seed =>
  if 0 < s then .done s 28 else
  let unfenced := valueA seed
  .platform .physicalWrite64 0x82105010 unfenced 0 0 0 0 fun s _ =>
  if 0 < s then .done s 29 else
  .platform .fenceInstruction 0 0 0 0 0 0 fun s _ =>
  if 0 < s then .done s 30 else
  .platform .physicalRead64 0x82106000 0 0 0 0 0 fun s seed =>
  if 0 < s then .done s 31 else
  let synchronized := valueA seed
  .platform .physicalWrite64 0x82105018 synchronized 0 0 0 0 fun s _ =>
  if 0 < s then .done s 32 else
  .uartWriteByte (if unfenced = 111 then 85 else if unfenced = 222 then 83 else 88) fun s =>
  if 0 < s then .done s 33 else
  .uartWriteByte (if synchronized = 111 then 73 else 88) fun s =>
  if 0 < s then .done s 34 else
  .done 0 synchronized
  else .done 1 initial
  else .done 1 second
end Lemma.Qemu.SoftTlbExecProbe
