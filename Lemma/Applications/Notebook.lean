import Lemma.Multimodal.TutorPackage
import Lemma.Multimodal.SchoolPacket
import Lemma.Services.Arithmetic.ClientV8
import Lemma.User.Multimodal
import Lemma.Documents.MathematicsEntry
import Lemma.Courses.NumberPad
import Lemma.Courses.PackageReader
import Lemma.Courses.PackageCommand
import Lemma.Courses.SchoolSubmission
import Lemma.Courses.PackageRender
import Lemma.Courses.ControlRender
import Lemma.Courses.PackageWorkspace
import Lemma.Courses.BrowseHistory
import Lemma.Courses.ReaderLocation
import Lemma.Courses.WorkspaceCodec
import Lemma.Courses.PackageAwaitClient
import Lemma.Services.Store.RecoveryClient
import Lemma.Notebook.RetryPolicy
import Lemma.Notebook.RetryClosurePolicy
import Lemma.Notebook.RetryWorkspacePolicy
import Lemma.Notebook.RetryReaderPolicy
import Lemma.Notebook.ControlBacklog
import Lemma.Ink.Surface
import Lemma.Ink.Rasterizer
import Lemma.Documents.Ink
import Lemma.Services.Store.Client
import Lemma.User.CapabilityConsole
import Lemma.Courses.Arithmetic
import Lemma.Courses.ArithmeticAligned
import Lemma.Services.Arithmetic.ClientV2
import Lemma.Services.Arithmetic.ClientV3
import Lemma.Services.Arithmetic.ClientV5
import Lemma.Services.Arithmetic.ClientV7
import Lemma.Documents.MathematicsClosure
import Lemma.Services.Arithmetic.ClientV6
import Lemma.Documents.MathematicsString
import Lemma.Documents.MathematicsArray
import Lemma.Services.Arithmetic.ClientV4
import Lemma.Documents.MathematicsBytes

/-! Capability-isolated pen notebook. Pixels, input interpretation, raw ink,
page/edit records and save publication execute in compiled User Lean. Two
bounded ink buffers let input continue while the store flushes another chunk.
The framebuffer and current page index are owned virtual memory; previous page
history is streamed from the document service when that page is reopened. -/
namespace Lemma.Applications.Notebook

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Ink

private def statusFailed (s : UInt8) : Bool := if s = 0 then false else true
private def different (a b : UInt64) : Bool := if a = b then false else true

def state : UInt64 := 0x20800
def raw : UInt64 := 0x20300
def context : UInt64 := 0x20400
private def rawCaptureReadyFlag : UInt64 := state + 736
private def schoolActivityFlag : UInt64 := state + 760
-- These lifecycle gates are used by the first ordinary Save, before the
-- optional multimodal/queue arenas exist. Keep them in the owned boot BSS,
-- below packageAllocationAddress and the outgoing Store packet at0x20b00.
private def schoolQueueReadyFlag : UInt64 := state + 712
private def schoolQueueError : UInt64 := state + 720
private def schoolSubmissionHeader : UInt64 := Lemma.User.Multimodal.records + 2560
def outgoing : UInt64 := 0x20b00
def incoming : UInt64 := 0x20c00
def ink0 : UInt64 := 0x300000
def ink1 : UInt64 := 0x308000
def pageIndex : UInt64 := 0x310000
def loadedInk : UInt64 := 0x318000
def rootBuffer : UInt64 := 0x320000
def mathematics : UInt64 := 0x329000
def mathematicsSave : UInt64 := 0x32a000
def mathematicsIO : UInt64 := 0x32b000
-- Root records use the first64 bytes of their page. The remaining bounded
-- bitmap and a separate owned queue coalesce at most16384 controller tiles.
def dirtyBitmap : UInt64 := rootBuffer + 512
def dirtyQueue : UInt64 := 0x321000
private def get (slot : UInt64) : Action := Memory.read64 (state + slot)
private def put (slot value : UInt64) : Action := Memory.write64 (state + slot) value
private def failed : Action := .done 95 0
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def maximum (a b : UInt64) : UInt64 := if a < b then b else a

/-- A fresh checkpoint Begin is only Pending. Only a matching Status completion
may authorize the notebook's Saved transition; unknown detail is a failure. -/
def checkpointResponseStatus (operation detail : UInt64) : UInt8 :=
  if operation = 12 then if detail = 1 then 0 else 234 else
  if operation = 13 then if detail ≤ 1 then 0 else 234 else 234

/-- Explicit Save confirms previously acknowledged data, without checkpointing.
The prior ACK is captured before issuing Inspect; mounting/read-only/error mode
or a regressed sequence cannot confirm it. Outstanding local writing is checked
separately before submission and before displaying Saved. -/
def saveResponseStatus (operation mode observed prior : UInt64) : UInt8 :=
  if operation = 8 then if mode = 1 then if prior ≤ observed then 0 else 234
  else 234 else 234

/-- Developer observations originate in the authorized guest consumer. These
bounded records describe UI commit state without host document parsing. -/
private def reportCommitState (tag value object : UInt64) : Action :=
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (if tag = 0x421 then
    .bind (get 112) fun s tail => if statusFailed s = true then .done s 0 else
    .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 rawCaptureReadyFlag) fun s ready => if statusFailed s = true then .done s 0 else
    .bind (if ready = 1 then Memory.read64 (Lemma.User.Multimodal.records+2448) else .done 0 0)
      fun s captured => if statusFailed s = true then .done s 0 else
    .done 0 (if tail ||| pinned ||| captured = 0 then tag else 0x423)
    else .done 0 tag) fun s observedTag => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console observedTag value page ns object

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := ink0 + i.toUInt64 * 4096
  .bind (Syscall.allocatePage address) fun s actual => if statusFailed s = true then .done s 0 else
  if actual = address then .done 0 (acc + 1) else failed

private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (if i = 0 then
    .bind (Memory.write64 rawCaptureReadyFlag 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 schoolActivityFlag 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 schoolQueueReadyFlag 0) fun s _ => if statusFailed s = true then .done s 0 else
    Memory.write64 schoolQueueError 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

private def nextRequest : Action :=
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  if request < 0x7ffffffffffffffe then
  .bind (put 176 (request + 1)) fun s _ => .done s (request + 1) else .done 235 0

/-- Concurrent school queue receipts can arrive before an older foreground
reply is consumed. Preserve the greatest observed Store sequence; this is an
observation floor, never a manufactured Save or queue acknowledgement. -/
private def observeStoreSequence (sequence : UInt64) : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  if school = 1 then
    .bind (get 128) fun s prior => if statusFailed s = true then .done s 0 else put 128 (maximum prior sequence)
  else put 128 sequence

private def blocking (operation object transaction offset count source : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.call endpoint outgoing incoming operation ns object transaction offset count source request)
    fun s sequence =>
  .bind (observeStoreSequence sequence) fun stored _ => if statusFailed stored = true then .done stored 0 else .done s sequence

private def readPartStep (i _ : UInt32) (acc object target length _ : UInt64) : Action :=
  let offset := i.toUInt64 * 128
  let count := minimum 128 (length - offset)
  .bind (blocking 5 object 0 offset count 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 56) fun s actualCount => if statusFailed s = true then .done s 0 else
  if different actualCount count = true then .done 234 0 else
  .bind (Lemma.Services.Store.Format.copy (Lemma.Services.Store.Client.responseData incoming) (target + offset) count) fun s _ =>
  .done s (acc + count)

/-- Read an exact fixed record through bounded IPC. A short read is malformed
before any bytes from that reply enter the destination. -/
def readObject (object target length : UInt64) : Action :=
  if length ≤ 32768 then
  .boundedFoldU64 256 readPartStep ((length + 127) / 128).toUInt32 0 object target length 0 fun s n => .done s n
  else .done 234 0

/-- Check the resident edit cursor before changing visibility or adding an
operation. A new operation may replace a redo suffix, but never exceed512. -/
def preflightEdit (buffer : UInt64) : Action :=
  .bind (Lemma.Documents.Ink.field buffer 40) fun s edits => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field buffer 48) fun s cursor => if statusFailed s = true then .done s 0 else
  if 512 < edits then .done 234 0 else if edits < cursor then .done 234 0 else
  if cursor = 512 then .done 235 0 else .done 0 cursor

/-- Reserve logical index capacity before publishing an immutable chunk.
Only the first chunk needs a new edit; continuations share its stroke/edit ID.
This read-only preflight does not advance IDs or alter resident records. -/
def preflightChunk (buffer starting : UInt64) : Action :=
  if 1 < starting then .done 234 0 else
  .bind (Lemma.Documents.Ink.field buffer 32) fun s count => if statusFailed s = true then .done s 0 else
  if 512 < count then .done 234 0 else if count = 512 then .done 235 0 else
  if starting = 0 then .done 0 count else
  .bind (preflightEdit buffer) fun s _ => .done s count

/-- Twenty bounded text cells: full commit state, namespace, page and width.
Read-only is written READ ONLY because the small authored alphabet has no dash. -/
def statusCharacter (save index ns page brush : UInt64) : UInt64 :=
  if index < 9 then
    if save = 0 then
      if index = 0 then 83 else if index = 1 then 65 else if index = 2 then 86 else
      if index = 3 then 69 else if index = 4 then 68 else 32
    else if save = 1 then
      if index = 0 then 80 else if index = 1 then 69 else if index = 2 then 78 else
      if index = 3 then 68 else if index = 4 then 73 else if index = 5 then 78 else
      if index = 6 then 71 else 32
    else if save = 2 then
      if index = 0 then 70 else if index = 1 then 65 else if index = 2 then 73 else
      if index = 3 then 76 else if index = 4 then 69 else if index = 5 then 68 else 32
    else
      if index = 0 then 82 else if index = 1 then 69 else if index = 2 then 65 else
      if index = 3 then 68 else if index = 5 then 79 else if index = 6 then 78 else
      if index = 7 then 76 else if index = 8 then 89 else 32
  else if index = 10 then 78 else if index = 11 then 48 + ns else
    if index = 13 then 80 else if index = 14 then 48 + page / 10 else
    if index = 15 then 48 + page % 10 else if index = 17 then 87 else
    if index = 18 then 48 + brush / 256 else 32

/-- The additive COURSE label is a bounded scalar presentation literal. Keep
the historical footer's audited sparse switch unchanged. -/
def courseCharacter (index : UInt64) : UInt64 :=
  if 22 ≤ index then
    if index < 28 then (0x455352554f43 >>> ((index - 22) * 8)) &&& 255 else 32
  else 32

/-- Square3-pixel glyphs in12-pixel cells, inside336×16 owned pixels. -/
def statusPixel (x y ns page save brush : UInt64) : UInt64 :=
  if x < 336 then if y < 15 then
  let withinCell := x % 12
  if withinCell < 9 then
    let index := x / 12
    let code := if 22 ≤ index then courseCharacter index else statusCharacter save index ns page brush
    if (Surface.letter code >>> (14 - (y / 3 * 3 + withinCell / 3))) &&& 1 = 1 then 0 else 15
  else 15 else 15 else 15

private def statusStep (i _ : UInt32) (acc ns page save dimensions : UInt64) : Action :=
  let x := (i.toUInt64 % 168) * 2
  let y := i.toUInt64 / 168
  let brush := dimensions &&& 0xffff
  let width := dimensions >>> 16
  let packed := (statusPixel x y ns page save brush <<< 4) ||| statusPixel (x + 1) y ns page save brush
  .bind (Memory.write8 (Surface.framebuffer + (132 + y) * ((width + 1) / 2) + (24 + x) / 2) packed) fun s _ => .done s acc

private def statusBar : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s save => if statusFailed s = true then .done s 0 else
  .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 2688 statusStep 2688 0 ns page save (brush ||| (width <<< 16)) fun s _ => .done s 0

private def dirty (x0 y0 x1 y1 : UInt64) : Action :=
  .bind (get 336) fun s oldX => if statusFailed s = true then .done s 0 else
  .bind (get 344) fun s oldY => if statusFailed s = true then .done s 0 else
  .bind (get 352) fun s endX => if statusFailed s = true then .done s 0 else
  .bind (get 360) fun s endY => if statusFailed s = true then .done s 0 else
  .bind (put 336 (minimum x0 oldX)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 (minimum y0 oldY)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 352 (maximum x1 endX)) fun s _ => if statusFailed s = true then .done s 0 else
  put 360 (maximum y1 endY)

private def clearDirtyStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (dirtyBitmap + i.toUInt64 * 8) 0) fun s _ => .done s acc

private def clearDirtyTiles : Action :=
  .boundedFoldU64 256 clearDirtyStep 256 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 456 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 464 0) fun s _ => if statusFailed s = true then .done s 0 else put 472 0

private def queuePut (slot index : UInt64) : Action :=
  let address := dirtyQueue + slot / 4 * 8
  let shift := slot % 4 * 16
  .bind (Memory.read64 address) fun s word => if statusFailed s = true then .done s 0 else
  Memory.write64 address ((word &&& ~~~((0xffff : UInt64) <<< shift)) ||| (index <<< shift))

private def queueGet (slot : UInt64) : Action :=
  .bind (Memory.read64 (dirtyQueue + slot / 4 * 8)) fun s word =>
  if statusFailed s = true then .done s 0 else .done 0 ((word >>> (slot % 4 * 16)) &&& 0xffff)

private def markDirtyTile (index : UInt64) : Action :=
  if 16384 ≤ index then .done 234 0 else
  let address := dirtyBitmap + index / 8
  let mask := (1 : UInt64) <<< (index % 8)
  .bind (Memory.read8 address) fun s bits => if statusFailed s = true then .done s 0 else
  if bits &&& mask = mask then .done 0 index else
  .bind (get 456) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 472) fun s head => if statusFailed s = true then .done s 0 else
  if 16384 ≤ count then .done 235 0 else if 16384 ≤ head then .done 234 0 else
  .bind (queuePut head index) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write8 address (bits ||| mask)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 472 ((head + 1) % 16384)) fun s _ => if statusFailed s = true then .done s 0 else put 456 (count + 1)

private def uploadTileIndex (surface dimensions index : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let columns := (width + 31) / 32
  if columns * ((height + 31) / 32) ≤ index then .done 234 0 else
  let x := (index % columns) * 32
  let y := (index / columns) * 32
  .bind (Surface.loadTile x y width height) fun s _ => if statusFailed s = true then .done s 0 else
  Surface.uploadTile surface x y width height

private def restorePaperStep (_ _ : UInt32) (acc surface dimensions _ _ : UInt64) : Action :=
  .bind (get 488) fun s index => if statusFailed s = true then .done s 0 else
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  if ((width + 31) / 32) * ((height + 31) / 32) ≤ index then .done 0 acc else
  .bind (uploadTileIndex surface dimensions index) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 488 (index + 1)) fun s _ => if statusFailed s = true then .done s 0 else .done 0 (acc + 1)

/-- Full-controller restoration uses the same four-tile budget and owned
Surface-v2 packet as ordinary dirty progress. The cursor names only the prefix
actually accepted by the controller; a failed suffix remains for retry. -/
def restorePaperBatch (surface dimensions : UInt64) : Action :=
  .bind (get 488) fun s index => if statusFailed s = true then .done s 0 else
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let total := ((width + 31) / 32) * ((height + 31) / 32)
  if total ≤ index then .done 0 0 else
  if 4096 < width then .done 16 0 else if 4096 < height then .done 16 0 else
  let amount := minimum 4 (total - index)
  let lanes := index ||| ((index + 1) <<< 16) |||
    ((index + 2) <<< 32) ||| ((index + 3) <<< 48)
  -- Surface-v2 requires zero inactive lanes. Avoid a shift by 64 for the
  -- complete batch; a single mask clips the final one, two or three lanes.
  let packed := if amount = 4 then lanes else
    lanes &&& (((1 : UInt64) <<< (amount * 16)) - 1)
  .bind (Surface.uploadIndexedBulk surface width height packed amount) fun result completed =>
  if amount < completed then .done 95 0 else
  if completed = 0 then .done result 0 else
  .bind (put 488 (index + completed)) fun s _ =>
  if statusFailed s = true then .done s 0 else .done result completed

private def uploadDirtyStep (_ _ : UInt32) (acc surface dimensions _ _ : UInt64) : Action :=
  .bind (get 456) fun s count => if statusFailed s = true then .done s 0 else
  if count = 0 then .done 0 acc else if 16384 < count then .done 234 0 else
  .bind (get 464) fun s tail => if statusFailed s = true then .done s 0 else
  if 16384 ≤ tail then .done 234 0 else
  .bind (queueGet tail) fun s index => if statusFailed s = true then .done s 0 else
  .bind (uploadTileIndex surface dimensions index) fun s _ => if statusFailed s = true then .done s 0 else
  let address := dirtyBitmap + index / 8
  let mask := (1 : UInt64) <<< (index % 8)
  .bind (Memory.read8 address) fun s bits => if statusFailed s = true then .done s 0 else
  if bits &&& mask = 0 then .done 234 0 else
  .bind (Memory.write8 address (bits ^^^ mask)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 464 ((tail + 1) % 16384)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 456 (count - 1)) fun s _ => if statusFailed s = true then .done s 0 else .done 0 (acc + 1)

private def collectDirtyIndexStep (i _ : UInt32) (packed tail _ _ _ : UInt64) : Action :=
  .bind (queueGet ((tail + i.toUInt64) % 16384)) fun s index => if statusFailed s = true then .done s 0 else
  if 16384 ≤ index then .done 234 0 else
  .bind (Memory.read8 (dirtyBitmap + index / 8)) fun s bits => if statusFailed s = true then .done s 0 else
  if bits &&& ((1 : UInt64) <<< (index % 8)) = 0 then .done 234 0 else
  .done 0 (packed ||| (index <<< (i.toUInt64 * 16)))

/-- Consume only the ordered prefix actually accepted by the unchanged
controller ABI. This helper never uploads, and pending entries stay queued. -/
private def consumeDirtyIndexStep (_ _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (get 456) fun s count => if statusFailed s = true then .done s 0 else
  if count = 0 then .done 234 0 else if 16384 < count then .done 234 0 else
  .bind (get 464) fun s tail => if statusFailed s = true then .done s 0 else
  if 16384 ≤ tail then .done 234 0 else
  .bind (queueGet tail) fun s index => if statusFailed s = true then .done s 0 else
  if 16384 ≤ index then .done 234 0 else
  let address := dirtyBitmap + index / 8
  let mask := (1 : UInt64) <<< (index % 8)
  .bind (Memory.read8 address) fun s bits => if statusFailed s = true then .done s 0 else
  if bits &&& mask = 0 then .done 234 0 else
  .bind (Memory.write8 address (bits ^^^ mask)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 464 ((tail + 1) % 16384)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 456 (count - 1)) fun s _ => if statusFailed s = true then .done s 0 else .done 0 (acc + 1)

private def uploadDirtyBatch (limit surface dimensions : UInt64) : Action :=
  if limit = 0 then .done 0 0 else if 4 < limit then .done 234 0 else
  .bind (get 456) fun s count => if statusFailed s = true then .done s 0 else
  if count = 0 then .done 0 0 else if 16384 < count then .done 234 0 else
  .bind (get 464) fun s tail => if statusFailed s = true then .done s 0 else
  if 16384 ≤ tail then .done 234 0 else
  let amount := minimum limit count
  .boundedFoldU64 4 collectDirtyIndexStep amount.toUInt32 0 tail 0 0 0 fun s packed => if statusFailed s = true then .done s 0 else
  .bind (Surface.uploadIndexedBulk surface (dimensions &&& 0xffff) (dimensions >>> 16) packed amount)
    fun result completed =>
  if amount < completed then .done 95 0 else
  .boundedFoldU64 4 consumeDirtyIndexStep completed.toUInt32 0 0 0 0 0 fun s consumed =>
  if statusFailed s = true then .done s 0 else .done result consumed

/-- Bounded display progress also repairs interrupted refreshes from the owned
framebuffer. Recovery cursor/phase remain ordinary user memory, not document truth. -/
def pumpRefresh : Action :=
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.status surface) fun s status => if statusFailed s = true then .done s 0 else
  if status &&& 1 = 1 then .done 0 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  -- A completed full quality request alone clears controller bit8. If that
  -- accepted request was reset too, start a new complete framebuffer upload.
  .bind (if status &&& 8 = 8 then
    if recovery = 1 then .done 0 0 else
    .bind clearDirtyTiles fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 488 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 480 1) fun s _ => if statusFailed s = true then .done s 0 else
    dirty 0 0 width height
    else put 480 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s x0 => if statusFailed s = true then .done s 0 else
  if x0 = 0xffff then .done 0 0 else
  .bind (get 344) fun s y0 => if statusFailed s = true then .done s 0 else
  .bind (get 352) fun s x1 => if statusFailed s = true then .done s 0 else
  .bind (get 360) fun s y1 => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (if recovery = 1 then
    .boundedFoldU64 4 restorePaperStep 4 0 surface (width ||| (height <<< 16)) 0 0 fun s count => .done s count
    else .done 0 0) fun s uploaded => if statusFailed s = true then .done s 0 else
  .bind (get 488) fun s restored => if statusFailed s = true then .done s 0 else
  if (if recovery = 1 then
    if restored < ((width + 31) / 32) * ((height + 31) / 32) then true else false
    else false) = true then .done 0 0 else
  -- At most four uploads per main-loop iteration. FIFO consumption and store
  -- progress continue between batches; a refresh names only uploaded pixels.
  .boundedFoldU64 4 uploadDirtyStep (4 - uploaded).toUInt32 0 surface (width ||| (height <<< 16)) 0 0 fun s _ =>
  if statusFailed s = true then .done s 0 else
  .bind (get 456) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind (Surface.acceptedSequence surface) fun s previous => if statusFailed s = true then .done s 0 else
  if previous = 0xffffffffffffffff then .done 170 0 else
  .bind (Surface.refresh surface (previous + 1) x0 y0 (x1 - x0) (y1 - y0) 2) fun s sequence =>
  if s = 171 then .done 0 0 else if statusFailed s = true then .done s 0 else
  .bind (put 480 (if recovery = 1 then 2 else 0)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 352 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 360 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 440) fun s opened => if statusFailed s = true then .done s 0 else
  .bind (if opened = 1 then reportCommitState 0x425 sequence 0 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 440 0) fun s _ => .done s sequence
  else .done 0 0

/-- Surface-v2 Package successor only. Keep the historical single-tile
refresh implementation above unchanged for its admitted legacy roots. -/
def pumpRefreshBatched : Action :=
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.status surface) fun s status => if statusFailed s = true then .done s 0 else
  if status &&& 1 = 1 then .done 0 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  -- A completed full quality request alone clears controller bit8. If that
  -- accepted request was reset too, start a new complete framebuffer upload.
  .bind (if status &&& 8 = 8 then
    if recovery = 1 then .done 0 0 else
    .bind clearDirtyTiles fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 488 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 480 1) fun s _ => if statusFailed s = true then .done s 0 else
    dirty 0 0 width height
    else put 480 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s x0 => if statusFailed s = true then .done s 0 else
  if x0 = 0xffff then .done 0 0 else
  .bind (get 344) fun s y0 => if statusFailed s = true then .done s 0 else
  .bind (get 352) fun s x1 => if statusFailed s = true then .done s 0 else
  .bind (get 360) fun s y1 => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (if recovery = 1 then
    .boundedFoldU64 4 restorePaperStep 4 0 surface (width ||| (height <<< 16)) 0 0 fun s count => .done s count
    else .done 0 0) fun s uploaded => if statusFailed s = true then .done s 0 else
  .bind (get 488) fun s restored => if statusFailed s = true then .done s 0 else
  if (if recovery = 1 then
    if restored < ((width + 31) / 32) * ((height + 31) / 32) then true else false
    else false) = true then .done 0 0 else
  -- At most four uploads per main-loop iteration. FIFO consumption and store
  -- progress continue between batches; a refresh names only uploaded pixels.
  .bind (uploadDirtyBatch (4 - uploaded) surface (width ||| (height <<< 16))) fun s _ =>
  if statusFailed s = true then .done s 0 else
  .bind (get 456) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind (Surface.acceptedSequence surface) fun s previous => if statusFailed s = true then .done s 0 else
  if previous = 0xffffffffffffffff then .done 170 0 else
  .bind (Surface.refresh surface (previous + 1) x0 y0 (x1 - x0) (y1 - y0) 2) fun s sequence =>
  if s = 171 then .done 0 0 else if statusFailed s = true then .done s 0 else
  .bind (put 480 (if recovery = 1 then 2 else 0)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 352 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 360 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 440) fun s opened => if statusFailed s = true then .done s 0 else
  .bind (if opened = 1 then reportCommitState 0x425 sequence 0 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 440 0) fun s _ => .done s sequence
  else .done 0 0

/-- Package cohort10: batch the complete restored framebuffer as well as dirty FIFO tiles. -/
def pumpRefreshRestoredBatched : Action :=
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.status surface) fun s status => if statusFailed s = true then .done s 0 else
  if status &&& 1 = 1 then .done 0 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  -- A completed full quality request alone clears controller bit8. If that
  -- accepted request was reset too, start a new complete framebuffer upload.
  .bind (if status &&& 8 = 8 then
    if recovery = 1 then .done 0 0 else
    .bind clearDirtyTiles fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 488 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 480 1) fun s _ => if statusFailed s = true then .done s 0 else
    dirty 0 0 width height
    else put 480 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s x0 => if statusFailed s = true then .done s 0 else
  if x0 = 0xffff then .done 0 0 else
  .bind (get 344) fun s y0 => if statusFailed s = true then .done s 0 else
  .bind (get 352) fun s x1 => if statusFailed s = true then .done s 0 else
  .bind (get 360) fun s y1 => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (if recovery = 1 then
    restorePaperBatch surface (width ||| (height <<< 16))
    else .done 0 0) fun s uploaded => if statusFailed s = true then .done s 0 else
  .bind (get 488) fun s restored => if statusFailed s = true then .done s 0 else
  if (if recovery = 1 then
    if restored < ((width + 31) / 32) * ((height + 31) / 32) then true else false
    else false) = true then .done 0 0 else
  -- At most four uploads per main-loop iteration. FIFO consumption and store
  -- progress continue between batches; a refresh names only uploaded pixels.
  .bind (uploadDirtyBatch (4 - uploaded) surface (width ||| (height <<< 16))) fun s _ =>
  if statusFailed s = true then .done s 0 else
  .bind (get 456) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind (Surface.acceptedSequence surface) fun s previous => if statusFailed s = true then .done s 0 else
  if previous = 0xffffffffffffffff then .done 170 0 else
  .bind (Surface.refresh surface (previous + 1) x0 y0 (x1 - x0) (y1 - y0) 2) fun s sequence =>
  if s = 171 then .done 0 0 else if statusFailed s = true then .done s 0 else
  .bind (put 480 (if recovery = 1 then 2 else 0)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 352 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 360 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 440) fun s opened => if statusFailed s = true then .done s 0 else
  .bind (if opened = 1 then reportCommitState 0x425 sequence 0 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 440 0) fun s _ => .done s sequence
  else .done 0 0

private def contextStep (i _ : UInt32) (acc record first last dimensions : UInt64) : Action :=
  let index := i.toUInt64
  if index = 6 then
    .bind (Lemma.Documents.Ink.field record 56) fun s value => if statusFailed s = true then .done s 0 else
    Memory.write64 (context + 48) value
  else if index = 7 then
    .bind (Lemma.Documents.Ink.field record 88) fun s value => if statusFailed s = true then .done s 0 else
    Memory.write64 (context + 56) value
  else
    let sample := if index = 0 then first else if index = 1 then first else
      if index = 4 then first else last
    let isY := if index = 1 then true else if index = 3 then true else false
    .bind (Lemma.Documents.Ink.field sample (if 4 ≤ index then 32 else if isY = true then 24 else 16)) fun s rawValue =>
    if statusFailed s = true then .done s 0 else
    if 4 ≤ index then Memory.write64 (context + index * 8) rawValue else
    .bind (Lemma.Documents.Ink.field record (if isY = true then 80 else 72)) fun s range => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field record 104) fun s sourceHeight => if statusFailed s = true then .done s 0 else
    let value := if isY = true then Lemma.Documents.Ink.displayY (Lemma.Documents.Ink.pageY rawValue range sourceHeight) (dimensions >>> 16)
      else Geometry.normalized rawValue range
    .bind (Memory.write64 (context + index * 8) value) fun s _ => .done s acc

private def rasterTileStep (i _ : UInt32) (acc origin extent dimensions upload : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  let columns := extent &&& 0xffff
  let x := (origin &&& 0xffff) + (i.toUInt64 % columns) * 32
  let y := (origin >>> 16) + (i.toUInt64 / columns) * 32
  .bind (Rasterizer.segmentSurface context Surface.framebuffer x y width height) fun s changed => if statusFailed s = true then .done s 0 else
  if changed = 0 then .done 0 acc else
  if upload = 0 then .done 0 (acc + changed) else
  .bind (markDirtyTile (y / 32 * ((width + 31) / 32) + x / 32)) fun s _ => .done s (acc + changed)

private def renderPair (record first last upload : UInt64) : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  let dimensions := width ||| (height <<< 16)
  .boundedFoldU64 8 contextStep 8 0 record first last dimensions fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field context 0) fun s qx0 => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field context 8) fun s qy0 => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field context 16) fun s qx1 => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field context 24) fun s qy1 => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field context 48) fun s brush => if statusFailed s = true then .done s 0 else
  let radius := (brush + 511) / 512
  let px0 := Geometry.pixel qx0 width
  let py0 := Geometry.pixel qy0 height
  let px1 := Geometry.pixel qx1 width
  let py1 := Geometry.pixel qy1 height
  let left := minimum px0 px1
  let top := minimum py0 py1
  let x0 := (if radius < left then left - radius else 0) / 32 * 32
  let y0 := (if radius < top then top - radius else 0) / 32 * 32
  let x1 := minimum width (maximum px0 px1 + radius + 1)
  let y1 := minimum height (maximum py0 py1 + radius + 1)
  let columns := (x1 - x0 + 31) / 32
  let rows := (y1 - y0 + 31) / 32
  .boundedFoldU64 16384 rasterTileStep (columns * rows).toUInt32 0
    (x0 ||| (y0 <<< 16)) (columns ||| (rows <<< 16)) dimensions upload fun s changed =>
  if statusFailed s = true then .done s 0 else
  if upload = 0 then .done 0 changed else if changed = 0 then .done 0 0 else dirty x0 y0 x1 y1

