import Lemma.Core0.Memory

/-! Actual CSR permissions and trap qualification policy. Only the individual
hardware accesses and fixed privilege/context transport are generated primitives.
All corpus selection, records, expectations, recovery and verdicts are checked
Lean Actions. The complete record buffer is cleared by the guest itself. -/
namespace Lemma.Platform.RiscV.Development.CounterSuProgressPolicy
open Lemma.Core0.Memory

def base : UInt64 := 0x80100000
def rows : UInt64 := 0x80100100
def context : UInt64 := 0x80108000
def trapFrame : UInt64 := 0x80109ee0
def cycleSentinel : UInt64 := 0x1122334455667788
def retiredSentinel : UInt64 := 0x2233445566778899
def startMagic : UInt64 := 0x4353504449414701
def doneMagic : UInt64 := 0x435350444f4e4501
def failed (s : UInt8) : Bool := if s = 0 then false else true
def read (p : UInt64) : Action := .platform .physicalRead64 p 0 0 0 0 0 fun s v => .done s v
def write (p v : UInt64) : Action := .platform .physicalWrite64 p v 0 0 0 0 fun s r => .done s r
def header (i : UInt64) : Action := read (base+i*8)
def emit (i v : UInt64) : Action := write (base+i*8) v
def cycle : Action := .platform .readMachineCycle 0 0 0 0 0 0 fun s v => .done s v
def retired : Action := .platform .readMachineRetired 0 0 0 0 0 0 fun s v => .done s v
def inhibit : Action := .platform .readMachineInhibit 0 0 0 0 0 0 fun s v => .done s v
def time : Action := .platform .readTime 0 0 0 0 0 0 fun s v => .done s v
def writeInhibit (v : UInt64) : Action := .platform .writeMachineInhibit v 0 0 0 0 0 fun s r => .done s r
def writeCycle (v : UInt64) : Action := .platform .writeMachineCycle v 0 0 0 0 0 fun s r => .done s r
def writeRetired (v : UInt64) : Action := .platform .writeMachineRetired v 0 0 0 0 0 fun s r => .done s r
def writeMEnable (v : UInt64) : Action := .platform .writeMachineCounterEnable v 0 0 0 0 0 fun s r => .done s r
def mEnable : Action := .platform .readMachineCounterEnable 0 0 0 0 0 0 fun s r => .done s r
def writeSEnable (v : UInt64) : Action := .platform .writeSupervisorCounterEnable v 0 0 0 0 0 fun s r => .done s r
def sEnable : Action := .platform .readSupervisorCounterEnable 0 0 0 0 0 0 fun s r => .done s r

def same (a b : UInt64) : Bool := if a = b then true else false
def less (a b : UInt64) : Bool := if a < b then true else false

def caseMask (n : UInt64) : UInt64 :=
  let group := n/7
  if group < 8 then group else 0xfffffffffffffff8+group-8
def caseMode (n : UInt64) : UInt64 := if n%7 < 4 then 1 else 0
def caseOp (n : UInt64) : UInt64 := if n%7 = 0 then 10 else (n%7-1)%3
def expectedMask (n : UInt64) : UInt64 := (n/7)%8
def expectedInhibit (n : UInt64) : UInt64 := if n/7 < 8 then 5 else 0
def allowed (n : UInt64) : Bool :=
  if caseMode n = 1 then true else ((expectedMask n >>> caseOp n) &&& 1) = 1
def both (a b : Bool) : Bool := if a = true then b else false
def ordered (a b : UInt64) : Bool := if a ≤ b then true else false
def between (lo v hi : UInt64) : Bool := both (ordered lo v) (ordered v hi)
def validPC (pc : UInt64) : Bool :=
  if pc < 0x80000000 then false else if 0x80010000 ≤ pc then false else pc%4 = 0
def expectedInstruction (op : UInt64) : UInt64 := (0xc00+op)*1048576+0x2573

/-- The S-owned WARL write is read back in the same lower-mode routine. M does
not overwrite scounteren before the following S and U permission observations. -/
def probe (op value : UInt64) : Action :=
  if op = 0 then .platform .readCounterCycle 0 0 0 0 0 0 fun s v => .done s v else
  if op = 1 then .platform .readCounterTime 0 0 0 0 0 0 fun s v => .done s v else
  if op = 2 then .platform .readCounterRetired 0 0 0 0 0 0 fun s v => .done s v else
  if op = 10 then .bind (writeSEnable value) fun s _ =>
    if failed s = true then .done s 0 else sEnable
  else .done 60 op

