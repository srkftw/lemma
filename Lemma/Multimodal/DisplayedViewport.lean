import Lemma.Drivers.Paper
import Lemma.Platform.LemmaSim.DeviceABI

/-! Kernel-side completion-bound history adapter for OpticalDerived/1.
Not yet installed in the active DeviceService/Notebook configuration. It wraps the actual
existing Paper.refresh operation and reads the existing controller status and
completed sequence; accepted requests never become displayed immediately.
This first adapter admits full-viewport publications only. Partial-refresh or
reset makes the entire gaze binding unknown until a new full publication. It
does not claim optical onset. Caller must reserve one disjoint owned kernel page
and provide current workbook semantic identities through its trusted path. -/
namespace Lemma.Multimodal.DisplayedViewport
open Lemma.Core0.Memory Lemma.Kernel.Memory
open Lemma.Platform.LemmaSim
private def failed (s : UInt8) : Bool := if s = 0 then false else true
private def different (a b : UInt64) : Bool := if a = b then false else true
private def get (state n : UInt64) : Action := Access.read64 (state+n*8)
private def put (state n v : UInt64) : Action := Access.write64 (state+n*8) v
private def paper (offset : UInt64) : Action := IO.read64 (DeviceABI.paperBase+offset)
private def commonTick : Action :=
  .bind (IO.read64 0x200bff8) fun s tick => if failed s = true then .done s 0 else
  if 0x0ccccccccccccccb < tick then .done 15 0 else .done 0 (tick*10)
/-- Explicit profile relation: canonical100MHz acquisition clock and10MHz
mtime are derived from the same synthetic clock/reset domain. Never use this
adapter for asynchronous/external clocks. Mapping uncertainty is ten100MHz
ticks; capture/availability and observation time remain distinct. -/
def mappingIdentity : UInt64 := 0x100000001
private def clearStep (i _ : UInt32) (acc state _ _ _ : UInt64) : Action :=
  .bind (put state i.toUInt64 0) fun s _ => .done s acc

def «initialize» (state displayEpoch : UInt64) : Action :=
  if state % 4096 = 0 then
  if displayEpoch = 0 then .done 2 0 else
  if 0x7ffffffffffffffe < displayEpoch then .done 15 0 else
  .boundedFoldU64 128 clearStep 128 0 state 0 0 0 fun s _ => if failed s = true then .done s 0 else
  .bind (put state 1 displayEpoch) fun s _ => .done s displayEpoch
  else .done 2 0

/-- New external-interaction/reset epoch clears every live history entry.
Sealed archival histories require their own explicitly authorized replay path. -/
def reset (state nextEpoch : UInt64) : Action :=
  .bind (get state 1) fun s current => if failed s = true then .done s 0 else
  if nextEpoch ≤ current then .done 4 0 else «initialize» state nextEpoch

private def closeEntry (i _ : UInt32) (acc state now _ _ : UInt64) : Action :=
  let slot := state+256+i.toUInt64*128
  .bind (get slot 0) fun s valid => if failed s = true then .done s 0 else
  if valid = 0 then .done 0 acc else
  .bind (get slot 12) fun s endTick => if failed s = true then .done s 0 else
  if endTick = 0 then .bind (put slot 12 now) fun s _ => .done s acc else .done 0 acc

/-- Call this before every partial update, warm/cold reset, control loss,
non-wrapper refresh or geometry change. It retains old closed time intervals
but removes present-state authority. No tutor action can call this directly. -/
def invalidate (state : UInt64) : Action :=
  .bind commonTick fun s now => if failed s = true then .done s 0 else
  .bind (put state 0 0) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 4 closeEntry 4 0 state now 0 0 fun s _ => .done s now

private def identityValid (source edition revision viewport object sequence : UInt64) : Bool :=
  if source = 0 then false else if edition = 0 then false else
  if revision = 0 then false else if viewport = 0 then false else
  if object = 0 then false else if sequence = 0 then false else
  if 0x7ffffffffffffffe < sequence then false else true

/-- Actual driver refresh plus pending semantic binding. Full-screen only;
existing tile raster/upload remains outside and still executes normally. -/
def refresh (state source edition revision viewport object sequence width height mode : UInt64) : Action :=
  if identityValid source edition revision viewport object sequence = false then .done 2 0 else
  .bind (get state 0) fun s pending => if failed s = true then .done s 0 else
  if pending = 1 then .done 6 0 else
  .bind (get state 1) fun s epoch => if failed s = true then .done s 0 else
  if epoch = 0 then .done 9 0 else
  .bind (get state 3) fun s prior => if failed s = true then .done s 0 else
  if sequence ≤ prior then .done 4 0 else
  .bind Lemma.Drivers.Paper.dimensions fun s dimensions => if failed s = true then .done s 0 else
  if different (dimensions &&& 0xffffffff) width = true then .done 2 0 else
  if different (dimensions >>> 32) height = true then .done 2 0 else
  .bind (invalidate state) fun s _ => if failed s = true then .done s 0 else
  .bind (Lemma.Drivers.Paper.refresh sequence 0 0 width height mode) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 8 source) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 9 edition) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 10 revision) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 11 viewport) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 12 object) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 13 sequence) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 14 width) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 15 height) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 3 sequence) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 0 1) fun s _ => .done s sequence

private def publishStep (i _ : UInt32) (acc state slot _ _ : UInt64) : Action :=
  let n := i.toUInt64
  if n < 6 then
  .bind (get state (8+n)) fun s value => if failed s = true then .done s 0 else
  .bind (put slot (1+n) value) fun s _ => .done s acc
  else if n = 6 then .bind (get state 14) fun s value => if failed s = true then .done s 0 else
  .bind (put slot 9 value) fun s _ => .done s acc else
  .bind (get state 15) fun s value => if failed s = true then .done s 0 else
  .bind (put slot 10 value) fun s _ => .done s acc