private def renderChunkStep (i _ : UInt32) (acc record _ _ _ : UInt64) : Action :=
  let sample := record + 128 + i.toUInt64 * 72
  .bind (Lemma.Documents.Ink.field sample 40) fun s flags => if statusFailed s = true then .done s 0 else
  if flags &&& 1 = 0 then .done 0 acc else
  let previous := if i = 0 then sample else sample - 72
  .bind (renderPair record previous sample 0) fun s _ => .done s (acc + 1)

private def renderLoadedChunk (page stroke bytes : UInt64) : Action :=
  .bind (Lemma.Documents.Ink.validateChunkHeader loadedInk page stroke) fun s expected =>
  if statusFailed s = true then .done s 0 else
  if different bytes expected = true then .done 234 0 else
  let count := (expected - 128) / 72
  .boundedFoldU64 384 renderChunkStep count.toUInt32 0 loadedInk 0 0 0 fun s n => .done s n

private def redrawEntryStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex i.toUInt64) 16) fun s visible => if statusFailed s = true then .done s 0 else
  if visible = 0 then .done 0 acc else
  .bind (Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex i.toUInt64) 0) fun s object => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex i.toUInt64) 8) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (readObject object loadedInk 128) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.validateChunkHeader loadedInk page stroke) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (readObject object loadedInk bytes) fun s copied => if statusFailed s = true then .done s 0 else
  if different copied bytes = true then .done 234 0 else
  .bind (renderLoadedChunk page stroke copied) fun s _ => .done s (acc + 1)

private def redraw : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (Surface.background width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field pageIndex 32) fun s count => if statusFailed s = true then .done s 0 else
  if 512 < count then .done 234 0 else
  .boundedFoldU64 512 redrawEntryStep count.toUInt32 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind statusBar fun s _ => if statusFailed s = true then .done s 0 else
  .bind clearDirtyTiles fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (get 584) fun s bulk => if statusFailed s = true then .done s 0 else
  .bind (if bulk = 1 then Surface.uploadAllBulk surface width height else Surface.uploadAll surface width height) fun s _ => if statusFailed s = true then .done s 0 else
  dirty 0 0 width height

private def loadPage (page : UInt64) : Action :=
  .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (readObject (0x100 + page) loadedInk 128) fun s _ =>
  .bind (if s = 230 then Lemma.Documents.Ink.emptyPage pageIndex page else if s = 0 then
    .bind (Lemma.Documents.Ink.pageRecordBytes loadedInk) fun s bytes => if statusFailed s = true then .done s 0 else
    .bind (readObject (0x100 + page) loadedInk bytes) fun s copied => if statusFailed s = true then .done s 0 else
    Lemma.Documents.Ink.decodePage loadedInk pageIndex page copied
    else .done s 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind redraw fun s _ => if statusFailed s = true then .done s 0 else put 440 1

private def readOnlyNotebook (status : UInt8) : Action :=
  .bind (put 136 3) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 424 status.toUInt64) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 416 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 88 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x424 status.toUInt64 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.emptyPage pageIndex 1) fun s _ => if statusFailed s = true then .done s 0 else redraw

private def readNotebook : Action :=
  .bind (readObject 1 rootBuffer 64) fun s _ =>
  if s = 230 then
    .bind (put 88 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 416 1) fun s _ => if statusFailed s = true then .done s 0 else loadPage 1
  else if statusFailed s = true then
    readOnlyNotebook s
  else
    .bind (Lemma.Documents.Ink.field rootBuffer 0) fun s magic => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field rootBuffer 8) fun s version => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field rootBuffer 16) fun s kind => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field rootBuffer 24) fun s pages => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field rootBuffer 32) fun s brush => if statusFailed s = true then .done s 0 else
    if different magic Lemma.Documents.Ink.magic = true then .done 234 0 else if different version 1 = true then .done 234 0 else if different kind 1 = true then .done 234 0 else
    if pages = 0 then .done 234 0 else if 64 < pages then .done 234 0 else
    if (if brush = 256 then true else if brush = 512 then true else if brush = 1024 then true else if brush = 2048 then true else false) = false then .done 234 0 else
    .bind (put 272 brush) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 88 pages) fun s _ => if statusFailed s = true then .done s 0 else loadPage 1

/-- Switching the home notebook closes the old namespace and opens the new
one through the ordinary document endpoint. Toolbar dispatch permits this
only after all pending transactions and partial strokes have drained. -/
private def loadNotebook (ns : UInt64) : Action :=
  .bind (get 72) fun s previous => if statusFailed s = true then .done s 0 else
  .bind (if previous = 0 then .done 0 0 else blocking 10 0 0 0 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 72 ns) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 416 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (blocking 1 0 0 0 0 0) fun s _ =>
  if statusFailed s = true then readOnlyNotebook s else
  .bind (put 136 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind readNotebook fun s _ => if statusFailed s = true then readOnlyNotebook s else .done 0 0

private def statusTileStep (i _ : UInt32) (acc _ dimensions _ _ : UInt64) : Action :=
  let width := dimensions &&& 0xffff
  .bind (markDirtyTile (4 * ((width + 31) / 32) + i.toUInt64)) fun s _ => .done s acc

private def publishStatus : Action :=
  .bind statusBar fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 12 statusTileStep 12 0 surface (width ||| (height <<< 16)) 0 0 fun s _ =>
  if statusFailed s = true then .done s 0 else dirty 0 128 384 160

private def issueStore (operation offset count source : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 384) fun s transaction => if statusFailed s = true then .done s 0 else
  .bind (get 496) fun s checkpoint => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing operation ns object
    (if operation = 12 then checkpoint else if operation = 13 then checkpoint else
      if operation = 7 then 0 else if operation = 8 then 0 else transaction)
    offset count source request)
    fun s pending => if statusFailed s = true then .done s 0 else
  .bind (put 168 pending) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 operation) fun s _ => if statusFailed s = true then .done s 0 else put 448 count

/-- A school queue staging transaction yields to ordinary page/ink Save.
The retained Save buffers stay pending until the queue's actual Abort or Commit
is terminal; no competing Store Begin can turn interactive work into Busy. -/
private def issue (operation offset count source : UInt64) : Action :=
  if operation = 2 then
    .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
    if school = 1 then
    .bind (Memory.read64 schoolQueueReadyFlag) fun s initialized => if statusFailed s = true then .done s 0 else
    if initialized = 1 then
      .bind Lemma.Courses.SchoolSubmission.suspend fun s _ => if statusFailed s = true then .done s 0 else
      .bind Lemma.Courses.SchoolSubmission.writerActive fun s active => if statusFailed s = true then .done s 0 else
      if active = 1 then
        .bind (put 168 0) fun s _ => if statusFailed s = true then .done s 0 else put 160 8
      else .bind (put 160 1) fun s _ => if statusFailed s = true then .done s 0 else issueStore operation offset count source
    else issueStore operation offset count source
    else issueStore operation offset count source
  else issueStore operation offset count source

private def startSave (source bytes object stage : UInt64) : Action :=
  .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe ≤ sequence then .done 235 0 else
  .bind (put 208 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 216 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 200 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 384 (sequence + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 184 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 (sequence + 1) object) fun s _ => if statusFailed s = true then .done s 0 else issue 2 0 bytes 0

/-- Snapshot the bounded current index into compact v2 bytes. The staging
span is immutable until the async store has consumed its transaction. -/
private def savePage (page : UInt64) : Action :=
  .bind (Lemma.Documents.Ink.encodePage pageIndex loadedInk) fun s bytes =>
  if statusFailed s = true then .done s 0 else startSave loadedInk bytes (0x100 + page) 1

private def issueNext : Action :=
  .bind (get 184) fun s offset => if statusFailed s = true then .done s 0 else
  .bind (get 216) fun s bytes => if statusFailed s = true then .done s 0 else
  if offset = bytes then
    .bind (put 160 3) fun s _ => if statusFailed s = true then .done s 0 else issue 4 0 0 0
  else if offset < bytes then
    .bind (get 208) fun s source => if statusFailed s = true then .done s 0 else
    .bind (put 160 2) fun s _ => if statusFailed s = true then .done s 0 else
    issue 3 offset (minimum 128 (bytes - offset)) (source + offset)
  else .done 234 0

private def finishRecord : Action :=
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  if stage = 0 then
    .bind (get 208) fun s source => if statusFailed s = true then .done s 0 else
    .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field source 32) fun s stroke => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.field source 112) fun s lifecycle => if statusFailed s = true then .done s 0 else
    .bind (preflightChunk pageIndex (lifecycle &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.addEntry pageIndex object stroke) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (if lifecycle &&& 1 = 1 then Lemma.Documents.Ink.addEdit pageIndex 1 stroke else .done 0 0)
      fun s _ => if statusFailed s = true then .done s 0 else
    savePage page
  else if stage = 1 then
    .bind (get 88) fun s pages => if statusFailed s = true then .done s 0 else
    .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.root rootBuffer pages brush) fun s _ => if statusFailed s = true then .done s 0 else
    startSave rootBuffer 64 1 2
  else if stage = 3 then
    .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
    .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 (if rawCount = 0 then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
    .bind (reportCommitState 0x421 sequence object) fun s _ => if statusFailed s = true then .done s 0 else publishStatus
  else if stage = 2 then
    .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
    .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 144 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 416 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 (if rawCount = 0 then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
    .bind (get 240) fun s stroke => if statusFailed s = true then .done s 0 else
    .bind (reportCommitState 0x421 sequence stroke) fun s _ =>
    if statusFailed s = true then .done s 0 else publishStatus
  else .done 234 0

private def saveFailure (status : UInt8) : Action :=
  .bind (put 424 status.toUInt64) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 2) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x424 status.toUInt64 object) fun s _ => if statusFailed s = true then .done s 0 else publishStatus

private def cancelInput : Action :=
  .bind (put 104 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 112 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 296 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 304 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 408 0) fun s _ => if statusFailed s = true then .done s 0 else
  put 432 1

/-- A declared representation limit stops the unsaved tail and resynchronizes
contact. The previous resident/persistent page stays available; the loop keeps
running to publish Failed and its recovery refresh rather than exiting User. -/
def failWriting (status : UInt8) : Action :=
  .bind cancelInput fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 144 0) fun s _ => if statusFailed s = true then .done s 0 else saveFailure status

private def pumpSave : Action :=
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 0 then .done 0 0 else
  if phase = 8 then
    .bind (get 216) fun s bytes => if statusFailed s = true then .done s 0 else issue 2 0 bytes 0
  else
  if phase = 5 then
    .bind (get 504) fun s deadline => if statusFailed s = true then .done s 0 else
    .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
    if now < deadline then .done 0 0 else
    .bind (put 160 4) fun s _ => if statusFailed s = true then .done s 0 else issue 13 0 0 0
  else
  .bind (get 168) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 232) fun s operation => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.pollCall pending incoming operation ns object request 0) fun s sequence =>
  if s = IPCABI.wouldBlock then .done 0 0 else if statusFailed s = true then saveFailure s else
  .bind (if phase = 6 then
    .bind (get 496) fun s prior => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s mode =>
    if statusFailed s = true then .done s 0 else .done (saveResponseStatus operation mode sequence prior) 0
    else .done 0 0) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (observeStoreSequence sequence) fun s _ => if statusFailed s = true then .done s 0 else
  if phase = 1 then issueNext else if phase = 2 then
    .bind (get 184) fun s offset => if statusFailed s = true then .done s 0 else
    .bind (get 448) fun s count => if statusFailed s = true then .done s 0 else
    .bind (put 184 (offset + count)) fun s _ => if statusFailed s = true then .done s 0 else issueNext
  else if phase = 3 then
    .bind finishRecord fun s value => if statusFailed s = true then failWriting s else .done 0 value
  else if phase = 4 then
    .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s detail => if statusFailed s = true then .done s 0 else
    if checkpointResponseStatus operation detail = 234 then saveFailure 234 else
    if detail = 1 then
      .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
      if 0xffffffffffffffff - 1000000 < now then saveFailure 235 else
      .bind (put 504 (now + 1000000)) fun s _ => if statusFailed s = true then .done s 0 else put 160 5
    else if detail = 0 then if operation = 13 then
      .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
      .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (put 136 (if count = 0 then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (reportCommitState 0x421 sequence 0) fun s _ => if statusFailed s = true then .done s 0 else publishStatus
    else saveFailure 234 else saveFailure 234
  else if phase = 6 then
    .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
    .bind (get 144) fun s buffered => if statusFailed s = true then .done s 0 else
    let clean := if count ||| buffered = 0 then true else false
    .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 (if clean then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (reportCommitState (if clean then 0x421 else 0x423) sequence 0) fun s _ =>
    if statusFailed s = true then .done s 0 else publishStatus
  else .done 234 0

private def courseTileStep (i _ : UInt32) (acc width _ _ _ : UInt64) : Action :=
  .bind (markDirtyTile ((5 + i.toUInt64 / 13) * ((width + 31) / 32) + i.toUInt64 % 13)) fun s _ => .done s acc

private def renderCourse : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.Arithmetic.render mathematics width) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 65 courseTileStep 65 0 width 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  dirty 0 160 416 320

private def reportCourse : Action :=
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 48) fun s goal => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 96) fun s outcome => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 104) fun s evidence => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x450 revision goal outcome evidence

private def saveCourse : Action :=
  .bind (Lemma.Documents.Mathematics.copyCurrent mathematics mathematicsSave) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (startSave mathematicsSave Lemma.Documents.Mathematics.currentBytes (Lemma.Documents.Mathematics.object page) 3) fun s _ =>
  if statusFailed s = true then saveFailure s else publishStatus

/-- Failed application admission leaves ink and the store available. A storage
failure still follows the existing Failed barrier path. -/
private def courseError (status : UInt8) : Action :=
  .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x454 status.toUInt64 0) fun s _ => if statusFailed s = true then .done s 0 else redraw

private def allocateCourse : Action :=
  .bind (get 520) fun s allocated => if statusFailed s = true then .done s 0 else
  .bind (if allocated = 0 then
    .bind (Syscall.allocatePage mathematics) fun s actual => if statusFailed s = true then .done s 0 else
    if actual = mathematics then put 520 1 else failed
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 520) fun s allocated => if statusFailed s = true then .done s 0 else
  .bind (if allocated = 1 then
    .bind (Syscall.allocatePage mathematicsSave) fun s actual => if statusFailed s = true then .done s 0 else
    if actual = mathematicsSave then put 520 2 else failed
  else if allocated = 2 then .done 0 0 else if allocated = 3 then .done 0 0 else failed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 528) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 520) fun s allocated => if statusFailed s = true then .done s 0 else
  if endpoint = 0 then .done 0 0 else if allocated = 3 then .done 0 0 else
  .bind (Syscall.allocatePage mathematicsIO) fun s actual => if statusFailed s = true then .done s 0 else
  if actual = mathematicsIO then put 520 3 else failed

-- Versioned software selection occupies a formerly unused state word.
-- Main initialization sets it before any course request or document load.
private def pollArithmetic (transaction incoming outgoing request : UInt64) : Action :=
  .bind (get 576) fun s selection => if statusFailed s = true then .done s 0 else
  if selection = 7 then Lemma.Services.Arithmetic.ClientV7.pollCall transaction incoming outgoing request
  else if selection = 6 then Lemma.Services.Arithmetic.ClientV6.pollCall transaction incoming outgoing request
  else if selection = 5 then Lemma.Services.Arithmetic.ClientV5.pollCall transaction incoming outgoing request
  else if selection = 4 then Lemma.Services.Arithmetic.ClientV4.pollCall transaction incoming outgoing request
  else if selection = 3 then Lemma.Services.Arithmetic.ClientV3.pollCall transaction incoming outgoing request
  else if selection = 2 then Lemma.Services.Arithmetic.ClientV2.pollCall transaction incoming outgoing request else failed

private def callArithmetic (endpoint outgoing document request : UInt64) : Action :=
  .bind (get 576) fun s selection => if statusFailed s = true then .done s 0 else
  if selection = 7 then Lemma.Services.Arithmetic.ClientV7.beginCall endpoint outgoing document request
  else if selection = 6 then Lemma.Services.Arithmetic.ClientV6.beginCall endpoint outgoing document request
  else if selection = 5 then Lemma.Services.Arithmetic.ClientV5.beginCall endpoint outgoing document request
  else if selection = 4 then Lemma.Services.Arithmetic.ClientV4.beginCall endpoint outgoing document request
  else if selection = 3 then Lemma.Services.Arithmetic.ClientV3.beginCall endpoint outgoing document request
  else if selection = 2 then Lemma.Services.Arithmetic.ClientV2.beginCall endpoint outgoing document request else failed

private def completeArithmetic (revision goal outcome request budget : UInt64) : Action :=
  .bind (get 576) fun s selection => if statusFailed s = true then .done s 0 else
  if selection = 7 then Lemma.Documents.MathematicsClosure.completeExecution mathematics revision goal outcome request budget
  else if selection = 6 then Lemma.Documents.MathematicsString.completeExecution mathematics revision goal outcome request budget
  else if selection = 5 then Lemma.Documents.MathematicsArray.completeExecution mathematics revision goal outcome request budget
  else if selection = 4 then Lemma.Documents.MathematicsBytes.completeExecution mathematics revision goal outcome request budget
  else if selection = 3 then Lemma.Documents.Mathematics.completeExecutionSums mathematics revision goal outcome request budget
  else if selection = 2 then Lemma.Documents.Mathematics.completeExecution mathematics revision goal outcome request budget else failed

private def createArithmetic (ns page : UInt64) : Action :=
  .bind (get 576) fun s selection => if statusFailed s = true then .done s 0 else
  if selection = 7 then Lemma.Documents.MathematicsClosure.create mathematics ns page
  else if selection = 6 then Lemma.Documents.MathematicsString.create mathematics ns page
  else if selection = 5 then Lemma.Documents.MathematicsArray.create mathematics ns page
  else if selection = 4 then Lemma.Documents.MathematicsBytes.create mathematics ns page
  else if selection = 3 then Lemma.Documents.Mathematics.createSums mathematics ns page
  else if selection = 2 then Lemma.Documents.Mathematics.createCurrent mathematics ns page else failed

private def upgradeArithmetic (ns page : UInt64) : Action :=
  .bind (get 576) fun s selection => if statusFailed s = true then .done s 0 else
  if selection = 7 then
  .bind (Lemma.Documents.MathematicsClosure.validate mathematics ns page) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.MathematicsClosure.upgrade mathematics
  else if selection = 6 then
  .bind (Lemma.Documents.MathematicsString.validate mathematics ns page) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.MathematicsString.upgrade mathematics
  else if selection = 5 then
  .bind (Lemma.Documents.MathematicsArray.validate mathematics ns page) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.MathematicsArray.upgrade mathematics
  else if selection = 4 then
  .bind (Lemma.Documents.MathematicsBytes.validate mathematics ns page) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.MathematicsBytes.upgrade mathematics
  else if selection = 3 then
  .bind (Lemma.Documents.Mathematics.validateSums mathematics ns page) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.Mathematics.upgradeSums mathematics
  else if selection = 2 then
  .bind (Lemma.Documents.Mathematics.validate mathematics ns page) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.Mathematics.upgradeCurrent mathematics else failed

/-- Caller cancellation consumes the terminal transaction exactly once. A
reply already accepted by the kernel is discarded without publishing evidence. -/
private def cancelArithmetic : Action :=
  .bind (get 536) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (if phase = 1 then
    .bind (get 544) fun s transaction => if statusFailed s = true then .done s 0 else
    .bind (get 552) fun s request => if statusFailed s = true then .done s 0 else
    .bind (IPC.cancel transaction) fun canceled _ =>
    if (if canceled = 0 then true else if canceled = IPCABI.alreadyCompleted then true else false) = true then
    .bind (pollArithmetic transaction (mathematicsIO + 256) mathematicsIO request) fun terminal _ =>
    if terminal = IPCABI.wouldBlock then .done IPCABI.invalidTransaction 0 else .done 0 terminal.toUInt64
    else .done canceled 0
    else .done 0 0) fun s terminal => if statusFailed s = true then .done s 0 else
  .bind (put 536 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x458 phase terminal 0 0

private def beginArithmetic : Action :=
  .bind (get 528) fun s endpoint => if statusFailed s = true then .done s 0 else
  if endpoint = 0 then .bind (Lemma.Documents.Mathematics.submit mathematics) fun s _ => .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 144) fun s attempts => if statusFailed s = true then .done s 0 else
  if attempts = 8 then .bind (Lemma.Documents.Mathematics.submit mathematics) fun s _ => .done s 0 else if 8 < attempts then .done 234 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (callArithmetic endpoint mathematicsIO mathematics request) fun s transaction =>
  if statusFailed s = true then .done s 0 else
  .bind (put 544 transaction) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 552 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 536 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 48) fun s goal => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x459 request revision goal transaction

/-- Polling never blocks pen input. Publication and error redraw wait until
current raw ink has reached its ordinary Store boundary, retaining the complete
submitted identity while the independently linked checker runs. -/
private def pumpArithmetic : Action :=
  .bind (get 536) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 0 then .done 0 0 else
  .bind (if phase = 1 then
    .bind (get 544) fun s transaction => if statusFailed s = true then .done s 0 else
    .bind (get 552) fun s request => if statusFailed s = true then .done s 0 else
    .bind (pollArithmetic transaction (mathematicsIO + 256) mathematicsIO request) fun s outcome =>
    if s = IPCABI.wouldBlock then .done 0 0 else
    .bind (put 560 outcome) fun stored _ => if statusFailed stored = true then .done stored 0 else
    .bind (put 568 s.toUInt64) fun stored _ => if statusFailed stored = true then .done stored 0 else
    put 536 (if s = 0 then 2 else 3)
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 1 then .done 0 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke = 0 then
  .bind (put 536 0) fun s _ => if statusFailed s = true then .done s 0 else
  if phase = 3 then
    .bind (get 568) fun s error => if statusFailed s = true then .done s 0 else courseError error.toUInt8
  else if phase = 2 then
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 24)) fun s submittedNS => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 32)) fun s submittedPage => if statusFailed s = true then .done s 0 else
  if ns = submittedNS then if page = submittedPage then
  .bind (Memory.read64 (mathematicsIO + 40)) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 48)) fun s goal => if statusFailed s = true then .done s 0 else
  .bind (get 560) fun s outcome => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 104)) fun s request => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 96)) fun s budget => if statusFailed s = true then .done s 0 else
  .bind (completeArithmetic revision goal outcome request budget) fun s _ =>
  if statusFailed s = true then courseError s else
  .bind renderCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind reportCourse fun s _ => if statusFailed s = true then .done s 0 else saveCourse
  else courseError 234 else courseError 234 else courseError 234 else .done 0 0

private def openCourse : Action :=
  .bind allocateCourse fun s _ => if statusFailed s = true then courseError s else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.legacyBytes) fun readStatus _ =>
  .bind (if readStatus = 230 then createArithmetic ns page else
    if readStatus = 0 then
    .bind (Lemma.Documents.Mathematics.field mathematics 8) fun s version => if statusFailed s = true then .done s 0 else
    .bind (if version = 2 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.bytes
      else if version = 3 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.currentBytes
      else if version = 4 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.currentBytes
      else if version = 5 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.currentBytes
      else if version = 8 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.currentBytes
      else if version = 7 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.currentBytes
      else if version = 6 then readObject (Lemma.Documents.Mathematics.object page) mathematics Lemma.Documents.Mathematics.currentBytes
      else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
    upgradeArithmetic ns page
    else .done readStatus 0) fun s upgraded =>
  if statusFailed s = true then courseError s else
  .bind (put 512 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind renderCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind reportCourse fun s _ => if statusFailed s = true then .done s 0 else
  if readStatus = 230 then saveCourse else if upgraded = 1 then saveCourse else .done 0 0

private def coursePress (x y : UInt64) : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| checking = 0 then
  .bind (if 240 ≤ y then if y < 260 then if x < 84 then beginArithmetic
      else Lemma.Courses.Arithmetic.press mathematics (x - 24) (y - 160)
      else Lemma.Courses.Arithmetic.press mathematics (x - 24) (y - 160)
      else Lemma.Courses.Arithmetic.press mathematics (x - 24) (y - 160)) fun s close =>
  if statusFailed s = true then courseError s else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if checking = 1 then .done 0 0 else
  if close = 1 then .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else redraw
  else if 220 ≤ y then if y < 260 then
    .bind renderCourse fun s _ => if statusFailed s = true then .done s 0 else
    .bind reportCourse fun s _ => if statusFailed s = true then .done s 0 else saveCourse
  else .done 0 0 else .done 0 0 else .done 0 0

private def toggleCourse : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending = 0 then
  .bind (get 512) fun s active => if statusFailed s = true then .done s 0 else
  if active = 1 then .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else redraw
  else openCourse else .done 0 0

private def prepareChunk (buffer stroke lifecycle : UInt64) : Action :=
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
  .bind (get 64) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.chunk buffer page stroke brush pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.put buffer 72 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.put buffer 80 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.put buffer 96 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.put buffer 104 height) fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Documents.Ink.put buffer 112 lifecycle

private def enqueue : Action :=
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  if different phase 0 = true then .done 0 0 else
  .bind (get 144) fun s previous => if statusFailed s = true then .done s 0 else
  if different previous 0 = true then .done 0 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 0 then .done 0 0 else
  .bind (get 120) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field source 112) fun s lifecycle => if statusFailed s = true then .done s 0 else
  .bind (preflightChunk pageIndex (lifecycle &&& 1)) fun s _ =>
  if statusFailed s = true then failWriting s else
  .bind (Lemma.Documents.Ink.finishChunk source count (lifecycle ||| (if active = 0 then 2 else 0)))
    fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field source 32) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (put 240 stroke) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 144 source) fun s _ => if statusFailed s = true then .done s 0 else
  let next := if source = ink0 then ink1 else ink0
  .bind (put 120 next) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 112 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if active = 0 then .done 0 0 else
    .bind (prepareChunk next stroke 4) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Services.Store.Format.copy (source + 128 + (count - 1) * 72) (next + 128) 72)
      fun s _ => if statusFailed s = true then .done s 0 else put 112 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave source bytes (0x10001 + sequence) 0) fun s _ =>
  if statusFailed s = true then saveFailure s else publishStatus

private def latestVisibleStep (i amount : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  if different acc 0 = true then .done 0 acc else
  let index := amount.toUInt64 - 1 - i.toUInt64
  .bind (Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex index) 16) fun s visible =>
  if statusFailed s = true then .done s 0 else
  if visible = 1 then Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex index) 8
  else .done 0 0