/-- Actual context/CSR observations. Recovery follows only a captured illegal
instruction or the fixed lower-mode routine's real ECALL. -/
def trap (frame cause tval : UInt64) : Action :=
  if (same frame (trapFrame)) = false then .done 61 frame else
  .bind (header 2) fun s row => if failed s = true then .done s 0 else
  if row < rows then .done 62 row else
  if rows+112*144 ≤ row then .done 62 row else
  if (same ((row-rows)%144) (0)) = false then .done 62 row else
  .bind (read (frame+256)) fun s pc => if failed s = true then .done s 0 else
  .bind (read (frame+264)) fun s status => if failed s = true then .done s 0 else
  .bind (read (row+8)) fun s requested => if failed s = true then .done s 0 else
  let origin := (status >>> 11) &&& 3
  if (same origin (requested)) = false then .done 63 origin else
  .bind (header 19) fun s count => if failed s = true then .done s 0 else
  .bind (emit 19 (count+1)) fun s _ => if failed s = true then .done s 0 else
  .bind (read (row+48)) fun s previous => if failed s = true then .done s 0 else
  if cause = 2 then
    if (same previous (0)) = false then .done 64 previous else
    .bind (write (row+48) cause) fun s _ => if failed s = true then .done s 0 else
    .bind (write (row+56) tval) fun s _ => if failed s = true then .done s 0 else
    .bind (write (row+64) pc) fun s _ => if failed s = true then .done s 0 else
    .bind (write (row+72) origin) fun s _ => if failed s = true then .done s 0 else
    .bind (header 5) fun s count => if failed s = true then .done s 0 else
    .bind (emit 5 (count+1)) fun s _ => if failed s = true then .done s 0 else
    .bind (write (frame+256) (pc+4)) fun s _ => .done s frame
  else if both (same cause (requested+8)) (less requested 2) = true then
    .bind (read (frame+80)) fun s resultStatus => if failed s = true then .done s 0 else
    if (same resultStatus (0)) = false then .done 65 resultStatus else
    .bind (read (frame+88)) fun s result => if failed s = true then .done s 0 else
    .bind (write (context+80) result) fun s _ => if failed s = true then .done s 0 else
    .bind (header 4) fun s count => if failed s = true then .done s 0 else
    .bind (emit 4 (count+1)) fun s _ => if failed s = true then .done s 0 else
    .bind (emit 6 cause) fun s _ => if failed s = true then .done s 0 else
    .bind (emit 7 pc) fun s _ => if failed s = true then .done s 0 else
    .bind (emit 8 tval) fun s _ => if failed s = true then .done s 0 else
    .bind (emit 9 origin) fun s _ => if failed s = true then .done s 0 else
    if previous = 0 then
      .bind (write (row+48) cause) fun s _ => if failed s = true then .done s 0 else
      .bind (write (row+56) tval) fun s _ => if failed s = true then .done s 0 else
      .bind (write (row+64) pc) fun s _ => if failed s = true then .done s 0 else
      .bind (write (row+72) origin) fun s _ => .done s context
    else if previous = 2 then .done 0 context else .done 66 previous
  else .done 67 cause

def clearWord (_ _ : UInt32) (index _ _ _ _ : UInt64) : Action :=
  .bind (write (base+index*8) 0) fun s _ => .done s (index+1)

