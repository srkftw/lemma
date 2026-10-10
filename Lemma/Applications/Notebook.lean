import Lemma.Ink.Surface
import Lemma.Ink.Rasterizer
import Lemma.Documents.Ink
import Lemma.Services.Store.Client
import Lemma.User.CapabilityConsole

/-! Capability-isolated pen notebook. Pixels, input interpretation, raw ink,
page/edit records and save publication execute in compiled User Lean. Two
bounded ink buffers let input continue while the store flushes another chunk.
The framebuffer and current page index are owned virtual memory; previous page
history is streamed from the document service when that page is reopened. -/
namespace Lemma.Applications.Notebook
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Ink

private def statusFailed (s : UInt8) : Bool := if s = 0 then false else true
private def different (a b : UInt64) : Bool := if a = b then false else true

def state : UInt64 := 0x20800
def raw : UInt64 := 0x20300
def context : UInt64 := 0x20400
def outgoing : UInt64 := 0x20b00
def incoming : UInt64 := 0x20c00
def ink0 : UInt64 := 0x300000
def ink1 : UInt64 := 0x308000
def pageIndex : UInt64 := 0x310000
def loadedInk : UInt64 := 0x318000
def rootBuffer : UInt64 := 0x320000
private def get (slot : UInt64) : Action := Memory.read64 (state + slot)
private def put (slot value : UInt64) : Action := Memory.write64 (state + slot) value
private def failed : Action := .done 95 0
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def maximum (a b : UInt64) : UInt64 := if a < b then b else a

private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := ink0 + i.toUInt64 * 4096
  .bind (Syscall.allocatePage address) fun s actual => if statusFailed s = true then .done s 0 else
  if actual = address then .done 0 (acc + 1) else failed

private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

private def nextRequest : Action :=
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  if request < 0x7ffffffffffffffe then
  .bind (put 176 (request + 1)) fun s _ => .done s (request + 1) else .done 235 0

private def blocking (operation object transaction offset count source : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.call endpoint outgoing incoming operation ns object transaction offset count source request)
    fun s sequence =>
  .bind (put 128 sequence) fun stored _ => if statusFailed stored = true then .done stored 0 else .done s sequence

private def readPartStep (i _ : UInt32) (acc object target length _ : UInt64) : Action :=
  let offset := i.toUInt64 * 128
  let count := minimum 128 (length - offset)
  .bind (blocking 5 object 0 offset count 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Format.copy (Lemma.Services.Store.Client.responseData incoming) (target + offset) count) fun s _ =>
  .done s (acc + count)

private def readObject (object target length : UInt64) : Action :=
  if length ≤ 32768 then
  .boundedFoldU64 256 readPartStep ((length + 127) / 128).toUInt32 0 object target length 0 fun s n => .done s n
  else .done 234 0

private def setPixel (x y color : UInt64) : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  if width ≤ x then .done 234 0 else if height ≤ y then .done 234 0 else
  let address := Surface.framebuffer + y * ((width + 1) / 2) + x / 2
  .bind (Memory.read8 address) fun s byte => if statusFailed s = true then .done s 0 else
  Memory.write8 address (if x % 2 = 0 then (byte &&& (15 : UInt64)) ||| (color <<< 4) else (byte &&& (240 : UInt64)) ||| color)

/-- Authored3x5 bits. S/P/F/R mark Saved/Pending/Failed/Read-only; page and
namespace digits and brush width remain visible beside the tool strip. -/
private def letter (code : UInt64) : UInt64 :=
  if code = 83 then 0x73e7 else if code = 80 then 0x7bea else if code = 70 then 0x7be4 else
  if code = 82 then 0x7beb else if code = 72 then 0x5bed else
  if code = 48 then 0x7b6f else if code = 49 then 0x2c97 else if code = 50 then 0x73e7 else
  if code = 51 then 0x73cf else if code = 52 then 0x5bc9 else if code = 53 then 0x79cf else
  if code = 54 then 0x79ef else if code = 55 then 0x7249 else if code = 56 then 0x7bef else
  if code = 57 then 0x7bcf else 0