private def editPage (operation : UInt64) : Action :=
  .bind (if operation = 3 then Lemma.Documents.Ink.undo pageIndex else
    if operation = 4 then Lemma.Documents.Ink.redo pageIndex else
    .bind (Lemma.Documents.Ink.field pageIndex 32) fun s count => if statusFailed s = true then .done s 0 else
    .boundedFoldU64 512 latestVisibleStep count.toUInt32 0 0 0 0 0 fun s stroke =>
    if statusFailed s = true then .done s 0 else if stroke = 0 then .done 0 0 else
    .bind (preflightEdit pageIndex) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.visibility pageIndex stroke 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.addEdit pageIndex 2 stroke) fun s _ => .done s stroke)
    fun s changed => if statusFailed s = true then saveFailure s else
  if changed = 0 then .done 0 0 else
  .bind (put 240 changed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind redraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (savePage page) fun s _ =>
  if statusFailed s = true then saveFailure s else publishStatus

private def toolbar (button : UInt64) : Action :=
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if checking = 0 then
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s pending => if statusFailed s = true then .done s 0 else
  if different (phase ||| rawCount ||| pending) 0 = true then .done 0 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if 2 ≤ status then .done 0 0 else
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  .bind (if course = 1 then .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else redraw
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 88) fun s pages => if statusFailed s = true then .done s 0 else
  if button = 0 then
    .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
    .bind (loadNotebook (if ns = 1 then 2 else 1)) fun s _ => if statusFailed s = true then saveFailure s else
    .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
    if create = 1 then
      .bind (savePage 1) fun s _ =>
      if statusFailed s = true then saveFailure s else publishStatus
    else .done 0 0
  else if button = 1 then if 1 < page then loadPage (page - 1) else .done 0 0
  else if button = 2 then if page < pages then loadPage (page + 1) else
    if pages < 64 then
      .bind (put 88 (pages + 1)) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (loadPage (pages + 1)) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (savePage (pages + 1)) fun s _ =>
      if statusFailed s = true then saveFailure s else publishStatus
    else saveFailure 235
  else if button = 3 then editPage 3 else if button = 4 then editPage 4 else if button = 5 then editPage 5 else
  if button = 6 then
    .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
    .bind (put 272 (if brush < 2048 then brush * 2 else 256)) fun s _ =>
    if statusFailed s = true then .done s 0 else
    .bind (get 272) fun s width => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.root rootBuffer pages width) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (startSave rootBuffer 64 1 2) fun s _ => if statusFailed s = true then saveFailure s else publishStatus
  else if button = 7 then
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
    .bind (put 496 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 224 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 160 6) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (reportCommitState 0x423 sequence 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (issue 8 0 0 0) fun s _ => if statusFailed s = true then saveFailure s else publishStatus
  else if button = 8 then
    .bind (put 224 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 160 4) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
    .bind (reportCommitState 0x423 sequence 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind nextRequest fun s ticket => if statusFailed s = true then .done s 0 else
    .bind (put 496 ticket) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (issue 12 0 0 0) fun s _ => if statusFailed s = true then saveFailure s else publishStatus
  else .done 0 0 else .done 0 0

/-- The scalar IPC ABI has one pending call per process. Writing takes
priority: cancel and consume a pending check before starting an ink stroke,
so its later Store call owns the slot without discarding raw samples. -/
private def beginStroke : Action :=
  .bind (get 536) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (if phase = 1 then cancelArithmetic else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (preflightChunk pageIndex 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (get 96) fun s next => if statusFailed s = true then .done s 0 else
  let stroke := maximum next (sequence + 1)
  if 0x7ffffffffffffffe ≤ stroke then .done 235 0 else
  .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
  .bind (prepareChunk buffer stroke 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 96 (stroke + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 104 stroke) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => .done s buffer

private def appendRaw : Action :=
  .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if 384 ≤ count then .done 235 0 else
  let sample := buffer + 128 + count * 72
  .bind (Lemma.Services.Store.Format.copy raw sample 72) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 112 (count + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  if flags &&& 1 = 0 then
    .bind (put 104 0) fun s _ => if statusFailed s = true then .done s 0 else enqueue
  else .bind (renderPair buffer (if count = 0 then sample else sample - 72) sample 1) fun s _ =>
    if statusFailed s = true then .done s 0 else
    if count + 1 = 384 then enqueue else .done 0 0

private def pumpCancelledRedraw : Action :=
  .bind (get 432) fun s needed => if statusFailed s = true then .done s 0 else
  if needed = 0 then .done 0 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  if different phase 0 = true then .done 0 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (if status < 2 then put 136 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind redraw fun s _ => if statusFailed s = true then .done s 0 else put 432 0

private def inputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      cancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then appendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    if 2 ≤ status then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then toolbar (minimum 8 (px / (width / 9))) else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then toggleCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then if py < 320 then if 24 ≤ px then if px < 408 then coursePress px py else
      .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
      else .done 0 0 else .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
    else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw

/-- A service turn drains at most eight queued samples. The controller read is
nonblocking; Empty is observed once and ends the turn. A full raw chunk is
checked before fetching another sample, and release, loss, or a toolbar action
returns to the save/display pumps before a new contact can begin. -/
def drainInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind cancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind inputSample fun s _ => if statusFailed s = true then .done s consumed else
    if count = 383 then .done Status.iterationStop (consumed + 1) else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

private def step : Action :=
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 384 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then cancelInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else inputSample
  else .bind (drainInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

/-- A large disk scan never owns an expiring open Reply. Mode zero means
Mounting; no Ready or Saved observation is emitted. A checked ten-minute
monotonic acceptance deadline bounds readiness; each RPC retains its separate
thirty-second failure ceiling. Failed media is never automatically formatted. -/
private def mountStatusStep (_ _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (get 504) fun s deadline => if statusFailed s = true then .done s 0 else
  .bind Syscall.time fun s before => if statusFailed s = true then .done s 0 else
  if deadline ≤ before then .done IPCABI.timeout 0 else
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.call endpoint outgoing incoming 8 1 0 0 0 0 0 request)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind Syscall.time fun s after => if statusFailed s = true then .done s 0 else
  if deadline ≤ after then .done IPCABI.timeout 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s mode => if statusFailed s = true then .done s 0 else
  if mode = 0 then
    .bind (Syscall.sleep 1000000) fun s _ => .done s (acc + 1)
  else if mode ≤ 3 then .done Status.iterationStop mode else .done 234 0

private def waitForMount : Action :=
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  if 0xffffffffffffffff - 6000000000 < now then .done 235 0 else
  .bind (put 504 (now + 6000000000)) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 6000 mountStatusStep 6000 0 0 0 0 0 fun s mode =>
  if s = Status.iterationStop then .done 0 mode else
  if s = 0 then .done IPCABI.timeout 0 else .done s 0

private def initializeMedium : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.call endpoint outgoing incoming 11 0 0 0 0 0 0 1) fun s sequence =>
  if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x41f sequence 0 0 0) fun s _ =>
  if statusFailed s = true then .done s 0 else Syscall.exit 0

private def mainWithExecution (bootArgument selection bulkMode : UInt64) : Action :=
  if 3 < bootArgument then failed else
  if (if selection = 2 then true else if selection = 3 then true else if selection = 4 then true else if selection = 5 then true else if selection = 6 then true else selection = 7) = false then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 selection) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 bulkMode) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument % 2 = 1 then initializeMedium else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 512 then failed else if 4096 < width then failed else
  if height < 320 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if bulkMode = 1 then Surface.allocateBulk else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop step

/-- Historical software selection: bootargs0..3 keep Protocol2/document3. -/
def main (bootArgument : UInt64) : Action := mainWithExecution bootArgument 2 0

/-- Explicit sums software selection on the unchanged canonical machine. -/
def mainSums (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithExecution bootArgument 3 0 else
  if bootArgument = 3 then mainWithExecution bootArgument 3 0 else failed

/-- Surface-v2 is selected by its own immutable software deployment. Historical
main/mainSums roots keep their legacy upload and reject operation5. -/
def mainSumsBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithExecution bootArgument 3 1 else
  if bootArgument = 3 then mainWithExecution bootArgument 3 1 else failed

/-- The bytes deployment selects a distinct Protocol4/document5 authority.
Surface-v2 transports exactly the same owned controller pixels. -/
def mainBytesBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithExecution bootArgument 4 1 else
  if bootArgument = 3 then mainWithExecution bootArgument 4 1 else failed

/-- Full-width managed arrays select Protocol5/document6 without granting the
checker any storage, ink or controller authority. -/
def mainArrayBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithExecution bootArgument 5 1 else
  if bootArgument = 3 then mainWithExecution bootArgument 5 1 else failed

/-- Protocol6/document7 preserve original submissions through a full-width
hexadecimal UTF-8 String roundtrip in the separate arithmetic process. -/
def mainStringBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithExecution bootArgument 6 1 else
  if bootArgument = 3 then mainWithExecution bootArgument 6 1 else failed

/-- Explicit development closure deployment: Protocol7/Document8 with real
scalar capture graphs in the separately linked User7 arithmetic authority. -/
def mainClosureBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithExecution bootArgument 7 1 else
  if bootArgument = 3 then mainWithExecution bootArgument 7 1 else failed

/-! Additive failure policy. No historical root calls these Actions. A genuine
Store error retains the exact staged owned record; status inspection is never a
Saved observation. Transport failures which make Store read-only stay Failed. -/

def retryRetainFailure (knownSequence : UInt64) : Action :=
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  .bind (get 208) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 216) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryPolicy.retainableFailure error source bytes object stage = false then .done 0 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then put 640 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 600 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 608 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 616 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 624 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 632 knownSequence) fun s _ => if statusFailed s = true then .done s 0 else
  put 648 1

def retryBeginInspect : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 640) fun s attempts => if statusFailed s = true then .done s 0 else
  let allowed := Lemma.Notebook.RetryPolicy.retryStatus attempts source bytes object stage
  if statusFailed allowed = true then saveFailure allowed else
  .bind (put 640 (attempts + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s prior => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 prior 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (issue 8 0 0 0) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

def retryPollInspect : Action :=
  .bind (get 168) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.pollCall pending incoming 8 ns 0 request 0) fun s observed =>
  if s = IPCABI.wouldBlock then .done 0 0 else if statusFailed s = true then saveFailure s else
  .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s mode => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  let allowed := Lemma.Notebook.RetryPolicy.reconciliationStatus mode observed known
  if statusFailed allowed = true then saveFailure allowed else
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryPolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

def retryPumpSave : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 7 then retryPollInspect else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s known => if statusFailed s = true then .done s 0 else
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if after = 0 then if status = 2 then
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 0 then retryRetainFailure known else
    if before = 1 then retryRetainFailure known else
    if before = 2 then retryRetainFailure known else
    if before = 3 then retryRetainFailure known else .done 0 0
  else if before = 3 then if stage = 2 then
    .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else put 640 0
  else .done 0 0 else .done 0 0 else .done 0 0

def retryToolbar (button : UInt64) : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if status < 2 then toolbar button else
  if button = 7 then
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if error = 227 then
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s contact => if statusFailed s = true then .done s 0 else
  if retained = 1 then if phase ||| checking ||| contact = 0 then retryBeginInspect else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0

/-- Exhaustion/loss stops only this new contact. It neither discards the
pinned failed record nor releases an in-flight Store request. -/
def retryInputLimit : Action :=
  .bind (put 104 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 432 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 664 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 424 235) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 2) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x424 235 object) fun s _ => if statusFailed s = true then .done s 0 else publishStatus

def retryCancelInput : Action :=
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  if retained = 1 then retryInputLimit else cancelInput

def retryAppendRaw : Action :=
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  if retained = 0 then appendRaw else
  .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryPolicy.offlineBufferAvailable buffer pinned count = false then
    retryInputLimit
  else
  let sample := buffer + 128 + count * 72
  .bind (Lemma.Services.Store.Format.copy raw sample 72) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 112 (count + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  if flags &&& 1 = 0 then put 104 0 else
  renderPair buffer (if count = 0 then sample else sample - 72) sample 1

def retryInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      retryCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then retryAppendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then retryToolbar (minimum 8 (px / (width / 9))) else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 1 then
      if py < 160 then .done 0 0 else
      .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
      .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
      if Lemma.Notebook.RetryPolicy.offlineBufferAvailable buffer pinned 0 = false then .done 0 0 else
      .bind beginStroke fun s _ => if statusFailed s = true then saveFailure s else
      .bind (put 136 status) fun s _ => if statusFailed s = true then .done s 0 else retryAppendRaw
    else if 2 ≤ status then .done 0 0 else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then toggleCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then if py < 320 then if 24 ≤ px then if px < 408 then coursePress px py else
      .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
      else .done 0 0 else .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
    else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw

def drainRetryInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s consumed else
    if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind retryCancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind retryInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

def retryStep : Action :=
  .bind retryPumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpCancelledRedraw else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (get 664) fun s overflow => if statusFailed s = true then .done s 0 else
  .bind (if overflow = 1 then .done 0 0 else if retained = 1 then .done 0 0 else if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then retryCancelInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else retryInputSample
  else .bind (drainRetryInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

private def mainWithRetryExecution (bootArgument selection bulkMode : UInt64) : Action :=
  if 3 < bootArgument then failed else
  if (if selection = 3 then true else false) = false then failed else
  .boundedFoldU64 86 clearStep 86 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 592 Lemma.Notebook.RetryPolicy.version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 selection) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 bulkMode) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument % 2 = 1 then initializeMedium else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 512 then failed else if 4096 < width then failed else
  if height < 320 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if bulkMode = 1 then Surface.allocateBulk else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop retryStep

/-- Explicit retry software root; historical Wire/Clocked roots are unchanged.
The retry policy does not make a read-only Store writable or publish a receipt. -/
def mainRetrySumsBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithRetryExecution bootArgument 3 1 else
  if bootArgument = 3 then mainWithRetryExecution bootArgument 3 1 else failed

/-! Recoverable-v2 is separately selected. Its control/READ receipts never
publish Saved. It keeps the original owned source and acknowledged floor, then
uses a new exact publication request only after the peer frame and shadow mount
are reconciled. Higher or different durable data remain Failed, without rollback.
672lastFullACK/680failureTicket/688epochFloor/696mountedSequence/704verifyOffset.
The existing Retry-v1 and all historical entry points remain unchanged. -/

def recoverableVersion : UInt64 := 2

private def recoverableIssueControl (operation : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.RecoveryClient.beginCall endpoint outgoing operation ns ticket request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else put 232 operation

def recoverableBegin : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 640) fun s attempts => if statusFailed s = true then .done s 0 else
  let allowed := Lemma.Notebook.RetryPolicy.retryStatus attempts source bytes object stage
  if statusFailed allowed = true then saveFailure allowed else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  if ticket = 0 then saveFailure 234 else
  .bind (put 640 (attempts+1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 known object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recoverableIssueControl 14) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

private def recoverableResubmit : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryPolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

/-- The remount receipt follows a real durability barrier. Full exact READ/EOF
of known+1 reconciles the original record once; it never issues another PUT for
that record. Only subsequent page/root stages use new ordinary transactions. -/
private def recoverableFinishRetained : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryPolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  if known = 0x7fffffffffffffff then saveFailure 234 else
  if observed = known+1 then
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 208 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 216 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 200 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 384 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind finishRecord fun s result => if statusFailed s = true then saveFailure s else
  if stage = 2 then
    .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 640 0) fun s _ => if statusFailed s = true then .done s 0 else put 672 observed
  else .done 0 result
  else saveFailure 234

private def recoverableIssueRead : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 704) fun s offset => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryPolicy.retainedRecordValid source bytes object stage = false then .done 234 0 else
  if offset % 8 = 0 then
  if offset < bytes then
  let count := minimum 128 (bytes-offset)
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 offset count 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 count) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 10
  else .done 234 0 else .done 234 0

private def recoverableIssueEndRead : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 bytes 8 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 11

private def recoverableCompareStep (i _ : UInt32) (acc source offset _ _ : UInt64) : Action :=
  .bind (Memory.read64 (source+offset+i.toUInt64*8)) fun s expected => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (incoming+128+i.toUInt64*8)) fun s observed => if statusFailed s = true then .done s 0 else
  if expected = observed then .done 0 (acc+8) else .done 234 0

def recoverablePollRead : Action :=
  .bind (get 168) fun s token =>
    if s = 0 then
      .bind (get 72) fun s ns =>
        if s = 0 then
          .bind (get 616) fun s object =>
            if s = 0 then
              .bind (get 176) fun s request =>
                if s = 0 then
                  .bind (get 448) fun s expectedCount =>
                    if s = 0 then
                      .bind (Lemma.Services.Store.Client.pollCall token incoming 5 ns object request expectedCount) fun replyStatus sequence =>
                        if replyStatus = IPCABI.wouldBlock then
                          .done 0 0
                        else
                          if replyStatus = 0 then
                            .bind (get 696) fun s mounted =>
                              if s = 0 then
                                if sequence = mounted then
                                  .bind (Lemma.Services.Store.Client.responseField incoming 56) fun s count =>
                                    if s = 0 then
                                      .bind (get 160) fun s phase =>
                                        if s = 0 then
                                          if phase = 11 then
                                            if count = 0 then
                                              recoverableFinishRetained
                                            else
                                              saveFailure 234
                                          else
                                            if count = expectedCount then
                                              if 0 < count then
                                                if count ≤ 128 then
                                                  if count % 8 = 0 then
                                                    .bind (get 600) fun s source =>
                                                      if s = 0 then
                                                        .bind (get 704) fun s offset =>
                                                          if s = 0 then
                                                            .bind (get 608) fun s bytes =>
                                                              if s = 0 then
                                                                if offset ≤ bytes then
                                                                  if count ≤ bytes-offset then
                                                                    .boundedFoldU64 16 recoverableCompareStep (count/8).toUInt32 0 source offset 0 0 fun s compared =>
                                                                      if s = 0 then
                                                                        if compared = count then
                                                                          .bind (put 704 (offset+count)) fun s _ =>
                                                                            if s = 0 then
                                                                              if offset+count = bytes then
                                                                                .bind recoverableIssueEndRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                              else
                                                                                .bind recoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                            else .done s 0
                                                                        else
                                                                          saveFailure 234
                                                                      else
                                                                        saveFailure s
                                                                  else
                                                                    saveFailure 234
                                                                else
                                                                  saveFailure 234
                                                              else .done s 0
                                                          else .done s 0
                                                      else .done s 0
                                                  else
                                                    saveFailure 234
                                                else
                                                  saveFailure 234
                                              else
                                                saveFailure 234
                                            else
                                              saveFailure 234
                                        else .done s 0
                                    else .done s 0
                                else
                                  saveFailure 234
                              else .done s 0
                          else
                            saveFailure replyStatus
                    else .done s 0
                else .done s 0
            else .done s 0
        else .done s 0
    else .done s 0

def recoverablePollControl : Action :=
  .bind (get 168) fun s token =>
    if s = 0 then
      .bind (get 72) fun s ns =>
        if s = 0 then
          .bind (get 176) fun s request =>
            if s = 0 then
              .bind (get 232) fun s operation =>
                if s = 0 then
                  .bind (Lemma.Services.Store.RecoveryClient.pollCall token incoming operation ns request) fun replyStatus sequence =>
                    if replyStatus = IPCABI.wouldBlock then
                      .done 0 0
                    else
                      if replyStatus = 0 then
                        .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s detail =>
                          if s = 0 then
                            if detail = 1 then
                              .bind (put 160 9) fun s _ => if statusFailed s = true then .done s 0 else
                              .bind (recoverableIssueControl 15) fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                            else
                              if detail = 2 then
                                .bind (Memory.read64 (incoming+128)) fun s epoch =>
                                  if s = 0 then
                                    .bind (get 688) fun s priorEpoch =>
                                      if s = 0 then
                                        .bind (get 632) fun s known =>
                                          if s = 0 then
                                            .bind (get 672) fun s saved =>
                                              if s = 0 then
                                                if priorEpoch < epoch then
                                                  if saved ≤ known then
                                                    if saved ≤ sequence then
                                                      if known ≤ sequence then
                                                        .bind (put 688 epoch) fun s _ =>
                                                          if s = 0 then
                                                            .bind (put 696 sequence) fun s _ =>
                                                              if s = 0 then
                                                                if sequence = known then recoverableResubmit else if sequence = known+1 then
                                                                  .bind (put 704 0) fun s _ => if statusFailed s = true then .done s 0 else
                                                                  .bind recoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                else saveFailure 234
                                                              else .done s 0
                                                          else .done s 0
                                                      else
                                                        saveFailure 234
                                                    else
                                                      saveFailure 234
                                                  else
                                                    saveFailure 234
                                                else
                                                  saveFailure 234
                                              else .done s 0
                                          else .done s 0
                                      else .done s 0
                                  else .done s 0
                              else
                                saveFailure 234
                          else .done s 0
                      else
                        saveFailure replyStatus
                else .done s 0
            else .done s 0
        else .done s 0
    else .done s 0

def recoverablePumpSave : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 8 then recoverablePollControl else if before = 9 then recoverablePollControl else
  if before = 10 then recoverablePollRead else if before = 11 then recoverablePollRead else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s failureTicket => if statusFailed s = true then .done s 0 else
  .bind retryPumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if after = 0 then
  if (if before = 1 then (1 : UInt64) else if before = 2 then 1 else if before = 3 then 1 else 0) = 1 then
  if status = 2 then if error = 227 then put 680 failureTicket else .done 0 0 else
  if before = 3 then if stage = 2 then
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else put 672 sequence
  else .done 0 0 else .done 0 0
  else .done 0 0 else .done 0 0

def recoverableToolbar (button : UInt64) : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if status < 2 then toolbar button else
  if button = 7 then
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if (if error = 227 then (1 : UInt64) else if error = 234 then 1 else 0) = 1 then
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s contact => if statusFailed s = true then .done s 0 else
  if retained = 1 then if phase ||| checking ||| contact = 0 then recoverableBegin else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0

def recoverableInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      retryCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then retryAppendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then recoverableToolbar (minimum 8 (px / (width / 9))) else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 1 then
      if py < 160 then .done 0 0 else
      .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
      .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
      if Lemma.Notebook.RetryPolicy.offlineBufferAvailable buffer pinned 0 = false then .done 0 0 else
      .bind beginStroke fun s _ => if statusFailed s = true then saveFailure s else
      .bind (put 136 status) fun s _ => if statusFailed s = true then .done s 0 else retryAppendRaw
    else if 2 ≤ status then .done 0 0 else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then toggleCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then if py < 320 then if 24 ≤ px then if px < 408 then coursePress px py else
      .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
      else .done 0 0 else .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
    else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw

def drainRecoverableInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s consumed else
    if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind retryCancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind recoverableInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

def recoverableStep : Action :=
  .bind recoverablePumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpCancelledRedraw else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (get 664) fun s overflow => if statusFailed s = true then .done s 0 else
  .bind (if overflow = 1 then .done 0 0 else if retained = 1 then .done 0 0 else if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then retryCancelInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else recoverableInputSample
  else .bind (drainRecoverableInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

private def mainWithRecoverableExecution (bootArgument selection bulkMode : UInt64) : Action :=
  if 3 < bootArgument then failed else
  if (if selection = 3 then true else false) = false then failed else
  .boundedFoldU64 96 clearStep 96 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 592 recoverableVersion) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 selection) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 bulkMode) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument % 2 = 1 then initializeMedium else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 512 then failed else if 4096 < width then failed else
  if height < 320 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if bulkMode = 1 then Surface.allocateBulk else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 672 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop recoverableStep

/-- Recovery software root, version2. Host attach and control receipts do not
acknowledge data; the ordinary publication chain is still mandatory. -/
def mainRecoverableSumsBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithRecoverableExecution bootArgument 3 1 else
  if bootArgument = 3 then mainWithRecoverableExecution bootArgument 3 1 else failed

/-! Append-only Recovery3 family. Existing roots and all definitions
above remain literal; this new family selects Closure7/Doc8 only. -/

def closureRecoverableVersion : UInt64 := 3

/-- The new stage3 path binds the actual still-current namespace/page and
validates a literal Doc8 snapshot before any retry or completion. Historical
raw/page/root checks remain the existing scalar policy. This is neither an
execution result nor a durability receipt. -/
private def closureRecoverableValidateRecord (source bytes object stage : UInt64) : Action :=
  if Lemma.Notebook.RetryClosurePolicy.retainedRecordValid source bytes object stage = false then
    .done 234 0
  else if stage = 3 then
    .bind (get 72) fun s ns =>
      if statusFailed s = true then .done s 0 else
      .bind (get 80) fun s page =>
        if statusFailed s = true then .done s 0 else
        if object = Lemma.Documents.Mathematics.object page then
          .bind (get 536) fun s checking =>
            if statusFailed s = true then .done s 0 else
            if checking = 0 then
              .bind (Lemma.Documents.Mathematics.field source 8) fun s version =>
                if statusFailed s = true then .done s 0 else
                if version = 8 then Lemma.Documents.MathematicsClosure.validate source ns page
                else .done 234 0
            else .done 234 0
        else .done 234 0
  else .done 0 0

def closureRecoverableRetainFailure (knownSequence : UInt64) : Action :=
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  .bind (get 208) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 216) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryClosurePolicy.retainableFailure error source bytes object stage = false then .done 0 0 else
  .bind (closureRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then put 640 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 600 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 608 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 616 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 624 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 632 knownSequence) fun s _ => if statusFailed s = true then .done s 0 else
  put 648 1

def closureRecoverableTransactionPump : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 7 then saveFailure 234 else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s known => if statusFailed s = true then .done s 0 else
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if after = 0 then if status = 2 then
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 0 then closureRecoverableRetainFailure known else
    if before = 1 then closureRecoverableRetainFailure known else
    if before = 2 then closureRecoverableRetainFailure known else
    if before = 3 then closureRecoverableRetainFailure known else .done 0 0
  else if before = 3 then if Lemma.Notebook.RetryClosurePolicy.publicationEnds stage = true then
    .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else put 640 0
  else .done 0 0 else .done 0 0 else .done 0 0

private def closureRecoverableIssueControl (operation : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.RecoveryClient.beginCall endpoint outgoing operation ns ticket request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else put 232 operation

def closureRecoverableBegin : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 640) fun s attempts => if statusFailed s = true then .done s 0 else
  let allowed := Lemma.Notebook.RetryClosurePolicy.retryStatus attempts source bytes object stage
  if statusFailed allowed = true then saveFailure allowed else
  .bind (closureRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  if ticket = 0 then saveFailure 234 else
  .bind (put 640 (attempts+1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 known object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (closureRecoverableIssueControl 14) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

private def closureRecoverableResubmit : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryClosurePolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  .bind (closureRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

/-- The remount receipt follows a real durability barrier. Full exact READ/EOF
of known+1 reconciles the original record once; it never issues another PUT for
that record. Only subsequent page/root stages use new ordinary transactions. -/

private def closureRecoverableFinishRetained : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryClosurePolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  .bind (closureRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  if known = 0x7fffffffffffffff then saveFailure 234 else
  if observed = known+1 then
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 208 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 216 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 200 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 384 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind finishRecord fun s result => if statusFailed s = true then saveFailure s else
  if Lemma.Notebook.RetryClosurePolicy.publicationEnds stage = true then
    .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 640 0) fun s _ => if statusFailed s = true then .done s 0 else put 672 observed
  else .done 0 result
  else saveFailure 234

private def closureRecoverableIssueRead : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 704) fun s offset => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryClosurePolicy.retainedRecordValid source bytes object stage = false then .done 234 0 else
  if offset % 8 = 0 then
  if offset < bytes then
  let count := minimum 128 (bytes-offset)
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 offset count 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 count) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 10
  else .done 234 0 else .done 234 0

private def closureRecoverableIssueEndRead : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 bytes 8 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 11

private def closureRecoverableCompareStep (i _ : UInt32) (acc source offset _ _ : UInt64) : Action :=
  .bind (Memory.read64 (source+offset+i.toUInt64*8)) fun s expected => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (incoming+128+i.toUInt64*8)) fun s observed => if statusFailed s = true then .done s 0 else
  if expected = observed then .done 0 (acc+8) else .done 234 0

def closureRecoverablePollRead : Action :=
  .bind (get 168) fun s token =>
    if s = 0 then
      .bind (get 72) fun s ns =>
        if s = 0 then
          .bind (get 616) fun s object =>
            if s = 0 then
              .bind (get 176) fun s request =>
                if s = 0 then
                  .bind (get 448) fun s expectedCount =>
                    if s = 0 then
                      .bind (Lemma.Services.Store.Client.pollCall token incoming 5 ns object request expectedCount) fun replyStatus sequence =>
                        if replyStatus = IPCABI.wouldBlock then
                          .done 0 0
                        else
                          if replyStatus = 0 then
                            .bind (get 696) fun s mounted =>
                              if s = 0 then
                                if sequence = mounted then
                                  .bind (Lemma.Services.Store.Client.responseField incoming 56) fun s count =>
                                    if s = 0 then
                                      .bind (get 160) fun s phase =>
                                        if s = 0 then
                                          if phase = 11 then
                                            if count = 0 then
                                              closureRecoverableFinishRetained
                                            else
                                              saveFailure 234
                                          else
                                            if count = expectedCount then
                                              if 0 < count then
                                                if count ≤ 128 then
                                                  if count % 8 = 0 then
                                                    .bind (get 600) fun s source =>
                                                      if s = 0 then
                                                        .bind (get 704) fun s offset =>
                                                          if s = 0 then
                                                            .bind (get 608) fun s bytes =>
                                                              if s = 0 then
                                                                if offset ≤ bytes then
                                                                  if count ≤ bytes-offset then
                                                                    .boundedFoldU64 16 closureRecoverableCompareStep (count/8).toUInt32 0 source offset 0 0 fun s compared =>
                                                                      if s = 0 then
                                                                        if compared = count then
                                                                          .bind (put 704 (offset+count)) fun s _ =>
                                                                            if s = 0 then
                                                                              if offset+count = bytes then
                                                                                .bind closureRecoverableIssueEndRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                              else
                                                                                .bind closureRecoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                            else .done s 0
                                                                        else
                                                                          saveFailure 234
                                                                      else
                                                                        saveFailure s
                                                                  else
                                                                    saveFailure 234
                                                                else
                                                                  saveFailure 234
                                                              else .done s 0
                                                          else .done s 0
                                                      else .done s 0
                                                  else
                                                    saveFailure 234
                                                else
                                                  saveFailure 234
                                              else
                                                saveFailure 234
                                            else
                                              saveFailure 234
                                        else .done s 0
                                    else .done s 0
                                else
                                  saveFailure 234
                              else .done s 0
                          else
                            saveFailure replyStatus
                    else .done s 0
                else .done s 0
            else .done s 0
        else .done s 0
    else .done s 0

def closureRecoverablePollControl : Action :=
  .bind (get 168) fun s token =>
    if s = 0 then
      .bind (get 72) fun s ns =>
        if s = 0 then
          .bind (get 176) fun s request =>
            if s = 0 then
              .bind (get 232) fun s operation =>
                if s = 0 then
                  .bind (Lemma.Services.Store.RecoveryClient.pollCall token incoming operation ns request) fun replyStatus sequence =>
                    if replyStatus = IPCABI.wouldBlock then
                      .done 0 0
                    else
                      if replyStatus = 0 then
                        .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s detail =>
                          if s = 0 then
                            if detail = 1 then
                              .bind (put 160 9) fun s _ => if statusFailed s = true then .done s 0 else
                              .bind (closureRecoverableIssueControl 15) fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                            else
                              if detail = 2 then
                                .bind (Memory.read64 (incoming+128)) fun s epoch =>
                                  if s = 0 then
                                    .bind (get 688) fun s priorEpoch =>
                                      if s = 0 then
                                        .bind (get 632) fun s known =>
                                          if s = 0 then
                                            .bind (get 672) fun s saved =>
                                              if s = 0 then
                                                if priorEpoch < epoch then
                                                  if saved ≤ known then
                                                    if saved ≤ sequence then
                                                      if known ≤ sequence then
                                                        .bind (put 688 epoch) fun s _ =>
                                                          if s = 0 then
                                                            .bind (put 696 sequence) fun s _ =>
                                                              if s = 0 then
                                                                if sequence = known then closureRecoverableResubmit else if sequence = known+1 then
                                                                  .bind (put 704 0) fun s _ => if statusFailed s = true then .done s 0 else
                                                                  .bind closureRecoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                else saveFailure 234
                                                              else .done s 0
                                                          else .done s 0
                                                      else
                                                        saveFailure 234
                                                    else
                                                      saveFailure 234
                                                  else
                                                    saveFailure 234
                                                else
                                                  saveFailure 234
                                              else .done s 0
                                          else .done s 0
                                      else .done s 0
                                  else .done s 0
                              else
                                saveFailure 234
                          else .done s 0
                      else
                        saveFailure replyStatus
                else .done s 0
            else .done s 0
        else .done s 0
    else .done s 0

def closureRecoverablePumpSave : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 8 then closureRecoverablePollControl else if before = 9 then closureRecoverablePollControl else
  if before = 10 then closureRecoverablePollRead else if before = 11 then closureRecoverablePollRead else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s failureTicket => if statusFailed s = true then .done s 0 else
  .bind closureRecoverableTransactionPump fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if after = 0 then
  if (if before = 1 then (1 : UInt64) else if before = 2 then 1 else if before = 3 then 1 else 0) = 1 then
  if status = 2 then if error = 227 then put 680 failureTicket else .done 0 0 else
  if before = 3 then if Lemma.Notebook.RetryClosurePolicy.publicationEnds stage = true then
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else put 672 sequence
  else .done 0 0 else .done 0 0
  else .done 0 0 else .done 0 0

def closureRecoverableToolbar (button : UInt64) : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if status < 2 then toolbar button else
  if button = 7 then
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if (if error = 227 then (1 : UInt64) else if error = 234 then 1 else 0) = 1 then
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s contact => if statusFailed s = true then .done s 0 else
  if retained = 1 then if phase ||| checking ||| contact = 0 then closureRecoverableBegin else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0

def closureRecoverableInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      retryCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then retryAppendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then closureRecoverableToolbar (minimum 8 (px / (width / 9))) else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 1 then
      if py < 160 then .done 0 0 else
      .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
      .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
      if Lemma.Notebook.RetryPolicy.offlineBufferAvailable buffer pinned 0 = false then .done 0 0 else
      .bind beginStroke fun s _ => if statusFailed s = true then saveFailure s else
      .bind (put 136 status) fun s _ => if statusFailed s = true then .done s 0 else retryAppendRaw
    else if 2 ≤ status then .done 0 0 else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then toggleCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then if py < 320 then if 24 ≤ px then if px < 408 then coursePress px py else
      .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
      else .done 0 0 else .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
    else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw

def drainClosureRecoverableInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s consumed else
    if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind retryCancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind closureRecoverableInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

def closureRecoverableStep : Action :=
  .bind closureRecoverablePumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpCancelledRedraw else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (get 664) fun s overflow => if statusFailed s = true then .done s 0 else
  .bind (if overflow = 1 then .done 0 0 else if retained = 1 then .done 0 0 else if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then retryCancelInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else closureRecoverableInputSample
  else .bind (drainClosureRecoverableInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

private def mainWithClosureRecoverableExecution (bootArgument selection bulkMode : UInt64) : Action :=
  if 3 < bootArgument then failed else
  if (if selection = 7 then true else false) = false then failed else
  .boundedFoldU64 96 clearStep 96 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 592 closureRecoverableVersion) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 selection) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 bulkMode) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument % 2 = 1 then initializeMedium else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 512 then failed else if 4096 < width then failed else
  if height < 320 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if bulkMode = 1 then Surface.allocateBulk else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 672 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop closureRecoverableStep

