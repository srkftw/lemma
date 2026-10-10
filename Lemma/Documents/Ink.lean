import Lemma.User.Memory
import Lemma.Ink.Geometry

/-! Notebook ink records v1. Every field is little-endian u64. Original raw
72-byte controller samples remain distinct from display coordinates. The page
index retains immutable chunk/stroke IDs plus a versioned visibility edit log.
Only the current page index and one streamed ink chunk need be resident. -/
namespace Lemma.Documents.Ink
open Lemma.Core0.Memory
open Lemma.User

private def statusFailed (s : UInt8) : Bool := if s = 0 then false else true
private def different (a b : UInt64) : Bool := if a = b then false else true

def magic : UInt64 := 0x314b4e49414d454c
def version : UInt64 := 1
def maximumPages : UInt64 := 64
def maximumSamples : UInt64 := 384
def maximumEntries : UInt64 := 512
def maximumEdits : UInt64 := 512
def headerBytes : UInt64 := 128
def sampleBytes : UInt64 := 72
def pageBytes : UInt64 := 20608
def editOffset : UInt64 := 12416
def malformed : UInt8 := 234
def full : UInt8 := 235
def field (buffer offset : UInt64) : Action := Memory.read64 (buffer + offset)
def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value
def entry (buffer index : UInt64) : UInt64 := buffer + 128 + index * 24
def edit (buffer index : UInt64) : UInt64 := buffer + editOffset + index * 16

private def zeroStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (buffer + i.toUInt64 * 8) 0) fun s _ => .done s acc

def emptyPage (buffer page : UInt64) : Action :=
  if page = 0 then .done malformed 0 else if maximumPages < page then .done malformed 0 else
  .boundedFoldU64 2576 zeroStep 2576 0 buffer 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 0 magic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 8 version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 16 2) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 24 page) fun s _ => .done s 0


def root (buffer pages brush : UInt64) : Action :=
  if pages = 0 then .done malformed 0 else if maximumPages < pages then .done malformed 0 else
  .boundedFoldU64 8 zeroStep 8 0 buffer 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 0 magic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 8 version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 16 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 24 pages) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 32 brush) fun s _ => .done s 0


def chunk (buffer page stroke brush pressureMaximum : UInt64) : Action :=
  .boundedFoldU64 16 zeroStep 16 0 buffer 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 0 magic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 8 version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 16 3) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 24 page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 32 stroke) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 56 brush) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 64 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 88 pressureMaximum) fun s _ => .done s 0



def finishChunk (buffer count lifecycle : UInt64) : Action :=
  if count = 0 then .done malformed 0 else if maximumSamples < count then .done full 0 else
  if lifecycle &&& 0xfffffffffffffff8 = 0 then
  .bind (put buffer 48 count) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 112 lifecycle) fun s _ => .done s (128 + count * 72)
   else .done malformed 0

private def entryValidateStep (i count : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field (entry buffer i.toUInt64) 0) fun s object => if statusFailed s = true then .done s 0 else
  .bind (field (entry buffer i.toUInt64) 8) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (field (entry buffer i.toUInt64) 16) fun s visible => if statusFailed s = true then .done s 0 else
  if i < count then
    if 0x10000 < object then if 0 < stroke then if visible ≤ 1 then .done 0 (acc + 1)
    else .done malformed 0 else .done malformed 0 else .done malformed 0
  else if object ||| stroke ||| visible = 0 then .done 0 acc else .done malformed 0


private def editValidateStep (i count : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field (edit buffer i.toUInt64) 0) fun s kind => if statusFailed s = true then .done s 0 else
  .bind (field (edit buffer i.toUInt64) 8) fun s stroke => if statusFailed s = true then .done s 0 else
  if i < count then
    if (if kind = 1 then true else if kind = 2 then true else false) = true then
    if 0 < stroke then .done 0 (acc + 1) else .done malformed 0
    else .done malformed 0
  else if kind ||| stroke = 0 then .done 0 acc else .done malformed 0