private def statusStep (i _ : UInt32) (acc ns page save brush : UInt64) : Action :=
  let x := i.toUInt64 % 160
  let y := i.toUInt64 / 160
  let index := x / 24
  let code := if index = 0 then (if save = 0 then 83 else if save = 1 then 80 else if save = 2 then 70 else 82)
    else if index = 1 then 48 + ns else if index = 2 then 48 + page / 10 else
    if index = 3 then 48 + page % 10 else if index = 5 then 48 + brush / 256 else 32
  let withinCell := x % 24
  let black := if withinCell < 18 then if y < 15 then
    if (letter code >>> (14 - (y / 3 * 3 + withinCell / 6))) &&& 1 = 1 then true else false
    else false else false
  .bind (setPixel (24 + x) (132 + y) (if black = true then 0 else 15)) fun s _ => .done s acc

private def statusBar : Action :=
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 136) fun s save => if statusFailed s = true then .done s 0 else
  .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 2560 statusStep 2560 0 ns page save brush fun s _ => .done s 0

private def dirty (x0 y0 x1 y1 : UInt64) : Action :=
  .bind (get 336) fun s oldX => if statusFailed s = true then .done s 0 else
  .bind (get 344) fun s oldY => if statusFailed s = true then .done s 0 else
  .bind (get 352) fun s endX => if statusFailed s = true then .done s 0 else
  .bind (get 360) fun s endY => if statusFailed s = true then .done s 0 else
  .bind (put 336 (minimum x0 oldX)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 (minimum y0 oldY)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 352 (maximum x1 endX)) fun s _ => if statusFailed s = true then .done s 0 else
  put 360 (maximum y1 endY)

private def pumpRefresh : Action :=
  .bind (get 336) fun s x0 => if statusFailed s = true then .done s 0 else
  if x0 = 0xffff then .done 0 0 else
  .bind (get 344) fun s y0 => if statusFailed s = true then .done s 0 else
  .bind (get 352) fun s x1 => if statusFailed s = true then .done s 0 else
  .bind (get 360) fun s y1 => if statusFailed s = true then .done s 0 else
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s previous => if statusFailed s = true then .done s 0 else
  if previous = 0xffffffffffffffff then .done 170 0 else
  .bind (Surface.refresh surface (previous + 1) x0 y0 (x1 - x0) (y1 - y0) 2) fun s sequence =>
  if s = 171 then .done 0 0 else if statusFailed s = true then .done s 0 else
  .bind (put 336 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 344 0xffff) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 352 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 360 0) fun s _ => .done s sequence

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
  .bind (Surface.loadTile x y width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Rasterizer.segment context Surface.tile x y width height) fun s changed => if statusFailed s = true then .done s 0 else
  if changed = 0 then .done 0 acc else
  .bind (Surface.storeTile x y width height) fun s _ => if statusFailed s = true then .done s 0 else
  if upload = 0 then .done 0 (acc + changed) else
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.uploadTile surface x y width height) fun s _ => .done s (acc + changed)

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
  if upload = 0 then .done 0 changed else dirty x0 y0 x1 y1

private def renderChunkStep (i _ : UInt32) (acc record _ _ _ : UInt64) : Action :=
  let sample := record + 128 + i.toUInt64 * 72
  .bind (Lemma.Documents.Ink.field sample 40) fun s flags => if statusFailed s = true then .done s 0 else
  if flags &&& 1 = 0 then .done 0 acc else
  let previous := if i = 0 then sample else sample - 72
  .bind (renderPair record previous sample 0) fun s _ => .done s (acc + 1)

private def renderLoadedChunk : Action :=
  .bind (Lemma.Documents.Ink.field loadedInk 0) fun s magic => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 8) fun s version => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 16) fun s kind => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 48) fun s count => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 56) fun s brush => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 88) fun s pressure => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 96) fun s sourceWidth => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 104) fun s sourceHeight => if statusFailed s = true then .done s 0 else
  if different magic Lemma.Documents.Ink.magic = true then .done 234 0 else if different version 1 = true then .done 234 0 else
  if different kind 3 = true then .done 234 0 else if count = 0 then .done 234 0 else if 384 < count then .done 234 0 else
  if brush < 256 then .done 234 0 else if 8192 < brush then .done 234 0 else if 65535 < pressure then .done 234 0 else
  if Geometry.validDimension sourceWidth = false then .done 234 0 else
  if Geometry.validDimension sourceHeight = false then .done 234 0 else if sourceHeight ≤ 161 then .done 234 0 else
  .boundedFoldU64 384 renderChunkStep count.toUInt32 0 loadedInk 0 0 0 fun s n => .done s n