/-- Recovery software root, version3. Host attach and control receipts do not
acknowledge data; the ordinary publication chain is still mandatory. -/

def mainRecoverableClosureBulk (bootArgument : UInt64) : Action :=
  if bootArgument = 2 then mainWithClosureRecoverableExecution bootArgument 7 1 else
  if bootArgument = 3 then mainWithClosureRecoverableExecution bootArgument 7 1 else failed

end Lemma.Applications.Notebook

/-! Additive installed-course workspace path. Historical roots and definitions
are unchanged. A separate software deployment must select the completed root;
component code below alone does not establish a running Notebook workflow. -/
namespace Lemma.Applications.Notebook
open Lemma.Core0.Memory Lemma.User Lemma.Ink

private def packageBytes : UInt64 := 0x332000
private def packageGlyphs : UInt64 := 0x33a000
private def packageWorkspace : UInt64 := 0x33b000
private def packageContext : UInt64 := 0x33c000
private def packageDocumentStage : UInt64 := 0x33d000
private def packageState : UInt64 := packageContext + 2048
private def packageOutgoing : UInt64 := packageContext + 512
private def packageIncoming : UInt64 := packageContext + 256
private def packageBindingScratch : UInt64 := packageContext + 1024
private def packageSubmitted : UInt64 := packageContext + 1152
-- Layout2 keeps this owned word below the Store outgoing packet.
private def packageAllocationAddress : UInt64 := state + 752
private def packageGet (offset : UInt64) : Action := Memory.read64 (packageState + offset)
private def packagePut (offset value : UInt64) : Action := Memory.write64 (packageState + offset) value

-- The old offset768 aliases Notebook.outgoing. Keep this counter wholly
-- below its0x20b00 Store packet, including across mount/save traffic.
private def packageAllocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if i.toUInt64 < allocated then .done 0 (acc + 1) else
  if i.toUInt64 = allocated then
  let address := packageBytes + i.toUInt64 * 4096
  .bind (Syscall.allocatePage address) fun s actual => if statusFailed s = true then .done s 0 else
  if actual = address then
  .bind (Memory.write64 packageAllocationAddress (allocated + 1)) fun s _ => if statusFailed s = true then .done s 0 else .done 0 (acc + 1)
  else failed else failed

/-- Twelve lazy owned pages retain zero-before-publication, generation/quota
and mapping checks. A checked allocation failure keeps its actual completed
prefix for a later explicit attempt; pumps cannot touch these private spans
until the complete count12 is present. It does not stop ordinary ink handling. -/
private def allocatePackage : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if 12 < allocated then failed else if allocated = 12 then .done 0 0 else
  .boundedFoldU64 12 packageAllocateStep 12 0 0 0 0 0 fun s actual =>
  if statusFailed s = true then .done s 0 else if actual = 12 then .done 0 0 else failed

private def packageConfigureStep (i _ : UInt32) (acc endpoint ns reference first : UInt64) : Action :=
  let value := if i = 0 then endpoint else if i = 1 then packageOutgoing else
    if i = 2 then packageIncoming else if i = 3 then ns else
    if i = 4 then reference &&& 0xffff else if i = 5 then reference >>> 16 else
    if i = 6 then packageBytes else if i = 7 then 32768 else first
  .bind (Memory.write64 (packageContext + i.toUInt64 * 8) value) fun s _ => .done s acc

/-- A reader reserves its entire bounded request-ID span before beginning.
Writing/canceling later cannot reuse an ID already assigned to this reader. -/
private def beginPackageRead (identity edition : UInt64) : Action :=
  if identity = 0 then .done 240 0 else if 65535 < identity then .done 240 0 else
  if edition = 0 then .done 240 0 else if 0xffffffff < edition then .done 240 0 else
  .bind allocatePackage fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageContext + 80)) fun s existing => if statusFailed s = true then .done s 0 else
  if existing = 0 then
  .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s documentNs => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  let ns := if school = 1 then Lemma.Courses.PackageCommand.selectedPackageNamespace else documentNs
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe - 257 < request then .done 235 0 else
  .bind (put 176 (request + 257)) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 9 packageConfigureStep 9 0 endpoint ns (identity ||| (edition <<< 16)) (request + 1)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageReader.start packageContext) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then
    .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else packagePut 256 floor
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  if 0xffffffffffffffff - 300000000 < now then .done 235 0 else
  .bind (packagePut 40 (now + 300000000)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 48 identity) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 56 edition) fun s _ => if statusFailed s = true then .done s 0 else
  packagePut 32 1
  else .done 231 0

/-- Every successfully admitted READ advances the observed sequence floor only.
This never publishes durable success. EOF uses the separately reserved257th
request after full CRC/identity validation; phase2 is visible only after EOF. -/
private def packageReadFloor : Action :=
  .bind (Lemma.Services.Store.Client.responseField packageIncoming 40) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then packageGet 256 else get 128) fun s floor => if statusFailed s = true then .done s 0 else
  if sequence < floor then .done 234 0 else
  .bind (if school = 1 then packagePut 256 sequence else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  observeStoreSequence sequence

private def packageReadComplete : Action :=
  .bind (packagePut 32 2) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 72 1) fun s _ => if statusFailed s = true then .done s 0 else packagePut 144 1

private def packageReadEOF (phase : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageContext + 24)) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (packageGet 48) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (packageGet 56) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageContext + 64)) fun s first => if statusFailed s = true then .done s 0 else
  let object := Lemma.Courses.PackageFormat.object identity edition
  if phase = 3 then
    .bind (Lemma.Services.Store.Client.beginCall endpoint packageOutgoing 5 ns object 0 length 1 0 (first + 256)) fun s pending =>
    if statusFailed s = true then .done s 0 else if pending = 0 then .done IPCABI.invalidTransaction 0 else
    .bind (Memory.write64 (packageContext + 80) pending) fun s _ => if statusFailed s = true then .done s 0 else packagePut 32 5
  else
    .bind (Memory.read64 (packageContext + 80)) fun s pending => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Services.Store.Client.pollCall pending packageIncoming 5 ns object (first + 256) 1) fun result _ =>
    if result = IPCABI.wouldBlock then .done 0 0 else
    .bind (Memory.write64 (packageContext + 80) 0) fun s _ => if statusFailed s = true then .done s 0 else
    if statusFailed result = true then .done result 0 else
    .bind packageReadFloor fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Services.Store.Client.responseField packageIncoming 48) fun s mode => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Services.Store.Client.responseField packageIncoming 56) fun s count => if statusFailed s = true then .done s 0 else
    if mode = 1 then if count = 0 then packageReadComplete else .done 240 0 else .done 240 0

private def pumpPackageRead : Action :=
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  let work := if phase = 1 then (1 : UInt64) else if phase = 3 then 1 else if phase = 5 then 1 else 0
  if work = 1 then
  .bind (packageGet 40) fun s deadline => if statusFailed s = true then .done s 0 else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  if deadline ≤ now then .done IPCABI.timeout 0 else
  if phase = 3 then packageReadEOF phase else if phase = 5 then packageReadEOF phase else
  .bind (Memory.read64 (packageContext + 72)) fun s oldPhase => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageReader.step packageContext) fun s _ =>
  if s = IPCABI.wouldBlock then .done 0 0 else if statusFailed s = true then .done s 0 else
  .bind (if oldPhase = 1 then packageReadFloor else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageContext + 72)) fun s rawPhase => if statusFailed s = true then .done s 0 else
  if rawPhase = 2 then
    .bind (Lemma.Courses.PackageReader.finish packageContext) fun s length => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (packageBytes + 80)) fun s crc => if statusFailed s = true then .done s 0 else
    .bind (packageGet 160) fun s expected => if statusFailed s = true then .done s 0 else
    if expected = 0 then finish length else if expected = crc then finish length else .done 243 0
  else .done 0 0
  else .done 0 0
where
  finish (length : UInt64) : Action :=
    .bind (packagePut 0 length) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageGet 176) fun s ordinal => if statusFailed s = true then .done s 0 else
    .bind (packagePut 8 ordinal) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 16 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 24 0) fun s _ => if statusFailed s = true then .done s 0 else packagePut 32 3

private def packageTileStep (i _ : UInt32) (acc width changed _ _ : UInt64) : Action :=
  let column := i.toUInt64 % 13
  let row := i.toUInt64 / 13
  if changed &&& ((1 : UInt64) <<< column) = 0 then .done 0 acc else
  if changed &&& ((1 : UInt64) <<< (13 + row)) = 0 then .done 0 acc else
  .bind (markDirtyTile ((10 + row) * ((width + 31) / 32) + column)) fun s _ => .done s acc

/-- The existing genuine package renderer validates source/cache/framebuffer
spans and builds its actual owned pixels. Only the old Notebook dirty/controller
path publishes them; no new renderer or host ink path is introduced. -/
private def renderPackageText : Action :=
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s ordinal => if statusFailed s = true then .done s 0 else
  .bind (packageGet 16) fun s role => if statusFailed s = true then .done s 0 else
  .bind (packageGet 24) fun s position => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
   .bind (if role < 8 then
    Lemma.Courses.PackageRender.renderAlignedSelectedDelta packageBytes length ordinal role position packageGlyphs width height
    else if role < 12 then
    Lemma.Courses.PackageRender.renderAlignedHeaderSelectedDelta packageBytes length (role - 8) position packageGlyphs width height
    else .done 241 0)
    fun s next => if statusFailed s = true then .done s 0 else
  let changed := next >>> 32
  .boundedFoldU64 130 packageTileStep 130 0 width changed 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 64 (next &&& 0xffffffff)) fun s _ => if statusFailed s = true then .done s 0 else
  if changed = 0 then .done 0 0 else dirty 0 320 416 640
  else .done 244 0

/-- Stage an explicitly selected exercise, with its canonical typed goal and
new revision, in an unpublished wrapper. Untrusted prose is never a goal. The
active wrapper/current Doc8 are read-only throughout this operation. Caller
cancels and consumes any outstanding checker before invoking this Action and
publishes only its successful staging result through the ordinary Store path. -/
private def stagePackageExercise (ordinal : UInt64) : Action :=
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.eventCapacity mathematics) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe ≤ revision then .done 235 0 else
  .bind (Lemma.Courses.PackageBinding.capture packageBindingScratch packageBytes length ordinal (revision + 1))
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 64)) fun s goal => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 80)) fun s domain => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 88)) fun s assumptions => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 96)) fun s budget => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageWorkspace.stageRefresh packageWorkspace mathematics mathematicsSave)
    fun s _ => if statusFailed s = true then .done s 0 else
  let stagedDocument := mathematicsSave + Lemma.Courses.PackageWorkspace.inner
  .bind (Lemma.Documents.Mathematics.revise stagedDocument) fun s actual => if statusFailed s = true then .done s 0 else
  if actual = revision + 1 then
  .bind (Lemma.Documents.Mathematics.put stagedDocument 48 goal) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.put stagedDocument 120 domain) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.put stagedDocument 128 assumptions) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.put stagedDocument 136 budget) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.appendEvent stagedDocument 4 1 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageWorkspace.captureSelection mathematicsSave packageBytes length ordinal packageBindingScratch)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageWorkspace.validate mathematicsSave ns page) fun s _ =>
  if statusFailed s = true then .done s 0 else .done 0 mathematicsSave
  else .done 234 0
  else .done 244 0

/-- Keep the source buffer frozen until the real append/BARRIER reply. Wrapper
RAM validation is never the notebook Saved transition. The ordinary save pump
supplies namespace/sequence and publishes its existing Pending/Failed/Saved. -/
private def savePackageWorkspace : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.WorkspaceCodec.encode packageWorkspace mathematicsSave ns page) fun s length =>
  if statusFailed s = true then .done s 0 else
  .bind (startSave mathematicsSave length (Lemma.Courses.PackageWorkspace.object page) 3)
    fun s _ => if statusFailed s = true then saveFailure s else publishStatus
  else .done 231 0


/-- No other process or DMA owns these private spans. During this Action the
validated staging bytes remain immutable; interrupts may suspend execution but
cannot edit the owned source. Publication faults remain actual access errors,
not rollback promises. Cold recovery always comes from the acknowledged Store
record, never this partly published RAM. -/
private def adoptPackageStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let offset := 8 + i.toUInt64 * 8
  .bind (Memory.read64 (mathematicsSave + offset)) fun s value => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (packageWorkspace + offset) value) fun s _ => .done s acc

private def adoptPackageWorkspace : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageWorkspace.validate mathematicsSave ns page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageWorkspace 0) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 463 adoptPackageStep 463 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.copyCurrent (mathematicsSave + Lemma.Courses.PackageWorkspace.inner) mathematics)
    fun s copied => if statusFailed s = true then .done s 0 else
  if copied = Lemma.Documents.Mathematics.currentBytes then
  Memory.write64 packageWorkspace Lemma.Courses.PackageWorkspace.magic else .done 240 0

private def renderPackageCourse : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.Arithmetic.renderSparse mathematics width) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 65 courseTileStep 65 0 width 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  dirty 0 160 416 320

/- All current course publications, including checker replies and restored
selections, use the same revision-bound renderer as numeric input. Keep the
historical sparse declaration for predecessor source/artifact identities. -/
private def renderPackageCourseScoped : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.ArithmeticAligned.render mathematics width) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 65 courseTileStep 65 0 width 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  dirty 0 160 416 320

private def publishPackageWorkspace : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind adoptPackageWorkspace fun s _ => if statusFailed s = true then .done s 0 else
  .bind renderPackageCourseScoped fun s _ => if statusFailed s = true then .done s 0 else
  .bind reportCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 1) fun s _ => if statusFailed s = true then .done s 0 else savePackageWorkspace
  else .done 231 0

/-- Capture selection before the real Protocol7 call. Its copied typed payload
and package snapshot stay private and immutable until terminal consumption.
The same one-pending-call ABI governs reader, checker and Store. -/
private def beginPackageArithmetic : Action :=
  .bind (get 528) fun s endpoint => if statusFailed s = true then .done s 0 else
  if endpoint = 0 then .done 241 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageWorkspace.validate packageWorkspace ns page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 144) fun s attempts => if statusFailed s = true then .done s 0 else
  if 8 ≤ attempts then .done 235 0 else
  .bind (Memory.read64 (packageWorkspace + 48)) fun s mask => if statusFailed s = true then .done s 0 else
  .bind (if (mask >>> 8) &&& 1 = 1 then
    .bind (Lemma.Courses.PackageWorkspace.snapshotSelection packageWorkspace packageSubmitted) fun s _ =>
    if statusFailed s = true then .done s 0 else packagePut 80 1
    else packagePut 80 0) fun s _ => if statusFailed s = true then .done s 0 else beginArithmetic

/-- Only the existing admitted Protocol7 terminal reply can reach this helper.
Completion occurs in the separate Doc8 staging page; a failed provenance or
resource guard cannot change the active mathematical object/history. -/
private def stagePackageCompletion : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 24)) fun s submittedNS => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 32)) fun s submittedPage => if statusFailed s = true then .done s 0 else
  if ns = submittedNS then if page = submittedPage then
  .bind (Memory.read64 (mathematicsIO + 40)) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 48)) fun s goal => if statusFailed s = true then .done s 0 else
  .bind (get 560) fun s outcome => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 104)) fun s request => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (mathematicsIO + 96)) fun s budget => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.copyCurrent mathematics packageDocumentStage) fun s copied => if statusFailed s = true then .done s 0 else
  if copied = Lemma.Documents.Mathematics.currentBytes then
  .bind (Lemma.Documents.MathematicsClosure.completeExecution packageDocumentStage revision goal outcome request budget)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 80) fun s known => if statusFailed s = true then .done s 0 else
  if known = 1 then
    Lemma.Courses.PackageWorkspace.stageCompleted packageWorkspace packageDocumentStage packageSubmitted request mathematicsSave
  else if known = 0 then
    Lemma.Courses.PackageWorkspace.stageCompletedUnknown packageWorkspace packageDocumentStage request mathematicsSave
  else .done 240 0
  else .done 240 0 else .done 234 0 else .done 234 0

private def pumpPackageArithmetic : Action :=
  .bind (get 536) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 0 then .done 0 0 else
  .bind (if phase = 1 then
    .bind (get 544) fun s transaction => if statusFailed s = true then .done s 0 else
    .bind (get 552) fun s request => if statusFailed s = true then .done s 0 else
    .bind (pollArithmetic transaction (mathematicsIO + 256) mathematicsIO request) fun s outcome =>
    if s = IPCABI.wouldBlock then .done 0 0 else
    .bind (put 560 outcome) fun stored _ => if statusFailed stored = true then .done stored 0 else
    .bind (put 568 s.toUInt64) fun stored _ => if statusFailed stored = true then .done stored 0 else
    put 536 (if s = 0 then 2 else 3)
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 1 then .done 0 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke = 0 then
  .bind (put 536 0) fun s _ => if statusFailed s = true then .done s 0 else
  if phase = 3 then
    .bind (get 568) fun s error => if statusFailed s = true then .done s 0 else courseError error.toUInt8
  else if phase = 2 then
    .bind stagePackageCompletion fun s _ => if statusFailed s = true then courseError s else publishPackageWorkspace
  else .done 234 0 else .done 0 0


private def packageRecord : UInt64 := packageContext + 128
private def recordGet (offset : UInt64) : Action := Memory.read64 (packageRecord + offset)
private def recordPut (offset value : UInt64) : Action := Memory.write64 (packageRecord + offset) value

/-- A private fixed-record reader yields after one actual Store begin/poll.
Configuration stays immutable until terminal consumption; publication requires
an independently observed exact EOF, not just a header's declared length. -/
private def startPackageRecord (object target length headerOnly : UInt64) : Action :=
  if length = 0 then .done 240 0 else if 4096 < length then .done 242 0 else
  if 1 < headerOnly then .done 240 0 else
  if (if headerOnly = 1 then if length = 64 then (1 : UInt64) else 0 else 1) = 0 then .done 240 0 else
  .bind (recordGet 32) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  if 0xffffffffffffffff - 300000000 < now then .done 242 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (recordPut 0 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 8 target) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 16 length) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 24 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 40 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 48 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 64 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 72 (now + 300000000)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 80 ns) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then
    .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else recordPut 96 floor
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 88 headerOnly) fun s _ => if statusFailed s = true then .done s 0 else recordPut 56 0
  else .done 231 0

private def stopPackageRecord (status : UInt8) : Action :=
  .bind (recordPut 64 status.toUInt64) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 56 5) fun s _ => if statusFailed s = true then .done s 0 else .done status 0

private def cancelPackageRecord : Action :=
  .bind (recordGet 32) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (if pending = 0 then .done 0 0 else
    .bind (IPC.cancel pending) fun s _ =>
    if (if s = 0 then (1 : UInt64) else if s = IPCABI.alreadyCompleted then 1 else 0) = 1 then
    .bind (Syscall.call 67 pending packageIncoming IPCABI.maximumPacket 0 0) fun terminal _ =>
    if terminal = IPCABI.wouldBlock then .done IPCABI.invalidTransaction 0 else .done 0 0
    else .done s 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 32 0) fun s _ => if statusFailed s = true then .done s 0 else stopPackageRecord IPCABI.canceled

private def beginPackageRecordPiece (phase : UInt64) : Action :=
  .bind (recordGet 0) fun s object => if statusFailed s = true then .done s 0 else
  .bind (recordGet 16) fun s length => if statusFailed s = true then .done s 0 else
  .bind (recordGet 24) fun s copied => if statusFailed s = true then .done s 0 else
  .bind (recordGet 80) fun s ns => if statusFailed s = true then .done s 0 else
  if copied ≤ length then
  let count := if phase = 2 then (1 : UInt64) else minimum 128 (length - copied)
  if count = 0 then .done 240 0 else
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint packageOutgoing 5 ns object 0 copied count 0 request)
    fun s pending => if statusFailed s = true then stopPackageRecord s else
  if pending = 0 then stopPackageRecord IPCABI.invalidTransaction else
  .bind (recordPut 32 pending) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 40 count) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (recordPut 48 request) fun s _ => if statusFailed s = true then .done s 0 else
  recordPut 56 (if phase = 2 then 3 else 1)
  else .done 240 0

private def pollPackageRecordPiece (phase : UInt64) : Action :=
  .bind (recordGet 0) fun s object => if statusFailed s = true then .done s 0 else
  .bind (recordGet 8) fun s target => if statusFailed s = true then .done s 0 else
  .bind (recordGet 16) fun s length => if statusFailed s = true then .done s 0 else
  .bind (recordGet 24) fun s copied => if statusFailed s = true then .done s 0 else
  .bind (recordGet 32) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (recordGet 40) fun s count => if statusFailed s = true then .done s 0 else
  .bind (recordGet 48) fun s request => if statusFailed s = true then .done s 0 else
  .bind (recordGet 80) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.pollCall pending packageIncoming 5 ns object request count) fun result sequence =>
  if result = IPCABI.wouldBlock then .done 0 0 else
  .bind (recordPut 32 0) fun s _ => if statusFailed s = true then .done s 0 else
  if statusFailed result = true then stopPackageRecord result else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then recordGet 96 else get 128) fun s floor => if statusFailed s = true then .done s 0 else
  if sequence < floor then stopPackageRecord 234 else
  .bind (if school = 1 then recordPut 96 sequence else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (observeStoreSequence sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField packageIncoming 48) fun s mode => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField packageIncoming 56) fun s actual => if statusFailed s = true then .done s 0 else
  if mode = 1 then if phase = 3 then
    if actual = 0 then recordPut 56 4 else stopPackageRecord 240
  else if actual = count then if copied < length then if count ≤ length - copied then
    .bind (Lemma.Services.Store.Format.copy (Lemma.Services.Store.Client.responseData packageIncoming) (target + copied) count)
      fun s _ => if statusFailed s = true then stopPackageRecord s else
    .bind (recordPut 24 (copied + count)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (recordGet 88) fun s headerOnly => if statusFailed s = true then .done s 0 else
    recordPut 56 (if copied + count = length then if headerOnly = 1 then 4 else 2 else 0)
  else stopPackageRecord 240 else stopPackageRecord 240 else stopPackageRecord 240
  else stopPackageRecord 240

private def pumpPackageRecord : Action :=
  .bind (recordGet 56) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 4 then .done 0 1 else if phase = 5 then
    .bind (recordGet 64) fun s error => if statusFailed s = true then .done s 0 else .done error.toUInt8 0
  else
  .bind (recordGet 72) fun s deadline => if statusFailed s = true then .done s 0 else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  if deadline ≤ now then
    .bind cancelPackageRecord fun s _ => if s = IPCABI.canceled then stopPackageRecord IPCABI.timeout else .done s 0
  else if phase = 0 then beginPackageRecordPiece phase else if phase = 2 then beginPackageRecordPiece phase
  else if phase = 1 then pollPackageRecordPiece phase else if phase = 3 then pollPackageRecordPiece phase else .done 240 0


private def packageCourseError (status : UInt8) : Action :=
  .bind (packagePut 96 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else courseError status

private def finishOpenPackageCourse (migration : UInt64) : Action :=
  .bind adoptPackageWorkspace fun s _ => if statusFailed s = true then packageCourseError s else
  .bind (packagePut 120 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 96 4) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 512 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind renderPackageCourseScoped fun s _ => if statusFailed s = true then .done s 0 else
  .bind reportCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if migration = 1 then savePackageWorkspace else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageWorkspace + 48)) fun s mask => if statusFailed s = true then .done s 0 else
  .bind (if (mask >>> 8) &&& 1 = 1 then restoreSelection else
    .bind (packagePut 128 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 136 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else packagePut 176 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 1) fun s _ => if statusFailed s = true then .done s 0 else packagePut 152 1
where
  restoreSelection : Action :=
    let selection := packageWorkspace + Lemma.Courses.PackageWorkspace.selection
    .bind (Memory.read64 (selection + 16)) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (selection + 24)) fun s edition => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (selection + 32)) fun s crc => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (selection + 40)) fun s node => if statusFailed s = true then .done s 0 else
    .bind (packagePut 128 identity) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 136 edition) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 160 crc) fun s _ => if statusFailed s = true then .done s 0 else packagePut 176 (node - 1)

private def openPackageCourse : Action :=
  .bind allocateCourse fun s _ => if statusFailed s = true then courseError s else
  .bind allocatePackage fun s _ => if statusFailed s = true then courseError s else
  .bind (packagePut 232 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 240 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (packagePut 120 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 32 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 72 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startPackageRecord (Lemma.Courses.PackageWorkspace.object page) mathematicsSave 64 1)
    fun s _ => if statusFailed s = true then packageCourseError s else packagePut 96 1

/-- Reopen reads only through the actual Store endpoint. Missing workspace
alone permits importing the old Doc8 object; malformed/unsupported records never
format or overwrite anything. Header bytes select only the bounded full length.
Original old checker/learner evidence is validated and retained as Unknown
package provenance before the new wrapper is staged. -/
private def pumpOpenPackageCourse : Action :=
  .bind (packageGet 96) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 0 then .done 0 0 else if phase = 4 then .done 0 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind pumpPackageRecord fun result _ =>
  .bind (recordGet 56) fun s recordPhase => if statusFailed s = true then .done s 0 else
  if result = 230 then
    if phase = 1 then
      .bind (startPackageRecord (Lemma.Documents.Mathematics.object page) packageDocumentStage 64 1)
        fun s _ => if statusFailed s = true then packageCourseError s else packagePut 96 2
    else if phase = 2 then
      .bind (Lemma.Documents.MathematicsClosure.create packageDocumentStage ns page) fun s _ => if statusFailed s = true then packageCourseError s else
      .bind (Lemma.Courses.PackageWorkspace.create mathematicsSave packageDocumentStage ns page) fun s _ =>
      if statusFailed s = true then packageCourseError s else finishOpenPackageCourse 1
    else packageCourseError result
  else if statusFailed result = true then packageCourseError result else
  if recordPhase = 4 then
    if phase = 1 then
      .bind (Lemma.Courses.WorkspaceCodec.recordLength mathematicsSave) fun s length =>
      if statusFailed s = true then packageCourseError s else
      .bind (startPackageRecord (Lemma.Courses.PackageWorkspace.object page) mathematicsSave length 0)
        fun s _ => if statusFailed s = true then packageCourseError s else packagePut 96 5
    else if phase = 5 then
      .bind (Memory.read64 mathematicsSave) fun s tag => if statusFailed s = true then packageCourseError s else
      .bind (if tag = Lemma.Courses.PackageWorkspace.magic then
        Lemma.Courses.PackageWorkspace.validate mathematicsSave ns page
      else
        .bind (recordGet 16) fun s length => if statusFailed s = true then .done s 0 else
        .bind (Lemma.Courses.WorkspaceCodec.restore mathematicsSave length packageBytes mathematicsSave ns page) fun s copied =>
        if statusFailed s = true then .done s 0 else
        if copied = Lemma.Courses.PackageWorkspace.bytes then .done 0 0 else .done 240 0)
        fun s _ => if statusFailed s = true then packageCourseError s else finishOpenPackageCourse 0
    else if phase = 2 then
      .bind (Lemma.Documents.Mathematics.field packageDocumentStage 8) fun s version => if statusFailed s = true then .done s 0 else
      let length := if version = 1 then Lemma.Documents.Mathematics.legacyBytes else
        if version = 2 then Lemma.Documents.Mathematics.bytes else
        if 3 ≤ version then if version ≤ 8 then Lemma.Documents.Mathematics.currentBytes else 0 else 0
      if length = 0 then packageCourseError 241 else
      .bind (startPackageRecord (Lemma.Documents.Mathematics.object page) packageDocumentStage length 0)
        fun s _ => if statusFailed s = true then packageCourseError s else packagePut 96 3
    else if phase = 3 then
      .bind (Lemma.Documents.MathematicsClosure.validate packageDocumentStage ns page) fun s _ => if statusFailed s = true then packageCourseError s else
      .bind (Lemma.Documents.MathematicsClosure.upgrade packageDocumentStage) fun s _ => if statusFailed s = true then packageCourseError s else
      .bind (Lemma.Courses.PackageWorkspace.create mathematicsSave packageDocumentStage ns page) fun s _ =>
      if statusFailed s = true then packageCourseError s else finishOpenPackageCourse 1
    else packageCourseError 240
  else .done 0 0


/-- Editing a package answer preserves its current lesson only through a new
full package capture bound to the actual new revision. Explicit builtin NEXT
and LIMIT clear only current provenance, retaining old known history. A CHECK
button cannot fall through to the local presentation helper's submit method. -/
private def stagePackagePress (x y : UInt64) : Action :=
  let column := (x - 24) / 12
  let row := (y - 160) / 20
  if row = 4 then if column < 5 then .done 241 0 else stage column row
  else stage column row
where
  stage (column row : UInt64) : Action :=
    .bind (Lemma.Documents.Mathematics.copyCurrent mathematics packageDocumentStage) fun s copied => if statusFailed s = true then .done s 0 else
    if copied = Lemma.Documents.Mathematics.currentBytes then
    .bind (Lemma.Courses.Arithmetic.press packageDocumentStage (x - 24) (y - 160)) fun s _ => if statusFailed s = true then .done s 0 else
    let unknown := if row = 4 then if column < 10 then (1 : UInt64) else if 15 ≤ column then if column < 21 then 1 else 0 else 0 else 0
    .bind (if unknown = 1 then Lemma.Courses.PackageWorkspace.stageUnknownSelection packageWorkspace packageDocumentStage mathematicsSave
      else Lemma.Courses.PackageWorkspace.stageRefresh packageWorkspace packageDocumentStage mathematicsSave)
      fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (mathematicsSave + 48)) fun s mask => if statusFailed s = true then .done s 0 else
    .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
    let recapture := if unknown = 0 then if (mask >>> 8) &&& 1 = 1 then if phase = 2 then (1 : UInt64) else 0 else 0 else 0
    if recapture = 1 then
      .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (mathematicsSave + Lemma.Courses.PackageWorkspace.selection + 16)) fun s identity => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (mathematicsSave + Lemma.Courses.PackageWorkspace.selection + 24)) fun s edition => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (mathematicsSave + Lemma.Courses.PackageWorkspace.selection + 40)) fun s node => if statusFailed s = true then .done s 0 else
      .bind (packageGet 48) fun s loadedIdentity => if statusFailed s = true then .done s 0 else
      .bind (packageGet 56) fun s loadedEdition => if statusFailed s = true then .done s 0 else
      if identity = loadedIdentity then if edition = loadedEdition then if 0 < node then
        Lemma.Courses.PackageWorkspace.captureSelection mathematicsSave packageBytes length (node - 1) packageBindingScratch
      else .done 240 0 else .done 0 0 else .done 0 0
    else .done 0 0
    else .done 240 0

