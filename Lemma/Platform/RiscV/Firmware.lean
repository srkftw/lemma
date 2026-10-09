import Lemma.Core0.Memory

/-! Private machine ABI v1. No SBI compatibility is claimed. The M handler
touches only its fixed private frame/storage and the closed timer primitives.
It never follows an S/U-supplied pointer. All policy below is compiled Lean. -/
namespace Lemma.Platform.RiscV.Firmware
open Lemma.Core0.Memory

def frameAddress : UInt64 := 0x8010fee0
def irqCountAddress : UInt64 := 0x80100000
def lastDeadlineAddress : UInt64 := 0x80100008
def quantumMin : UInt64 := 1000
def quantumMax : UInt64 := 10000000
def read (address : UInt64) : Action :=
  .platform .physicalRead64 address 0 0 0 0 0 fun s v => .done s v
def write (address value : UInt64) : Action :=
  .platform .physicalWrite64 address value 0 0 0 0 fun s v => .done s v
def time : Action := .platform .readTime 0 0 0 0 0 0 fun s v => .done s v
def compare (deadline : UInt64) : Action :=
  .platform .setMachineCompare deadline 0 0 0 0 0 fun s v => .done s v
def notify (pending : UInt64) : Action :=
  .platform .forwardSupervisor pending 0 0 0 0 0 fun s v => .done s v
def failed (s : UInt8) : Bool := if s = 0 then false else true
def validDeadline (now deadline : UInt64) : Bool :=
  if now < deadline then
    if quantumMin ≤ deadline - now then
      if deadline - now ≤ quantumMax then true else false
    else false
  else false
def validPc (pc : UInt64) : Bool :=
  if 0x80200000 ≤ pc then
    if pc < 0x80300000 - 4 then
      if pc % 4 = 0 then true else false
    else false
  else false

/-- Return two ABI words in saved a0/a1 and advance only a validated S ECALL. -/
def reply (pc : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (write (frameAddress + 80) status.toUInt64) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write (frameAddress + 88) value) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write (frameAddress + 256) (pc + 4)) fun s _ => .done s frameAddress

def arm (pc deadline : UInt64) : Action :=
  .bind (notify 0) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (compare deadline) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (write lastDeadlineAddress deadline) fun s _ =>
  if failed s = true then .done s 0 else reply pc 0 deadline

/-- 1: acknowledge/rearm a bounded future deadline. 2: machine time.
3: origin witness (saved MPP=S and cause=S ECALL). 4: actual hardware IRQs.
5: acknowledge and arm a bounded relative interval using the M clock. Computing
the deadline here avoids racing the minimum interval against an S-to-M call.
Unsupported numbers are recoverable errors, never permissive success. -/
def call (pc number payload : UInt64) : Action :=
  if number = 1 then
    .bind time fun s now =>
    if failed s = true then .done s 0 else
    if validDeadline now payload = false then reply pc 22 0 else
    arm pc payload
  else if number = 2 then
    .bind time fun s now => if s = 0 then reply pc 0 now else .done s 0
  else if number = 3 then reply pc 0 0x534543414c4c0001
  else if number = 4 then
    .bind (read irqCountAddress) fun s count =>
    if s = 0 then reply pc 0 count else .done s 0
  else if number = 5 then
    if quantumMin ≤ payload then
      if payload ≤ quantumMax then
        .bind time fun s now =>
        if failed s = true then .done s 0 else
        if now ≤ 0xffffffffffffffff - payload then arm pc (now + payload)
        else reply pc 22 0
      else reply pc 22 0
    else reply pc 22 0
  else reply pc 17 0

def timerInterrupt : Action :=
  .bind (compare 0xffffffffffffffff) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (read irqCountAddress) fun s count =>
  if failed s = true then .done s 0 else
  if count = 0xffffffffffffffff then .done 48 0 else
  .bind (write irqCountAddress (count + 1)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (notify 1) fun s _ => .done s frameAddress

def dispatch (frame cause _trapValue : UInt64) : Action :=
  if frame = frameAddress then
    .bind (read (frameAddress + 264)) fun s status =>
    if failed s = true then .done s 0 else
    let origin := (status >>> 11) &&& 3
    if origin = 3 then .done 48 0 else
    if cause = 0x8000000000000007 then timerInterrupt else
    if cause = 9 then
      if origin = 1 then
        .bind (read (frameAddress + 256)) fun s pc =>
        if failed s = true then .done s 0 else
        if validPc pc = false then .done 48 0 else
        .bind (read (frameAddress + 136)) fun s number =>
        if failed s = true then .done s 0 else
        .bind (read (frameAddress + 80)) fun s payload =>
        if failed s = true then .done s 0 else call pc number payload
      else .done 48 0
    else .done 48 0
  else .done 48 0

end Lemma.Platform.RiscV.Firmware
