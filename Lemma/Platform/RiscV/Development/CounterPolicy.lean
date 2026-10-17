import Lemma.Core0.Memory

/-! Guest-issued counter qualification policy. The typed primitive boundary
contains only individual CSR accesses; all tests, conditions and records are
ordinary checked Lean lowered under core0-firmware-v0.2. -/
namespace Lemma.Platform.RiscV.Development.CounterPolicy
open Lemma.Core0.Memory

def recordBase : UInt64 := 0x80100100
def expectedMisa : UInt64 := 0x8000000000141100
def startMagic : UInt64 := 0x4353524755455354
def completedMagic : UInt64 := 0x4353525041535301

def failed (status : UInt8) : Bool := if status = 0 then false else true
def different (value expected : UInt64) : Bool := if value = expected then false else true
def wrappedValid (cycle retired : UInt64) : Bool :=
  if cycle < 65536 then if retired < 65536 then true else false else false
def resumedValid (cycle retired : UInt64) : Bool :=
  if 123456 < cycle then if 789 < retired then true else false else false
def cycleOnlyValid (c0 i0 c1 i1 : UInt64) : Bool :=
  if 3000 < c0 then if c0 < c1 then if i0 = 4000 then
    if i1 = i0 then true else false else false else false else false
def retiredOnlyValid (c0 i0 c1 i1 : UInt64) : Bool :=
  if c0 = 1000 then if c1 = c0 then if 2000 < i0 then
    if i0 < i1 then true else false else false else false else false
def stableValid (c0 i0 t0 c1 i1 t1 : UInt64) : Bool :=
  if c0 = 123456 then if c1 = c0 then if i0 = 789 then
    if i1 = i0 then if t0 < t1 then true else false else false
    else false else false else false

def emit (index value : UInt64) : Action :=
  .platform .physicalWrite64 (recordBase + index * 8) value 0 0 0 0 fun s v => .done s v

def misa : Action := .platform .readMisa 0 0 0 0 0 0 fun s v => .done s v
def cycle : Action := .platform .readMachineCycle 0 0 0 0 0 0 fun s v => .done s v
def retired : Action := .platform .readMachineRetired 0 0 0 0 0 0 fun s v => .done s v
def inhibit : Action := .platform .readMachineInhibit 0 0 0 0 0 0 fun s v => .done s v
def counteren : Action := .platform .readMachineCounterEnable 0 0 0 0 0 0 fun s v => .done s v
def time : Action := .platform .readTime 0 0 0 0 0 0 fun s v => .done s v
def writeCycle (value : UInt64) : Action :=
  .platform .writeMachineCycle value 0 0 0 0 0 fun s v => .done s v
def writeRetired (value : UInt64) : Action :=
  .platform .writeMachineRetired value 0 0 0 0 0 fun s v => .done s v
def writeInhibit (value : UInt64) : Action :=
  .platform .writeMachineInhibit value 0 0 0 0 0 fun s v => .done s v
def writeCounteren (value : UInt64) : Action :=
  .platform .writeMachineCounterEnable value 0 0 0 0 0 fun s v => .done s v

/-- Independent CY/IR inhibition, followed by actual modulo-2^64 counter wrap.
No instruction or clock parity between fast and pipeline machines is assumed. -/
def wrapped : Action :=
  .bind (writeInhibit 5) fun s _ => if failed s = true then .done s 0 else
  .bind (writeCycle 0xfffffffffffffffd) fun s _ => if failed s = true then .done s 0 else
  .bind (writeRetired 0xfffffffffffffffd) fun s _ => if failed s = true then .done s 0 else
  .bind (writeInhibit 0) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c => if failed s = true then .done s 0 else
  .bind retired fun s i => if failed s = true then .done s 0 else
  .bind (emit 21 c) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 22 i) fun s _ => if failed s = true then .done s 0 else
  if wrappedValid c i = true then
    .bind (writeInhibit 5) fun s _ => if failed s = true then .done s 0 else
    .bind (emit 23 completedMagic) fun s _ => .done s 0
  else .done 48 0