private def packageCoursePress (x y : UInt64) : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| checking = 0 then
  let submit := if 240 ≤ y then if y < 260 then if x < 84 then (1 : UInt64) else 0 else 0 else 0
  if submit = 1 then
    .bind beginPackageArithmetic fun s _ => if statusFailed s = true then courseError s else .done 0 0
  else
    .bind (stagePackagePress x y) fun s _ => if statusFailed s = true then courseError s else publishPackageWorkspace
  else .done 0 0

private def cancelPackageRead : Action :=
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (if phase = 1 then
    .bind (Lemma.Courses.PackageReader.cancel packageContext) fun result _ =>
    if result = IPCABI.canceled then .done 0 0 else .done result 0
    else if phase = 5 then
    .bind (Memory.read64 (packageContext + 80)) fun s pending => if statusFailed s = true then .done s 0 else
    .bind (IPC.cancel pending) fun s _ =>
    if (if s = 0 then (1 : UInt64) else if s = IPCABI.alreadyCompleted then 1 else 0) = 1 then
    .bind (Syscall.call 67 pending packageIncoming IPCABI.maximumPacket 0 0) fun terminal _ =>
    if terminal = IPCABI.wouldBlock then .done IPCABI.invalidTransaction 0 else Memory.write64 (packageContext + 80) 0
    else .done s 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  let canceled := if phase = 1 then (1 : UInt64) else if phase = 3 then 1 else if phase = 5 then 1 else 0
  .bind (packagePut 32 (if canceled = 1 then 4 else phase)) fun s _ => if statusFailed s = true then .done s 0 else
  packagePut 152 0

private def cancelPackageWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind cancelPackageRead fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 96) fun s opening => if statusFailed s = true then .done s 0 else
  let active := if opening = 5 then (1 : UInt64) else if 0 < opening then if opening < 4 then 1 else 0 else 0
  .bind (if active = 1 then
    .bind cancelPackageRecord fun s _ => if s = IPCABI.canceled then .done 0 0 else .done s 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 96 (if active = 1 then 0 else opening)) fun s _ => .done s 0
  else .done 0 0


private def packageHex (value digit : UInt64) : UInt64 :=
  let nibble := (value >>> (digit * 4)) &&& 15
  if nibble < 10 then 48 + nibble else 55 + nibble

/-- These original labels are presentation assets only. The numeric fields
come from requested or actually validated package state, never a host menu. -/
private def packageControlCharacter (row column requested shown position : UInt64) : UInt64 :=
  let chunk := column / 8
  let packed : UInt64 := if row = 0 then
      if chunk = 0 then 0x2020202b45444f4e else if chunk = 1 then 0x2020202b454c4f52 else
      if chunk = 2 then 0x2020202b45474150 else 0x2020202020455355
    else if row = 1 then
      if chunk = 0 then 0x20202b544e454449 else if chunk = 1 then 0x2020202b54494445 else
      if chunk = 2 then 0x2020202044414f4c else 0x2020205445534552
    else if row = 2 then
      if chunk = 0 then 0x2020454352554f53 else if chunk = 1 then 0x204e4f4954494445 else
      if chunk = 2 then 0x2020535448474952 else 0x202020454c544954
    else if row = 3 then
      if chunk = 0 then 0x3030304920514552 else if chunk = 1 then 0x3030303030452030 else
      if chunk = 2 then 0x2030304e20303030 else 0x2020202020303052
    else
      if chunk = 0 then 0x3030492044414552 else if chunk = 1 then 0x3030303045203030 else
      if chunk = 2 then 0x2020202030303030 else 0x2020202020202020
  if row = 3 then
    if 5 ≤ column then if column < 9 then packageHex (requested &&& 65535) (8 - column) else
    if 11 ≤ column then if column < 19 then packageHex (requested >>> 16) (18 - column) else
    if column = 21 then (48 : UInt64) + (position &&& 255) / 10 else if column = 22 then (48 : UInt64) + (position &&& 255) % 10 else
    if column = 25 then (48 : UInt64) + (position >>> 8) / 10 else if column = 26 then (48 : UInt64) + (position >>> 8) % 10 else
    (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
  else if row = 4 then
    if 6 ≤ column then if column < 10 then packageHex (shown &&& 65535) (9 - column) else
    if 12 ≤ column then if column < 20 then packageHex (shown >>> 16) (19 - column) else
    (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
    else (packed >>> (column % 8 * 8)) &&& 255
  else (packed >>> (column % 8 * 8)) &&& 255

private def packageControlByte (i _ : UInt32) (acc address value _ _ : UInt64) : Action :=
  .bind (Memory.write8 (address + i.toUInt64) ((value >>> (i.toUInt64 * 8)) &&& 255)) fun s _ => .done s acc

private def packageControlStep (i _ : UInt32) (acc width requested shown position : UInt64) : Action :=
  let x := i.toUInt64 % 24 * 16
  let y := i.toUInt64 / 24
  let column := x / 12
  let first := Lemma.Courses.PackageRender.glyph (packageControlCharacter (y / 20) column requested shown position)
  let second : UInt64 := if column < 31 then
    Lemma.Courses.PackageRender.glyph (packageControlCharacter (y / 20) (column + 1) requested shown position) else 0
  let value := Lemma.Courses.PackageRender.sparsePanelWord x y first second
  let target := Surface.framebuffer + (640 + y) * ((width + 1) / 2) + 12 + x / 2
  if target % 8 = 0 then .bind (Memory.write64 target value) fun s _ => .done s acc else
  .boundedFoldU64 8 packageControlByte 8 acc target value 0 0 fun s value => .done s value

private def packageControlTile (i _ : UInt32) (acc width _ _ _ : UInt64) : Action :=
  .bind (markDirtyTile ((20 + i.toUInt64 / 13) * ((width + 31) / 32) + i.toUInt64 % 13)) fun s _ => .done s acc

/-- Canonical submission identity remains visible while package prose changes.
All values are actual guest Doc8 fields; revision is displayed with all64 bits.
D is the admitted domain, A the assumption set, and B the current budget. -/
private def packageIdentityCharacter (column revision context : UInt64) : UInt64 :=
  let packed : UInt64 := if column / 8 = 0 then 0x3030303020564552 else
    if column / 8 = 1 then 0x3030303030303030 else
    if column / 8 = 2 then 0x2030442030303030 else 0x2020303042203041
  if 4 ≤ column then if column < 20 then packageHex revision (19 - column) else
    if column = 22 then (48 : UInt64) + (context &&& 255) else
    if column = 25 then (48 : UInt64) + ((context >>> 8) &&& 255) else
    if column = 28 then (48 : UInt64) + ((context >>> 16) &&& 255) / 10 else
    if column = 29 then (48 : UInt64) + ((context >>> 16) &&& 255) % 10 else
    (packed >>> (column % 8 * 8)) &&& 255
  else (packed >>> (column % 8 * 8)) &&& 255

private def packageIdentityStep (i _ : UInt32) (acc width revision context _ : UInt64) : Action :=
  let x := i.toUInt64 % 24 * 16
  let y := i.toUInt64 / 24
  let column := x / 12
  let first := Lemma.Courses.PackageRender.glyph (packageIdentityCharacter column revision context)
  let second : UInt64 := if column < 31 then
    Lemma.Courses.PackageRender.glyph (packageIdentityCharacter (column + 1) revision context) else 0
  let word := Lemma.Courses.PackageRender.sparsePanelWord x y first second
  let address := Surface.framebuffer + (740 + y) * ((width + 1) / 2) + 12 + x / 2
  if address % 8 = 0 then .bind (Memory.write64 address word) fun s _ => .done s acc else
  .boundedFoldU64 8 packageControlByte 8 acc address word 0 0 fun s value => .done s value

private def renderPackageIdentity (width : UInt64) : Action :=
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 120) fun s domain => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 128) fun s assumptions => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 136) fun s budget => if statusFailed s = true then .done s 0 else
  Lemma.Courses.ControlRender.renderIdentity width 760 revision
    (domain ||| (assumptions <<< 8) ||| (budget <<< 16))


private def renderPackageControls : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  if width < 416 then .done 240 0 else if height < 760 then .done 240 0 else
  .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (packageGet 48) fun s loadedIdentity => if statusFailed s = true then .done s 0 else
  .bind (packageGet 56) fun s loadedEdition => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s ordinal => if statusFailed s = true then .done s 0 else
  .bind (packageGet 16) fun s role => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.ControlRender.renderControls width height (identity ||| (edition <<< 16))
    (if phase = 2 then loadedIdentity ||| (loadedEdition <<< 16) else 0) ((ordinal + (1 : UInt64)) ||| (role <<< 8)))
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (renderPackageIdentity width) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 52 packageControlTile 52 0 width 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else dirty 0 640 416 760

private def packageView (ordinal role position : UInt64) : Action :=
  .bind (packagePut 8 ordinal) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 16 role) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 24 position) fun s _ => if statusFailed s = true then .done s 0 else
  .bind renderPackageText fun s _ => if statusFailed s = true then courseError s else renderPackageControls

private def packageControlPress (x y : UInt64) : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| checking = 0 then
  let button := (x - 24) / 96
  let row := (y - 640) / 20
  .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s ordinal => if statusFailed s = true then .done s 0 else
  .bind (packageGet 16) fun s role => if statusFailed s = true then .done s 0 else
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if row = 1 then
    if button = 0 then .bind (packagePut 128 (if identity < 65535 then identity + 1 else 1)) fun s _ => if statusFailed s = true then .done s 0 else renderPackageControls
    else if button = 1 then .bind (packagePut 136 (if edition < 0xffffffff then edition + 1 else 1)) fun s _ => if statusFailed s = true then .done s 0 else renderPackageControls
    else if button = 2 then
      .bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 176 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (beginPackageRead identity edition) fun s _ => if statusFailed s = true then courseError s else renderPackageControls
    else if button = 3 then .bind (packagePut 128 1) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 136 1) fun s _ => if statusFailed s = true then .done s 0 else renderPackageControls else .done 0 0
  else if phase = 2 then
    if row = 0 then
      if button = 0 then
        .bind (Memory.read64 (packageBytes + 40)) fun s count => if statusFailed s = true then .done s 0 else
        if count = 0 then .done 240 0 else if 16 < count then .done 242 0 else
        packageView (if ordinal + 1 < count then ordinal + 1 else 0) role 0
      else if button = 1 then packageView ordinal (if role < 11 then role + 1 else 0) 0
      else if button = 2 then
        .bind (packageGet 64) fun s next => if statusFailed s = true then .done s 0 else
        let descriptor := if role < 8 then packageBytes + Lemma.Courses.PackageFormat.headerBytes + ordinal * Lemma.Courses.PackageFormat.entryBytes + 112 + role * 8
          else packageBytes + 96 + (role - 8) * 8
        .bind (Memory.read64 descriptor) fun s span => if statusFailed s = true then .done s 0 else
        packageView ordinal role (if next < Lemma.Courses.PackageFormat.spanLength span then next else 0)
      else if button = 3 then
        .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else
        .bind (stagePackageExercise ordinal) fun s _ => if statusFailed s = true then courseError s else
        .bind publishPackageWorkspace fun s _ => if statusFailed s = true then .done s 0 else renderPackageControls
      else .done 0 0
    else if row = 2 then
      if button = 0 then packageView ordinal 9 0 else if button = 1 then packageView ordinal 10 0 else
      if button = 2 then packageView ordinal 11 0 else if button = 3 then packageView ordinal 8 0 else .done 0 0
    else .done 0 0
  else .done 0 0 else .done 0 0

/-- One owned IPC slot is shared by raw writing, package reads and checking.
A fresh raw contact explicitly cancels/consumes the read or checker before
another operation begins. No canceled reply can publish package evidence. -/
private def packageCancelInput : Action :=
  .bind cancelPackageWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else cancelInput

private def packageCloseState : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (packagePut 96 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 120 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 72 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 0) fun s _ => if statusFailed s = true then .done s 0 else packagePut 152 0
  else .done 0 0

/-- Save owns the ordinary Store status request without leaving the current
course or rebuilding its framebuffer. Only the existing validated response
pump can subsequently publish Saved; admitting this request publishes Pending.
Busy raw/checker work keeps its single IPC slot and is never overwritten. -/
def packageRequestSave : Action :=
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if checking = 0 then
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s pending => if statusFailed s = true then .done s 0 else
  if phase ||| rawCount ||| pending = 0 then
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if 2 ≤ status then .done 0 0 else
  .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (put 496 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 6) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 sequence 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (issue 8 0 0 0) fun s _ => if statusFailed s = true then saveFailure s else publishStatus
  else .done 0 0 else .done 0 0

private def packageToolbar (button : UInt64) : Action :=
  .bind cancelPackageWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending = 0 then
  if button = 7 then packageRequestSave else
  .bind packageCloseState fun s _ => if statusFailed s = true then .done s 0 else toolbar button
  else .done 0 0

private def togglePackageCourse : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending = 0 then
  .bind cancelPackageWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 512) fun s active => if statusFailed s = true then .done s 0 else
  if active = 1 then
    .bind packageCloseState fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 512 0) fun s _ => if statusFailed s = true then .done s 0 else redraw
  else openPackageCourse else .done 0 0

/-- Package UI actions are separate from raw annotation. All original pen
sequence/epoch/time, contact and raw chunk checks precede the new hit tests. -/
private def packageInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      packageCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then appendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    if 2 ≤ status then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind cancelPackageWork fun s _ => if statusFailed s = true then courseError s else
    .bind cancelArithmetic fun s _ => if statusFailed s = true then courseError s else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then packageToolbar (minimum 8 (px / (width / 9))) else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then togglePackageCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then
      if py < 320 then if 24 ≤ px then if px < 408 then packageCoursePress px py else write else write else
      if 640 ≤ py then if py < 700 then if 24 ≤ px then if px < 408 then packageControlPress px py else write else write else write else write
    else write
  write : Action :=
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw

private def drainPackageInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind packageCancelInput fun s _ => if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind packageInputSample fun s _ => if statusFailed s = true then .done s consumed else
    if count = 383 then .done Status.iterationStop (consumed + 1) else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else .done 0 (consumed + 1)

/-- The package context is touched only after all12 pages are actually mapped.
Reader/open/presentation work runs only with the shared syscall slot idle.
A stalled or failed checker, read or Save preserves ordinary raw ink pumps. -/
private def pumpPackageWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking = 0 then
  .bind pumpOpenPackageCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s openedSave => if statusFailed s = true then .done s 0 else
  if openedSave = 0 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
  .bind (if automatic = 1 then
    .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    beginPackageRead identity edition else .done 0 0) fun s _ => if statusFailed s = true then packageCourseError s else
  .bind pumpPackageRead fun result _ =>
  if statusFailed result = true then
    .bind cancelPackageRead fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else courseError result
  else
  .bind (packageGet 72) fun s text => if statusFailed s = true then .done s 0 else
  .bind (if text = 1 then
    .bind renderPackageText fun s _ => if statusFailed s = true then courseError s else packagePut 72 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 144) fun s controls => if statusFailed s = true then .done s 0 else
  if controls = 1 then
    .bind renderPackageControls fun s _ => if statusFailed s = true then courseError s else packagePut 144 0
  else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0

private def packageBusy : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (packageGet 232) fun s selecting => if statusFailed s = true then .done s 0 else
  if school = 1 then if selecting = 1 then .done 0 1 else existing else existing
  else .done 0 0
where
  existing : Action :=
    .bind (packageGet 96) fun s opening => if statusFailed s = true then .done s 0 else
    .bind (packageGet 32) fun s reading => if statusFailed s = true then .done s 0 else
    .bind (packageGet 72) fun s text => if statusFailed s = true then .done s 0 else
    .bind (packageGet 144) fun s controls => if statusFailed s = true then .done s 0 else
    .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
    if opening = 5 then .done 0 1 else
    if 0 < opening then if opening < 4 then .done 0 1 else done reading text controls automatic
    else done reading text controls automatic

  done (reading text controls automatic : UInt64) : Action :=
    if reading = 1 then .done 0 1 else if reading = 3 then .done 0 1 else if reading = 5 then .done 0 1 else
    .done 0 (text ||| controls ||| automatic)

private def packageStep : Action :=
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 384 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind packageBusy fun s work => if statusFailed s = true then .done s 0 else
  if work = 0 then
    if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
      .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
      if s = 175 then packageCancelInput else if s = 174 then Syscall.sleep 10000 else
      if statusFailed s = true then .done s 0 else packageInputSample
    else drain input
  else drain input
where
  drain (input : UInt64) : Action :=
    .bind (drainPackageInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

/-- Explicit four-image package/Closure software. Production mode2 waits for
actual mounted Store publication via operation16. Development formatting mode3
uses the historical mode observer because this Notebook is the guest formatter;
it never waits on its own formatting. Historical boot roots are unchanged. -/
def mainPackageClosureBulk (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 512 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop packageStep

/-! Opt-in package recovery4. The same package parser, compact workspace,
Protocol7 checker, ink constructors and controller rendering remain the
ordinary path. Recovery reuses the Store14/15 remount protocol and compares
every retained encoded byte plus exact EOF before finishing the old record.
No attachment, transport receipt or mounted-mode response implies Saved.
Historical mainPackageClosureBulk and Recovery3 remain unchanged.
-/

/-- Retained encoded bytes stay immutable. Only a separate owned scratch page
is changed by validation; an unrelated namespace, page, decoder length, active
checker or incomplete package allocation rejects before retry/publication. -/
private def packageRecoverableValidateRecord (source bytes object stage : UInt64) : Action :=
  if Lemma.Notebook.RetryWorkspacePolicy.retainedRecordValid source bytes object stage = false then .done 234 0 else
  if stage = 3 then
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  if object = Lemma.Courses.PackageWorkspace.object page then
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if checking = 0 then if allocated = 12 then
  .bind (Memory.read64 source) fun s tag => if statusFailed s = true then .done s 0 else
  if tag = Lemma.Courses.WorkspaceCodec.magic then
    .bind (Lemma.Courses.WorkspaceCodec.decode source bytes packageDocumentStage ns page) fun s decoded =>
    if statusFailed s = true then .done s 0 else
    if decoded = Lemma.Courses.PackageWorkspace.bytes then .done 0 0 else .done 234 0
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done 0 0

def packageRecoverableRetainFailure (knownSequence : UInt64) : Action :=
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  .bind (get 208) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 216) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryWorkspacePolicy.retainableFailure error source bytes object stage = false then .done 0 0 else
  .bind (packageRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then put 640 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 600 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 608 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 616 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 624 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 632 knownSequence) fun s _ => if statusFailed s = true then .done s 0 else
  put 648 1

def packageRecoverableTransactionPump : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 7 then saveFailure 234 else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s known => if statusFailed s = true then .done s 0 else
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if after = 0 then if status = 2 then
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 0 then packageRecoverableRetainFailure known else
    if before = 1 then packageRecoverableRetainFailure known else
    if before = 2 then packageRecoverableRetainFailure known else
    if before = 3 then packageRecoverableRetainFailure known else .done 0 0
  else if before = 3 then if Lemma.Notebook.RetryWorkspacePolicy.publicationEnds stage = true then
    .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else put 640 0
  else .done 0 0 else .done 0 0 else .done 0 0

private def packageRecoverableIssueControl (operation : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.RecoveryClient.beginCall endpoint outgoing operation ns ticket request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else put 232 operation

def packageRecoverableBegin : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 640) fun s attempts => if statusFailed s = true then .done s 0 else
  let allowed := Lemma.Notebook.RetryWorkspacePolicy.retryStatus attempts source bytes object stage
  if statusFailed allowed = true then saveFailure allowed else
  .bind (packageRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  if ticket = 0 then saveFailure 234 else
  .bind (put 640 (attempts+1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 known object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageRecoverableIssueControl 14) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

private def packageRecoverableResubmit : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryWorkspacePolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  .bind (packageRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

/-- The remount receipt follows a real durability barrier. Full exact READ/EOF
of known+1 reconciles the original record once; it never issues another PUT for
that record. Only subsequent page/root stages use new ordinary transactions. -/

private def packageRecoverableFinishRetained : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryWorkspacePolicy.retainedRecordValid source bytes object stage = false then saveFailure 234 else
  .bind (packageRecoverableValidateRecord source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  if known = 0x7fffffffffffffff then saveFailure 234 else
  if observed = known+1 then
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 208 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 216 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 200 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 384 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind finishRecord fun s result => if statusFailed s = true then saveFailure s else
  if Lemma.Notebook.RetryWorkspacePolicy.publicationEnds stage = true then
    .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 640 0) fun s _ => if statusFailed s = true then .done s 0 else put 672 observed
  else .done 0 result
  else saveFailure 234

private def packageRecoverableIssueRead : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 704) fun s offset => if statusFailed s = true then .done s 0 else
  if Lemma.Notebook.RetryWorkspacePolicy.retainedRecordValid source bytes object stage = false then .done 234 0 else
  if offset % 8 = 0 then
  if offset < bytes then
  let count := minimum 128 (bytes-offset)
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 offset count 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 count) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 10
  else .done 234 0 else .done 234 0

private def packageRecoverableIssueEndRead : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 bytes 8 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 11

private def packageRecoverableCompareStep (i _ : UInt32) (acc source offset _ _ : UInt64) : Action :=
  .bind (Memory.read64 (source+offset+i.toUInt64*8)) fun s expected => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (incoming+128+i.toUInt64*8)) fun s observed => if statusFailed s = true then .done s 0 else
  if expected = observed then .done 0 (acc+8) else .done 234 0

def packageRecoverablePollRead : Action :=
  .bind (get 168) fun s token =>
    if s = 0 then
      .bind (get 72) fun s ns =>
        if s = 0 then
          .bind (get 616) fun s object =>
            if s = 0 then
              .bind (get 176) fun s request =>
                if s = 0 then
                  .bind (get 448) fun s expectedCount =>
                    if s = 0 then
                      .bind (Lemma.Services.Store.Client.pollCall token incoming 5 ns object request expectedCount) fun replyStatus sequence =>
                        if replyStatus = IPCABI.wouldBlock then
                          .done 0 0
                        else
                          if replyStatus = 0 then
                            .bind (get 696) fun s mounted =>
                              if s = 0 then
                                if sequence = mounted then
                                  .bind (Lemma.Services.Store.Client.responseField incoming 56) fun s count =>
                                    if s = 0 then
                                      .bind (get 160) fun s phase =>
                                        if s = 0 then
                                          if phase = 11 then
                                            if count = 0 then
                                              packageRecoverableFinishRetained
                                            else
                                              saveFailure 234
                                          else
                                            if count = expectedCount then
                                              if 0 < count then
                                                if count ≤ 128 then
                                                  if count % 8 = 0 then
                                                    .bind (get 600) fun s source =>
                                                      if s = 0 then
                                                        .bind (get 704) fun s offset =>
                                                          if s = 0 then
                                                            .bind (get 608) fun s bytes =>
                                                              if s = 0 then
                                                                if offset ≤ bytes then
                                                                  if count ≤ bytes-offset then
                                                                    .boundedFoldU64 16 packageRecoverableCompareStep (count/8).toUInt32 0 source offset 0 0 fun s compared =>
                                                                      if s = 0 then
                                                                        if compared = count then
                                                                          .bind (put 704 (offset+count)) fun s _ =>
                                                                            if s = 0 then
                                                                              if offset+count = bytes then
                                                                                .bind packageRecoverableIssueEndRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                              else
                                                                                .bind packageRecoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                            else .done s 0
                                                                        else
                                                                          saveFailure 234
                                                                      else
                                                                        saveFailure s
                                                                  else
                                                                    saveFailure 234
                                                                else
                                                                  saveFailure 234
                                                              else .done s 0
                                                          else .done s 0
                                                      else .done s 0
                                                  else
                                                    saveFailure 234
                                                else
                                                  saveFailure 234
                                              else
                                                saveFailure 234
                                            else
                                              saveFailure 234
                                        else .done s 0
                                    else .done s 0
                                else
                                  saveFailure 234
                              else .done s 0
                          else
                            saveFailure replyStatus
                    else .done s 0
                else .done s 0
            else .done s 0
        else .done s 0
    else .done s 0

def packageRecoverablePollControl : Action :=
  .bind (get 168) fun s token =>
    if s = 0 then
      .bind (get 72) fun s ns =>
        if s = 0 then
          .bind (get 176) fun s request =>
            if s = 0 then
              .bind (get 232) fun s operation =>
                if s = 0 then
                  .bind (Lemma.Services.Store.RecoveryClient.pollCall token incoming operation ns request) fun replyStatus sequence =>
                    if replyStatus = IPCABI.wouldBlock then
                      .done 0 0
                    else
                      if replyStatus = 0 then
                        .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s detail =>
                          if s = 0 then
                            if detail = 1 then
                              .bind (put 160 9) fun s _ => if statusFailed s = true then .done s 0 else
                              .bind (packageRecoverableIssueControl 15) fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                            else
                              if detail = 2 then
                                .bind (Memory.read64 (incoming+128)) fun s epoch =>
                                  if s = 0 then
                                    .bind (get 688) fun s priorEpoch =>
                                      if s = 0 then
                                        .bind (get 632) fun s known =>
                                          if s = 0 then
                                            .bind (get 672) fun s saved =>
                                              if s = 0 then
                                                if priorEpoch < epoch then
                                                  if saved ≤ known then
                                                    if saved ≤ sequence then
                                                      if known ≤ sequence then
                                                        .bind (put 688 epoch) fun s _ =>
                                                          if s = 0 then
                                                            .bind (put 696 sequence) fun s _ =>
                                                              if s = 0 then
                                                                if sequence = known then packageRecoverableResubmit else if sequence = known+1 then
                                                                  .bind (put 704 0) fun s _ => if statusFailed s = true then .done s 0 else
                                                                  .bind packageRecoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
                                                                else saveFailure 234
                                                              else .done s 0
                                                          else .done s 0
                                                      else
                                                        saveFailure 234
                                                    else
                                                      saveFailure 234
                                                  else
                                                    saveFailure 234
                                                else
                                                  saveFailure 234
                                              else .done s 0
                                          else .done s 0
                                      else .done s 0
                                  else .done s 0
                              else
                                saveFailure 234
                          else .done s 0
                      else
                        saveFailure replyStatus
                else .done s 0
            else .done s 0
        else .done s 0
    else .done s 0

def packageRecoverablePumpSave : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 8 then packageRecoverablePollControl else if before = 9 then packageRecoverablePollControl else
  if before = 10 then packageRecoverablePollRead else if before = 11 then packageRecoverablePollRead else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s failureTicket => if statusFailed s = true then .done s 0 else
  .bind packageRecoverableTransactionPump fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if after = 0 then
  if (if before = 1 then (1 : UInt64) else if before = 2 then 1 else if before = 3 then 1 else 0) = 1 then
  if status = 2 then if error = 227 then put 680 failureTicket else .done 0 0 else
  if before = 3 then if Lemma.Notebook.RetryWorkspacePolicy.publicationEnds stage = true then
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else put 672 sequence
  else .done 0 0 else .done 0 0
  else .done 0 0 else .done 0 0

def packageRecoverableToolbar (button : UInt64) : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if status < 2 then packageToolbar button else
  if button = 7 then
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if (if error = 227 then (1 : UInt64) else if error = 234 then 1 else 0) = 1 then
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s contact => if statusFailed s = true then .done s 0 else
  if retained = 1 then if phase ||| checking ||| contact = 0 then packageRecoverableBegin else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0

private def packageRetainedInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      retryCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then retryAppendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then packageRecoverableToolbar (minimum 8 (px / (width / 9))) else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 1 then
      if py < 160 then .done 0 0 else
      .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
      .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
      if Lemma.Notebook.RetryPolicy.offlineBufferAvailable buffer pinned 0 = false then .done 0 0 else
      .bind beginStroke fun s _ => if statusFailed s = true then saveFailure s else
      .bind (put 136 status) fun s _ => if statusFailed s = true then .done s 0 else retryAppendRaw
    else .done 0 0

/-- Normal UI uses the existing package hit tests. Retained failures admit
only the existing bounded offline ink path and explicit Save reconciliation. -/
def packageRecoverableInputSample : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  if status < 2 then if retained = 0 then packageInputSample else packageRetainedInputSample
  else packageRetainedInputSample

def drainPackageRecoverableInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s consumed else
    if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind retryCancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind packageRecoverableInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

def packageRecoverableStep : Action :=
  .bind packageRecoverablePumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpPackageArithmetic else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpPackageWork else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpCancelledRedraw else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (get 664) fun s overflow => if statusFailed s = true then .done s 0 else
  .bind (if overflow = 1 then .done 0 0 else if retained = 1 then .done 0 0 else if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then packageBusy else .done 0 0) fun s work => if statusFailed s = true then .done s 0 else
  if (if work = 0 then if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then retryCancelInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else packageRecoverableInputSample
  else .bind (drainPackageRecoverableInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

def mainRecoverablePackageClosureBulk (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 96 clearStep 96 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 592 Lemma.Notebook.RetryWorkspacePolicy.version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 512 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 672 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop packageRecoverableStep



/-! Number-pad deployment1. Historical Notebook roots remain unchanged.
The keypad uses packageState+184 (painted),+192 (limit) and+200 (raw overdraw);
the existing reader uses its separate context0..88, package UI0..176. These
words are not durable document fields and confer no checking authority. -/
private def numericTileStep (i _ : UInt32) (acc width _ _ _ : UInt64) : Action :=
  .bind (markDirtyTile ((5 + i.toUInt64 / 12) * ((width + 31) / 32) + 14 + i.toUInt64 % 12)) fun s _ => .done s acc

private def numericPumpPad : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking = 0 then
  .bind (packageGet 184) fun s painted => if statusFailed s = true then .done s 0 else
  if painted = 0 then
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (packageGet 192) fun s limited => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.NumberPad.render width height limited) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 84 numericTileStep 84 0 width 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (dirty 448 160 832 360) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 200 0) fun s _ => if statusFailed s = true then .done s 0 else packagePut 184 1
  else .done 0 0 else .done 0 0
  else packagePut 184 0 else .done 0 0

private def numericToolbar (button : UInt64) : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  .bind (if allocated = 12 then packagePut 184 0 else .done 0 0) fun s _ =>
  if statusFailed s = true then .done s 0 else packageToolbar button

private def numericToggleCourse : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  .bind (if allocated = 12 then packagePut 184 0 else .done 0 0) fun s _ =>
  if statusFailed s = true then .done s 0 else togglePackageCourse

/-- Number-entry presentation successor: the same staged publication, report,
controls and Store transaction, with aligned stores for the arithmetic pane.
Historical package publishers and their source-bound artifacts stay intact. -/
private def numericPublishAligned : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind adoptPackageWorkspace fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.ArithmeticAligned.render mathematics width) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 65 courseTileStep 65 0 width 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (dirty 0 160 416 320) fun s _ => if statusFailed s = true then .done s 0 else
  .bind reportCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 1) fun s _ => if statusFailed s = true then .done s 0 else savePackageWorkspace
  else .done 231 0