def checkCase (index result preCycle preRetired preTime : UInt64) : Action :=
  let row := rows+index*144
  let mode := caseMode index
  let op := caseOp index
  .bind (write (row+40) result) fun s _ => if failed s = true then .done s 0 else
  .bind (read (row+48)) fun s cause => if failed s = true then .done s 0 else
  .bind (read (row+56)) fun s tval => if failed s = true then .done s 0 else
  .bind (read (row+64)) fun s pc => if failed s = true then .done s 0 else
  .bind (read (row+72)) fun s origin => if failed s = true then .done s 0 else
  .bind cycle fun s c => if failed s = true then .done s 0 else
  .bind retired fun s r => if failed s = true then .done s 0 else
  .bind time fun s t => if failed s = true then .done s 0 else
  .bind inhibit fun s inhibited => if failed s = true then .done s 0 else
  .bind sEnable fun s enabled => if failed s = true then .done s 0 else
  .bind (write (row+80) preCycle) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+88) c) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+96) preRetired) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+104) r) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+112) preTime) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+120) t) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+128) enabled) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+136) inhibited) fun s _ => if failed s = true then .done s 0 else
  let expectedCause := if allowed index = true then mode+8 else 2
  let instructionOK := if cause = 2 then both (same tval (expectedInstruction op)) (validPC pc) else both (same tval (0)) (validPC pc)
  let resultOK : Bool := if allowed index = false then result = 0 else
    if op = 10 then result = expectedMask index else
    if op = 0 then between preCycle result c else
    if op = 1 then between preTime result t else between preRetired result r
  let counterOK : Bool := if expectedInhibit index = 5 then
      both (same preCycle cycleSentinel) (both (same c cycleSentinel) (both (same preRetired retiredSentinel) (same r retiredSentinel)))
    else both (less preCycle c) (less preRetired r)
  let good : Bool := if same cause (expectedCause) = false then false else if same origin (mode) = false then false else
    if instructionOK = false then false else if resultOK = false then false else if counterOK = false then false else
    if same inhibited (expectedInhibit index) = false then false else if same enabled (expectedMask index) = false then false else less preTime t
  .bind (header 18) fun s errors => if failed s = true then .done s 0 else
  .bind (emit 18 (if good = true then errors else errors+1)) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 3 (index+1)) fun s _ => .done s (index+1)

def eachCase (_ _ : UInt32) (index _ _ _ _ : UInt64) : Action :=
  let row := rows+index*144
  let mode := caseMode index
  let op := caseOp index
  .bind (writeInhibit (expectedInhibit index)) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 2 row) fun s _ => if failed s = true then .done s 0 else
  .bind (write row index) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+8) mode) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+16) op) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+24) (caseMask index)) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+32) (expectedMask index)) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+72) mode) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c => if failed s = true then .done s 0 else
  .bind retired fun s r => if failed s = true then .done s 0 else
  .bind time fun s t => if failed s = true then .done s 0 else
  if mode = 0 then
    .platform .counterEnterUser op (caseMask index) 0 0 0 0 fun s v =>
      if failed s = true then .done s 0 else checkCase index v c r t
  else .platform .counterEnterSupervisor op (caseMask index) 0 0 0 0 fun s v =>
    if failed s = true then .done s 0 else checkCase index v c r t

def finish : Action :=
  .bind time fun s t => if failed s = true then .done s 0 else
  .bind (emit 11 t) fun s _ => if failed s = true then .done s 0 else
  .bind cycle fun s c => if failed s = true then .done s 0 else
  .bind (emit 14 c) fun s _ => if failed s = true then .done s 0 else
  .bind retired fun s r => if failed s = true then .done s 0 else
  .bind (emit 15 r) fun s _ => if failed s = true then .done s 0 else
  .bind inhibit fun s i => if failed s = true then .done s 0 else
  .bind (emit 13 i) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 1 doneMagic) fun s _ => if failed s = true then .done s 0 else
  .bind (header 18) fun s errors => if failed s = true then .done s 0 else
  if errors = 0 then .done 0 0 else .done 68 errors

def main : Action :=
  .bind (.boundedFoldU64 4096 clearWord 4096 0 0 0 0 0 fun s v => .done s v) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 0 startMagic) fun s _ => if failed s = true then .done s 0 else
  .bind (writeInhibit 5) fun s _ => if failed s = true then .done s 0 else
  .bind (writeCycle cycleSentinel) fun s _ => if failed s = true then .done s 0 else
  .bind (writeRetired retiredSentinel) fun s _ => if failed s = true then .done s 0 else
  .bind inhibit fun s i => if failed s = true then .done s 0 else
  .bind (emit 12 i) fun s _ => if failed s = true then .done s 0 else
  .bind (writeMEnable 0xffffffffffffffff) fun s _ => if failed s = true then .done s 0 else
  .bind mEnable fun s mc => if failed s = true then .done s 0 else
  .bind (emit 17 mc) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 18 (if mc = 7 then 0 else 1)) fun s _ => if failed s = true then .done s 0 else
  .bind time fun s t => if failed s = true then .done s 0 else
  .bind (emit 10 t) fun s _ => if failed s = true then .done s 0 else
  .bind (.boundedFoldU64 112 eachCase 112 0 0 0 0 0 fun s v => .done s v) fun s _ => if failed s = true then .done s 0 else finish

end Lemma.Platform.RiscV.Development.CounterSuProgressPolicy