private def redrawEntryStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex i.toUInt64) 16) fun s visible => if statusFailed s = true then .done s 0 else
  if visible = 0 then .done 0 acc else
  .bind (Lemma.Documents.Ink.field (Lemma.Documents.Ink.entry pageIndex i.toUInt64) 0) fun s object => if statusFailed s = true then .done s 0 else
  .bind (readObject object loadedInk 128) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field loadedInk 48) fun s count => if statusFailed s = true then .done s 0 else
  if count = 0 then .done 234 0 else if 384 < count then .done 234 0 else
  .bind (readObject object loadedInk (128 + count * 72)) fun s _ => if statusFailed s = true then .done s 0 else
  .bind renderLoadedChunk fun s _ => .done s (acc + 1)

private def redraw : Action :=
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .bind (Surface.background width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Documents.Ink.field pageIndex 32) fun s count => if statusFailed s = true then .done s 0 else
  if 512 < count then .done 234 0 else
  .boundedFoldU64 512 redrawEntryStep count.toUInt32 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind statusBar fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Surface.uploadAll surface width height) fun s _ => if statusFailed s = true then .done s 0 else
  dirty 0 0 width height

private def loadPage (page : UInt64) : Action :=
  .bind (readObject (0x100 + page) pageIndex Lemma.Documents.Ink.pageBytes) fun s _ =>
  .bind (if s = 230 then Lemma.Documents.Ink.emptyPage pageIndex page else if s = 0 then Lemma.Documents.Ink.validatePage pageIndex page else .done s 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 80 page) fun s _ => if statusFailed s = true then .done s 0 else redraw

private def loadNotebook (ns : UInt64) : Action :=
  .bind (put 72 ns) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (readObject 1 rootBuffer 64) fun s _ =>
  if s = 230 then
    .bind (put 88 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 416 1) fun s _ => if statusFailed s = true then .done s 0 else loadPage 1
  else if statusFailed s = true then
    .bind (put 136 3) fun stored _ => if statusFailed stored = true then .done stored 0 else
    .bind (put 424 s.toUInt64) fun stored _ => if statusFailed stored = true then .done stored 0 else
    .bind (Lemma.Documents.Ink.emptyPage pageIndex 1) fun stored _ => if statusFailed stored = true then .done stored 0 else redraw
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

private def statusTileStep (i _ : UInt32) (acc surface dimensions _ _ : UInt64) : Action :=
  let x := i.toUInt64 * 32
  let width := dimensions &&& 0xffff
  let height := dimensions >>> 16
  .bind (Surface.loadTile x 128 width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.uploadTile surface x 128 width height) fun s _ => .done s acc

private def publishStatus : Action :=
  .bind statusBar fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (get 32) fun s width => if statusFailed s = true then .done s 0 else
  .bind (get 40) fun s height => if statusFailed s = true then .done s 0 else
  .boundedFoldU64 6 statusTileStep 6 0 surface (width ||| (height <<< 16)) 0 0 fun s _ =>
  if statusFailed s = true then .done s 0 else dirty 0 128 192 160

