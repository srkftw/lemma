import Lemma.USB.Control
import Lemma.Platform.LemmaSim.IO
import Lemma.Kernel.Memory.Frames

/-! Kernel-only owned-buffer PIO for lemma-usb-device/1. Each service call is
bounded; receive heads and queued transmit slots remain circuit-owned until
explicit POP or actual USB ACK. No successful link transfer means durability. -/
namespace Lemma.USB.Controller
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def invalid : UInt8 := 197
def busy : UInt8 := 196
private def fatal : Action := .done 255 0
def read (base offset : UInt64) : Action := Lemma.Platform.LemmaSim.IO.read64 (base+offset)
def write (base offset value : UInt64) : Action := Lemma.Platform.LemmaSim.IO.write64 (base+offset) value

def «initialize» (base : UInt64) : Action :=
  .bind (read base 0) fun s magic => if s = 0 then
  .bind (read base 8) fun s version => if s = 0 then
  if (if magic = 0x315645444253554c then (if version = 1 then true else false) else false) then .done 0 64 else .done invalid 0
  else .done s 0 else .done s 0

def endpointCommand (base endpoint command : UInt64) : Action :=
  if (if endpoint ≤ 2 then (if (if 1 ≤ command then (if command ≤ 5 then true else false) else false) then true else false) else false) then
  .bind (write base 48 0) fun s _ => if s = 0 then
  .bind (write base 56 ((endpoint <<< 8) ||| command)) fun s _ => if s = 0 then
  .bind (read base 48) fun s fault => if s = 0 then
  if fault = 0 then .done 0 0 else if fault = 3 then .done busy 0 else .done invalid 0
  else .done s 0 else .done s 0 else .done s 0 else .done invalid 0

private def ownedPutStep (i _count : UInt32) (base endpoint address offset _ : UInt64) : Action :=
  .bind (Access.read64 (address+offset+i.toUInt64*8)) fun s value => if s = 0 then
  .bind (write base (256+endpoint*64+i.toUInt64*8) value) fun s _ => .done s base
  else .done s 0

/-- The physical source is derived only from a generation-checked owner1 /
purpose1 frame. Partial final words may be read within the owned page, but only
`length` bytes become visible. The circuit zeroes the unused immutable tail. -/
def submitOwned (base endpoint handle offset length : UInt64) : Action :=
  if (if endpoint ≤ 1 then (if (if length ≤ 64 then (if (if offset % 8 = 0 then (if offset ≤ 4096-((length+7)/8)*8 then true else false) else false) then true else false) else false) then true else false) else false) then
  .bind (Frames.resolvePurpose 1 handle 1) fun s address => if s = 0 then
  .bind (read base 16) fun s state => if s = 0 then
  if state &&& (64 <<< endpoint) = 0 then
  if (if endpoint = 0 then true else if state &&& 8 = 8 then true else false) then
  .bind (write base 48 0) fun s _ => if s = 0 then
  .boundedFoldU64 8 ownedPutStep ((length+7)/8).toUInt32 base endpoint address offset 0 fun s _ => if s = 0 then
  .bind (write base (64+endpoint*8) length) fun s _ => if s = 0 then endpointCommand base endpoint 1 else .done s 0
  else .done s 0 else .done s 0 else .done busy 0 else .done busy 0 else .done s 0 else .done s 0
  else .done invalid 0

private def ownedGetStep (i _count : UInt32) (base endpoint address offset _ : UInt64) : Action :=
  .bind (read base (512+(if endpoint = 2 then 64 else 0)+i.toUInt64*8)) fun s value => if s = 0 then
  .bind (Access.write64 (address+offset+i.toUInt64*8) value) fun s _ => .done s base else .done s 0

/-- Copy before destructive POP. Bad generation/purpose, alignment or capacity
cannot consume a packet. Retained head stays immutable throughout this call. -/
def receiveOwned (base endpoint handle offset capacity : UInt64) : Action :=
  if (if ((if endpoint = 0 then true else if endpoint = 2 then true else false)) then (if (if capacity ≤ 64 then (if (if offset % 8 = 0 then (if offset ≤ 4096-((capacity+7)/8)*8 then true else false) else false) then true else false) else false) then true else false) else false) then
  .bind (Frames.resolvePurpose 1 handle 1) fun s address => if s = 0 then
  .bind (read base 16) fun s state => if s = 0 then
  if (if state &&& (if endpoint = 0 then 16 else 32) = 0 then false else true) then
  .bind (read base (if endpoint = 0 then 80 else 88)) fun s metadata => if s = 0 then
  let length := metadata &&& 127
  if length ≤ capacity then
  .boundedFoldU64 8 ownedGetStep ((length+7)/8).toUInt32 base endpoint address offset 0 fun s _ => if s = 0 then
  .bind (endpointCommand base endpoint 2) fun s _ => .done s length else .done s 0
  else .done invalid 0 else .done s 0 else .done busy 0 else .done s 0 else .done s 0
  else .done invalid 0

private def responseWord (which index configuration halt endpoint : UInt64) : UInt64 :=
  if (if which = 1 then true else if which = 2 then true else false) then Control.descriptorWord which index else
  if index = 0 then
    if which = 5 then configuration else
    if which = 7 then
      if endpoint = 0 then (halt >>> 4) &&& 1 else
      if endpoint = 129 then (halt >>> 5) &&& 1 else (halt >>> 6) &&& 1
    else 0
  else 0

private def responseStep (i _count : UInt32) (base which configuration halt endpoint : UInt64) : Action :=
  .bind (write base (256+i.toUInt64*8) (responseWord which i.toUInt64 configuration halt endpoint)) fun s _ => .done s base

/-- Standard control policy executes in Lean. Address/config writes are only
proposals; hardware validates the retained actual SETUP and applies them after
its zero-length DATA1 status packet receives the host's real ACK. -/
def serviceSetup (base : UInt64) : Action :=
  .bind (read base 16) fun s state => if s = 0 then
  if (if state &&& 16 = 0 then false else true) then
  .bind (read base 80) fun s metadata => if s = 0 then
  if metadata &&& 383 = 264 then
  .bind (read base 160) fun s generation => if s = 0 then
  .bind (read base 512) fun s setup => if s = 0 then
  .bind (read base 24) fun s address => if s = 0 then
  .bind (read base 32) fun s configuration => if s = 0 then
  .bind (read base 152) fun s halt => if s = 0 then
  .bind (write base 168 generation) fun s _ => if s = 0 then
  let plan := Control.plan setup address configuration
  let which := plan &&& 255
  let length := (plan >>> 8) &&& 255
  let value := plan >>> 16
  if which = 0 then
    .bind (endpointCommand base 0 3) fun s _ => if s = 0 then endpointCommand base 0 2 else .done s 0
  else
  .bind (write base 48 0) fun s _ => if s = 0 then
  .bind (if which = 3 then write base 96 value else
    if which = 4 then write base 104 value else
    if (if which = 8 then true else if which = 9 then true else false) then endpointCommand base (if value = 129 then 1 else 2) (if which = 8 then 4 else 3)
    else .done 0 0) fun s _ => if s = 0 then
  .boundedFoldU64 8 responseStep ((length+7)/8).toUInt32 base which configuration halt value fun s _ => if s = 0 then
  .bind (write base 64 length) fun s _ => if s = 0 then
  .bind (endpointCommand base 0 1) fun s _ => if s = 0 then
  .bind (endpointCommand base 0 2) fun s _ => .done s which
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else
  if metadata &&& 383 = 0 then endpointCommand base 0 2 else .done invalid 0
  else .done s 0
  else .done busy 0 else .done s 0
end Lemma.USB.Controller
