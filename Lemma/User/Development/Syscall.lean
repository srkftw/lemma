import Lemma.User.Entry
import Lemma.User.Syscall
import Lemma.User.Memory

/-! Quarantined ABI-v1 user corpus. Every control record is built by compiled
U-mode code and sent in one ordinary console syscall. Binary inputs arrive at
runtime; no kernel test dispatcher or privileged probe implements these cases. -/
namespace Lemma.User.Development.Syscall
open Lemma.Core0.Memory

def failure : UInt8 := 95
def packetAddress : UInt64 := 0x20200
def inputAddress : UInt64 := 0x20300
def acknowledgeAddress : UInt64 := 0x20400
def pageA : UInt64 := 0x40000
def pageB : UInt64 := 0x41000
def crossing : UInt64 := 0x40ff8
def failed (s : UInt8) : Bool := if s = 0 then false else true

def hexDigit (n : UInt64) : UInt64 :=
  if n < 10 then n + 48 else n + 87

def hexStep (i _ : UInt32) (acc address word _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 (address + i.toUInt64)
    (hexDigit ((word >>> (60 - i.toUInt64 * 4)) &&& 15))) fun s _ =>
  .done s (acc + 1)

def spaceWord (address word : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 address 32) fun s _ =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 16 hexStep 16 0 (address + 1) word 0 0 fun s count =>
  if failed s = true then .done s 0 else
  if count = 16 then .done 0 0 else .done failure 0

def record (tag caseId status value nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 packetAddress 75) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Memory.write8 (packetAddress + 1) 49) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord (packetAddress + 2) tag) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord (packetAddress + 19) caseId) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord (packetAddress + 36) status) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord (packetAddress + 53) value) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (spaceWord (packetAddress + 70) nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Memory.write8 (packetAddress + 87) 10) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.consoleWrite packetAddress 88) fun s count =>
  if failed s = true then .done s 0 else
  if count = 88 then .done 0 0 else .done failure count

def result (caseId : UInt64) (status : UInt8) (value nonce : UInt64) : Action :=
  record 0xe1 caseId status.toUInt64 value nonce

def observe (caseId address nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.read64 address) fun s value =>
  record 0xe5 caseId s.toUInt64 value nonce

def payloadByte (index nonce : UInt64) : UInt64 :=
  if index = 0 then 0 else if index = 1 then 255 else
  ((nonce >>> (((index - 2) % 8) * 8)) &&& 255) ^^^ ((index * 17) &&& 255)

def fillStep (i _ : UInt32) (acc address nonce _ _ : UInt64) : Action :=
  .bind (Lemma.User.Memory.write8 (address + i.toUInt64) (payloadByte i.toUInt64 nonce)) fun s _ =>
  .done s (acc + 1)

def fill (address length nonce : UInt64) : Action :=
  .boundedFoldU64 256 fillStep length.toUInt32 0 address nonce 0 0 fun s count =>
  if failed s = true then .done s 0 else
  if count = length then .done 0 0 else .done failure count

/-- Retry only an empty nonblocking read. The reported value is the actual
count from one successful syscall, never a sum of partial reads. The hardware
time deadline and the fold budget both bound a missing host input. -/
def receiveStep (_ _ : UInt32) (_ pointer length deadline _ : UInt64) : Action :=
  .bind Lemma.User.Syscall.time fun s now =>
  if failed s = true then .done s 0 else
  if deadline ≤ now then .done failure 0 else
  .bind (Lemma.User.Syscall.consoleRead pointer length) fun s count =>
  if s = Lemma.User.ABI.noByte then
    if count = 0 then .done 0 0 else .done failure count
  else
  if failed s = true then
    -- The fold's private success-stop marker must never reinterpret a
    -- nonzero syscall status as a successful receive.
    if s = Status.iterationStop then .done failure count else .done s count
  else
  .done Status.iterationStop count

def receiveOnce (pointer length : UInt64) : Action :=
  .bind Lemma.User.Syscall.time fun s now =>
  if failed s = true then .done s 0 else
  .boundedFoldU64 100000 receiveStep 100000 0 pointer length (now + 10000000) 0 fun s count =>
  if s = Status.iterationStop then .done 0 count else
  if s = 0 then .done failure count else .done s count