def validatePage (buffer page : UInt64) : Action :=
  .bind (field buffer 0) fun s observed => if statusFailed s = true then .done s 0 else
  .bind (field buffer 8) fun s v => if statusFailed s = true then .done s 0 else
  .bind (field buffer 16) fun s kind => if statusFailed s = true then .done s 0 else
  .bind (field buffer 24) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (field buffer 32) fun s count => if statusFailed s = true then .done s 0 else
  .bind (field buffer 40) fun s edits => if statusFailed s = true then .done s 0 else
  .bind (field buffer 48) fun s cursor => if statusFailed s = true then .done s 0 else
  if observed = magic then if v = version then if kind = 2 then if identity = page then
  if count ≤ maximumEntries then if edits ≤ maximumEdits then if cursor ≤ edits then
  .boundedFoldU64 512 entryValidateStep count.toUInt32 0 buffer 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 512 editValidateStep edits.toUInt32 0 buffer 0 0 0 fun s _ => .done s count

  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0


private def visibilityStep (i _ : UInt32) (acc buffer stroke visible _ : UInt64) : Action :=
  .bind (field (entry buffer i.toUInt64) 8) fun s observed => if statusFailed s = true then .done s 0 else
  if observed = stroke then
    .bind (put (entry buffer i.toUInt64) 16 visible) fun s _ => .done s (acc + 1)
  else .done 0 acc

def visibility (buffer stroke visible : UInt64) : Action :=
  .bind (field buffer 32) fun s count => if statusFailed s = true then .done s 0 else
  if count ≤ maximumEntries then if visible ≤ 1 then
  .boundedFoldU64 512 visibilityStep count.toUInt32 0 buffer stroke visible 0 fun s n => .done s n
  else .done malformed 0 else .done malformed 0

def addEntry (buffer object stroke : UInt64) : Action :=
  .bind (field buffer 32) fun s count => if statusFailed s = true then .done s 0 else
  if count < maximumEntries then
  .bind (put (entry buffer count) 0 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put (entry buffer count) 8 stroke) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put (entry buffer count) 16 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 32 (count + 1)) fun s _ => .done s count

  else .done full 0

private def clearEditsStep (i _ : UInt32) (acc buffer start _ _ : UInt64) : Action :=
  .bind (put (edit buffer (start + i.toUInt64)) 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put (edit buffer (start + i.toUInt64)) 8 0) fun s _ => .done s acc

def addEdit (buffer kind stroke : UInt64) : Action :=
  .bind (field buffer 48) fun s cursor => if statusFailed s = true then .done s 0 else
  .bind (field buffer 40) fun s count => if statusFailed s = true then .done s 0 else
  if cursor < maximumEdits then if cursor ≤ count then if count ≤ maximumEdits then
  .boundedFoldU64 512 clearEditsStep (count - cursor).toUInt32 0 buffer cursor 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put (edit buffer cursor) 0 kind) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put (edit buffer cursor) 8 stroke) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 40 (cursor + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 48 (cursor + 1)) fun s _ => .done s cursor

   else .done malformed 0 else .done malformed 0 else .done full 0

def undo (buffer : UInt64) : Action :=
  .bind (field buffer 48) fun s cursor => if statusFailed s = true then .done s 0 else
  if cursor = 0 then .done 0 0 else if maximumEdits < cursor then .done malformed 0 else
  .bind (field (edit buffer (cursor - 1)) 0) fun s kind => if statusFailed s = true then .done s 0 else
  .bind (field (edit buffer (cursor - 1)) 8) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (visibility buffer stroke (if kind = 1 then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 48 (cursor - 1)) fun s _ => .done s stroke


def redo (buffer : UInt64) : Action :=
  .bind (field buffer 48) fun s cursor => if statusFailed s = true then .done s 0 else
  .bind (field buffer 40) fun s count => if statusFailed s = true then .done s 0 else
  if cursor = count then .done 0 0 else if count < cursor then .done malformed 0 else
  if maximumEdits < count then .done malformed 0 else
  .bind (field (edit buffer cursor) 0) fun s kind => if statusFailed s = true then .done s 0 else
  .bind (field (edit buffer cursor) 8) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (visibility buffer stroke (if kind = 1 then 1 else 0)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put buffer 48 (cursor + 1)) fun s _ => .done s stroke


def pageY (raw maximum sourceHeight : UInt64) : UInt64 :=
  let pixel := Lemma.Ink.Geometry.pixel (Lemma.Ink.Geometry.normalized raw maximum) sourceHeight
  if pixel ≤ 160 then 0 else (pixel - 160) * 0x1000000 / (sourceHeight - 161)

def displayY (normalized height : UInt64) : UInt64 :=
  let pixel := 160 + Lemma.Ink.Geometry.pixel normalized (height - 160)
  (pixel * 0x1000000 + height - 2) / (height - 1)

end Lemma.Documents.Ink
