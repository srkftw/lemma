import Lemma.Multimodal.TutorAction
import Lemma.Courses.PackageTarget

/-! Additive application of the historical immutable package format. Only an
exact new source marker designates tutor assistance. No old bytes or checker
references are reinterpreted. Header editionAnchor carries384hex bytes of the
copied action packet; original guest validation precedes decoding. The caller
must validate against its own still-current document anchor before rendering.
This local UART/Store path supplies integrity only, not protected transport. -/
namespace Lemma.Multimodal.TutorPackage
open Lemma.Core0.Memory Lemma.User Lemma.Courses.PackageFormat
private def different (a b : UInt64) : Bool := if a = b then false else true
private def markerByte (i : UInt64) : UInt64 :=
  let word := if i/8 = 0 then 0x75742d616d6d656c else if i/8 = 1 then 0x697373612d726f74 else 0x322f65636e617473
  (word >>> (i%8*8)) &&& 255
private def markerStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Memory.read8 (address+i.toUInt64)) fun s byte => if s = 0 then
  .done 0 (acc ||| (byte ^^^ markerByte i.toUInt64)) else .done s 0
private def nibble (byte : UInt64) : UInt64 :=
  if 48 ≤ byte then if byte ≤ 57 then byte-48 else
  if 97 ≤ byte then if byte ≤ 102 then byte-87 else 256 else 256 else 256
private def decodeStep (i _ : UInt32) (acc source output _ _ : UInt64) : Action :=
  .bind (Memory.read8 (source+i.toUInt64*2)) fun s high => if s = 0 then
  .bind (Memory.read8 (source+i.toUInt64*2+1)) fun s low => if s = 0 then
  let a := nibble high
  let b := nibble low
  if a < 16 then if b < 16 then
  .bind (Memory.write8 (output+i.toUInt64) ((a <<< 4) ||| b)) fun s _ => .done s acc
  else .done malformed 0 else .done malformed 0 else .done s 0 else .done s 0
private def separate (address bytes output : UInt64) : Bool :=
  if address ≤ output then bytes ≤ output-address else output+192 ≤ address

/-- Only the guest's dedicated LOAD intent requires a marked response. An
ordinary historical chooser load retains its original package semantics. -/
def requiredMarkerReason (requested selected marked : UInt64) : UInt64 :=
  if requested = 1 then if selected = 60001 then if marked = 0 then 18 else 0 else 0 else 0

private def annotationByte (claim index : UInt64) : UInt64 :=
  let word := if index/8 = 0 then 0x4946495245564e55 else
    if index/8 = 1 then 0x5349535341204445 else
    if claim = 0 then 0x203a45434e4154 else
    if index/8 = 2 then 0x202d2045434e4154 else
    if index/8 = 3 then 0x474e494b43454843 else
    if index/8 = 4 then 0x474e49444e455020 else 0x203a
  (word >>> (index%8*8)) &&& 255
private def annotationStep (i _ : UInt32) (acc address claim _ _ : UInt64) : Action :=
  .bind (Memory.read8 (address+i.toUInt64)) fun s byte => if s = 0 then
  .done 0 (acc ||| (byte ^^^ annotationByte claim i.toUInt64)) else .done s 0

/-- Requires successful decode of this immutable package into output. Claim0
must begin with exactly `UNVERIFIED ASSISTANCE: `; claim1 with exactly
`UNVERIFIED ASSISTANCE - CHECKING PENDING: `. The guest enforces these23/42
visible ASCII bytes independently of the companion/publisher. Unknown claim
classes remain the action validator's reason14, never checked authority. -/
def annotationReason (address output : UInt64) : Action :=
  .bind (Memory.read64 (output+96)) fun s claim => if s = 0 then
  if 1 < claim then .done 0 0 else
  .bind (Memory.read64 (address+248)) fun s body => if s = 0 then
  let count : UInt64 := if claim = 0 then 23 else 42
  if spanLength body < count then .done 0 19 else
  .boundedFoldU64 42 annotationStep count.toUInt32 0 (address+spanOffset body) claim 0 0 fun s delta =>
  if s = 0 then .done 0 (if delta = 0 then 0 else 19) else .done s 0
  else .done s 0 else .done s 0

/--0 means an ordinary package;1means a decoded marked assistance package.
Output is192 caller-owned bytes disjoint from the full immutable package. -/
def decode (address bytes output : UInt64) : Action :=
  if output%8 = 0 then if address%8 = 0 then if output ≤ 0xffffffffffffffff-192 then
  if separate address bytes output = true then
  .bind (Lemma.Courses.PackageTarget.validate address bytes) fun s _ => if s = 0 then
  .bind (Memory.read64 (address+104)) fun s source => if s = 0 then
  if spanLength source = 24 then
  .boundedFoldU64 24 markerStep 24 0 (address+spanOffset source) 0 0 0 fun s difference => if s = 0 then
  if difference = 0 then
  .bind (Memory.read64 (address+112)) fun s packet => if s = 0 then
  if spanLength packet = 384 then
  .boundedFoldU64 192 decodeStep 192 0 (address+spanOffset packet) output 0 0 fun s _ => if s = 0 then
  .bind (Memory.read64 (address+32)) fun s edition => if s = 0 then
  .bind (Memory.read64 (output+40)) fun s sequence => if s = 0 then
  if edition = sequence then
  .bind (Memory.read64 (address+40)) fun s count => if s = 0 then
  .bind (Memory.read64 (address+136)) fun s kind => if s = 0 then
  .bind (Memory.read64 (address+248)) fun s body => if s = 0 then
  .bind (Memory.read64 (output+104)) fun s textBytes => if s = 0 then
  if count = 1 then if kind = 1 then if spanLength body = textBytes then .done 0 1
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done 0 0 else .done s 0
  else .done 0 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0

/-- Result0 ordinary package;1accepted unverified assistance;32+reason rejected
assistance. No result is an exact-mathematics verdict. Caller must not render a
32+result, and must record actual paper completion/digital PCM separately. -/
def validate (address bytes output context now : UInt64) : Action :=
  .bind (decode address bytes output) fun s marked => if s = 0 then
  if marked = 0 then .done 0 0 else
  .bind (TutorAction.validate output context now) fun s reason => if s = 0 then
  if reason = 0 then
  .bind (annotationReason address output) fun s annotation => if s = 0 then
  if annotation = 0 then .done 0 1 else .done 0 (32+annotation) else .done s 0
  else .done 0 (32+reason)
  else .done s 0 else .done s 0
end Lemma.Multimodal.TutorPackage