private def numericPadPress (key : UInt64) : Action :=
  if key = 12 then .done 0 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| checking = 0 then
  .bind (Lemma.Documents.Mathematics.copyCurrent mathematics packageDocumentStage) fun s copied => if statusFailed s = true then .done s 0 else
  if copied = Lemma.Documents.Mathematics.currentBytes then
  .bind (Lemma.Documents.MathematicsEntry.press packageDocumentStage key) fun s changed => if statusFailed s = true then courseError s else
  .bind (packageGet 184) fun s painted => if statusFailed s = true then .done s 0 else
  .bind (packageGet 192) fun s prior => if statusFailed s = true then .done s 0 else
  .bind (packageGet 200) fun s damaged => if statusFailed s = true then .done s 0 else
  let limited := if changed = 2 then (1 : UInt64) else 0
  .bind (packagePut 192 limited) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if Lemma.Courses.NumberPad.repaintNeeded painted prior limited damaged = 1 then
    packagePut 184 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  if changed = 1 then
  .bind (Lemma.Courses.PackageWorkspace.stageRefresh packageWorkspace packageDocumentStage mathematicsSave)
    fun s _ => if statusFailed s = true then courseError s else
  .bind recapture fun s _ => if statusFailed s = true then courseError s else numericPublishAligned
  else .done 0 0
  else .done 240 0 else .done 0 0
where
  recapture : Action :=
    .bind (Memory.read64 (mathematicsSave + 48)) fun s mask => if statusFailed s = true then .done s 0 else
    .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
    let recapture := if (mask >>> 8) &&& 1 = 1 then if phase = 2 then (1 : UInt64) else 0 else 0
    if recapture = 1 then
      .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (mathematicsSave + Lemma.Courses.PackageWorkspace.selection + 16)) fun s identity => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (mathematicsSave + Lemma.Courses.PackageWorkspace.selection + 24)) fun s edition => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (mathematicsSave + Lemma.Courses.PackageWorkspace.selection + 40)) fun s node => if statusFailed s = true then .done s 0 else
      .bind (packageGet 48) fun s loadedIdentity => if statusFailed s = true then .done s 0 else
      .bind (packageGet 56) fun s loadedEdition => if statusFailed s = true then .done s 0 else
      if identity = loadedIdentity then if edition = loadedEdition then if 0 < node then
        Lemma.Courses.PackageWorkspace.captureSelection mathematicsSave packageBytes length (node - 1) packageBindingScratch
      else .done 240 0 else .done 0 0 else .done 0 0
    else .done 0 0

/-- A raw stroke can cross the keypad even when both endpoints are outside.
Mark conservatively once at admission. Keep the existing overdraw visible until
the next key; only the completed full pad render clears this transient word. -/
private def numericMarkPadOverdraw : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then packagePut 200 1 else .done 0 0

private def numericInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      packageCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then appendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    if 2 ≤ status then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind cancelPackageWork fun s _ => if statusFailed s = true then courseError s else
    .bind cancelArithmetic fun s _ => if statusFailed s = true then courseError s else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then numericToolbar (minimum 8 (px / (width / 9))) else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then numericToggleCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then
      if 448 ≤ px then if px < 832 then if 160 ≤ py then if py < 360 then
        numericPadPress (Lemma.Courses.NumberPad.key (px - 448) (py - 160)) else write else write else write else
      if py < 320 then if 24 ≤ px then if px < 408 then packageCoursePress px py else write else write else
      if 640 ≤ py then if py < 700 then if 24 ≤ px then if px < 408 then packageControlPress px py else write else write else write else write
    else write
  write : Action :=
    .bind numericMarkPadOverdraw fun s _ => if statusFailed s = true then failWriting s else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw

private def drainNumericInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind packageCancelInput fun s _ => if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind numericInputSample fun s _ => if statusFailed s = true then .done s consumed else
    if count = 383 then .done Status.iterationStop (consumed + 1) else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else .done 0 (consumed + 1)

/-- The generic loss recovery reconstructs the committed ink page. Repaint
its active course overlays afterwards, using only already validated package
bytes. A cancelled partial reader stays cancelled; it cannot publish prose or
mathematical evidence. No Store write or Saved transition occurs here. -/
private def numericPumpCancelledRedraw : Action :=
  .bind (get 432) fun s needed => if statusFailed s = true then .done s 0 else
  if needed = 0 then .done 0 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind pumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind renderPackageCourseScoped fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (packagePut 72 (if phase = 2 then 1 else 0)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 1) fun s _ => if statusFailed s = true then .done s 0 else packagePut 184 0
  else .done 0 0 else .done 0 0

private def numericStep : Action :=
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpPad fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 384 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind packageBusy fun s work => if statusFailed s = true then .done s 0 else
  if work = 0 then
    if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
      .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
      if s = 175 then packageCancelInput else if s = 174 then Syscall.sleep 10000 else
      if statusFailed s = true then .done s 0 else numericInputSample
    else drain input
  else drain input
where
  drain (input : UInt64) : Action :=
    .bind (drainNumericInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

def mainPackageNumberPad (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop numericStep


/-! Number-pad recovery successor. The existing recovery4 publication and
receipt reconciliation remain authoritative; healthy input uses the same15
number pad. Failed/unreconciled saves retain the bounded offline ink policy.
Historical normal and recovery roots retain their bodies. -/
private def numericRecoverableInputSample : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  if status < 2 then if retained = 0 then numericInputSample else retainedInput
  else retainedInput
where
  retainedInput : Action :=
    -- Retained recovery admits offline ink and explicit Save only. Any such
    -- sample conservatively marks the pad before the original guarded path.
    .bind numericMarkPadOverdraw fun s _ => if statusFailed s = true then .done s 0 else
    packageRetainedInputSample

private def drainNumericRecoverableInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s consumed else
    if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind retryCancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind numericRecoverableInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

private def numericRecoverableStep : Action :=
  .bind packageRecoverablePumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpPackageArithmetic else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpPackageWork else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then numericPumpCancelledRedraw else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then numericPumpPad else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (get 664) fun s overflow => if statusFailed s = true then .done s 0 else
  .bind (if overflow = 1 then .done 0 0 else if retained = 1 then .done 0 0 else if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then packageBusy else .done 0 0) fun s work => if statusFailed s = true then .done s 0 else
  if (if work = 0 then if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then retryCancelInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else numericRecoverableInputSample
  else .bind (drainNumericRecoverableInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

def mainRecoverablePackageNumberPad (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 96 clearStep 96 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 592 Lemma.Notebook.RetryWorkspacePolicy.version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 672 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop numericRecoverableStep




/-! Display-location successor. Source history guides the package reader only;
current submission applicability and checker/Save authorities stay separate.
Historical roots retain their bodies and existing open policy. -/
private def restoreBrowseLocation : Action :=
  .bind (Memory.read64 (packageWorkspace + 48)) fun s mask => if statusFailed s = true then .done s 0 else
  if (mask >>> 8) &&& 1 = 1 then .done 0 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.BrowseHistory.location packageWorkspace ns page) fun s location =>
  if statusFailed s = true then .done s 0 else
  if location = 0 then .done 0 0 else
  -- All source fields are read before changing private reader metadata. The
  -- actual installed package still must pass its ordinary edition/CRC checks.
  .bind (Memory.read64 (location + 16)) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (location + 24)) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (location + 32)) fun s crc => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (location + 40)) fun s node => if statusFailed s = true then .done s 0 else
  .bind (packagePut 128 identity) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 136 edition) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 160 crc) fun s _ => if statusFailed s = true then .done s 0 else packagePut 176 (node - 1)

private def pumpBrowseOpenCourse : Action :=
  .bind (packageGet 96) fun s before => if statusFailed s = true then .done s 0 else
  .bind pumpOpenPackageCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 96) fun s after => if statusFailed s = true then .done s 0 else
  if before = 4 then .done 0 0 else if after = 4 then restoreBrowseLocation else .done 0 0

private def pumpPackageBrowseWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking = 0 then
  .bind pumpBrowseOpenCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s openedSave => if statusFailed s = true then .done s 0 else
  if openedSave = 0 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
  .bind (if automatic = 1 then
    .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    beginPackageRead identity edition else .done 0 0) fun s _ => if statusFailed s = true then packageCourseError s else
  .bind pumpPackageRead fun result _ =>
  if statusFailed result = true then
    .bind cancelPackageRead fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else courseError result
  else
  .bind (packageGet 72) fun s text => if statusFailed s = true then .done s 0 else
  .bind (if text = 1 then
    .bind renderPackageText fun s _ => if statusFailed s = true then courseError s else packagePut 72 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 144) fun s controls => if statusFailed s = true then .done s 0 else
  if controls = 1 then
    .bind renderPackageControls fun s _ => if statusFailed s = true then courseError s else packagePut 144 0
  else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0


private def numericBrowseStep : Action :=
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageBrowseWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpPad fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 384 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind packageBusy fun s work => if statusFailed s = true then .done s 0 else
  if work = 0 then
    if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
      .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
      if s = 175 then packageCancelInput else if s = 174 then Syscall.sleep 10000 else
      if statusFailed s = true then .done s 0 else numericInputSample
    else drain input
  else drain input
where
  drain (input : UInt64) : Action :=
    .bind (drainNumericInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

def mainPackageNumberPadBrowse (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop numericBrowseStep


/-! Node-bookmark successor. Explicit Save in an open installed course appends
one separate reader record through the existing Store transaction/barrier.
Workspace, goal/evidence/history and raw ink are untouched. Reopen reads the
record through the existing cooperative exact-length/EOF reader; only a
validated matching immutable package can supply displayed text. Historical
entry roots retain their input, save and open functions.

Private package words208/216/224 are lookup phase/acknowledged reader revision/
pending reader publication. Reader staging uses128 bytes at offset3840 of the
owned mathematicsSave page, beyond the old codec's3808-byte maximum. The live copy
occupies128 bytes after the unchanged3712-byte workspace in its owned page.
This first record preserves a node, not text role or an intra-node offset. -/
private def bookmarkStaging : UInt64 := mathematicsSave + 3840
private def bookmarkLive : UInt64 := packageWorkspace + Lemma.Courses.PackageWorkspace.bytes

private def bookmarkCourseError (status : UInt8) : Action :=
  .bind (packagePut 208 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 72 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else packageCourseError status

private def copyBookmarkStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let offset := 8 + i.toUInt64 * 8
  .bind (Memory.read64 (bookmarkStaging + offset)) fun s value => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (bookmarkLive + offset) value) fun s _ => .done s acc

private def adoptBookmark : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.ReaderLocation.validate bookmarkStaging ns page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 bookmarkLive 0) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 15 copyBookmarkStep 15 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 bookmarkLive Lemma.Courses.ReaderLocation.magic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (bookmarkLive + 72)) fun s revision => if statusFailed s = true then .done s 0 else packagePut 216 revision

private def pumpBookmarkSave : Action :=
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (packageGet 224) fun s readerSave => if statusFailed s = true then .done s 0 else
  if readerSave = 1 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  if pending = 0 then
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (if status < 2 then adoptBookmark else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  packagePut 224 0
  else .done 0 0 else .done 0 0 else .done 0 0

private def bookmarkRequestSave : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| checking = 0 then
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if status < 2 then
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
  if phase = 2 then if 3 ≤ lookup then
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s ordinal => if statusFailed s = true then .done s 0 else
  .bind (packageGet 216) fun s revision => if statusFailed s = true then .done s 0 else
  if Lemma.Courses.ReaderLocation.maximumRevision ≤ revision then .done 242 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.ReaderLocation.capture bookmarkStaging packageBytes length ordinal ns page (revision + 1))
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave bookmarkStaging Lemma.Courses.ReaderLocation.bytes (Lemma.Courses.ReaderLocation.object page) 3)
    fun s _ => if statusFailed s = true then saveFailure s else
  .bind (packagePut 224 1) fun s _ => if statusFailed s = true then .done s 0 else publishStatus
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0

private def bookmarkToolbar (button : UInt64) : Action :=
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if button = 7 then if course = 1 then bookmarkRequestSave else numericToolbar button
  else numericToolbar button

private def cancelBookmarkWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (packageGet 232) fun s selecting => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then if selecting = 1 then
    .bind cancelPackageRecord fun result _ =>
    if result = IPCABI.canceled then packagePut 232 0 else .done result 0
    else .done 0 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 96) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (if phase = 8 then
    .bind cancelPackageRecord fun s _ => if s = IPCABI.canceled then .done 0 0 else .done s 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if phase = 8 then
    .bind (packagePut 208 0) fun s _ => if statusFailed s = true then .done s 0 else packagePut 96 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  cancelPackageWork
  else .done 0 0

private def cancelBookmarkInput : Action :=
  .bind Lemma.Notebook.ControlBacklog.reset fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelBookmarkWork fun s _ => if statusFailed s = true then .done s 0 else packageCancelInput

private def finishBookmarkLookup : Action :=
  .bind adoptBookmark fun s _ => if statusFailed s = true then bookmarkCourseError s else
  .bind (Memory.read64 (bookmarkLive + 32)) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (bookmarkLive + 40)) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (bookmarkLive + 48)) fun s crc => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (bookmarkLive + 56)) fun s node => if statusFailed s = true then .done s 0 else
  .bind (packagePut 128 identity) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 136 edition) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 160 crc) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 176 (node - 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 208 4) fun s _ => if statusFailed s = true then .done s 0 else packagePut 96 4

private def pumpBookmarkOpen : Action :=
  .bind (packageGet 96) fun s before => if statusFailed s = true then .done s 0 else
  if before = 8 then
    .bind pumpPackageRecord fun result _ =>
    if result = 230 then
      .bind (packagePut 208 3) fun s _ => if statusFailed s = true then .done s 0 else packagePut 96 4
    else if statusFailed result = true then bookmarkCourseError result else
    .bind (recordGet 56) fun s phase => if statusFailed s = true then .done s 0 else
    if phase = 4 then finishBookmarkLookup else .done 0 0
  else
  .bind pumpBrowseOpenCourse fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 96) fun s after => if statusFailed s = true then .done s 0 else
  if before = 4 then if after = 4 then
    .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
    if lookup = 1 then
      .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
      .bind (startPackageRecord (Lemma.Courses.ReaderLocation.object page) bookmarkStaging Lemma.Courses.ReaderLocation.bytes 0)
        fun s _ => if statusFailed s = true then bookmarkCourseError s else
      .bind (packagePut 208 2) fun s _ => if statusFailed s = true then .done s 0 else packagePut 96 8
    else .done 0 0
  else .done 0 0 else if after = 4 then
    .bind (packagePut 216 0) fun s _ => if statusFailed s = true then .done s 0 else packagePut 208 1
  else .done 0 0

/-- Ordinary school selection is a guest Store record, admitted only after
an installed package's identity/edition/CRC were checked by the installer.
Read it with bounded IPC and an independent EOF. It chooses displayed source;
it never edits a document, checking selection, or prior attempt. School22
COURSE open follows this selected node, including a new due-review node in the
same edition; mathematical/ink work resumes independently. Legacy reader roots
retain bookmark-location precedence. -/
private def schoolSelectionWork : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s enabled => if statusFailed s = true then .done s 0 else
  if enabled = 1 then
  .bind (packageGet 232) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then .done 0 0 else if phase = 0 then
    .bind (startPackageRecord Lemma.Courses.PackageCommand.selectedObject packageBindingScratch
      Lemma.Courses.PackageCommand.selectedBytes 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (recordPut 80 Lemma.Courses.PackageCommand.selectedNamespace) fun s _ => if statusFailed s = true then .done s 0 else
    packagePut 232 1
  else if phase = 1 then
    .bind pumpPackageRecord fun result _ =>
    if result = 230 then packagePut 232 2 else
    if statusFailed result = true then .done result 0 else
    .bind (recordGet 56) fun s terminal => if statusFailed s = true then .done s 0 else
    if terminal = 4 then
      .bind (Memory.read64 (packageBindingScratch + 0)) fun s tag => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 8)) fun s version => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 16)) fun s ns => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 24)) fun s identity => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 32)) fun s edition => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 40)) fun s crc => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 48)) fun s node => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (packageBindingScratch + 56)) fun s reserved => if statusFailed s = true then .done s 0 else
      if Lemma.Courses.PackageCommand.selectionShape tag version ns identity edition crc node reserved = 1 then
      .bind (packagePut 128 identity) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 136 edition) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 160 crc) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 176 node) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 208 3) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 240 1) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 144 1) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (packagePut 152 1) fun s _ => if statusFailed s = true then .done s 0 else
      packagePut 232 2
      else .done 240 0
    else .done 0 0
  else .done 240 0
  else .done 0 0

private def validateBookmarkPackage : Action :=
  .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
  if lookup = 4 then
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.ReaderLocation.resolve bookmarkLive ns page packageBytes length) fun s _ =>
  if statusFailed s = true then bookmarkCourseError s else packagePut 208 5
  else .done 0 0 else .done 0 0

private def bookmarkBusy : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
  if lookup = 1 then .done 0 1 else if lookup = 2 then .done 0 1 else packageBusy
  else packageBusy else packageBusy



-- Mathematical taps arriving during owned publication are provisional FIFO
-- actions, never host edits or durable events. Bind the immutable displayed
-- package and node; a changed page/edition cancels the backlog before replay.
private def bookMathTap (x y : UInt64) : Bool :=
  if 160 ≤ y then
    if 448 ≤ x then if x < 832 then y < 360 else false
    else if 24 ≤ x then if x < 408 then y < 320 else false else false
  else false

private def bookInkTap (x y : UInt64) : Bool :=
  if y < 160 then false else
  if bookMathTap x y = true then false else
  if 640 ≤ y then if y < 700 then
    if 24 ≤ x then if x < 408 then false else true else true
  else true else true

private def bufferedBookInk : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if status < 2 then
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 0 then
  .bind numericMarkPadOverdraw fun s _ => if statusFailed s = true then failWriting s else
  .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw
  else .done 0 0 else .done 0 0

-- Closing a course (including a controlled queue error) may leave the home
-- controller upload in flight. The free raw buffer is still writable there;
-- otherwise a complete pen stroke can disappear before that upload finishes.
private def bufferHomeInk (x y : UInt64) : Action :=
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
  let py := Geometry.pixel (Geometry.normalized y maxY) height
  if 160 ≤ py then bufferedBookInk else .done 0 x

private def queueBookTap (x y : UInt64) : Action :=
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
  let px := Geometry.pixel (Geometry.normalized x maxX) width
  let py := Geometry.pixel (Geometry.normalized y maxY) height
  if bookMathTap px py = true then
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 24)) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 32)) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (packageGet 160) fun s crc => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s node => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Notebook.ControlBacklog.push px py ns page identity edition crc node) fun status _ =>
    if status = 0 then .done 0 0 else Lemma.Notebook.ControlBacklog.deferFailure status
  else Lemma.Notebook.ControlBacklog.deferFailure 243
  else (if bookInkTap px py = true then bufferedBookInk else .done 0 0) else bufferHomeInk x y

private def applyBookTap (x y : UInt64) : Action :=
  if bookMathTap x y = false then .done 243 0 else
  if 448 ≤ x then numericPadPress (Lemma.Courses.NumberPad.key (x - 448) (y - 160))
  else packageCoursePress x y

private def pumpBookTap : Action :=
  .bind Lemma.Notebook.ControlBacklog.front fun status row =>
  if status = 0 then if row = 0 then .done 0 0 else
  .bind (Memory.read64 row) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 8)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 16)) fun s expectedNS => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 24)) fun s expectedPage => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 32)) fun s expectedIdentity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 40)) fun s expectedEdition => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 48)) fun s expectedCRC => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (row + 56)) fun s expectedNode => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 24)) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 32)) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (packageGet 160) fun s crc => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s node => if statusFailed s = true then .done s 0 else
  if ns = expectedNS then if page = expectedPage then if identity = expectedIdentity then
  if edition = expectedEdition then if crc = expectedCRC then if node = expectedNode then
    .bind Lemma.Notebook.ControlBacklog.pop fun status _ =>
      if status = 0 then applyBookTap x y else Lemma.Notebook.ControlBacklog.deferFailure status
  else changed else changed else changed else changed else changed else changed
  else Lemma.Notebook.ControlBacklog.deferFailure status
where
  changed : Action := Lemma.Notebook.ControlBacklog.deferFailure 243

private def pumpBookControlBacklog : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking ||| recovery = 0 then
  if status < 2 then if dirtyX = 0xffff then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then
  .bind Lemma.Notebook.ControlBacklog.takeFailure fun s failure => if statusFailed s = true then .done s 0 else
  if failure = 0 then pumpBookTap else courseError failure.toUInt8
  else .done 0 0
  else Lemma.Notebook.ControlBacklog.reset
  else .done 0 0 else .done 0 0 else .done 0 0

private def bookmarkInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      cancelBookmarkInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then appendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
    .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
    .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
    .bind Lemma.Notebook.ControlBacklog.count fun queueStatus waiting =>
    if queueStatus = 0 then
    if different (pending ||| checking ||| waiting) 0 = true then queueBookTap x y else
    if 2 ≤ status then queueBookTap x y else
    if different dirtyX 0xffff = true then queueBookTap x y else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then queueBookTap x y else
    .bind cancelBookmarkWork fun s _ => if statusFailed s = true then courseError s else
    .bind cancelArithmetic fun s _ => if statusFailed s = true then courseError s else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then bookmarkToolbar (minimum 8 (px / (width / 9))) else
    if py < 160 then if 132 ≤ py then if 288 ≤ px then if px < 360 then numericToggleCourse else .done 0 0
      else .done 0 0 else .done 0 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if course = 1 then
      if 448 ≤ px then if px < 832 then if 160 ≤ py then if py < 360 then
        numericPadPress (Lemma.Courses.NumberPad.key (px - 448) (py - 160)) else write else write else write else
      if py < 320 then if 24 ≤ px then if px < 408 then packageCoursePress px py else write else write else
      if 640 ≤ py then if py < 700 then if 24 ≤ px then if px < 408 then packageControlPress px py else write else write else write else write
    else write
    else Lemma.Notebook.ControlBacklog.deferFailure queueStatus
  write : Action :=
    .bind numericMarkPadOverdraw fun s _ => if statusFailed s = true then failWriting s else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw


private def drainBookmarkInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind cancelBookmarkInput fun s _ => if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind bookmarkInputSample fun s _ => if statusFailed s = true then .done s consumed else
    if count = 383 then .done Status.iterationStop (consumed + 1) else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else .done 0 (consumed + 1)


private def pumpPackageBookmarkWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking = 0 then
  .bind pumpBookmarkOpen fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
  if lookup = 1 then .done 0 0 else if lookup = 2 then .done 0 0 else
  .bind (get 160) fun s openedSave => if statusFailed s = true then .done s 0 else
  if openedSave = 0 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
  .bind (if automatic = 1 then
    .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    beginPackageRead identity edition else .done 0 0) fun s _ => if statusFailed s = true then bookmarkCourseError s else
  .bind pumpPackageRead fun result _ =>
  if statusFailed result = true then
    .bind cancelPackageRead fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else courseError result
  else
  .bind validateBookmarkPackage fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 72) fun s text => if statusFailed s = true then .done s 0 else
  .bind (if text = 1 then
    .bind renderPackageText fun s _ => if statusFailed s = true then courseError s else packagePut 72 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 144) fun s controls => if statusFailed s = true then .done s 0 else
  if controls = 1 then
    .bind renderPackageControls fun s _ => if statusFailed s = true then courseError s else packagePut 144 0
  else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0



private def bookmarkStep : Action :=
  .bind pumpBookmarkSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageBookmarkWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpPad fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpBookControlBacklog fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 384 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind bookmarkBusy fun s work => if statusFailed s = true then .done s 0 else
  if work = 0 then
    if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
      .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
      if s = 175 then cancelBookmarkInput else if s = 174 then Syscall.sleep 10000 else
      if statusFailed s = true then .done s 0 else bookmarkInputSample
    else drain input
  else drain input
where
  drain (input : UInt64) : Action :=
    .bind (drainBookmarkInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed


def mainPackageNumberPadBookmark (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop bookmarkStep



/-! Recovery5 composes the Reader18 UI with Recovery4. A reader record has its
own exact shape and full package binding. Raw/page/root/workspace transactions
continue through their unchanged Recovery4 Actions. A failed reader publication
keeps both staging and the last acknowledged live record; explicit Save performs
the same remount/barrier/epoch protocol, then exact READ plus EOF or one normal
resubmission. No attachment or receipt is treated as a saved node. -/

private def readerRecoverableValidate (source bytes object stage : UInt64) : Action :=
  if Lemma.Notebook.RetryReaderPolicy.readerRecordValid source bytes object stage = false then .done 234 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  if object = Lemma.Courses.ReaderLocation.object page then
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if checking = 0 then if allocated = 12 then
  .bind (packageGet 224) fun s readerSave => if statusFailed s = true then .done s 0 else
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if readerSave = 1 then if phase = 2 then
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  Lemma.Courses.ReaderLocation.resolve source ns page packageBytes length
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0

private def readerRecoverableRetain (known ticket : UInt64) : Action :=
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  .bind (get 208) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 216) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 200) fun s stage => if statusFailed s = true then .done s 0 else
  if error = 227 then
  .bind (readerRecoverableValidate source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then put 640 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 600 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 608 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 616 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 624 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 632 known) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 680 ticket) fun s _ => if statusFailed s = true then .done s 0 else put 648 1
  else .done 0 0

private def readerRecoverableBegin : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (get 640) fun s attempts => if statusFailed s = true then .done s 0 else
  let allowed := Lemma.Notebook.RetryReaderPolicy.retryStatus attempts source bytes object stage
  if statusFailed allowed = true then saveFailure allowed else
  .bind (readerRecoverableValidate source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 680) fun s ticket => if statusFailed s = true then .done s 0 else
  if ticket = 0 then saveFailure 234 else
  .bind (put 640 (attempts + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 8) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (reportCommitState 0x423 known object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageRecoverableIssueControl 14) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

private def readerRecoverableResubmit : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (readerRecoverableValidate source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (startSave source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else publishStatus

private def readerRecoverableIssueRead : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (readerRecoverableValidate source bytes object stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing 5 ns object 0 0 128 0 request) fun s token =>
  if statusFailed s = true then .done s 0 else
  .bind (put 168 token) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 448 128) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 5) fun s _ => if statusFailed s = true then .done s 0 else put 160 10

private def readerRecoverableFinish : Action :=
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .bind (get 608) fun s bytes => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 624) fun s stage => if statusFailed s = true then .done s 0 else
  .bind (readerRecoverableValidate source bytes object stage) fun s _ => if statusFailed s = true then saveFailure s else
  .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
  .bind (get 696) fun s observed => if statusFailed s = true then .done s 0 else
  if known = 0x7fffffffffffffff then saveFailure 234 else
  if observed = known + 1 then
  .bind (put 128 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 208 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 216 bytes) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 224 object) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 200 stage) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 384 observed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind finishRecord fun s _ => if statusFailed s = true then saveFailure s else
  .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 640 0) fun s _ => if statusFailed s = true then .done s 0 else put 672 observed
  else saveFailure 234

