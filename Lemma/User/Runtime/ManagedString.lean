import Lemma.User.Runtime.ManagedBytes

/-! Bounded UTF-8 strings for the additive ordinary String bridge. Every string
is a real owned Arena object. Option.some owns one string child; Option.none is
the genuine immediate constructor and has no allocated object to reclaim. -/
namespace Lemma.User.Runtime.ManagedString
open Lemma.Core0.Memory Lemma.User.Runtime Lemma.User

def maximum : UInt64 := 40
def cookie : UInt64 := 0x3152545352414d4c
def optionCookie : UInt64 := 0x3154504f5254534c
private def invalidBit : UInt64 := 0x8000000000000000

/-- A strict UTF-8 automaton. The first continuation bounds exclude overlong
forms, surrogates and values above U+10FFFF. Counted values are Unicode scalars,
not grapheme clusters. Remaining/low/high/count occupy disjoint scalar fields. -/
def utf8Step (state byte : UInt64) : UInt64 :=
  if state &&& invalidBit = invalidBit then state else
  if 255 < byte then state ||| invalidBit else
  let remaining : UInt64 := state &&& 7
  let count : UInt64 := (state >>> 32) &&& 255
  if remaining = 0 then
    if byte < 128 then (count + (1 : UInt64)) <<< 32 else
    if byte < 194 then state ||| invalidBit else
    if byte < 224 then ((count + (1 : UInt64)) <<< 32) ||| (1 : UInt64) ||| ((128 : UInt64) <<< 8) ||| ((191 : UInt64) <<< 16) else
    if byte < 240 then
      ((count + (1 : UInt64)) <<< 32) ||| (2 : UInt64) |||
        ((if byte = 224 then (160 : UInt64) else 128) <<< 8) |||
        ((if byte = 237 then (159 : UInt64) else 191) <<< 16)
    else if byte < 245 then
      ((count + (1 : UInt64)) <<< 32) ||| (3 : UInt64) |||
        ((if byte = 240 then (144 : UInt64) else 128) <<< 8) |||
        ((if byte = 244 then (143 : UInt64) else 191) <<< 16)
    else state ||| invalidBit
  else
    let low : UInt64 := (state >>> 8) &&& 255
    let high : UInt64 := (state >>> 16) &&& 255
    if byte < low then state ||| invalidBit else
    if high < byte then state ||| invalidBit else
    (count <<< 32) ||| (remaining - (1 : UInt64)) ||| ((128 : UInt64) <<< 8) ||| ((191 : UInt64) <<< 16)

def utf8Complete (state : UInt64) : Bool :=
  if state &&& invalidBit = 0 then state &&& 7 = 0 else false

private def bytesUtf8Step (i _ : UInt32) (state handle length _ _ : UInt64) : Action :=
  if i.toUInt64 < length then
    .bind (ManagedBytes.get handle i.toUInt64) fun s byte =>
    if s = 0 then .done 0 (utf8Step state byte) else .done s 0
  else .done 0 state

private def bytesUtf8 (handle : UInt64) : Action :=
  .bind (ManagedBytes.size handle) fun s length => if s = 0 then
  .boundedFoldU64 48 bytesUtf8Step 48 0 handle length 0 0 fun s state =>
  if s = 0 then .done 0 state else .done s 0 else .done s 0

def validateUTF8 (handle : UInt64) : Action :=
  .bind (bytesUtf8 handle) fun s state =>
  if s = 0 then .done 0 (if utf8Complete state then 1 else 0) else .done s 0

private def stringUtf8Step (i _ : UInt32) (state handle length _ _ : UInt64) : Action :=
  if i.toUInt64 < length then
    .bind (Arena.bytesGet handle (24 + i.toUInt64)) fun s byte =>
    if s = 0 then .done 0 (utf8Step state byte) else .done s 0
  else .done 0 state

/-- Active access validates the complete typed layout and cached scalar count
against the actual bytes. A forged count or malformed byte sequence is rejected. -/
private def shape (handle : UInt64) : Action :=
  .bind (Arena.bytesLength handle) fun s bytes => if s = 0 then
  if bytes = 64 then
  .bind (Arena.bytesReadWord handle 0) fun s actual => if s = 0 then
  if actual = cookie then
  .bind (Arena.bytesReadWord handle 8) fun s length => if s = 0 then
  if length ≤ maximum then
  .bind (Arena.bytesReadWord handle 16) fun s points => if s = 0 then
  if points ≤ length then
  .boundedFoldU64 40 stringUtf8Step 40 0 handle length 0 0 fun s state => if s = 0 then
  if utf8Complete state then
    if ((state >>> 32) &&& 255) = points then .done 0 length else .done Arena.invalid 0
  else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done Arena.invalid 0 else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done Arena.invalid 0 else .done s 0

def byteSize (handle : UInt64) : Action := shape handle
def length (handle : UInt64) : Action :=
  .bind (shape handle) fun s _ => if s = 0 then Arena.bytesReadWord handle 16 else .done s 0