private def issue (operation offset count source : UInt64) : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 384) fun s transaction => if statusFailed s = true then .done s 0 else
  .bind nextRequest fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.beginCall endpoint outgoing operation ns object (if operation = 7 then 0 else transaction) offset count source request)
    fun s pending => if statusFailed s = true then .done s 0 else
  .bind (put 168 pending) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 232 operation) fun s _ => if statusFailed s = true then .done s 0 else put 448 count

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
  .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else issue 2 0 bytes 0

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
    .bind (Lemma.Documents.Ink.addEntry pageIndex object stroke) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (if lifecycle &&& 1 = 1 then Lemma.Documents.Ink.addEdit pageIndex 1 stroke else .done 0 0)
      fun s _ => if statusFailed s = true then .done s 0 else
    startSave pageIndex Lemma.Documents.Ink.pageBytes (0x100 + page) 1
  else if stage = 1 then
    .bind (get 88) fun s pages => if statusFailed s = true then .done s 0 else
    .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.root rootBuffer pages brush) fun s _ => if statusFailed s = true then .done s 0 else
    startSave rootBuffer 64 1 2
  else if stage = 2 then
    .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
    .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 144 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 416 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 (if rawCount = 0 then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
    .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
    .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
    .bind (get 240) fun s stroke => if statusFailed s = true then .done s 0 else
    .bind (CapabilityConsole.record console 0x421 sequence page ns stroke) fun s _ =>
    if statusFailed s = true then .done s 0 else publishStatus
  else .done 234 0

private def saveFailure (status : UInt8) : Action :=
  .bind (put 424 status.toUInt64) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 136 2) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else publishStatus

private def pumpSave : Action :=
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  if phase = 0 then .done 0 0 else
  .bind (get 168) fun s pending => if statusFailed s = true then .done s 0 else
  .bind (get 232) fun s operation => if statusFailed s = true then .done s 0 else
  .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
  .bind (get 224) fun s object => if statusFailed s = true then .done s 0 else
  .bind (get 176) fun s request => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.pollCall pending incoming operation ns object request 0) fun s sequence =>
  if s = IPCABI.wouldBlock then .done 0 0 else if statusFailed s = true then saveFailure s else
  .bind (put 128 sequence) fun s _ => if statusFailed s = true then .done s 0 else
  if phase = 1 then issueNext else if phase = 2 then
    .bind (get 184) fun s offset => if statusFailed s = true then .done s 0 else
    .bind (get 448) fun s count => if statusFailed s = true then .done s 0 else
    .bind (put 184 (offset + count)) fun s _ => if statusFailed s = true then .done s 0 else issueNext
  else if phase = 3 then finishRecord else if phase = 4 then
    .bind (get 112) fun s count => if statusFailed s = true then .done s 0 else
    .bind (put 160 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 (if count = 0 then 0 else 1)) fun s _ => if statusFailed s = true then .done s 0 else publishStatus
  else .done 234 0

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
    .bind (Lemma.Documents.Ink.visibility pageIndex stroke 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (Lemma.Documents.Ink.addEdit pageIndex 2 stroke) fun s _ => .done s stroke)
    fun s changed => if statusFailed s = true then saveFailure s else
  if changed = 0 then .done 0 0 else
  .bind (put 240 changed) fun s _ => if statusFailed s = true then .done s 0 else
  .bind redraw fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (startSave pageIndex Lemma.Documents.Ink.pageBytes (0x100 + page) 1) fun s _ =>
  if statusFailed s = true then saveFailure s else publishStatus

private def toolbar (button : UInt64) : Action :=
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  .bind (get 112) fun s rawCount => if statusFailed s = true then .done s 0 else
  .bind (get 144) fun s pending => if statusFailed s = true then .done s 0 else
  if different (phase ||| rawCount ||| pending) 0 = true then .done 0 0 else
  .bind (get 136) fun s status => if statusFailed s = true then .done s 0 else
  if 2 ≤ status then .done 0 0 else
  .bind (get 80) fun s page => if statusFailed s = true then .done s 0 else
  .bind (get 88) fun s pages => if statusFailed s = true then .done s 0 else
  if button = 0 then
    .bind (get 72) fun s ns => if statusFailed s = true then .done s 0 else
    .bind (loadNotebook (if ns = 1 then 2 else 1)) fun s _ => if statusFailed s = true then saveFailure s else
    .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
    if create = 1 then
      .bind (startSave pageIndex Lemma.Documents.Ink.pageBytes 0x101 1) fun s _ =>
      if statusFailed s = true then saveFailure s else publishStatus
    else .done 0 0
  else if button = 1 then if 1 < page then loadPage (page - 1) else .done 0 0
  else if button = 2 then if page < pages then loadPage (page + 1) else
    if pages < 64 then
      .bind (put 88 (pages + 1)) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (loadPage (pages + 1)) fun s _ => if statusFailed s = true then .done s 0 else
      .bind (startSave pageIndex Lemma.Documents.Ink.pageBytes (0x101 + pages) 1) fun s _ =>
      if statusFailed s = true then saveFailure s else publishStatus
    else saveFailure 235
  else if button = 3 then editPage 3 else if button = 4 then editPage 4 else if button = 5 then editPage 5 else
  if button = 6 then
    .bind (get 272) fun s brush => if statusFailed s = true then .done s 0 else
    .bind (put 272 (if brush < 2048 then brush * 2 else 256)) fun s _ =>
    if statusFailed s = true then .done s 0 else publishStatus
  else if button = 7 then
    .bind (put 224 0) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 160 4) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (put 136 1) fun s _ => if statusFailed s = true then .done s 0 else
    .bind (issue 7 0 0 0) fun s _ => if statusFailed s = true then saveFailure s else publishStatus
  else .done 0 0

