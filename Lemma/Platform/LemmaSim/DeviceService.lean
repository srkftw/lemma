import Lemma.Drivers.Paper
import Lemma.Drivers.Pen
import Lemma.Drivers.VirtIOBlock
import Lemma.Drivers.PLIC
import Lemma.Kernel.Task
import Lemma.Kernel.Memory.UserCopy

/-! Kernel device transport for named boot-granted endpoints. Endpoint identity,
not possession of an arbitrary endpoint, authorizes each operation. The notebook
receives surface/input grants; only the separately linked store receives block.
User spans are preflighted before copying or acknowledging destructive input.
No document, brush, serialization or recovery policy occurs here. -/
namespace Lemma.Platform.LemmaSim.DeviceService
open Lemma.Core0.Memory
open Lemma.Kernel
open Lemma.Kernel.Memory
open Lemma.User

def state : UInt64 := 0x80400c00
-- surface/input/block keys, tile/input handles, IRQ flags, block ready/status/kind,
-- input waiter, block waiter, last accepted paper sequence, paper IRQ masked
private def get (offset : UInt64) : Action := Access.read64 (state + offset)
private def put (offset value : UInt64) : Action := Access.write64 (state + offset) value
private def fatal : Action := .done 255 0
def waitStatus : UInt8 := 252

private def authorize (descriptor handle offset : UInt64) : Action :=
  .bind (Capability.lookup descriptor handle CapabilityABI.endpointType CapabilityABI.endpointCall) fun s key =>
  if s = 0 then
    .bind (get offset) fun s expected => if s = 0 then
    if key = expected then .done 0 key else .done CapabilityABI.denied 0
    else fatal
  else .done s 0

def configure (surface input block : UInt64) : Action :=
  .bind (put 0 surface) fun s _ => if s = 0 then
  .bind (put 8 input) fun s _ => if s = 0 then
  .bind (put 16 block) fun s _ => if s = 0 then
  .bind (Frames.allocate 1 1) fun s tile => if s = 0 then
  .bind (put 24 tile) fun s _ => if s = 0 then
  .bind (Frames.allocate 1 1) fun s pen => if s = 0 then
  .bind (put 32 pen) fun s _ => if s = 0 then
  .bind (put 40 0) fun s _ => if s = 0 then
  .bind (put 48 0) fun s _ => if s = 0 then
  .bind (put 72 0) fun s _ => if s = 0 then
  .bind (put 80 0) fun s _ => if s = 0 then put 88 0 else fatal else fatal
  else fatal else fatal else fatal else .done s 0 else fatal else .done s 0
  else fatal else fatal else fatal

private def metadata (descriptor pointer bytes : UInt64) : Action :=
  .bind (get 24) fun s handle => if s = 0 then
  .bind (UserCopy.copyFromUser descriptor pointer handle 1024 bytes) fun s _ => if s = 0 then
  .bind (Frames.resolvePurpose 1 handle 1) fun s base => if s = 0 then .done 0 (base + 1024) else fatal
  else .done s 0 else fatal

private def uploadOrdinary (descriptor fieldsPointer pixels : UInt64) : Action :=
  .bind (metadata descriptor fieldsPointer 32) fun s fields => if s = 0 then
  .bind (Access.read64 fields) fun s x => if s = 0 then
  .bind (Access.read64 (fields + 8)) fun s y => if s = 0 then
  .bind (Access.read64 (fields + 16)) fun s w => if s = 0 then
  .bind (Access.read64 (fields + 24)) fun s h => if s = 0 then
  if w = 0 then .done 170 0 else if 32 < w then .done 170 0 else
  if h = 0 then .done 170 0 else if 32 < h then .done 170 0 else
  .bind (get 24) fun s handle => if s = 0 then
  .bind (UserCopy.copyFromUser descriptor pixels handle 0 (((w + 1) / 2) * h)) fun s _ =>
  if s = 0 then Lemma.Drivers.Paper.upload handle x y w h else .done s 0
  else fatal else fatal else fatal else fatal else fatal else .done s 0

/-- Both buffers may share the single preflighted read page. The caller has
excluded the descriptor scratch alias; every remaining call before reuse is
read-only, and the paper driver is invoked only after the pixel copy finishes. -/
private def uploadBorrowed (descriptor fieldsPointer pixels firstHandle : UInt64) : Action :=
  .bind (UserCopy.copyFromUserReadPage descriptor fieldsPointer firstHandle 1024 32) fun s first => if s = 0 then
  .bind (Frames.resolvePurpose 1 firstHandle 1) fun s base => if s = 0 then
  let fields := base + 1024
  .bind (Access.read64 fields) fun s x => if s = 0 then
  .bind (Access.read64 (fields + 8)) fun s y => if s = 0 then
  .bind (Access.read64 (fields + 16)) fun s w => if s = 0 then
  .bind (Access.read64 (fields + 24)) fun s h => if s = 0 then
  if w = 0 then .done 170 0 else if 32 < w then .done 170 0 else
  if h = 0 then .done 170 0 else if 32 < h then .done 170 0 else
  .bind (get 24) fun s handle => if s = 0 then
  .bind (if handle = firstHandle then
    UserCopy.copyFromUserReusingReadPage descriptor fieldsPointer first pixels handle 0 (((w + 1) / 2) * h)
    else UserCopy.copyFromUser descriptor pixels handle 0 (((w + 1) / 2) * h)) fun s _ =>
  if s = 0 then Lemma.Drivers.Paper.upload handle x y w h else .done s 0
  else fatal else fatal else fatal else fatal else fatal else fatal else .done s 0

