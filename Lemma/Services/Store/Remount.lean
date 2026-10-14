import Lemma.Services.Store.Engine

/-! Opt-in shadow journal remount. It never formats, submits a write/barrier,
clears the current Engine's read-only flag, or reports Saved. Its caller must
hold the sole raw-block capability, resolve the quarantined opaque frame using
an actual receipt, and supply the checked connection epoch on both calls.
The separately selected server must pump actual READ completions into shadow.
Historical Engine and Store entry points do not call this library. -/
namespace Lemma.Services.Store.Remount
open Lemma.Core0.Memory

def version : UInt64 := 1
def shadow : UInt64 := 0x62000
def shadowBuffer : UInt64 := 0x63000
def current : UInt64 := 0x40000
def currentBuffer : UInt64 := 0x41000
def firstIndex : UInt64 := 0x42000
def secondIndex : UInt64 := 0x4e000
def controlMagic : UInt64 := 0x31544e554f4d534c
def invalid : UInt8 := 234
def busy : UInt8 := 231

/-- These are existing private Store indexes; only the unused one is cleared.
No arbitrary caller pointer becomes a context/index or source buffer. -/
def spareIndex (index : UInt64) : UInt64 :=
  if index = firstIndex then secondIndex else
  if index = secondIndex then firstIndex else 0

private def statusFailed (s : UInt8) : Bool := if s = 0 then false else true
private def different (a b : UInt64) : Bool := if a = b then false else true

def start (capacity ticket epoch : UInt64) : Action :=
  if ticket = 0 then .done invalid 0 else
  if epoch = 0 then .done invalid 0 else
  .bind (Engine.field current 0) fun s operation => if statusFailed s = true then .done s 0 else
  if different operation 0 = true then .done busy 0 else
  .bind (Engine.field current 336) fun s readonly => if statusFailed s = true then .done s 0 else
  if different readonly 1 = true then .done busy 0 else
  .bind (Engine.field current 24) fun s buffer => if statusFailed s = true then .done s 0 else
  if different buffer currentBuffer = true then .done invalid 0 else
  .bind (Engine.field shadow 0) fun s priorShadow => if statusFailed s = true then .done s 0 else
  if different priorShadow 0 = true then .done busy 0 else
  .bind (Engine.field current 48) fun s previousCapacity => if statusFailed s = true then .done s 0 else
  if different capacity previousCapacity = true then .done invalid 0 else
  .bind (Engine.field current 104) fun s activeIndex => if statusFailed s = true then .done s 0 else
  let unused := spareIndex activeIndex
  if unused = 0 then .done invalid 0 else
  .bind (Engine.mountStart shadow shadowBuffer unused capacity) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3584 controlMagic) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3592 version) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3600 ticket) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3608 epoch) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3616 capacity) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3624 activeIndex) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put shadow 3632 unused) fun s _ => .done s unused

private def copyStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let offset := i.toUInt64 * 8
  .bind (if 3584 ≤ offset then if offset < 3640 then .done 0 0
    else Engine.field shadow offset else Engine.field shadow offset) fun s value => if statusFailed s = true then .done s 0 else
  .bind (Engine.put current offset value) fun s _ => .done s (acc + 1)

/-- Publication follows only a complete real mount. The current index remains
untouched on every preflight failure. Adoption contains no external effect;
the selected server must keep its public mode read-only until this returns0.
A failed copy never authorizes writable mode. Cached sector bytes are invalidated
when switching from the shadow buffer to the current private buffer. -/
def adopt (ticket epoch : UInt64) : Action :=
  if ticket = 0 then .done invalid 0 else
  if epoch = 0 then .done invalid 0 else
  .bind (Engine.field current 0) fun s currentOperation => if statusFailed s = true then .done s 0 else
  if different currentOperation 0 = true then .done busy 0 else
  .bind (Engine.field current 336) fun s currentReadonly => if statusFailed s = true then .done s 0 else
  if different currentReadonly 1 = true then .done busy 0 else
  .bind (Engine.field shadow 3584) fun s magic => if statusFailed s = true then .done s 0 else
  if different magic controlMagic = true then .done invalid 0 else
  .bind (Engine.field shadow 3592) fun s schema => if statusFailed s = true then .done s 0 else
  if different schema version = true then .done invalid 0 else
  .bind (Engine.field shadow 3600) fun s actualTicket => if statusFailed s = true then .done s 0 else
  if different actualTicket ticket = true then .done invalid 0 else
  .bind (Engine.field shadow 3608) fun s actualEpoch => if statusFailed s = true then .done s 0 else
  if different actualEpoch epoch = true then .done invalid 0 else
  .bind (Engine.field shadow 0) fun s operation => if statusFailed s = true then .done s 0 else
  if different operation 0 = true then .done busy 0 else
  .bind (Engine.field shadow 32) fun s result => if statusFailed s = true then .done s 0 else
  if different result 0 = true then .done invalid 0 else
  .bind (Engine.field shadow 336) fun s readonly => if statusFailed s = true then .done s 0 else
  if different readonly 0 = true then .done invalid 0 else
  .bind (Engine.field shadow 24) fun s actualBuffer => if statusFailed s = true then .done s 0 else
  if different actualBuffer shadowBuffer = true then .done invalid 0 else
  .bind (Engine.field shadow 3616) fun s expectedCapacity => if statusFailed s = true then .done s 0 else
  .bind (Engine.field current 48) fun s currentCapacity => if statusFailed s = true then .done s 0 else
  if different expectedCapacity currentCapacity = true then .done invalid 0 else
  .bind (Engine.field shadow 48) fun s recoveredCapacity => if statusFailed s = true then .done s 0 else
  if different recoveredCapacity currentCapacity = true then .done invalid 0 else
  .bind (Engine.field shadow 3624) fun s originalIndex => if statusFailed s = true then .done s 0 else
  .bind (Engine.field current 104) fun s actualOriginalIndex => if statusFailed s = true then .done s 0 else
  if different originalIndex actualOriginalIndex = true then .done invalid 0 else
  .bind (Engine.field shadow 3632) fun s unused => if statusFailed s = true then .done s 0 else
  if different unused (spareIndex originalIndex) = true then .done invalid 0 else
  if unused = 0 then .done invalid 0 else
  .bind (Engine.field shadow 104) fun s actualUnused => if statusFailed s = true then .done s 0 else
  if different actualUnused unused = true then .done invalid 0 else
  .bind (Engine.field shadow 40) fun s sequence => if statusFailed s = true then .done s 0 else
  if Format.maximumSequence < sequence then .done invalid 0 else
  .boundedFoldU64 512 copyStep 512 0 0 0 0 0 fun s copied => if statusFailed s = true then .done s 0 else
  if different copied 512 = true then .done invalid 0 else
  .bind (Engine.invalidateReadCache current) fun s _ => if statusFailed s = true then .done s 0 else
  .bind (Engine.put current 24 currentBuffer) fun s _ => .done s sequence
end Lemma.Services.Store.Remount