/-- Complete the independent 16-byte input after the first actual crossing
read. Each successful syscall is logged with its own count; only the enclosing
copy accumulator is a total. An empty read is retried solely by receiveOnce. -/
def refillStep (i _ : UInt32) (acc pointer nonce _ _ : UInt64) : Action :=
  if acc = 16 then .done Status.iterationStop acc else
  if 16 < acc then .done failure acc else
  .bind (receiveOnce (pointer + acc) (16 - acc)) fun s count =>
  .bind (record 0xe4 (430 + i.toUInt64) s.toUInt64 count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  if failed s = true then .done s count else
  if count = 0 then .done failure count else
  if 16 - acc < count then .done failure count else
  let total := acc + count
  if total = 16 then .done Status.iterationStop total else .done 0 total

def completeInput (pointer firstCount nonce : UInt64) : Action :=
  if firstCount < 9 then .done failure firstCount else
  if 16 < firstCount then .done failure firstCount else
  if firstCount = 16 then .done 0 firstCount else
  .boundedFoldU64 7 refillStep 7 firstCount pointer nonce 0 0 fun s total =>
  if (if s = 0 then true else if s = Status.iterationStop then true else false) = true then
    if total = 16 then .done 0 total else .done failure total
  else .done s total

def scalarCases (nonce : UInt64) : Action :=
  .bind (Lemma.User.Syscall.time) fun s value =>
  .bind (result 2 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.call 17 0 0 0 0 0) fun s value =>
  .bind (result 3 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.yield) fun s value =>
  .bind (result 4 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.sleep 0) fun s value =>
  .bind (result 5 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.sleep 999) fun s value =>
  .bind (result 6 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.sleep 10000001) fun s value =>
  .bind (result 7 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.time) fun s value =>
  .bind (result 8 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.sleep 1000) fun s value =>
  .bind (result 9 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.time) fun s value =>
  .bind (result 10 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.time) fun s value =>
  .bind (result 11 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.sleep 1000000) fun s value =>
  .bind (result 12 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.time) fun s value =>
  .bind (result 13 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .done 0 0

def allocationCases (nonce : UInt64) : Action :=
  .bind (Lemma.User.Syscall.allocatePage pageA) fun s value =>
  .bind (result 20 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.allocatePage pageA) fun s value =>
  .bind (result 21 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.allocatePage (pageA + 1)) fun s value =>
  .bind (result 22 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.allocatePage 0x30000) fun s value =>
  .bind (result 23 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.allocatePage 0x100000) fun s value =>
  .bind (result 24 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.call Lemma.User.ABI.allocatePages 0x42000 2 0 0 0) fun s value =>
  .bind (result 25 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.releasePage 0x43000) fun s value =>
  .bind (result 26 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.allocatePage pageB) fun s value =>
  .bind (result 27 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (observe 50 pageA nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Memory.write64 pageA nonce) fun s _ =>
  if failed s = true then .done s 0 else
  observe 51 pageA nonce

def consoleOutputCases (nonce : UInt64) : Action :=
  .bind (fill crossing 16 nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (record 0xe2 40 0 16 nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.consoleWrite crossing 16) fun s count =>
  .bind (result 40 s count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (fill inputAddress 256 nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (record 0xe2 62 0 256 nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.consoleWrite inputAddress 256) fun s count =>
  .bind (result 62 s count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.releasePage pageB) fun s value =>
  .bind (result 28 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleWrite crossing 16) fun s value =>
  .bind (result 41 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead inputAddress 16) fun s value =>
  result 61 s value nonce

def consoleInputCases (nonce : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 crossing (nonce ^^^ 0x0123456789abcdef)) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (record 0xe3 42 0 17 nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (receiveOnce acknowledgeAddress 1) fun s count =>
  .bind (record 0xe4 420 s.toUInt64 count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  if failed s = true then .done s 0 else
  if (if count = 1 then false else true) = true then .done failure count else
  .bind (Lemma.User.Memory.read8 acknowledgeAddress) fun s byte =>
  if failed s = true then .done s 0 else
  if (if byte = 0xa5 then false else true) = true then .done failure byte else
  .bind (Lemma.User.Syscall.sleep 1000000) fun s deadline =>
  .bind (result 421 s deadline nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead crossing 16) fun s count =>
  .bind (result 42 s count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (observe 42 crossing nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.allocatePage pageB) fun s value =>
  .bind (result 63 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  if failed s = true then .done s 0 else
  .bind (receiveOnce crossing 32) fun s count =>
  .bind (record 0xe4 43 s.toUInt64 count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  if failed s = true then .done s 0 else
  if count < 9 then .done failure count else
  if 16 < count then .done failure count else
  .bind (completeInput crossing count nonce) fun s total =>
  if failed s = true then .done s 0 else
  if (if total = 16 then false else true) = true then .done failure total else
  .bind (record 0xe2 44 0 16 nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.consoleWrite crossing 16) fun s count =>
  .bind (result 44 s count nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.releasePage pageB) fun s value =>
  result 64 s value nonce

def boundaryCases (nonce : UInt64) : Action :=
  .bind (Lemma.User.Syscall.consoleWrite 0xffffffffffffffff 0) fun s value =>
  .bind (result 45 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead 0xffffffffffffffff 0) fun s value =>
  .bind (result 46 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleWrite inputAddress 257) fun s value =>
  .bind (result 47 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead inputAddress 257) fun s value =>
  .bind (result 48 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleWrite 0xfffffffffffffff8 16) fun s value =>
  .bind (result 49 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead 0xfffffffffffffff8 16) fun s value =>
  .bind (result 50 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleWrite 0x8000000000000040 1) fun s value =>
  .bind (result 51 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead 0x8000000000000040 1) fun s value =>
  .bind (result 52 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead 0x10000 16) fun s value =>
  .bind (result 53 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleWrite 0x30000 16) fun s value =>
  .bind (result 54 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead 0x30000 16) fun s value =>
  .bind (result 55 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleWrite 0x3fffb000 16) fun s value =>
  .bind (result 56 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.consoleRead 0x3fffb000 16) fun s value =>
  .bind (result 57 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.call Lemma.User.ABI.console 2 inputAddress 16 0 0) fun s value =>
  .bind (result 58 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.call Lemma.User.ABI.identity 0 0 0 0 1) fun s value =>
  .bind (result 59 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .done 0 0

def releaseCases (nonce : UInt64) : Action :=
  .bind (Lemma.User.Syscall.releasePage pageB) fun s value =>
  .bind (result 29 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.releasePage pageA) fun s value =>
  .bind (result 30 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.allocatePage pageA) fun s value =>
  .bind (result 31 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (observe 52 pageA nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.call Lemma.User.ABI.releasePages pageA 2 0 0 0) fun s value =>
  .bind (result 33 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.releasePage pageA) fun s value =>
  .bind (result 32 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (Lemma.User.Syscall.identity) fun s value =>
  .bind (result 60 s value nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .done 0 0

/-- The launch argument is an ordinary runtime nonce. Initial data is checked
through the maintained entry; subsequent operations use reusable user APIs.
Successful completion exits explicitly from the ordinary syscall bridge. -/
def main (nonce : UInt64) : Action :=
  .bind (Lemma.User.Entry.main nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind Lemma.User.Syscall.identity fun s identity =>
  .bind (record 0xe0 Lemma.User.ABI.version s.toUInt64 identity nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (result 1 s identity nonce) fun logged _ =>
  if failed logged = true then .done logged 0 else
  .bind (scalarCases nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (allocationCases nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (consoleOutputCases nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (consoleInputCases nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (boundaryCases nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (releaseCases nonce) fun s _ =>
  if failed s = true then .done s 0 else
  let digest := Lemma.User.Entry.mix nonce
  .bind (Lemma.User.Memory.write64 0x20000 digest) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (record 0xee 0 0 digest nonce) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Lemma.User.Syscall.exit ((nonce &&& 15) + 1)) fun _ _ =>
  .done failure 0

end Lemma.User.Development.Syscall