private def upload (descriptor fieldsPointer pixels : UInt64) : Action :=
  .bind (get 24) fun s handle => if s = 0 then
  if handle = descriptor then uploadOrdinary descriptor fieldsPointer pixels else
  uploadBorrowed descriptor fieldsPointer pixels handle
  else fatal

private def refresh (descriptor fieldsPointer : UInt64) : Action :=
  .bind (metadata descriptor fieldsPointer 48) fun s fields => if s = 0 then
  .bind (Access.read64 fields) fun s x => if s = 0 then
  .bind (Access.read64 (fields + 8)) fun s y => if s = 0 then
  .bind (Access.read64 (fields + 16)) fun s w => if s = 0 then
  .bind (Access.read64 (fields + 24)) fun s h => if s = 0 then
  .bind (Access.read64 (fields + 32)) fun s mode => if s = 0 then
  .bind (Access.read64 (fields + 40)) fun s seq => if s = 0 then
  Lemma.Drivers.Paper.refresh seq x y w h mode
  else fatal else fatal else fatal else fatal else fatal else fatal else .done s 0

/-- syscall64: cap, op, metadata, pixels, reserved. op0 geometry;1 upload;
2 refresh;3 last accepted sequence;4 controller status. Busy is bit0 and changes
only through the paper model's declared refresh/completion/reset transitions. -/
def surfaceStatus (fieldsPointer pixels : UInt64) : Action :=
  if fieldsPointer ||| pixels = 0 then
  .bind (IO.read64 (Lemma.Drivers.Paper.base + Lemma.Platform.LemmaSim.DeviceABI.paperStatusOffset)) fun s status => if s = 0 then
  if status &&& 8 = 8 then .done 0 status else
  .bind (get 88) fun s masked => if s = 0 then
  .bind (if masked = 1 then
    .bind Lemma.Drivers.PLIC.enablePaper fun s _ => if s = 0 then put 88 0 else fatal
    else .done 0 0) fun s _ => if s = 0 then .done 0 status else fatal
  else fatal else .done s 0
  else .done 16 0

def surface (descriptor handle op fieldsPointer pixels reserved : UInt64) : Action :=
  if reserved = 0 then
  .bind (authorize descriptor handle 0) fun s _ => if s = 0 then
    if op = 0 then Lemma.Drivers.Paper.dimensions else
    if op = 1 then upload descriptor fieldsPointer pixels else
    if op = 2 then refresh descriptor fieldsPointer else
    if op = 3 then IO.read64 (Lemma.Drivers.Paper.base + 112) else
    if op = 4 then surfaceStatus fieldsPointer pixels
    else .done 16 0
  else .done s 0 else .done 16 0

private def enablePen : Action := Lemma.Drivers.PLIC.enablePen

/-- syscall65: cap, op, output72, reserved, reserved. op0 returns pressure/range;
op1 takes a raw sample; op2 blocks until data/loss notification. Invalid output
is rejected before head ACK or loss ACK. Loss is a distinct175 result. -/
def input (descriptor handle op pointer r0 r1 : UInt64) : Action :=
  if r0 ||| r1 = 0 then
  .bind (authorize descriptor handle 8) fun s _ => if s = 0 then
  if op = 0 then IO.read64 (Lemma.Drivers.Pen.base + 72) else
  if op = 3 then IO.read64 (Lemma.Drivers.Pen.base + 56) else
  if op = 4 then IO.read64 (Lemma.Drivers.Pen.base + 64) else
  if (if op = 1 then true else if op = 2 then true else false) = true then
  .bind (UserCopy.validateWrite descriptor pointer 72) fun s _ => if s = 0 then
  .bind (get 32) fun s scratch => if s = 0 then
  .bind (Lemma.Drivers.Pen.take scratch) fun status seq =>
  if status = 0 then
    .bind (UserCopy.copyToUser descriptor pointer scratch 0 72) fun s _ => if s = 0 then
    .bind enablePen fun s _ => .done s seq else .done s 0
  else if status = Lemma.Drivers.Pen.empty then
    .bind enablePen fun s _ => if s = 0 then
    if op = 2 then
      .bind (put 72 descriptor) fun s _ => if s = 0 then .done waitStatus 0 else fatal
    else .done status 0 else fatal
  else .bind enablePen fun s _ => if s = 0 then .done status seq else fatal
  else fatal else .done s 0 else .done 16 0
  else .done s 0 else .done 16 0