private def location (handle : UInt64) : UInt64 :=
  Arena.page + 128 + (handle &&& 31) * 128

/-- Cancellation-independent typed cleanup uses only real mapped reads and the
allocator's actual generation/reference metadata. It cannot release a foreign
bytes slot merely because the caller supplied its scalar handle. -/
private def rawObject (handle bytes expectedCookie : UInt64) : Action :=
  .bind (Memory.read64 Arena.control) fun s phase => if s = 0 then
  if phase = 1 then
  .bind (Memory.read64 Arena.page) fun s magic => if s = 0 then
  if magic = 0x31414e4552414d4c then
  .bind (Memory.read64 (Arena.page + 8)) fun s version => if s = 0 then
  if version = 1 then
  .bind (Memory.read64 (Arena.control + 16)) fun s count => if s = 0 then
  if count = 0 then .done Arena.lifetime 0 else
  if Arena.capacity < count then .done Arena.lifetime 0 else
  let slot := handle &&& 31
  let generation := handle >>> 5
  if generation = 0 then .done Arena.invalid 0 else
  if Arena.maximumGeneration < generation then .done Arena.invalid 0 else
  if Arena.capacity ≤ slot then .done Arena.invalid 0 else
  let address := location handle
  .bind (Memory.read64 address) fun s state => if s = 0 then
  if state = 1 then
  .bind (Memory.read64 (address + 8)) fun s actualGeneration => if s = 0 then
  if actualGeneration = generation then
  .bind (Memory.read64 (address + 16)) fun s references => if s = 0 then
  if references = 0 then .done Arena.lifetime 0 else
  if 65535 < references then .done Arena.lifetime 0 else
  .bind (Memory.read64 (address + 24)) fun s tag => if s = 0 then
  .bind (Memory.read64 (address + 32)) fun s actualBytes => if s = 0 then
  if tag = Arena.bytesTag then if actualBytes = bytes then
  .bind (Memory.read64 (address + 64)) fun s actualCookie => if s = 0 then
  if actualCookie = expectedCookie then .done 0 address else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done Arena.invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done Arena.invalid 0
  else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done s 0 else .done Arena.lifetime 0 else .done s 0
  else .done Arena.lifetime 0 else .done s 0
  else .done Arena.lifetime 0 else .done s 0

def release (handle : UInt64) : Action :=
  .bind (rawObject handle 64 cookie) fun s _ => if s = 0 then Arena.release handle else .done s 0
def retain (handle : UInt64) : Action :=
  .bind (shape handle) fun s _ => if s = 0 then Arena.retain handle else .done s 0

private def allocate (bytes points : UInt64) : Action :=
  if maximum < bytes then .done Arena.exhausted 0 else
  if bytes < points then .done Arena.invalid 0 else
  .bind Arena.ensure fun s _ => if s = 0 then
  .bind (Arena.newBytes 64) fun s handle => if s = 0 then
  .bind (Arena.bytesWriteWord handle 0 cookie) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 8 bytes) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 16 points) fun s _ =>
  if s = 0 then .done 0 handle else .bind (Arena.release handle) fun _ _ => .done s 0
  else .bind (Arena.release handle) fun _ _ => .done s 0
  else .bind (Arena.release handle) fun _ _ => .done s 0
  else .done s 0 else .done s 0

private def fromBytesStep (i _ : UInt32) (acc input output bytes _ : UInt64) : Action :=
  if i.toUInt64 < bytes then
  .bind (ManagedBytes.get input i.toUInt64) fun s byte => if s = 0 then
  .bind (Arena.bytesSet output (24 + i.toUInt64) byte) fun s _ => .done s acc
  else .done s 0 else .done 0 acc

/-- String.ofByteArray consumes its ByteArray. Erased proof arguments do not
replace runtime UTF-8 validation or authorize malformed target strings. -/
def fromByteArray (input : UInt64) : Action :=
  .bind (ManagedBytes.size input) fun s bytes => if s = 0 then
  if maximum < bytes then .bind (Arena.release input) fun _ _ => .done Arena.exhausted 0 else
  .bind (bytesUtf8 input) fun s state => if s = 0 then
  if utf8Complete state then
  .bind (allocate bytes ((state >>> 32) &&& 255)) fun s output => if s = 0 then
  .boundedFoldU64 40 fromBytesStep 40 0 input output bytes 0 fun s _ => if s = 0 then
  .bind (Arena.release input) fun s _ =>
  if s = 0 then .done 0 output else .bind (Arena.release output) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ => .bind (Arena.release input) fun _ _ => .done s 0
  else .bind (Arena.release input) fun _ _ => .done s 0
  else .bind (Arena.release input) fun _ _ => .done Arena.invalid 0
  else .bind (Arena.release input) fun _ _ => .done s 0
  else .bind (Arena.release input) fun _ _ => .done s 0

