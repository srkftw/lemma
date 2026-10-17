import Lemma.Platform.LemmaSim.IO
import Lemma.Kernel.Memory.Frames

/-! Kernel8-only PIO boundary for the common OFDM DATA prerequisite.
Only genuinely compiled guest routines move bytes between live owned RAM and
hardware staging/immutable heads. No DMA, PLCP acquisition, MAC or HE claim. -/
namespace Lemma.Radio.WiFi.Controller
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def invalid : UInt8 := 208
def busy : UInt8 := 196
def read (base offset : UInt64) : Action := Lemma.Platform.LemmaSim.IO.read64 (base+offset)
def write (base offset value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write64 (base+offset) value

def «initialize» (base : UInt64) : Action :=
 .bind (read base 0) fun s magic => if s = 0 then
 .bind (read base 8) fun s version => if s = 0 then
 .bind (read base 136) fun s capacity => if s = 0 then
 if magic = 0x31415441444d4657 then if version = 1 then if capacity = 16 then .done 0 capacity
 else .done invalid 0 else .done invalid 0 else .done invalid 0
 else .done s 0 else .done s 0 else .done s 0

def descriptorValid (offset length seed : UInt64) : Bool :=
 if 0 < length then if length ≤ 16 then if offset ≤ 4096-length then
 if 0 < seed then if seed ≤ 127 then true else false else false
 else false else false else false

private def stageStep (index _count : UInt32) (base frame offset _ _ : UInt64) : Action :=
 .bind (Access.read8 (frame+offset+index.toUInt64)) fun s value => if s = 0 then
 .bind (write base (256+index.toUInt64*8) value) fun s _ => .done s base else .done s 0

/-- A queued Kernel-owned data frame must have exactly its retained queue pin.
The live owner/purpose/generation are checked before reading any payload byte.
The hardware privately captures staging on submit; completion remains separate. -/
def submitPinned (base owner handle offset length seed : UInt64) : Action :=
 if owner = Frames.kernelOwner then if descriptorValid offset length seed = true then
 .bind (Frames.resolvePurpose owner handle Frames.dataPurpose) fun s frame => if s = 0 then
 .bind (Frames.mappingCount owner handle) fun s pins => if s = 0 then
 if pins = 1 then
 .bind (read base 16) fun s state => if s = 0 then
 if state &&& (3 : UInt64) = 0 then if state &&& (24 : UInt64) = 24 then
 .bind (write base 24 length) fun s _ => if s = 0 then
 .bind (write base 32 seed) fun s _ => if s = 0 then
 .boundedFoldU64 16 stageStep length.toUInt32 base frame offset 0 0 fun s _ => if s = 0 then
 .bind (write base 56 1) fun s _ => if s = 0 then
 .bind (read base 16) fun s state => if s = 0 then
 if state &&& (1 : UInt64) = 1 then .done 0 handle else .done busy 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done busy 0 else .done busy 0 else .done s 0
 else .done busy 0 else .done s 0 else .done s 0
 else .done invalid 0 else .done invalid 0

def arm (base length seed : UInt64) : Action :=
 if descriptorValid 0 length seed = true then
 .bind (read base 16) fun s state => if s = 0 then
 if state &&& (3 : UInt64) = 0 then if state &&& (24 : UInt64) = 24 then
 .bind (write base 40 length) fun s _ => if s = 0 then
 .bind (write base 48 seed) fun s _ => if s = 0 then
 .bind (write base 56 2) fun s _ => if s = 0 then
 .bind (read base 16) fun s state => if s = 0 then
 if state &&& (2 : UInt64) = 2 then .done 0 length else .done busy 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done busy 0 else .done busy 0 else .done s 0 else .done invalid 0

private def receiveStep (index _count : UInt32) (base frame offset _ _ : UInt64) : Action :=
 .bind (read base (512+index.toUInt64*8)) fun s value => if s = 0 then
 if value ≤ 255 then
 .bind (Access.write8 (frame+offset+index.toUInt64) value) fun s _ => .done s base
 else .done invalid 0 else .done s 0

/-- Copy a verified immutable hardware head; ACK/PLIC completion is performed
by the caller only after successful owned-buffer publication. -/
def receiveOwned (base owner handle offset : UInt64) : Action :=
 if owner = Frames.kernelOwner then
 .bind (Frames.resolvePurpose owner handle Frames.dataPurpose) fun s frame => if s = 0 then
 .bind (read base 16) fun s state => if s = 0 then
 if state &&& (4 : UInt64) = 4 then
 .bind (read base 88) fun s length => if s = 0 then
 if descriptorValid offset length 1 = true then
 .boundedFoldU64 16 receiveStep length.toUInt32 base frame offset 0 0 fun s _ => .done s length
 else .done invalid 0 else .done s 0 else .done busy 0 else .done s 0 else .done s 0
 else .done invalid 0

def events (base : UInt64) : Action := read base 64
def acknowledge (base mask : UInt64) : Action :=
 if mask ≤ 7 then write base 64 mask else .done invalid 0
def releaseHead (base : UInt64) : Action := write base 56 3
def cancel (base : UInt64) : Action := write base 56 4
end Lemma.Radio.WiFi.Controller