private def copyBlock (descriptor pointer direction : UInt64) : Action :=
  .bind (Lemma.Drivers.VirtIOBlock.bounce) fun s bounce => if s = 0 then
  .bind (Access.read64 Lemma.Drivers.VirtIOBlock.state) fun s handle => if s = 0 then
  if direction = 0 then UserCopy.copyFromUser descriptor pointer handle 0x600 512
  else UserCopy.copyToUser descriptor pointer handle 0x600 512
  else fatal else .done s bounce

private def blockFinish (descriptor pointer : UInt64) : Action :=
  .bind (get 48) fun s ready => if s = 0 then
  if ready = 0 then .done Lemma.Drivers.VirtIOBlock.pending 0 else
  .bind (get 56) fun s status => if s = 0 then
  .bind (get 64) fun s kind => if s = 0 then
  .bind (if status = 0 then if kind = 1 then copyBlock descriptor pointer 1 else .done 0 0
    else .done 0 0) fun s _ => if s = 0 then
  .bind (put 48 0) fun s _ => if s = 0 then .done status.toUInt8 kind else fatal
  else .done s 0 else fatal else fatal else fatal

/-- syscall66: blockcap,op,sector,buffer512,reserved. Only store has this grant.
op0 capacity;1 read;2 write;3 flush;4 completion. Kernel owns and retains the DMA
frame. Failed/corrupt DMA remains quarantined by the driver, independent of task
lifetime. The store alone interprets successful flush as publication durability. -/
def block (descriptor handle op sector pointer reserved : UInt64) : Action :=
  if reserved = 0 then
  .bind (authorize descriptor handle 16) fun s _ => if s = 0 then
  if op = 0 then Lemma.Drivers.VirtIOBlock.capacity else
  if op = 4 then blockFinish descriptor pointer else
  if (if op = 1 then true else if op = 2 then true else if op = 3 then true else false) = true then
  .bind (get 48) fun s ready => if s = 0 then
  if ready = 0 then
  .bind (if op = 1 then UserCopy.validateWrite descriptor pointer 512 else
    if op = 2 then copyBlock descriptor pointer 0 else .done 0 0) fun s _ => if s = 0 then
  .bind (Lemma.Drivers.VirtIOBlock.submit (if op = 1 then 0 else if op = 2 then 1 else 4) sector) fun status request =>
  if status = 0 then .done Lemma.Drivers.VirtIOBlock.pending request else .done status 0
  else .done s 0 else .done 162 0 else fatal
  else .done 16 0 else .done s 0 else .done 16 0

/-- Called only following an actual source1 notification, not a status poll. -/
def blockInterrupt : Action :=
  .bind Lemma.Drivers.VirtIOBlock.finish fun status kind =>
  if status = Lemma.Drivers.VirtIOBlock.pending then .done 0 0 else
  .bind (put 56 status.toUInt64) fun s _ => if s = 0 then
  .bind (put 64 kind) fun s _ => if s = 0 then put 48 1 else fatal else fatal

private def wakeInput : Action :=
  .bind (get 72) fun s descriptor => if s = 0 then
  if descriptor = 0 then .done 0 0 else
  .bind (Task.lookup descriptor) fun s record => if s = 0 then
  .bind (Access.read64 (record + Task.stateOffset)) fun s state => if s = 0 then
  if state = Task.sleeping then
    .bind (Access.write64 (record + Task.deadlineOffset) 0) fun s _ => if s = 0 then
    .bind (Access.write64 (record + Task.stateOffset) Task.runnable) fun s _ => if s = 0 then put 72 0 else fatal else fatal
  else if state = Task.running then .done 0 0 else put 72 0
  else fatal else if s = 74 then put 72 0 else fatal else fatal

def notification (source : UInt64) : Action :=
  if source = 1 then
    .bind (get 40) fun s flags => if s = 0 then put 40 (flags ||| 2) else fatal
  else if source = 12 then
    .bind Lemma.Drivers.PLIC.disablePaper fun s _ => if s = 0 then
    .bind (put 88 1) fun s _ => if s = 0 then
    .bind (get 40) fun s flags => if s = 0 then
    .bind (put 40 (flags ||| 4096)) fun s _ => if s = 0 then wakeInput else fatal
    else fatal else fatal else fatal
  else if source = 13 then
    .bind Lemma.Drivers.PLIC.disablePen fun s _ => if s = 0 then wakeInput else fatal
  else fatal

def deferred : Action :=
  .bind (get 40) fun s flags => if s = 0 then
  .bind (put 40 0) fun s _ => if s = 0 then
  .bind (if flags &&& 2 = 2 then blockInterrupt else .done 0 0) fun s _ => if s = 0 then
  if flags &&& 4096 = 4096 then
    .bind Lemma.Drivers.Paper.completion fun s _ => if s = 0 then surfaceStatus 0 0 else fatal
  else .done 0 0
  else fatal else fatal else fatal

end Lemma.Platform.LemmaSim.DeviceService