private def appendStep (i _ : UInt32) (acc left right output leftBytes : UInt64) : Action :=
  .bind (Arena.bytesReadWord output 8) fun s total => if s = 0 then
  if i.toUInt64 < total then
  .bind (Arena.bytesGet (if i.toUInt64 < leftBytes then left else right)
    (24 + (if i.toUInt64 < leftBytes then i.toUInt64 else i.toUInt64 - leftBytes))) fun s byte =>
  if s = 0 then .bind (Arena.bytesSet output (24 + i.toUInt64) byte) fun s _ => .done s acc
  else .done s 0 else .done 0 acc else .done s 0

/-- Always copies before consuming the left reference. A borrowed right alias
remains valid, including when the source compiler retained an alias of left. -/
def append (left right : UInt64) : Action :=
  .bind (shape left) fun s leftBytes => if s = 0 then
  .bind (shape right) fun s rightBytes => if s = 0 then
  if maximum - leftBytes < rightBytes then .bind (release left) fun _ _ => .done Arena.exhausted 0 else
  .bind (Arena.bytesReadWord left 16) fun s leftPoints => if s = 0 then
  .bind (Arena.bytesReadWord right 16) fun s rightPoints => if s = 0 then
  .bind (allocate (leftBytes + rightBytes) (leftPoints + rightPoints)) fun s output => if s = 0 then
  .boundedFoldU64 40 appendStep 40 0 left right output leftBytes fun s _ => if s = 0 then
  .bind (release left) fun s _ =>
  if s = 0 then .done 0 output else .bind (Arena.release output) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ => .bind (release left) fun _ _ => .done s 0
  else .bind (release left) fun _ _ => .done s 0
  else .bind (release left) fun _ _ => .done s 0
  else .bind (release left) fun _ _ => .done s 0
  else .bind (release left) fun _ _ => .done s 0
  else .bind (release left) fun _ _ => .done s 0

private def toBytesStep (i _ : UInt32) (acc input output bytes _ : UInt64) : Action :=
  if i.toUInt64 < bytes then
  .bind (Arena.bytesGet input (24 + i.toUInt64)) fun s byte => if s = 0 then
  .bind (Arena.bytesSet output (16 + i.toUInt64) byte) fun s _ => .done s acc
  else .done s 0 else .done 0 acc

/-- The upstream primitive consumes its String reference. The copy is published
only after complete byte copying and real input release. A retained alias survives. -/
def toByteArray (input : UInt64) : Action :=
  .bind (shape input) fun s bytes => if s = 0 then
  .bind (Arena.newBytes 64) fun s output => if s = 0 then
  .bind (Arena.bytesWriteWord output 0 ManagedBytes.cookie) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord output 8 bytes) fun s _ => if s = 0 then
  .boundedFoldU64 40 toBytesStep 40 0 input output bytes 0 fun s _ => if s = 0 then
  .bind (release input) fun s _ =>
  if s = 0 then .done 0 output else .bind (Arena.release output) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ => .bind (release input) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ => .bind (release input) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ => .bind (release input) fun _ _ => .done s 0
  else .bind (release input) fun _ _ => .done s 0
  else .bind (release input) fun _ _ => .done s 0

def some (child : UInt64) : Action :=
  .bind (shape child) fun s _ => if s = 0 then
  .bind (Arena.newBytes 16) fun s output => if s = 0 then
  .bind (Arena.bytesWriteWord output 0 optionCookie) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord output 8 child) fun s _ =>
  if s = 0 then .done 0 output else
    .bind (Arena.release output) fun _ _ => .bind (release child) fun _ _ => .done s 0
  else .bind (Arena.release output) fun _ _ => .bind (release child) fun _ _ => .done s 0
  else .bind (release child) fun _ _ => .done s 0
  else .bind (release child) fun _ _ => .done s 0

def getSome (handle : UInt64) : Action :=
  if handle = 0 then .done Arena.invalid 0 else
  .bind (Arena.bytesLength handle) fun s bytes => if s = 0 then
  if bytes = 16 then
  .bind (Arena.bytesReadWord handle 0) fun s actual => if s = 0 then
  if actual = optionCookie then
  .bind (Arena.bytesReadWord handle 8) fun s child => if s = 0 then
  .bind (shape child) fun s _ => .done s child
  else .done s 0 else .done Arena.invalid 0 else .done s 0
  else .done Arena.invalid 0 else .done s 0

def optionTag (handle : UInt64) : Action :=
  if handle = 0 then .done 0 0 else .bind (getSome handle) fun s _ => .done s 1

def retainOption (handle : UInt64) : Action :=
  if handle = 0 then .done 0 0 else
  .bind (getSome handle) fun s _ => if s = 0 then Arena.retain handle else .done s 0

def releaseOption (handle : UInt64) : Action :=
  if handle = 0 then .done 0 0 else
  .bind (rawObject handle 16 optionCookie) fun s address => if s = 0 then
  .bind (Memory.read64 (address + 16)) fun s references => if s = 0 then
  if 1 < references then Arena.release handle else
  .bind (Memory.read64 (address + 72)) fun s child => if s = 0 then
  .bind (release child) fun s _ => if s = 0 then Arena.release handle else .done s 0
  else .done s 0 else .done s 0 else .done s 0

end Lemma.User.Runtime.ManagedString
