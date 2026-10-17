import Lemma.Core0.Memory

/-! Actual CSR permissions and trap qualification policy. Only the individual
hardware accesses and fixed privilege/context transport are generated primitives.
All corpus selection, records, expectations, recovery and verdicts are checked
Lean Actions. The complete record buffer is cleared by the guest itself. -/
namespace Lemma.Platform.RiscV.Development.CounterSuPolicy
open Lemma.Core0.Memory

def base : UInt64 := 0x80100000
def rows : UInt64 := 0x80100100
def context : UInt64 := 0x80108000
def trapFrame : UInt64 := 0x80109ee0
def cycleSentinel : UInt64 := 0x1122334455667788
def retiredSentinel : UInt64 := 0x2233445566778899
def startMagic : UInt64 := 0x4353554449414701
def doneMagic : UInt64 := 0x435355444f4e4501
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

def caseMode (n : UInt64) : UInt64 :=
  if n < 384 then (n / 3) % 2 else
  if n < 390 then (n-384)/3 else
  if n < 394 then (n-390)/2 else
  if n < 398 then (n-394)/2 else 3
def caseOp (n : UInt64) : UInt64 :=
  if n < 384 then n%3 else
  if n < 390 then (n-384)%3+3 else
  if n < 394 then (n-390)%2+6 else
  if n < 398 then (n-394)%2+8 else
  if n < 401 then n-398 else n-401+3
def caseM (n : UInt64) : UInt64 := if n < 384 then n/6/8 else if n < 398 then 7 else 0
def caseS (n : UInt64) : UInt64 := if n < 384 then (n/6)%8 else if n < 398 then 7 else 0
def allowed (mode op m s : UInt64) : Bool :=
  if op < 3 then
    if mode = 3 then true else
    if ((m >>> op) &&& 1) = 0 then false else
    if mode = 1 then true else ((s >>> op) &&& 1) = 1
  else if op < 8 then false else if mode = 0 then false else true
def expectedCause (mode op m s : UInt64) : UInt64 :=
  if allowed mode op m s = false then 2 else if mode = 3 then 0 else mode+8
def expectedInstruction (op : UInt64) : UInt64 :=
  let csr := if op < 3 then 0xc00+op else if op < 6 then 0xc00+op-3 else if op < 8 then 0xb00 else 0x106
  if ((0x2b8 >>> op) &&& 1) = 1 then csr*1048576+0x51073 else csr*1048576+0x2573
def validResult (op value permission : UInt64) : Bool :=
  if permission = 0 then value = 0 else
  if op = 0 then value = cycleSentinel else
  if op = 1 then 0 < value else
  if op = 2 then value = retiredSentinel else
  if op = 8 then value = 7 else value = 0
def validPC (pc : UInt64) : Bool :=
  if pc < 0x80000000 then false else if 0x80010000 ≤ pc then false else if pc%4 = 0 then true else false
def both (a b : Bool) : Bool := if a = true then b else false

/-- Called as ordinary compiled code in each actual selected privilege. -/
def probe (op value : UInt64) : Action :=
  if op = 0 then .platform .readCounterCycle 0 0 0 0 0 0 fun s v => .done s v else
  if op = 1 then .platform .readCounterTime 0 0 0 0 0 0 fun s v => .done s v else
  if op = 2 then .platform .readCounterRetired 0 0 0 0 0 0 fun s v => .done s v else
  if op = 3 then .platform .attemptWriteCounterCycle value 0 0 0 0 0 fun s v => .done s v else
  if op = 4 then .platform .attemptWriteCounterTime value 0 0 0 0 0 fun s v => .done s v else
  if op = 5 then .platform .attemptWriteCounterRetired value 0 0 0 0 0 fun s v => .done s v else
  if op = 6 then cycle else
  if op = 7 then writeCycle value else
  if op = 8 then sEnable else
  if op = 9 then writeSEnable value else .done 60 op