private def readerRecoverablePollControl : Action :=
  .bind (get 168) fun s token => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  .bind (get 232) fun s operation => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.RecoveryClient.pollCall token incoming operation ns request) fun status sequence =>
  if status = IPCABI.wouldBlock then .done 0 0 else if statusFailed status = true then saveFailure status else
  .bind (Lemma.Services.Store.Client.responseField incoming 48) fun s detail => if statusFailed s = true then .done s 0 else
  if detail = 1 then
    .bind (put 160 9) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageRecoverableIssueControl 15) fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
  else if detail = 2 then
    .bind (Memory.read64 (incoming + 128)) fun s epoch => if statusFailed s = true then .done s 0 else
    .bind (get 688) fun s prior => if statusFailed s = true then .done s 0 else
    .bind (get 632) fun s known => if statusFailed s = true then .done s 0 else
    .bind (get 672) fun s saved => if statusFailed s = true then .done s 0 else
    if prior < epoch then if saved ≤ known then if saved ≤ sequence then if known ≤ sequence then
    .bind (put 688 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 696 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    if sequence = known then readerRecoverableResubmit else
    if known = 0x7fffffffffffffff then saveFailure 234 else
    if sequence = known + 1 then
      .bind readerRecoverableIssueRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
    else saveFailure 234
    else saveFailure 234 else saveFailure 234 else saveFailure 234 else saveFailure 234
  else saveFailure 234

private def readerRecoverablePollRead : Action :=
  .bind (get 168) fun s token => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 616) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  .bind (get 448) fun s expectedCount => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.pollCall token incoming 5 ns object request expectedCount) fun status sequence =>
  if status = IPCABI.wouldBlock then .done 0 0 else if statusFailed status = true then saveFailure status else
  .bind (get 696) fun s mounted => if statusFailed s = true then .done s 0 else
  if sequence = mounted then
  .bind (Lemma.Services.Store.Client.responseField incoming 56) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 11 then if count = 0 then readerRecoverableFinish else saveFailure 234 else
  if phase = 10 then if count = 128 then if expectedCount = 128 then
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 16 packageRecoverableCompareStep 16 0 source 0 0 0 fun s compared =>
  if statusFailed s = true then saveFailure s else if compared = 128 then
  .bind packageRecoverableIssueEndRead fun s _ => if statusFailed s = true then saveFailure s else .done 0 0
  else saveFailure 234 else saveFailure 234 else saveFailure 234 else saveFailure 234 else saveFailure 234

private def readerRecoverableTransactionPump : Action :=
  .bind (get 160) fun s before => if statusFailed s = true then .done s 0 else
  if before = 8 then readerRecoverablePollControl else if before = 9 then readerRecoverablePollControl else
  if before = 10 then readerRecoverablePollRead else if before = 11 then readerRecoverablePollRead else
  if before = 0 then .done 0 0 else
  if before = 1 then transaction before else if before = 2 then transaction before else
  if before = 3 then transaction before else saveFailure 234
where
  transaction (before : UInt64) : Action :=
    .bind (get 128) fun s known => if statusFailed s = true then .done s 0 else
    .bind (get 176) fun s ticket => if statusFailed s = true then .done s 0 else
    .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 160) fun s after => if statusFailed s = true then .done s 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    if after = 0 then if status = 2 then readerRecoverableRetain known ticket else
    if before = 3 then
      .bind (put 648 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (put 640 0) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else put 672 sequence
    else .done 0 0 else .done 0 0

private def readerRecoverablePumpSave : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (packageGet 224) fun s readerSave => if statusFailed s = true then .done s 0 else
  if readerSave = 1 then
  .bind readerRecoverableTransactionPump fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if pending ||| retained = 0 then if status < 2 then
    .bind adoptBookmark fun s _ => if statusFailed s = true then .done s 0 else packagePut 224 0
  else .done 0 0 else .done 0 0
  else packageRecoverablePumpSave else packageRecoverablePumpSave

private def readerRecoverableToolbar (button : UInt64) : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s held => if statusFailed s = true then .done s 0 else
  if held = 0 then if status < 2 then bookmarkToolbar button else .done 0 0 else
  if status < 2 then .done 0 0 else
  if button = 7 then
  .bind (get 424) fun s error => if statusFailed s = true then .done s 0 else
  if (if error = 227 then (1 : UInt64) else if error = 234 then 1 else 0) = 1 then
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s contact => if statusFailed s = true then .done s 0 else
  if retained = 1 then if pending ||| checking ||| contact = 0 then
  .bind (get 600) fun s source => if statusFailed s = true then .done s 0 else
  if source = bookmarkStaging then readerRecoverableBegin else packageRecoverableBegin
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0

private def readerRetainedInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw + 64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  if different previousSequence 0 = true then
    if (if different epoch previousEpoch = true then true else if different sequence (previousSequence + 1) = true then true else if time < previousTime then true else false) = true then
      retryCancelInput
    else acceptSample sequence time x y flags epoch
  else acceptSample sequence time x y flags epoch
where
  acceptSample (sequence time x y flags epoch : UInt64) : Action :=
    .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
    .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    if different active 0 = true then retryAppendRaw else
    if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    if py < 128 then readerRecoverableToolbar (minimum 8 (px / (width / 9))) else
    .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
    if cancelled = 1 then .done 0 0 else
    .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
    if different queued 0 = true then .done 0 0 else
    .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
    if retained = 1 then
      if py < 160 then .done 0 0 else
      .bind (get 120) fun s buffer => if statusFailed s = true then .done s 0 else
      .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
      if Lemma.Notebook.RetryPolicy.offlineBufferAvailable buffer pinned 0 = false then .done 0 0 else
      .bind beginStroke fun s _ => if statusFailed s = true then saveFailure s else
      .bind (put 136 status) fun s _ => if statusFailed s = true then .done s 0 else retryAppendRaw
    else .done 0 0

private def readerRecoverableInputSample : Action :=
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  if status < 2 then if retained = 0 then bookmarkInputSample else retainedInput
  else retainedInput
where
  retainedInput : Action :=
    .bind numericMarkPadOverdraw fun s _ => if statusFailed s = true then .done s 0 else
    readerRetainedInputSample

private def drainReaderRecoverableInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    .bind (get 648) fun s retained => if statusFailed s = true then .done s consumed else
    if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then .done Status.iterationStop consumed else
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind retryCancelInput fun s _ =>
      if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind readerRecoverableInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .bind (get 112) fun s count => if statusFailed s = true then .done s consumed else
    if count = 384 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

/-! A fresh workspace has neither a selected source nor reader/history context.
Do not turn the conventional request1/edition1 into an implicit selection: the
installed package may be another edition. Keep the already rendered chooser
available for EDIT+/LOAD. Saved reader/history contexts retain automatic load.
This changes no submission, evidence, journal record or package bytes. -/
private def readerPrepareSelection : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (packageGet 240) fun s selected => if statusFailed s = true then .done s 0 else
  if school = 1 then if selected = 1 then .done 0 0 else prepare else prepare
where
  prepare : Action :=
    .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
    if allocated = 12 then
    .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
    if automatic = 1 then
    .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
    if lookup = 3 then
    .bind (Memory.read64 (packageWorkspace + 48)) fun s mask => if statusFailed s = true then .done s 0 else
    if (mask >>> 8) &&& 1 = 0 then
    .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
    .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Courses.BrowseHistory.location packageWorkspace ns page) fun s prior =>
    if statusFailed s = true then .done s 0 else
    if prior = 0 then packagePut 152 0 else .done 0 0
    else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0
private def readerPackageWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking = 0 then
  .bind pumpBookmarkOpen fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
  if lookup = 1 then .done 0 0 else if lookup = 2 then .done 0 0 else
  .bind (get 160) fun s openedSave => if statusFailed s = true then .done s 0 else
  if openedSave = 0 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind readerPrepareSelection fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
  .bind (if automatic = 1 then
    .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    beginPackageRead identity edition else .done 0 0) fun s _ => if statusFailed s = true then bookmarkCourseError s else
  .bind pumpPackageRead fun result _ =>
  if statusFailed result = true then
    .bind cancelPackageRead fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else courseError result
  else
  .bind validateBookmarkPackage fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 72) fun s text => if statusFailed s = true then .done s 0 else
  .bind (if text = 1 then
    .bind renderPackageText fun s _ => if statusFailed s = true then courseError s else packagePut 72 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 144) fun s controls => if statusFailed s = true then .done s 0 else
  if controls = 1 then
    .bind renderPackageControls fun s _ => if statusFailed s = true then courseError s else packagePut 144 0
  else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0

private def readerRecoverableStep : Action :=
  .bind readerRecoverablePumpSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 648) fun s retained => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then pumpPackageArithmetic else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then readerPackageWork else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then numericPumpCancelledRedraw else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then numericPumpPad else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpBookControlBacklog fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (get 664) fun s overflow => if statusFailed s = true then .done s 0 else
  .bind (if overflow = 1 then .done 0 0 else if retained = 1 then .done 0 0 else if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if (if count = 384 then if retained = 0 then (1 : UInt64) else 0 else 0) = 1 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (if retained = 0 then bookmarkBusy else .done 0 0) fun s work => if statusFailed s = true then .done s 0 else
  if (if work = 0 then if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false else false) = true then
    .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
    if s = 175 then cancelBookmarkInput else if s = 174 then Syscall.sleep 10000 else
    if statusFailed s = true then .done s 0 else readerRecoverableInputSample
  else .bind (drainReaderRecoverableInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else
    if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

def mainRecoverablePackageReader (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 96 clearStep 96 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 592 Lemma.Notebook.RetryReaderPolicy.version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 672 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop readerRecoverableStep




/-! Canonical chooser20 uses the same Reader18 lifecycle and the new explicit
fresh selection rule. Historical Reader18 and its exact artifacts stay intact. -/
private def chooserReaderStep : Action :=
  .bind pumpBookmarkSave fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpPackageArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind readerPackageWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpPad fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpBookControlBacklog fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  if count = 384 then Syscall.sleep 10000 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind bookmarkBusy fun s work => if statusFailed s = true then .done s 0 else
  if work = 0 then
    if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
      .bind (Syscall.call 65 input 2 raw 0 0) fun s _ =>
      if s = 175 then cancelBookmarkInput else if s = 174 then Syscall.sleep 10000 else
      if statusFailed s = true then .done s 0 else bookmarkInputSample
    else drain input
  else drain input
where
  drain (input : UInt64) : Action :=
    .bind (drainBookmarkInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed


def mainPackageReaderChooser (bootArgument : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop chooserReaderStep



private def tutorContext : UInt64 := Lemma.User.Multimodal.records + 1024
private def tutorPacket : UInt64 := Lemma.User.Multimodal.records + 1536
private def tutorState : UInt64 := Lemma.User.Multimodal.state + 144
private def schoolContext : UInt64 := Lemma.User.Multimodal.records + 1152
private def schoolPacket : UInt64 := Lemma.User.Multimodal.records + 1792
private def tutorPut (offset value : UInt64) : Action := Memory.write64 (tutorContext + offset) value
private def tutorGet (offset : UInt64) : Action := Memory.read64 (tutorContext + offset)

/- The local HELP request snapshots current, already validated mathematical
source anchors. A model cannot select these values through its package bytes.
The action/publication sequence exceeds the guest-observed durable frontier,
so cold boot cannot reuse a prior immutable assistance edition. -/
/-- School ASK binds the currently validated rendered node, including ordinary
written reasoning. It does not turn that source selection into a checker goal. -/
private def multimodalAskLocation (ns page : UInt64) : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  if school = 1 then
    .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
    if phase = 2 then
    .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
    .bind (packageGet 8) fun s ordinal => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Courses.PackageTarget.select packageBytes length ordinal) fun s entry => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (packageBytes + 24)) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (packageBytes + 32)) fun s edition => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 entry) fun s node => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (packageBindingScratch + 16) identity) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (packageBindingScratch + 24) edition) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (packageBindingScratch + 40) node) fun s _ => if statusFailed s = true then .done s 0 else
    .done 0 packageBindingScratch
    else .done 244 0
  else Lemma.Courses.BrowseHistory.location packageWorkspace ns page

private def multimodalAsk : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (multimodalAskLocation ns page) fun s binding => if statusFailed s = true then .done s 0 else
  if binding = 0 then .done 244 0 else
  .bind (Memory.read64 (binding + 16)) fun s source => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (binding + 24)) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (binding + 40)) fun s task => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 tutorState) fun s previous => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s durableFrontier => if statusFailed s = true then .done s 0 else
  let sequence := maximum previous durableFrontier
  if 0xffffffff ≤ sequence then .done 235 0 else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe - 3000000000 < now then .done 235 0 else
  .bind (tutorPut 0 (now + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 8 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 16 revision) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 24 (Lemma.Courses.PackageWorkspace.object page)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 32 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 40 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 48 source) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 56 edition) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 64 task) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 72 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 80 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 tutorState (sequence + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x721 (now + 1) revision (Lemma.Courses.PackageWorkspace.object page) (sequence + 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x722 source edition task now) fun s _ => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x723 1 (now + 3000000000) 1 0

/-- Explicit envelope selection leaves the saved source reader's CRC/node
expectation. The new package still passes its own full integrity validation
and the separate current document/school/action admission checks. -/
private def multimodalLoadTutor : Action :=
  .bind (Memory.read64 tutorState) fun s sequence => if statusFailed s = true then .done s 0 else
  if sequence = 0 then .done 244 0 else
  .bind cancelBookmarkWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 512 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 176 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (beginPackageRead 60001 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 128 60001) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (tutorState + 8) 1) fun s _ => if statusFailed s = true then .done s 0 else
  packagePut 136 sequence

private def multimodalJoinSchool : Action :=
  .bind (Memory.read64 tutorState) fun s sequence => if statusFailed s = true then .done s 0 else
  if sequence = 0 then .done 244 0 else
  .bind cancelBookmarkWork fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelArithmetic fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 512 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 176 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (beginPackageRead 60000 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 128 60000) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (tutorState + 24) 1) fun s _ => if statusFailed s = true then .done s 0 else
  packagePut 136 sequence

private def multimodalTutorDecision (reason : UInt64) : Action :=
  .bind (tutorGet 16) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (tutorGet 24) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x724 reason revision object 0) fun s _ => if statusFailed s = true then .done s 0 else
  if reason = 0 then .done 0 1 else .done 244 reason

private def multimodalCurrentTutor : Action :=
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (tutorGet 16) fun s expectedRevision => if statusFailed s = true then .done s 0 else
  .bind (tutorGet 24) fun s object => if statusFailed s = true then .done s 0 else
  if different expectedRevision revision = true then .done 0 3 else
  if different object (Lemma.Courses.PackageWorkspace.object page) = true then .done 0 4 else .done 0 0

private def multimodalAdmitSchool (length requested : UInt64) : Action :=
  .bind (Lemma.Multimodal.SchoolPacket.decode packageBytes length schoolPacket 1) fun s marked => if statusFailed s = true then .done s 0 else
  if marked = 0 then if requested = 1 then multimodalTutorDecision 29 else .done 0 0 else
  if requested = 0 then multimodalTutorDecision 29 else
  .bind multimodalCurrentTutor fun s current => if statusFailed s = true then .done s 0 else
  if different current 0 = true then multimodalTutorDecision current else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Multimodal.SchoolPacket.acceptInvitation packageBytes schoolPacket schoolContext tutorContext now)
    fun s reason => if statusFailed s = true then .done s 0 else
  if different reason 0 = true then multimodalTutorDecision reason else
  .bind (Memory.read64 (schoolContext + 48)) fun s binding => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (schoolContext + 56)) fun s generation => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (schoolContext + 72)) fun s policy => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x727 binding generation policy now) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then
    .bind (tutorGet 48) fun s source => if statusFailed s = true then .done s 0 else
    .bind (tutorGet 56) fun s edition => if statusFailed s = true then .done s 0 else
    .bind (tutorGet 64) fun s node => if statusFailed s = true then .done s 0 else
    .bind (packagePut 128 source) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 136 edition) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 160 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 176 (node - 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 208 3) fun s _ => if statusFailed s = true then .done s 0 else
    -- The invitation view is consumed. Its text/control flags must not publish
    -- against the asynchronously reloading original source. EOF of that source
    -- alone re-enables both flags through packageReadComplete.
    .bind (packagePut 72 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 144 0) fun s _ => if statusFailed s = true then .done s 0 else
    beginPackageRead source edition
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else .done 0 2

private def multimodalAdmitTutor : Action :=
  .bind (packageGet 32) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 2 then
  .bind (Memory.read64 (tutorState + 8)) fun s requested => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 24)) fun s joinRequested => if statusFailed s = true then .done s 0 else
  .bind (packageGet 128) fun s selected => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (tutorState + 8) 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (tutorState + 24) 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (multimodalAdmitSchool length joinRequested) fun s school => if statusFailed s = true then .done s 0 else
  if school = 2 then .done 0 2 else
  .bind (Lemma.Multimodal.SchoolPacket.decode packageBytes length tutorPacket 2) fun s schoolAction => if statusFailed s = true then .done s 0 else
  .bind (if schoolAction = 1 then .done 0 1 else Lemma.Multimodal.TutorPackage.decode packageBytes length tutorPacket) fun s marked => if statusFailed s = true then .done s 0 else
  let markerReason := Lemma.Multimodal.TutorPackage.requiredMarkerReason requested selected marked
  if 0 < markerReason then multimodalTutorDecision markerReason else
  if marked = 0 then .done 0 0 else
  .bind multimodalCurrentTutor fun s current => if statusFailed s = true then .done s 0 else
  if different current 0 = true then multimodalTutorDecision current else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  .bind (if schoolAction = 1 then Lemma.Multimodal.SchoolPacket.actionReason tutorPacket tutorContext schoolContext now else
    .bind (Lemma.Multimodal.SchoolPacket.active schoolContext) fun s joined => if statusFailed s = true then .done s 0 else
    if joined = 1 then .done 0 28 else Lemma.Multimodal.TutorAction.validate tutorPacket tutorContext now)
    fun s reason => if statusFailed s = true then .done s 0 else
  .bind (if reason = 0 then Lemma.Multimodal.TutorPackage.annotationReason packageBytes tutorPacket else .done 0 reason)
    fun s decision => if statusFailed s = true then .done s 0 else multimodalTutorDecision decision
  else .done 0 0

/-- Consume the proposal sequence after guest rasterization succeeds. This is
an acceptance/raster receipt only; panel completion remains separately observed.
The high water prevents LOAD from repeating an accepted live action. -/
private def multimodalTutorAccepted : Action :=
  .bind (Memory.read64 (tutorPacket + 40)) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (tutorPut 32 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x725 sequence 1 0 0

private def schoolQueueFailure (status : UInt8) : Action :=
  .bind (Memory.write64 schoolQueueError status.toUInt64) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x732 status.toUInt64 0 0 0

private def schoolQueueInitialize : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  if school = 1 then
    .bind (Memory.write64 schoolQueueReadyFlag 2) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
    if 0x7ffffffffffffffe - 1000000 < request then schoolQueueFailure 242 else
    .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
    .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
    .bind (put 176 (request + 1000000)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Courses.SchoolSubmission.initializeQueue endpoint console (request + 1)) fun result _ =>
    if statusFailed result = true then schoolQueueFailure result else
    .bind (Memory.write64 schoolQueueReadyFlag 1) fun s _ => if statusFailed s = true then .done s 0 else
    Lemma.Courses.SchoolSubmission.restore 1
  else .done 0 0

/- Queue failures retain ordinary notebook use. A nonzero status is visible
as a separate diagnostic; it can never manufacture Saved, school ACK, or proof. -/
/-- The scalar ABI has one pending call per task, including reader/checker
calls. A pending foreground intent also wins the next idle slot. -/
private def schoolForegroundWork : Action :=
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind bookmarkBusy fun s reader => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 16)) fun s intent => if statusFailed s = true then .done s 0 else
  .bind Lemma.Notebook.ControlBacklog.count fun s waiting => if statusFailed s = true then .done s 0 else
  .done 0 (pending ||| rawCount ||| rawPending ||| stroke ||| checking ||| reader ||| intent ||| waiting)

private def schoolQueueOwnsIPC : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  if school = 1 then
  .bind (Memory.read64 schoolQueueReadyFlag) fun s initialized => if statusFailed s = true then .done s 0 else
  if initialized = 1 then Lemma.Courses.SchoolSubmission.writerActive else .done 0 0 else .done 0 0

private def schoolQueuePump : Action :=
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  if school = 1 then
  .bind (Memory.read64 schoolQueueReadyFlag) fun s initialized => if statusFailed s = true then .done s 0 else
  if initialized = 0 then
    .bind schoolForegroundWork fun s work => if statusFailed s = true then .done s 0 else
    if work = 0 then schoolQueueInitialize else .done 0 0
  else if initialized = 1 then
    .bind schoolForegroundWork fun s work => if statusFailed s = true then .done s 0 else
    .bind (if work = 0 then Lemma.Courses.SchoolSubmission.resume
      else Lemma.Courses.SchoolSubmission.suspend) fun s _ => if statusFailed s = true then .done s 0 else
    .bind Lemma.Courses.SchoolSubmission.pump fun result _ =>
    .bind (if statusFailed result = true then
      .bind (Memory.write64 schoolQueueReadyFlag 2) fun s _ => if statusFailed s = true then .done s 0 else schoolQueueFailure result
      else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind Lemma.Courses.SchoolSubmission.frontier fun s queueFrontier => if statusFailed s = true then .done s 0 else
    .bind (get 128) fun s frontier => if statusFailed s = true then .done s 0 else put 128 (maximum frontier queueFrontier)
  else .done 0 0 else .done 0 0

private def schoolHeaderPut (offset value : UInt64) : Action := Memory.write64 (schoolSubmissionHeader + offset) value
private def schoolHeaderClear (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (schoolHeaderPut (i.toUInt64 * 8) 0) fun s _ => .done s acc

private def schoolWorkKind (revision identity edition node crc : UInt64) : Action :=
  .bind (Lemma.Courses.PackageWorkspace.snapshotSelection packageWorkspace packageBindingScratch) fun result _ =>
  if statusFailed result = true then .done 0 2 else
  .bind (Memory.read64 (packageBindingScratch + 16)) fun s source => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 24)) fun s published => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 32)) fun s checksum => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 40)) fun s task => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBindingScratch + 120)) fun s boundRevision => if statusFailed s = true then .done s 0 else
  .done 0 (if source = identity then if published = edition then if task = node then if checksum = crc then
    if boundRevision = revision then 1 else 2 else 2 else 2 else 2 else 2)

private def schoolContextCopy (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Memory.read64 (schoolContext + i.toUInt64 * 8)) fun s value => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut (128 + i.toUInt64 * 8) value) fun s _ => .done s acc

/-- SEND captures the selected publication, immutable mathematical revision,
full raw page references and already admitted school binding in guest Lean.
An existing pending attempt is retried with its original bytes and identity. -/
private def schoolSend : Action :=
  .bind (Memory.read64 schoolQueueReadyFlag) fun s initialized => if statusFailed s = true then .done s 0 else
  if initialized = 1 then
  .bind (Memory.read64 Lemma.Courses.SchoolSubmission.arena) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 26 then Lemma.Courses.SchoolSubmission.retry else if phase = 45 then Lemma.Courses.SchoolSubmission.retry else
  if (if phase = 0 then (1 : UInt64) else if phase = 29 then 1 else 0) = 1 then
  .bind (get 136) fun s saved => if statusFailed s = true then .done s 0 else
  if saved = 0 then
  .bind (packageGet 32) fun s loaded => if statusFailed s = true then .done s 0 else
  if loaded = 2 then
  .bind (packageGet 0) fun s length => if statusFailed s = true then .done s 0 else
  .bind (packageGet 8) fun s ordinal => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageTarget.select packageBytes length ordinal) fun s entry => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 24)) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 32)) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (packageBytes + 80)) fun s crc => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 entry) fun s node => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (schoolContext + 72)) fun s policy => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 40) fun s revision => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Mathematics.field mathematics 96) fun s checker => if statusFailed s = true then .done s 0 else
  .bind (schoolWorkKind revision identity edition node crc) fun s kind => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 128) fun s frontier => if statusFailed s = true then .done s 0 else
  .bind Syscall.time fun s now => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 32 schoolHeaderClear 32 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 0 Lemma.Courses.SchoolSubmission.magic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 8 Lemma.Courses.SchoolSubmission.version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 32 frontier) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 40 ns) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 48 page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 56 revision) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 64 identity) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 72 edition) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 80 node) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 88 crc) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 96 policy) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 104 kind) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 112 now) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (schoolHeaderPut 120 checker) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 13 schoolContextCopy 13 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  Lemma.Courses.SchoolSubmission.start schoolSubmissionHeader packageWorkspace pageIndex
  else .done 244 0 else .done 232 0 else .done 232 0
  else .done 244 0

private def schoolCancel : Action :=
  .bind (Memory.read64 schoolQueueReadyFlag) fun s initialized => if statusFailed s = true then .done s 0 else
  if initialized = 1 then
  .bind (Memory.read64 (Lemma.Courses.SchoolSubmission.arena + 96)) fun s queue => if statusFailed s = true then .done s 0 else
  Lemma.Courses.SchoolSubmission.cancel queue
  else .done 244 0

/-- Local diagnostic controls, guest-rasterized and submitted through paper.
CAPTURE is synthetic, five seconds, no transmission/retention. MUTE is local. -/
private def multimodalCharacter (index enabled : UInt64) : UInt64 :=
  if index < 12 then
    if enabled &&& 1 = 1 then
      if index < 6 then (0x455649544341 >>> (index * 8)) &&& 255 else 32
    else if index < 8 then (0x45525554504143 >>> (index * 8)) &&& 255 else 32
  else if index < 20 then
    if index < 16 then (0x4554554d >>> ((index - 12) * 8)) &&& 255 else 32
  else if index < 30 then
    if index < 27 then (0x46464f20474545 >>> ((index - 20) * 8)) &&& 255 else 32
  else if index < 36 then
    if (enabled >>> 8) &&& 1 = 1 then
      if index < 34 then (0x444e4553 >>> ((index - 30) * 8)) &&& 255 else if index = 35 then 88 else 32
    else 32
  else if index < 44 then
    if 36 ≤ index then if index < 39 then (0x4b5341 >>> ((index - 36) * 8)) &&& 255 else 32 else 32
  else if index < 48 then (0x44414f4c >>> ((index - 44) * 8)) &&& 255 else
  if 52 ≤ index then if index < 56 then (0x4e494f4a >>> ((index - 52) * 8)) &&& 255 else if enabled >>> 16 = 1 then if index < 60 then (0x53534f4c >>> ((index-56)*8)) &&& 255 else 32 else 32 else 32

private def multimodalBarStep (i _ : UInt32) (acc enabled width _ _ : UInt64) : Action :=
  let x := i.toUInt64 % 360 * 2
  let y := i.toUInt64 / 360
  let a := pixel x y enabled
  let b := pixel (x + 1) y enabled
  .bind (Memory.write8 (Surface.framebuffer + (132 + y) * ((width + 1) / 2) + 200 + x / 2) ((a <<< 4) ||| b)) fun s _ => .done s acc
where
  pixel (x y enabled : UInt64) : UInt64 :=
    if x % 12 < 9 then
      if (Lemma.Courses.PackageRender.glyph (multimodalCharacter (x / 12) enabled) >>> (14 - (y / 3 * 3 + x % 12 / 3))) &&& 1 = 1 then 0 else 15
    else 15

private def multimodalBarTile (i _ : UInt32) (acc width _ _ _ : UInt64) : Action :=
  .bind (markDirtyTile (4 * ((width + 31) / 32) + 12 + i.toUInt64)) fun s _ => .done s acc

private def multimodalBar : Action :=
  .bind Lemma.User.Multimodal.active fun s enabled => if mmFailed s = true then .done s 0 else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if mmFailed s = true then .done s 0 else
  .bind (Memory.read64 (Lemma.User.Multimodal.records+2480)) fun s lost => if mmFailed s = true then .done s 0 else
  let enabled := enabled ||| (school <<< 8) ||| (lost <<< 16)
  .bind (get 32) fun s width => if mmFailed s = true then .done s 0 else
  if width < 1120 then .done 16 0 else
  .boundedFoldU64 5400 multimodalBarStep 5400 0 enabled width 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 23 multimodalBarTile 23 0 width 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  dirty 400 132 1120 147

private def multimodalBookLoad : Action :=
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 32)) fun s expectedPage => if statusFailed s = true then .done s 0 else
  .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
  .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 40)) fun s expectedIdentity => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 48)) fun s expectedEdition => if statusFailed s = true then .done s 0 else
  if course = 1 then if page = expectedPage then if identity = expectedIdentity then if edition = expectedEdition then
    packageControlPress 264 670
  else .done 175 0 else .done 175 0 else .done 175 0 else .done 175 0

private def multimodalControl (operation : UInt64) : Action :=
  .bind (if operation = 3 then multimodalAsk else if operation = 4 then multimodalLoadTutor else if operation = 5 then multimodalJoinSchool else if operation = 6 then multimodalBookLoad else if operation = 7 then schoolSend else if operation = 8 then schoolCancel else Lemma.User.Multimodal.control operation) fun status result =>
  .bind (get 24) fun s console => if mmFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x712 operation status.toUInt64 result 0) fun s _ => if mmFailed s = true then .done s 0 else
  Memory.write64 (Lemma.User.Multimodal.state + 32) 1

