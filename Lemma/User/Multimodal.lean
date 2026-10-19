import Lemma.User.Capability
import Lemma.User.Memory
import Lemma.User.CapabilityConsole

/-! Transient converter diagnostic window for Notebook21. No upload, retention,
research or training bit is requested. A deliberate local tap grants at most
five seconds. The normal workbook starts with every modality refused. -/
namespace Lemma.User.Multimodal

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true
open Lemma.Core0.Memory
open Lemma.User

def records : UInt64 := 0x340000
/-- One explicitly allocated page: samples[0,512), tutor context[1024,1112),
tutor proposal[1536,1792), school context[1152,1256), JOIN packet[1792,1896),
state[2048,2304), config packet[2304,2368).
The Notebook uses state+160 for one transient ASK/LOAD/JOIN/chooser-LOAD intent,
+168 for an explicit pending JOIN read and+176/+184/+192 for the queued chooser
page/request identity/edition. Legacy tutor action v2 remains192bytes.
The original BSS20d00..20f20 remains owned by ControlBacklog. -/
def state : UInt64 := records + 2048
def packet : UInt64 := records + 2304
private def get (offset : UInt64) : Action := Memory.read64 (state + offset)
private def put (offset value : UInt64) : Action := Memory.write64 (state + offset) value
private def field (offset value : UInt64) : Action := Memory.write64 (packet + offset) value
private def invoke (operation stream pointer epoch : UInt64) : Action :=
  .bind (get 0) fun s cap => if mmFailed s = true then .done s 0 else Syscall.call 69 cap operation stream pointer epoch
private def clearStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64 * 8) 0) fun s _ => .done s acc

def «initialize» (console : UInt64) : Action :=
  .bind (Syscall.allocatePage records) fun s address => if mmFailed s = true then .done s 0 else
  if mmDifferent address records = true then .done 95 0 else
  .boundedFoldU64 32 clearStep 32 0 0 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Memory.write64 (records + 1152) 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (Capability.bootGrant 4) fun s cap => if mmFailed s = true then .done s 0 else
  .bind (put 0 cap) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 8 console) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 0 0 0 0) fun s features => if mmFailed s = true then .done s 0 else
  CapabilityConsole.record console 0x710 features 0 0 0

private def startStep (i _ : UInt32) (acc expiry _ _ _ : UInt64) : Action :=
  let stream := i.toUInt64
  .bind (invoke 11 stream 0 0) fun s previous => if mmFailed s = true then .done s 0 else
  .bind (field 0 0x31474d4d) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 8 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 16 3) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 24 100) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 32 32768) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 40 expiry) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 48 previous) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 56 1) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 2 stream packet 0) fun s epoch => if mmFailed s = true then .done s 0 else
  .bind (put (64 + stream * 8) epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 0 2) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 8 1000000) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 16 4) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (field 24 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 3 stream packet epoch) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (invoke 4 stream 0 epoch) fun s _ => .done s (acc + 1)

private def revokeStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (invoke 6 i.toUInt64 0 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put (64 + i.toUInt64 * 8) 0) fun s _ => .done s (acc + 1)

private def wipeStep (i _ : UInt32) (acc stream _ _ _ : UInt64) : Action :=
  .bind (Memory.write64 (records + stream * 64 + i.toUInt64 * 8) 0) fun s _ => .done s acc
private def wipe (stream : UInt64) : Action :=
  .boundedFoldU64 8 wipeStep 8 0 stream 0 0 0 fun s _ => .done s 0
private def wipeAllStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (wipe i.toUInt64) fun s _ => .done s acc

def revokeAll : Action :=
  .bind (put 16 0) fun s _ => if mmFailed s = true then .done s 0 else
  .bind (put 32 1) fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 9 revokeStep 9 0 0 0 0 0 fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 wipeAllStep 8 0 0 0 0 0 fun s _ => .done s 0

def control (operation : UInt64) : Action :=
  if operation = 1 then
    .bind (invoke 6 8 0 0) fun s _ => if mmFailed s = true then .done s 0 else put 32 1
  else
  if operation = 2 then
    .bind (invoke 6 0 0 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (put 64 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (put 32 1) fun s _ => if mmFailed s = true then .done s 0 else wipe 0
  else
  .bind (get 16) fun s enabled => if mmFailed s = true then .done s 0 else
  if enabled = 1 then revokeAll else
  .bind (invoke 10 0 0 0) fun s ticks => if mmFailed s = true then .done s 0 else
  if 0x7ffffffffffffffe - 500000000 < ticks then .done 14 0 else
  .bind (put 24 (ticks + 500000000)) fun s _ => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 startStep 8 0 (ticks + 500000000) 0 0 0 fun s _ =>
  if mmFailed s = true then .bind revokeAll fun _ _ => .done s 0 else
  .bind (put 16 1) fun s _ => if mmFailed s = true then .done s 0 else put 32 1

private def sampleStep (i _ : UInt32) (acc console _ _ _ : UInt64) : Action :=
  let stream := i.toUInt64
  .bind (get (64 + stream * 8)) fun s epoch => if mmFailed s = true then .done s 0 else
  if epoch = 0 then .done 0 acc else
  .bind (invoke 7 stream (records + stream * 64) epoch) fun status sequence =>
  if status = 6 then .done 0 acc else
  if mmFailed status = true then
    .bind (invoke 6 stream 0 0) fun _ _ =>
    .bind (put (64 + stream * 8) 0) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (wipe stream) fun s _ => if mmFailed s = true then .done s 0 else
    .bind (CapabilityConsole.record console 0x713 stream status.toUInt64 epoch 0) fun s _ => .done s acc
  else
  .bind (Memory.read64 (records + stream * 64)) fun s _value => if mmFailed s = true then .done s 0 else
  .bind (Memory.read64 (records + stream * 64 + 8)) fun s capture => if mmFailed s = true then .done s 0 else
  .bind (CapabilityConsole.record console 0x711 stream sequence 0 capture) fun s _ => .done s (acc + 1)

/-- At most one completed record per endpoint per turn. Faults cannot kill the
workbook. The diagnostic payload is overwritten in transient owned RAM. -/
def pump : Action :=
  .bind (get 16) fun s enabled => if mmFailed s = true then .done s 0 else
  if enabled = 0 then .done 0 0 else
  .bind (invoke 10 0 0 0) fun s ticks => if mmFailed s = true then .done s 0 else
  .bind (get 24) fun s expiry => if mmFailed s = true then .done s 0 else
  if expiry ≤ ticks then revokeAll else
  .bind (get 8) fun s console => if mmFailed s = true then .done s 0 else
  .boundedFoldU64 8 sampleStep 8 0 console 0 0 0 fun s count => .done s count

def active : Action := get 16

end Lemma.User.Multimodal