private def beginStroke : Action :=
  .bind (get 128) fun s sequence => if statusFailed s = true then .done s 0 else
  .bind (get 96) fun s next => if statusFailed s = true then .done s 0 else
  let stroke := maximum next (sequence + 1)
  if 0x7ffffffffffffffe ≤ stroke then saveFailure 235 else
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

private def cancelInput : Action :=
  .bind (put 104 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 112 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 296 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 304 0) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 408 0) fun s _ => if statusFailed s = true then .done s 0 else
  put 432 1

private def pumpCancelledRedraw : Action :=
  .bind (get 432) fun s needed => if statusFailed s = true then .done s 0 else
  if needed = 0 then .done 0 0 else
  .bind (get 160) fun s phase => if statusFailed s = true then .done s 0 else
  if different phase 0 = true then .done 0 0 else
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
    if py < 128 then toolbar (minimum 7 (px / (width / 8))) else
    if py < 160 then .done 0 0 else
    .bind beginStroke fun s _ => if statusFailed s = true then .done s 0 else appendRaw

private def step : Action :=
  .bind pumpSave fun s _ => if statusFailed s = true then .done s 0 else
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
  .bind (Syscall.call 65 input (if pending = 0 then if dirtyX = 0xffff then 2 else 1 else 1) raw 0 0) fun s _ =>
  if s = 175 then cancelInput else if s = 174 then Syscall.sleep 10000 else
  if statusFailed s = true then .done s 0 else inputSample

private def initializeMedium : Action :=
  .bind (get 16) fun s endpoint => if statusFailed s = true then .done s 0 else
  .bind (Lemma.Services.Store.Client.call endpoint outgoing incoming 11 0 0 0 0 0 0 1) fun s sequence =>
  if statusFailed s = true then .done s 0 else
  .bind (get 24) fun s console => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x41f sequence 0 0 0) fun s _ =>
  if statusFailed s = true then .done s 0 else Syscall.exit 0

def main (bootArgument : UInt64) : Action :=
  if 1 < bootArgument then failed else
  .boundedFoldU64 64 clearStep 64 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 0) fun s surface => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 1) fun s input => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 2) fun s documents => if statusFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 3) fun s console => if statusFailed s = true then .done s 0 else
  .bind (put 0 surface) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 8 input) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 16 documents) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (put 24 console) fun s _ => if statusFailed s = true then .done s 0 else
  if bootArgument = 1 then initializeMedium else
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
  .boundedFoldU64 33 allocateStep 33 0 0 0 0 0 fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.allocate width height) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (loadNotebook 1) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (get 416) fun s create => if statusFailed s = true then .done s 0 else
  .bind (if create = 1 then startSave pageIndex Lemma.Documents.Ink.pageBytes 0x101 1 else .done 0 0)
    fun s _ => if statusFailed s = true then .done s 0 else
  .bind pumpRefresh fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Surface.acceptedSequence surface) fun s accepted => if statusFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x420 geometry 1 1 accepted) fun s _ =>
  if statusFailed s = true then .done s 0 else .loop step

end Lemma.Applications.Notebook