def cycleOnly : Action :=
  .bind (writeInhibit 5) fun s _ => if failed s = true then .done s 0 else
  .bind (writeCycle 3000) fun s _ => if failed s = true then .done s 0 else
  .bind (writeRetired 4000) fun s _ => if failed s = true then .done s 0 else
  .bind (writeInhibit 4) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c0 => if failed s = true then .done s 0 else
  .bind retired fun s i0 => if failed s = true then .done s 0 else
  .bind (emit 17 c0) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 18 i0) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c1 => if failed s = true then .done s 0 else
  .bind retired fun s i1 => if failed s = true then .done s 0 else
  .bind (emit 19 c1) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 20 i1) fun s _ => if failed s = true then .done s 0 else
  if cycleOnlyValid c0 i0 c1 i1 = true then wrapped
  else .done 47 0

def retiredOnly : Action :=
  .bind (writeInhibit 5) fun s _ => if failed s = true then .done s 0 else
  .bind (writeCycle 1000) fun s _ => if failed s = true then .done s 0 else
  .bind (writeRetired 2000) fun s _ => if failed s = true then .done s 0 else
  .bind (writeInhibit 1) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c0 => if failed s = true then .done s 0 else
  .bind retired fun s i0 => if failed s = true then .done s 0 else
  .bind (emit 13 c0) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 14 i0) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c1 => if failed s = true then .done s 0 else
  .bind retired fun s i1 => if failed s = true then .done s 0 else
  .bind (emit 15 c1) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 16 i1) fun s _ => if failed s = true then .done s 0 else
  if retiredOnlyValid c0 i0 c1 i1 = true then cycleOnly
  else .done 46 0

def resumed : Action :=
  .bind (writeInhibit 0) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c => if failed s = true then .done s 0 else
  .bind retired fun s i => if failed s = true then .done s 0 else
  .bind (emit 11 c) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 12 i) fun s _ => if failed s = true then .done s 0 else
  if resumedValid c i = true then retiredOnly else .done 45 0

def stable : Action :=
  .bind (writeInhibit 5) fun s _ => if failed s = true then .done s 0 else
  .bind (writeCycle 123456) fun s _ => if failed s = true then .done s 0 else
  .bind (writeRetired 789) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c0 => if failed s = true then .done s 0 else
  .bind retired fun s i0 => if failed s = true then .done s 0 else
  .bind time fun s t0 => if failed s = true then .done s 0 else
  .bind (emit 5 c0) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 6 i0) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 7 t0) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c1 => if failed s = true then .done s 0 else
  .bind retired fun s i1 => if failed s = true then .done s 0 else
  .bind time fun s t1 => if failed s = true then .done s 0 else
  .bind (emit 8 c1) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 9 i1) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 10 t1) fun s _ => if failed s = true then .done s 0 else
  if stableValid c0 i0 t0 c1 i1 t1 = true then resumed
  else .done 44 0

def masks : Action :=
  .bind (writeInhibit 0xffffffffffffffff) fun s _ => if failed s = true then .done s 0 else
  .bind inhibit fun s value => if failed s = true then .done s 0 else
  .bind (emit 2 value) fun s _ => if failed s = true then .done s 0 else
  if different value 5 = true then .done 41 0 else
  .bind (writeCounteren 0xffffffffffffffff) fun s _ => if failed s = true then .done s 0 else
  .bind counteren fun s value => if failed s = true then .done s 0 else
  .bind (emit 3 value) fun s _ => if failed s = true then .done s 0 else
  if different value 7 = true then .done 42 0 else
  .bind (writeCounteren 0) fun s _ => if failed s = true then .done s 0 else
  .bind counteren fun s value => if failed s = true then .done s 0 else
  .bind (emit 4 value) fun s _ => if failed s = true then .done s 0 else
  if value = 0 then stable else .done 43 0

def main : Action :=
  .bind (emit 23 0) fun s _ => if failed s = true then .done s 0 else
  .bind inhibit fun s value => if failed s = true then .done s 0 else
  .bind (emit 24 value) fun s _ => if failed s = true then .done s 0 else
  if different value 0 = true then .done 49 value else
  .bind (emit 0 startMagic) fun s _ => if failed s = true then .done s 0 else
  .bind misa fun s value => if failed s = true then .done s 0 else
  .bind (emit 1 value) fun s _ => if failed s = true then .done s 0 else
  if value = expectedMisa then masks else .done 40 value

end Lemma.Platform.RiscV.Development.CounterPolicy