/-- ASK/LOAD taps are transient intents, retained before the ordinary busy
math-tap queue. One pending intent is bounded; identical taps coalesce and a
different second intent gets an explicit Busy receipt726/3. No school request,
package read, framebuffer write or receipt712 happens until idle dispatch. -/
private def multimodalQueueTutor (operation : UInt64) : Action :=
  .bind (Memory.read64 (tutorState + 16)) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (if pending = 0 then Memory.write64 (tutorState + 16) operation else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x726 operation (if pending = 0 then 1 else if pending = operation then 2 else 3) 0 0

/-- A chooser LOAD can arrive during the previous EDIT+ controller update.
Retain the exact page/request pair without starting a read or touching pixels.
The dispatcher refuses a different page or selected immutable publication. -/
private def multimodalQueueBookLoad : Action :=
  .bind (Memory.read64 (tutorState + 16)) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (if pending = 0 then
    .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (tutorState + 32) page) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (tutorState + 40) identity) fun s _ => if statusFailed s = true then .done s 0 else
    Memory.write64 (tutorState + 48) edition
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  multimodalQueueTutor 6

/-- Reuse the one bounded transient intent for a control tapped while the
queue holds the task's IPC slot. Ink stays in the raw buffers. Context is
captured before deferral; another tap cannot retarget this intent. -/
private def schoolQueueControl (x y : UInt64) : Action :=
  let operation : UInt64 := (0x100000000 : UInt64) ||| x ||| (y <<< 16)
  .bind (Memory.read64 (tutorState + 16)) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (if pending = 0 then
    .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
    .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (tutorState + 32) page) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (tutorState + 56) ns) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (tutorState + 80) course) fun s _ => if statusFailed s = true then .done s 0 else
    if course = 1 then
      .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
      .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
      .bind (packageGet 160) fun s crc => if statusFailed s = true then .done s 0 else
      .bind (packageGet 8) fun s node => if statusFailed s = true then .done s 0 else
      .bind (Memory.write64 (tutorState + 40) identity) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (Memory.write64 (tutorState + 48) edition) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (Memory.write64 (tutorState + 64) crc) fun s _ => if statusFailed s = true then .done s 0 else
      Memory.write64 (tutorState + 72) node
    else .done 0 0 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  multimodalQueueTutor operation

private def schoolControlContext : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 56)) fun s expectedNS => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 32)) fun s expectedPage => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 80)) fun s expectedCourse => if statusFailed s = true then .done s 0 else
  if (ns ^^^ expectedNS) ||| (page ^^^ expectedPage) ||| (course ^^^ expectedCourse) = 0 then
  if course = 1 then
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    .bind (packageGet 160) fun s crc => if statusFailed s = true then .done s 0 else
    .bind (packageGet 8) fun s node => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (tutorState + 40)) fun s expectedIdentity => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (tutorState + 48)) fun s expectedEdition => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (tutorState + 64)) fun s expectedCRC => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (tutorState + 72)) fun s expectedNode => if statusFailed s = true then .done s 0 else
    if (identity ^^^ expectedIdentity) ||| (edition ^^^ expectedEdition) ||| (crc ^^^ expectedCRC) ||| (node ^^^ expectedNode) = 0 then .done 0 0
    else .done 175 0
  else .done 0 0 else .done 175 0

private def schoolReplayControl (operation : UInt64) : Action :=
  let x := operation &&& 65535
  let y := (operation >>> 16) &&& 65535
  .bind (if operation >>> 32 = 1 then if x < 4096 then if y < 4096 then
    .bind schoolControlContext fun s _ => if statusFailed s = true then .done s 0 else press x y
    else .done 240 0 else .done 240 0 else .done 240 0) fun status result =>
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x712 operation status.toUInt64 result 0
where
  controls (x y : UInt64) : Action :=
    if 24 ≤ x then if x < 408 then
      if y < 320 then packageCoursePress x y else
      if 640 ≤ y then if y < 700 then packageControlPress x y else .done 240 0 else .done 240 0
    else .done 240 0 else .done 240 0
  press (x y : UInt64) : Action :=
    if y < 128 then
      .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
      if width < 832 then .done 240 0 else bookmarkToolbar (minimum 8 (x / (width / 9)))
    else if y < 160 then
      if 132 ≤ y then if 288 ≤ x then if x < 360 then numericToggleCourse
      else .done 240 0 else .done 240 0 else .done 240 0
    else
      .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
      if course = 1 then
        if 448 ≤ x then if x < 832 then if 160 ≤ y then if y < 360 then
          numericPadPress (Lemma.Courses.NumberPad.key (x - 448) (y - 160)) else controls x y
          else controls x y else controls x y else controls x y
      else .done 240 0

/-- The pending intent never borrows a Store/checker/display buffer. Dispatch
waits for the actual guest queues and paper ownership, then consumes it once.
A fresh ASK snapshots the source/revision at dispatch, not at raw admission. -/
private def multimodalPumpTutor : Action :=
  .bind (Memory.read64 (tutorState + 16)) fun s operation => if statusFailed s = true then .done s 0 else
  if operation = 0 then .done 0 0 else
  .bind (Memory.read64 (Lemma.User.Multimodal.records+2448)) fun s captured => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s store => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  if captured ||| stroke ||| rawCount ||| rawPending ||| store ||| checking = 0 then if dirtyX = 0xffff then
  .bind bookmarkBusy fun s work => if statusFailed s = true then .done s 0 else
  .bind Lemma.Notebook.ControlBacklog.count fun s waiting => if statusFailed s = true then .done s 0 else
  if work ||| waiting = 0 then
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.status surface) fun s status => if statusFailed s = true then .done s 0 else
  if status &&& 1 = 0 then
  .bind (Memory.write64 (tutorState + 16) 0) fun s _ => if statusFailed s = true then .done s 0 else
  if 0x100000000 ≤ operation then schoolReplayControl operation else multimodalControl operation
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0

/-- Local inhibition never waits behind mathematical/Store/paper work. Only
the named controller operation and an explicit receipt execute here. Rendering
waits for a free framebuffer and cannot mutate an owned display submission. -/
private def multimodalSafety (operation : UInt64) : Action :=
  .bind (Lemma.User.Multimodal.control operation) fun status result =>
  .bind (get 24) fun s console => if mmFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x712 operation status.toUInt64 result 0) fun s _ => if mmFailed s = true then .done s 0 else
  Memory.write64 (Lemma.User.Multimodal.state + 32) 1

private def multimodalPumpBar : Action :=
  .bind (Memory.read64 (Lemma.User.Multimodal.state + 32)) fun s pending => if mmFailed s = true then .done s 0 else
  if pending = 0 then .done 0 0 else
  .bind (get 104) fun s stroke => if mmFailed s = true then .done s 0 else
  .bind (get 160) fun s store => if mmFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if mmFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if mmFailed s = true then .done s 0 else
  if stroke ||| store ||| checking = 0 then if dirtyX = 0xffff then
  .bind (get 0) fun s surface => if mmFailed s = true then .done s 0 else
  .bind (Surface.status surface) fun s status => if mmFailed s = true then .done s 0 else
  if status &&& 1 = 0 then
    .bind multimodalBar fun s _ => if mmFailed s = true then .done s 0 else
    Memory.write64 (Lemma.User.Multimodal.state + 32) 0
  else .done 0 0 else .done 0 0 else .done 0 0


/-- Bounded transient capture, not durable ink. Four owned pages retain128
complete nine-word controller samples and original notebook/page/view context.
Arrival order/contact and application contact are separate: local inhibition
may bypass this queue without advancing or rewinding retained ink samples. -/
private def multimodalRawState : UInt64 := Lemma.User.Multimodal.records + 2432
private def multimodalRawBase : UInt64 := 0x350000
private def rawGet (offset : UInt64) : Action := Memory.read64 (multimodalRawState + offset)
private def rawPut (offset value : UInt64) : Action := Memory.write64 (multimodalRawState + offset) value
private def rawAllocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := multimodalRawBase+i.toUInt64*4096
  .bind (Syscall.allocatePage address) fun s actual => if statusFailed s = true then .done s 0 else
  if actual = address then .done 0 (acc+1) else .done 95 0
private def rawClearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (rawPut (i.toUInt64*8) 0) fun s _ => .done s acc
private def multimodalRawInitialize : Action :=
  .boundedFoldU64 4 rawAllocateStep 4 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 8 rawClearStep 8 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else rawPut 0 4

/-- reason1 discontinuity,2 capture capacity,3 controller loss,4 changed view.
Discard only uncommitted capture/current raw tail, keep Store ownership and its
pinned input untouched, inhibit held contact until release, and report loss.
735 counts retained representation samples, not inferred missing sensor edges. -/
private def multimodalRawLoss (reason : UInt64) : Action :=
  .bind (rawGet 16) fun s queued => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s tail => if statusFailed s = true then .done s 0 else
  .bind (rawGet 24) fun s contact => if statusFailed s = true then .done s 0 else
  .bind (rawGet 32) fun s previous => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s sequence => if statusFailed s = true then .done s 0 else
  let discarded := queued+tail+(if reason = 1 then 1 else if reason = 2 then 1 else 0)
  let total := if 0xffffffffffffffff-previous < discarded then 0xffffffffffffffff else previous+discarded
  .bind (rawPut 8 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (rawPut 16 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (rawPut 32 total) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (rawPut 40 contact) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (rawPut 48 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (Lemma.User.Multimodal.state+32) 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind cancelInput fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x735 reason discarded total sequence

private def multimodalRawPush : Action :=
  .bind (rawGet 0) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 4 then
  .bind (rawGet 8) fun s head => if statusFailed s = true then .done s 0 else
  .bind (rawGet 16) fun s count => if statusFailed s = true then .done s 0 else
  if head < 128 then if count < 128 then
  let row := multimodalRawBase+((head+count)%128)*128
  .bind (Lemma.Services.Store.Format.copy raw row 72) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (row+72) ns) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (row+80) page) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 (row+88) course) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if course = 1 then
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    .bind (packageGet 160) fun s crc => if statusFailed s = true then .done s 0 else
    .bind (packageGet 8) fun s node => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (row+96) identity) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (row+104) edition) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Memory.write64 (row+112) crc) fun s _ => if statusFailed s = true then .done s 0 else
    Memory.write64 (row+120) node
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else rawPut 16 (count+1)
  else multimodalRawLoss 2 else .done 243 0 else .done 95 0

private def multimodalApplySample (x y flags : UInt64) : Action :=
  .bind (get 408) fun s previousContact => if statusFailed s = true then .done s 0 else
  .bind (put 408 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  if different active 0 = true then appendRaw else
  if flags &&& 1 = 0 then .done 0 0 else if previousContact = 1 then .done 0 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
  let safetyX := Geometry.pixel (Geometry.normalized x maxX) width
  let safetyY := Geometry.pixel (Geometry.normalized y maxY) height
  -- Stopping an already active diagnostic window is local inhibition.
  -- Starting collection still follows the ordinary idle-only control path.
  .bind (if 132 ≤ safetyY then if safetyY < 160 then
    if 400 ≤ safetyX then if safetyX < 544 then Lemma.User.Multimodal.active
    else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0)
    fun s captureActive => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  if different captureActive 0 = true then multimodalSafety 0 else
  if (if school = 1 then if 132 ≤ safetyY then if safetyY < 160 then if 760 ≤ safetyX then if safetyX < 832 then true else false else false else false else false else false) = true then
    if safetyX < 808 then multimodalQueueTutor 7 else multimodalControl 8
  else
  if (if 132 ≤ safetyY then if safetyY < 160 then if 544 ≤ safetyX then if safetyX < 832 then true else false else false else false else false) = true then
    multimodalSafety (if safetyX < 640 then 1 else 2)
  else
  .bind (get 432) fun s cancelled => if statusFailed s = true then .done s 0 else
  if cancelled = 1 then .done 0 0 else
  if (if 132 ≤ safetyY then if safetyY < 160 then if 832 ≤ safetyX then if safetyX < 1120 then true else false else false else false else false) = true then
    multimodalQueueTutor (if safetyX < 928 then 3 else if safetyX < 1024 then 4 else 5)
  else
  .bind (get 512) fun s selectedCourse => if statusFailed s = true then .done s 0 else
  if (if selectedCourse = 1 then if 660 ≤ safetyY then if safetyY < 680 then if 216 ≤ safetyX then if safetyX < 312 then true else false else false else false else false else false) = true then
    multimodalQueueBookLoad
  else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind Lemma.Notebook.ControlBacklog.count fun queueStatus waiting =>
  if queueStatus = 0 then
  .bind schoolQueueOwnsIPC fun s queueOwns => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (tutorState + 16)) fun s intent => if statusFailed s = true then .done s 0 else
  if different (queueOwns ||| intent) 0 = true then
    if safetyY < 160 then schoolQueueControl safetyX safetyY else
    if selectedCourse = 1 then if bookInkTap safetyX safetyY = false then schoolQueueControl safetyX safetyY else queueBookTap x y
    else queueBookTap x y
  else
  if different (pending ||| checking ||| waiting) 0 = true then queueBookTap x y else
  if 2 ≤ status then queueBookTap x y else
  if different dirtyX 0xffff = true then queueBookTap x y else
  .bind (get 112) fun s queued => if statusFailed s = true then .done s 0 else
  if different queued 0 = true then queueBookTap x y else
  .bind cancelBookmarkWork fun s _ => if statusFailed s = true then courseError s else
  .bind cancelArithmetic fun s _ => if statusFailed s = true then courseError s else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
  let px := Geometry.pixel (Geometry.normalized x maxX) width
  let py := Geometry.pixel (Geometry.normalized y maxY) height
  if py < 128 then bookmarkToolbar (minimum 8 (px / (width / 9))) else
  if py < 160 then if 132 ≤ py then
    if 400 ≤ px then if px < 544 then multimodalControl 0 else
      if px < 640 then multimodalControl 1 else if px < 832 then multimodalControl 2 else
      if px < 928 then multimodalControl 3 else if px < 1024 then multimodalControl 4 else .done 0 0
    else if 288 ≤ px then if px < 360 then numericToggleCourse else .done 0 0 else .done 0 0
    else .done 0 0 else
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
    if 448 ≤ px then if px < 832 then if 160 ≤ py then if py < 360 then
      numericPadPress (Lemma.Courses.NumberPad.key (px - 448) (py - 160)) else write else write else write else
    if py < 320 then if 24 ≤ px then if px < 408 then packageCoursePress px py else write else write else
    if 640 ≤ py then if py < 700 then if 24 ≤ px then if px < 408 then packageControlPress px py else write else write else write else write
  else write
  else Lemma.Notebook.ControlBacklog.deferFailure queueStatus
where
  write : Action :=
    .bind numericMarkPadOverdraw fun s _ => if statusFailed s = true then failWriting s else
    .bind beginStroke fun s _ => if statusFailed s = true then failWriting s else appendRaw


private def multimodalRawPump : Action :=
  .bind (rawGet 8) fun s head => if statusFailed s = true then .done s 0 else
  .bind (rawGet 16) fun s count => if statusFailed s = true then .done s 0 else
  if head < 128 then if count = 0 then .done 0 0 else if 128 < count then .done 243 0 else
  .bind (get 112) fun s tail => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  if 384 ≤ tail then .done 0 0 else
  if active = 0 then if 0 < tail then .done 0 0 else eligible head count else eligible head count
  else .done 243 0
where
  eligible (head count : UInt64) : Action :=
    let row := multimodalRawBase+head*128
    .bind (Memory.read64 (row+16)) fun s x => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (row+24)) fun s y => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (row+40)) fun s flags => if statusFailed s = true then .done s 0 else
    .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
    .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
    .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
    .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
    let px := Geometry.pixel (Geometry.normalized x maxX) width
    let py := Geometry.pixel (Geometry.normalized y maxY) height
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    let control := if py < 160 then true else if course = 1 then bookInkTap px py = false else false
    .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
    .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
    .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
    .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
    .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
    if active = 0 then if control = true then
      if pending ||| pinned ||| checking = 0 then if dirtyX = 0xffff then apply row head count x y flags else .done 0 0
      else .done 0 0 else apply row head count x y flags
    else apply row head count x y flags
  apply (row head count x y flags : UInt64) : Action :=
    .bind (Memory.read64 (row+72)) fun s expectedNS => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (row+80)) fun s expectedPage => if statusFailed s = true then .done s 0 else
    .bind (Memory.read64 (row+88)) fun s expectedCourse => if statusFailed s = true then .done s 0 else
    .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
    .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
    .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
    if (ns ^^^ expectedNS) ||| (page ^^^ expectedPage) ||| (course ^^^ expectedCourse) = 0 then
    .bind (if course = 1 then
      .bind (Memory.read64 (row+96)) fun s identity => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (row+104)) fun s edition => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (row+112)) fun s crc => if statusFailed s = true then .done s 0 else
      .bind (Memory.read64 (row+120)) fun s node => if statusFailed s = true then .done s 0 else
      .bind (packageGet 128) fun s currentIdentity => if statusFailed s = true then .done s 0 else
      .bind (packageGet 136) fun s currentEdition => if statusFailed s = true then .done s 0 else
      .bind (packageGet 160) fun s currentCRC => if statusFailed s = true then .done s 0 else
      .bind (packageGet 8) fun s currentNode => if statusFailed s = true then .done s 0 else
      .done 0 (if (identity ^^^ currentIdentity) ||| (edition ^^^ currentEdition) ||| (crc ^^^ currentCRC) ||| (node ^^^ currentNode) = 0 then 1 else 0)
      else .done 0 1) fun s matching => if statusFailed s = true then .done s 0 else
    if matching = 1 then
    .bind (Lemma.Services.Store.Format.copy row raw 72) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (rawPut 8 ((head+1)%128)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (rawPut 16 (count-1)) fun s _ => if statusFailed s = true then .done s 0 else multimodalApplySample x y flags
    else multimodalRawLoss 4 else multimodalRawLoss 4

private def multimodalInputSample : Action :=
  .bind (Memory.read64 raw) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw+8)) fun s time => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw+16)) fun s x => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw+24)) fun s y => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw+40)) fun s flags => if statusFailed s = true then .done s 0 else
  .bind (Memory.read64 (raw+64)) fun s epoch => if statusFailed s = true then .done s 0 else
  .bind (get 288) fun s previousEpoch => if statusFailed s = true then .done s 0 else
  .bind (get 296) fun s previousSequence => if statusFailed s = true then .done s 0 else
  .bind (get 304) fun s previousTime => if statusFailed s = true then .done s 0 else
  .bind (rawGet 24) fun s previousContact => if statusFailed s = true then .done s 0 else
  .bind (rawPut 24 (flags &&& 1)) fun s _ => if statusFailed s = true then .done s 0 else
  if (if previousSequence = 0 then false else if different epoch previousEpoch = true then true else
      if different sequence (previousSequence+1) = true then true else time < previousTime) = true then multimodalRawLoss 1 else
  .bind (put 288 epoch) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 296 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 304 time) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (rawGet 40) fun s resync => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (get 48) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (get 56) fun s maxY => if statusFailed s = true then .done s 0 else
  let px := Geometry.pixel (Geometry.normalized x maxX) width
  let py := Geometry.pixel (Geometry.normalized y maxY) height
  .bind (Memory.read64 schoolActivityFlag) fun s school => if statusFailed s = true then .done s 0 else
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if (if flags &&& 1 = 1 then if previousContact = 0 then true else false else false) = true then
  if (if 132 ≤ py then if py < 160 then if 544 ≤ px then if px < 760 then true else false else false else false else false) = true then
    multimodalSafety (if px < 640 then 1 else 2)
  else if (if 132 ≤ py then if py < 160 then if 760 ≤ px then if px < 832 then true else false else false else false else false) = true then
    if school = 1 then if px < 808 then multimodalQueueTutor 7 else multimodalControl 8 else multimodalSafety 2
  else if (if 132 ≤ py then if py < 160 then if 832 ≤ px then if px < 1120 then true else false else false else false else false) = true then
    multimodalQueueTutor (if px < 928 then 3 else if px < 1024 then 4 else 5)
  else if (if course = 1 then if 660 ≤ py then if py < 680 then if 216 ≤ px then if px < 312 then true else false else false else false else false else false) = true then
    multimodalQueueBookLoad
  else if (if 132 ≤ py then if py < 160 then if 400 ≤ px then if px < 544 then true else false else false else false else false) = true then
    .bind Lemma.User.Multimodal.active fun s capture => if statusFailed s = true then .done s 0 else
    if capture = 1 then multimodalSafety 0 else ordinary resync flags
  else ordinary resync flags
  else ordinary resync flags
where
  ordinary (resync flags : UInt64) : Action :=
    if resync = 0 then multimodalRawPush else if flags &&& 1 = 0 then rawPut 40 0 else .done 0 0

private def drainMultimodalInput (input : UInt64) : Action :=
  .boundedFoldU64 8 drainStep 8 0 input 0 0 0 fun s consumed =>
    if s = Status.iterationStop then .done 0 consumed else .done s consumed
where
  drainStep (_ _ : UInt32) (consumed input _ _ _ : UInt64) : Action :=
    .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
    if s = 174 then .done Status.iterationStop consumed else
    if s = 175 then
      .bind (multimodalRawLoss 3) fun s _ => if statusFailed s = true then .done s consumed else .done Status.iterationStop consumed
    else if statusFailed s = true then .done s consumed else
    .bind multimodalInputSample fun s _ => if statusFailed s = true then .done s consumed else
    .bind (get 104) fun s active => if statusFailed s = true then .done s consumed else
    if active = 0 then .done Status.iterationStop (consumed + 1) else
    .done 0 (consumed + 1)

/-- Rejected text is terminal presentation work. The ordinary error path
leaves course mode, so it cannot later drain these flags. Retain the action
rejection/high water and every document/Store byte while releasing only this
unpublished view; otherwise packageBusy indefinitely blocks a fresh ASK. -/
private def multimodalAbandonPresentation : Action :=
  .bind (packagePut 72 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 144 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
  packagePut 32 4

private def multimodalPackageWork : Action :=
  .bind (Memory.read64 packageAllocationAddress) fun s allocated => if statusFailed s = true then .done s 0 else
  if allocated = 12 then
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s rawPending => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s stroke => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  if pending ||| rawCount ||| rawPending ||| stroke ||| checking = 0 then
  .bind pumpBookmarkOpen fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 208) fun s lookup => if statusFailed s = true then .done s 0 else
  if lookup = 1 then .done 0 0 else if lookup = 2 then .done 0 0 else
  .bind (get 160) fun s openedSave => if statusFailed s = true then .done s 0 else
  if openedSave = 0 then
  .bind (get 512) fun s course => if statusFailed s = true then .done s 0 else
  if course = 1 then
  .bind schoolSelectionWork fun s _ => if statusFailed s = true then bookmarkCourseError s else
  .bind (packageGet 232) fun s selecting => if statusFailed s = true then .done s 0 else
  if selecting = 1 then .done 0 0 else
  .bind readerPrepareSelection fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 152) fun s automatic => if statusFailed s = true then .done s 0 else
  .bind (if automatic = 1 then
    .bind (packagePut 152 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packageGet 128) fun s identity => if statusFailed s = true then .done s 0 else
    .bind (packageGet 136) fun s edition => if statusFailed s = true then .done s 0 else
    beginPackageRead identity edition else .done 0 0) fun s _ => if statusFailed s = true then bookmarkCourseError s else
  .bind pumpPackageRead fun result _ =>
  if statusFailed result = true then
    .bind cancelPackageRead fun s _ => if statusFailed s = true then .done s 0 else
    .bind (packagePut 32 4) fun s _ => if statusFailed s = true then .done s 0 else courseError result
  else
  .bind validateBookmarkPackage fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 72) fun s text => if statusFailed s = true then .done s 0 else
  .bind (if text = 1 then
    .bind multimodalAdmitTutor fun s marked => if statusFailed s = true then
      .bind multimodalAbandonPresentation fun cleanup _ => if statusFailed cleanup = true then .done cleanup 0 else courseError s
    else
    -- JOIN starts a new bounded original-publication read. It is not a text
    -- annotation and cannot rasterize until that read's validated EOF.
    if marked = 2 then .done 0 0 else
    .bind renderPackageText fun s _ => if statusFailed s = true then courseError s else
    .bind (if marked = 1 then multimodalTutorAccepted else .done 0 0) fun s _ => if statusFailed s = true then courseError s else packagePut 72 0
    else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (packageGet 144) fun s controls => if statusFailed s = true then .done s 0 else
  if controls = 1 then
    .bind renderPackageControls fun s _ => if statusFailed s = true then courseError s else packagePut 144 0
  else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0

/-- Capture work is not yet durable work. Keep Pending visible after a Store
completion while captured input remains. The private marker records only our
own status override, so an unrelated Pending/Failed state is never promoted.
Reconcile before controller upload, never from the preallocation Save path. -/
private def multimodalRawStatus : Action :=
  .bind (rawGet 16) fun s captured => if statusFailed s = true then .done s 0 else
  .bind (rawGet 56) fun s overridden => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if 0 < captured then
    if status = 0 then
      .bind (rawPut 56 1) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else publishStatus
    else .done 0 0
  else if overridden = 1 then
    if status = 1 then
      .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
      .bind (get 112) fun s tail => if statusFailed s = true then .done s 0 else
      .bind (get 144) fun s pinned => if statusFailed s = true then .done s 0 else
      .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
      .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
      if active ||| tail ||| pinned ||| pending ||| checking = 0 then
        .bind (rawPut 56 0) fun s _ => if statusFailed s = true then .done s 0 else
        .bind (put 136 0) fun s _ => if statusFailed s = true then .done s 0 else publishStatus
      else .done 0 0
    else rawPut 56 0
  else .done 0 0

private def multimodalStep : Action :=
  .bind multimodalRawPump fun s _ => if statusFailed s = true then .done s 0 else
  .bind Lemma.User.Multimodal.pump fun _ _ =>
  .bind schoolQueuePump fun _ _ =>
  .bind schoolQueueOwnsIPC fun s queueOwns => if statusFailed s = true then .done s 0 else
  .bind (if queueOwns = 0 then pumpBookmarkSave else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if queueOwns = 0 then pumpPackageArithmetic else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpCancelledRedraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if queueOwns = 0 then multimodalPackageWork else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind numericPumpPad fun s _ => if statusFailed s = true then .done s 0 else
  .bind multimodalRawStatus fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefreshRestoredBatched fun s _ => if statusFailed s = true then .done s 0 else
  .bind multimodalPumpBar fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if queueOwns = 0 then multimodalPumpTutor else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if queueOwns = 0 then pumpBookControlBacklog else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
  .bind (get 104) fun s active => if statusFailed s = true then .done s 0 else
  .bind (if count = 384 then enqueue else if active = 0 then enqueue else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 8) fun s input => if statusFailed s = true then .done s 0 else
  .bind (get 160) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 336) fun s dirtyX => if statusFailed s = true then .done s 0 else
  .bind (get 480) fun s recovery => if statusFailed s = true then .done s 0 else
  .bind (get 536) fun s checking => if statusFailed s = true then .done s 0 else
  .bind bookmarkBusy fun s work => if statusFailed s = true then .done s 0 else
  if work = 0 then
    if (if checking = 0 then if pending = 0 then if recovery = 0 then if dirtyX = 0xffff then true else false else false else false else false) = true then
      .bind (Syscall.call 65 input 1 raw 0 0) fun s _ =>
      if s = 175 then multimodalRawLoss 3 else if s = 174 then Syscall.sleep 10000 else
      if statusFailed s = true then .done s 0 else multimodalInputSample
    else drain input
  else drain input
where
  drain (input : UInt64) : Action :=
    .bind (drainMultimodalInput input) fun s consumed =>
    if statusFailed s = true then .done s 0 else if consumed = 0 then Syscall.sleep 10000 else .done 0 consumed

private def mainMultimodalConfigured (bootArgument school : UInt64) : Action :=
  if (if bootArgument = 2 then (1 : UInt64) else if bootArgument = 3 then 1 else 0) = 0 then failed else
  .boundedFoldU64 80 clearStep 80 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 schoolActivityFlag school) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 packageAllocationAddress 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 576 7) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 584 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (if 2 ≤ bootArgument then Capability.bootGrant 5 else .done 0 0) fun s arithmetic => if statusFailed s = true then .done s 0 else
  .bind (put 528 arithmetic) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 3 then
    .bind waitForMount fun s _ => if statusFailed s = true then .done s 0 else initializeMedium
  else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Courses.PackageAwaitClient.call documents outgoing incoming 1 0 request) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.responseField incoming 40) fun s floor => if statusFailed s = true then .done s 0 else
  .bind (put 128 floor) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.geometry surface) fun s geometry => if statusFailed s = true then .done s 0 else
  let width := geometry &&& 0xffffffff
  let height := geometry >>> 32
  if width < 832 then failed else if 4096 < width then failed else
  if height < 760 then failed else if 4096 < height then failed else
  .bind (put 32 width) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 40 height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 3 0 0 0) fun s maxX => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 4 0 0 0) fun s maxY => if statusFailed s = true then .done s 0 else
  .bind (Syscall.call 65 input 0 0 0 0) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (put 48 maxX) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 56 maxY) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 64 pressure) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 120 ink0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 272 512) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 41 allocateStep 41 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind Surface.allocateBulk fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then savePage 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.User.Multimodal.initialize console) fun s _ => if statusFailed s = true then .done s 0 else
  .bind multimodalRawInitialize fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 rawCaptureReadyFlag 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Memory.write64 schoolQueueReadyFlag 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind multimodalBar fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (if school = 1 then CapabilityConsole.record console 0x731 Lemma.Courses.SchoolSubmission.version
    Lemma.Courses.SchoolSubmission.maximumChunks Lemma.Courses.SchoolSubmission.maximumBytes 2 else .done 0 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop multimodalStep



/-- Legacy0.14 software keeps its existing chooser semantics. -/
def mainMultimodal (bootArgument : UInt64) : Action := mainMultimodalConfigured bootArgument 0

/-- Versioned ordinary school client: shared notebook plus durable selected
publication admission. The flag is initialized before any package access. -/
def mainMultimodalSchool (bootArgument : UInt64) : Action := mainMultimodalConfigured bootArgument 1

end Lemma.Applications.Notebook