def poll (state : UInt64) : Action :=
  .bind (get state 0) fun s pending => if failed s = true then .done s 0 else
  .bind (paper DeviceABI.paperStatusOffset) fun s status => if failed s = true then .done s 0 else
  if status &&& 8 = 8 then .bind (invalidate state) fun s _ => .done s 9 else
  .bind (paper DeviceABI.paperErrorOffset) fun s error => if failed s = true then .done s 0 else
  if different error 0 = true then .bind (invalidate state) fun s _ => .done s 9 else
  .bind (paper DeviceABI.paperSequenceOffset) fun s accepted => if failed s = true then .done s 0 else
  .bind (get state 3) fun s prior => if failed s = true then .done s 0 else
  if pending = 0 then
    if different accepted prior = true then .bind (invalidate state) fun s _ => .done s 9 else
    if status &&& 1 = 1 then .bind (invalidate state) fun s _ => .done s 9 else .done 0 0
  else
  if status &&& 1 = 1 then .done 6 0 else
  .bind (paper DeviceABI.paperCompletedOffset) fun s completed => if failed s = true then .done s 0 else
  .bind (get state 13) fun s sequence => if failed s = true then .done s 0 else
  if different completed sequence = true then .bind (invalidate state) fun s _ => .done s 9 else
  .bind commonTick fun s now => if failed s = true then .done s 0 else
  .bind (get state 2) fun s cursor => if failed s = true then .done s 0 else
  if 4 ≤ cursor then .done 2 0 else
  let slot := state+256+cursor*128
  .bind (put slot 0 0) fun s _ => if failed s = true then .done s 0 else
  .boundedFoldU64 8 publishStep 8 0 state slot 0 0 fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 7 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 8 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 11 now) fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 12 0) fun s _ => if failed s = true then .done s 0 else
  .bind (get state 1) fun s epoch => if failed s = true then .done s 0 else
  .bind (put slot 13 epoch) fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 14 10) fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 15 1) fun s _ => if failed s = true then .done s 0 else
  .bind (put slot 0 1) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 2 ((cursor+1)%4)) fun s _ => if failed s = true then .done s 0 else
  .bind (put state 0 0) fun s _ => .done s sequence

private def selectStep (i _ : UInt32) (acc state captureStart captureEnd now : UInt64) : Action :=
  let slot := state+256+i.toUInt64*128
  .bind (get slot 0) fun s valid => if failed s = true then .done s 0 else
  if valid = 0 then .done 0 acc else
  .bind (get slot 11) fun s startTick => if failed s = true then .done s 0 else
  .bind (get slot 12) fun s endTick => if failed s = true then .done s 0 else
  let limit := if endTick = 0 then now else endTick
  if captureStart < 10 then .done 0 acc else
  if captureStart-10 < startTick then .done 0 acc else
  if limit < captureEnd+10 then .done 0 acc else
  if acc = 0 then .done 0 slot else .done 0 0xffffffffffffffff

private def bindStep (i _ : UInt32) (acc slot params _ _ : UInt64) : Action :=
  let n := i.toUInt64
  .bind (get slot (1+n)) fun s value => if failed s = true then .done s 0 else
  .bind (put params (32+n) value) fun s _ => .done s acc

/-- Resolve from source capture interval, never arrival/current page. A missing
or retired record is explicit9, pending/partial epochs remain unavailable and
cannot be reconstructed from today's document. The selected immutable source
anchors replace all caller-supplied viewport labels in the transformer block. -/
def bindCapture (state frame params currentAcquisitionEpoch : UInt64) : Action :=
  .bind (get frame 4) fun s epoch => if failed s = true then .done s 0 else
  if different epoch currentAcquisitionEpoch = true then .done 8 0 else
  .bind (get frame 6) fun s captureStart => if failed s = true then .done s 0 else
  .bind (get frame 7) fun s captureEnd => if failed s = true then .done s 0 else
  if 0x7ffffffffffe0000 < captureEnd then .done 8 0 else
  if captureEnd < captureStart then .done 8 0 else
  .bind commonTick fun s now => if failed s = true then .done s 0 else
  .boundedFoldU64 4 selectStep 4 0 state captureStart captureEnd now fun s slot => if failed s = true then .done s 0 else
  if slot = 0 then .done 9 0 else if slot = 0xffffffffffffffff then .done 10 0 else
  .boundedFoldU64 6 bindStep 6 0 slot params 0 0 fun s _ => if failed s = true then .done s 0 else
  .bind (get slot 6) fun s sequence => if failed s = true then .done s 0 else
  .bind (get slot 11) fun s knownStart => if failed s = true then .done s 0 else
  .bind (get slot 12) fun s knownEnd => if failed s = true then .done s 0 else
  .bind (get slot 9) fun s width => if failed s = true then .done s 0 else
  .bind (get slot 10) fun s height => if failed s = true then .done s 0 else
  .bind (put params 20 now) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 24 mappingIdentity) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 25 epoch) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 26 1) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 27 1) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 28 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 29 10) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 30 knownStart) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 31 (if knownEnd = 0 then now else knownEnd)) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 38 sequence) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 39 knownStart) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 40 (if knownEnd = 0 then now else knownEnd)) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 41 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 42 0) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 43 width) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 44 height) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 45 1) fun s _ => if failed s = true then .done s 0 else
  .bind (put params 50 0) fun s _ => .done s slot

end Lemma.Multimodal.DisplayedViewport