/-- Actual context/CSR observations. Recovery follows only a captured illegal
instruction or the fixed lower-mode routine's real ECALL. -/
def trap (frame cause tval : UInt64) : Action :=
  if (same frame (trapFrame)) = false then .done 61 frame else
  .bind (header 2) fun s row => if failed s = true then .done s 0 else
  if row < rows then .done 62 row else
  if rows+404*80 ≤ row then .done 62 row else
  if (same ((row-rows)%80) (0)) = false then .done 62 row else
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

def checkCase (index result : UInt64) : Action :=
  let row := rows+index*80
  let mode := caseMode index
  let op := caseOp index
  let permission := if allowed mode op (caseM index) (caseS index) = true then 1 else 0
  .bind (write (row+40) result) fun s _ => if failed s = true then .done s 0 else
  .bind (read (row+48)) fun s cause => if failed s = true then .done s 0 else
  .bind (read (row+56)) fun s tval => if failed s = true then .done s 0 else
  .bind (read (row+64)) fun s pc => if failed s = true then .done s 0 else
  .bind (read (row+72)) fun s origin => if failed s = true then .done s 0 else
  .bind cycle fun s c => if failed s = true then .done s 0 else
  .bind retired fun s r => if failed s = true then .done s 0 else
  .bind inhibit fun s inhibited => if failed s = true then .done s 0 else
  let instructionOK := if cause = 2 then both (same tval (expectedInstruction op)) (validPC pc) else
    if cause = 0 then both (same tval (0)) (same pc (0)) else both (same tval (0)) (validPC pc)
  let good := if (same cause (expectedCause mode op (caseM index) (caseS index))) = false then false else
    if (same origin (mode)) = false then false else if instructionOK = false then false else
    if validResult op result permission = false then false else if (same c (cycleSentinel)) = false then false else
    if (same r (retiredSentinel)) = false then false else if inhibited = 5 then true else false
  .bind (header 18) fun s errors => if failed s = true then .done s 0 else
  .bind (emit 18 (if good = true then errors else errors+1)) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 3 (index+1)) fun s _ => .done s (index+1)

def eachCase (_ _ : UInt32) (index _ _ _ _ : UInt64) : Action :=
  let row := rows+index*80
  let mode := caseMode index
  let op := caseOp index
  .bind (writeMEnable (caseM index)) fun s _ => if failed s = true then .done s 0 else
  .bind (writeSEnable (caseS index)) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 2 row) fun s _ => if failed s = true then .done s 0 else
  .bind (write row index) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+8) mode) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+16) op) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+24) (caseM index)) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+32) (caseS index)) fun s _ => if failed s = true then .done s 0 else
  .bind (write (row+72) mode) fun s _ => if failed s = true then .done s 0 else
  if mode = 0 then
    .platform .counterEnterUser op 0xffffffffffffffff 0 0 0 0 fun s v =>
      if failed s = true then .done s 0 else checkCase index v
  else if mode = 1 then
    .platform .counterEnterSupervisor op 0xffffffffffffffff 0 0 0 0 fun s v =>
      if failed s = true then .done s 0 else checkCase index v
  else .bind (probe op 0xffffffffffffffff) fun s v =>
    if failed s = true then .done s 0 else checkCase index v

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
  .bind (writeSEnable 0xffffffffffffffff) fun s _ => if failed s = true then .done s 0 else
  .bind sEnable fun s sc => if failed s = true then .done s 0 else
  .bind (emit 16 sc) fun s _ => if failed s = true then .done s 0 else
  .bind (writeMEnable 0xffffffffffffffff) fun s _ => if failed s = true then .done s 0 else
  .bind mEnable fun s mc => if failed s = true then .done s 0 else
  .bind (emit 17 mc) fun s _ => if failed s = true then .done s 0 else
  .bind (emit 18 (if (same sc (7)) = false then 1 else if (same mc (7)) = false then 1 else if i = 5 then 0 else 1)) fun s _ => if failed s = true then .done s 0 else
  .bind time fun s t => if failed s = true then .done s 0 else
  .bind (emit 10 t) fun s _ => if failed s = true then .done s 0 else
  .bind (.boundedFoldU64 404 eachCase 404 0 0 0 0 0 fun s v => .done s v) fun s _ => if failed s = true then .done s 0 else finish

end Lemma.Platform.RiscV.Development.CounterSuPolicy
