import Lemma.Kernel.Memory.Access

/-! Bounded physical-memory SHA-256, FIPS180-4 (August2015), sections4.1.2,
4.2.2,5 and6.2. The caller owns private RAM workspace; this is no validation
token for untrusted mutable memory. No allocator, foreign runtime, device or
authentication policy lives here. An unsuccessful operation requires begin
before reuse. Digest bytes are published only by finish; a failed output write
may leave a partial output and is never success. -/
namespace Lemma.Crypto.SHA256
open Lemma.Core0.Memory
open Lemma.Kernel.Memory.Access

def contextBytes : UInt64 := 1024
def maximumUpdate : UInt64 := 4096
def maximumMessage : UInt64 := 0x4000000
def invalid : UInt8 := 248
def exhausted : UInt8 := 249
def wrongState : UInt8 := 250
private def mask : UInt64 := 0xffffffff
private def magic : UInt64 := 0x315348414d4c
-- state0..63, working64..127, schedule128..639; total640, used648,
-- pending block656..719, phase720. The remaining context is reserved.
def validSpan (address bytes : UInt64) : Bool :=
  if address < 0x80000000 then false else
  if 0x88000000 < address then false else bytes ≤ 0x88000000 - address
def separate (a an b bn : UInt64) : Bool :=
  if a ≤ b then an ≤ b-a else bn ≤ a-b
def validContext (context : UInt64) : Bool :=
  if context % 8 = 0 then validSpan context contextBytes else false
private def ror (word bits : UInt64) : UInt64 :=
  ((word >>> bits) ||| (word <<< (32-bits))) &&& mask
private def small0 (word : UInt64) : UInt64 := ror word 7 ^^^ ror word 18 ^^^ (word >>> 3)
private def small1 (word : UInt64) : UInt64 := ror word 17 ^^^ ror word 19 ^^^ (word >>> 10)
private def large0 (word : UInt64) : UInt64 := ror word 2 ^^^ ror word 13 ^^^ ror word 22
private def large1 (word : UInt64) : UInt64 := ror word 6 ^^^ ror word 11 ^^^ ror word 25
private def choose (a b c : UInt64) : UInt64 := (a &&& b) ^^^ ((~~~a) &&& c)
private def majority (a b c : UInt64) : UInt64 := (a &&& b) ^^^ (a &&& c) ^^^ (b &&& c)
private def initial (i : UInt64) : UInt64 :=
  if i = 0 then 0x6a09e667 else if i = 1 then 0xbb67ae85 else
  if i = 2 then 0x3c6ef372 else if i = 3 then 0xa54ff53a else
  if i = 4 then 0x510e527f else if i = 5 then 0x9b05688c else
  if i = 6 then 0x1f83d9ab else 0x5be0cd19
private def constant (i : UInt64) : UInt64 :=
  if i = 0 then 0x428a2f98 else if i = 1 then 0x71374491 else
  if i = 2 then 0xb5c0fbcf else if i = 3 then 0xe9b5dba5 else
  if i = 4 then 0x3956c25b else if i = 5 then 0x59f111f1 else
  if i = 6 then 0x923f82a4 else if i = 7 then 0xab1c5ed5 else
  if i = 8 then 0xd807aa98 else if i = 9 then 0x12835b01 else
  if i = 10 then 0x243185be else if i = 11 then 0x550c7dc3 else
  if i = 12 then 0x72be5d74 else if i = 13 then 0x80deb1fe else
  if i = 14 then 0x9bdc06a7 else if i = 15 then 0xc19bf174 else
  if i = 16 then 0xe49b69c1 else if i = 17 then 0xefbe4786 else
  if i = 18 then 0x0fc19dc6 else if i = 19 then 0x240ca1cc else
  if i = 20 then 0x2de92c6f else if i = 21 then 0x4a7484aa else
  if i = 22 then 0x5cb0a9dc else if i = 23 then 0x76f988da else
  if i = 24 then 0x983e5152 else if i = 25 then 0xa831c66d else
  if i = 26 then 0xb00327c8 else if i = 27 then 0xbf597fc7 else
  if i = 28 then 0xc6e00bf3 else if i = 29 then 0xd5a79147 else
  if i = 30 then 0x06ca6351 else if i = 31 then 0x14292967 else
  if i = 32 then 0x27b70a85 else if i = 33 then 0x2e1b2138 else
  if i = 34 then 0x4d2c6dfc else if i = 35 then 0x53380d13 else
  if i = 36 then 0x650a7354 else if i = 37 then 0x766a0abb else
  if i = 38 then 0x81c2c92e else if i = 39 then 0x92722c85 else
  if i = 40 then 0xa2bfe8a1 else if i = 41 then 0xa81a664b else
  if i = 42 then 0xc24b8b70 else if i = 43 then 0xc76c51a3 else
  if i = 44 then 0xd192e819 else if i = 45 then 0xd6990624 else
  if i = 46 then 0xf40e3585 else if i = 47 then 0x106aa070 else
  if i = 48 then 0x19a4c116 else if i = 49 then 0x1e376c08 else
  if i = 50 then 0x2748774c else if i = 51 then 0x34b0bcb5 else
  if i = 52 then 0x391c0cb3 else if i = 53 then 0x4ed8aa4a else
  if i = 54 then 0x5b9cca4f else if i = 55 then 0x682e6ff3 else
  if i = 56 then 0x748f82ee else if i = 57 then 0x78a5636f else
  if i = 58 then 0x84c87814 else if i = 59 then 0x8cc70208 else
  if i = 60 then 0x90befffa else if i = 61 then 0xa4506ceb else
  if i = 62 then 0xbef9a3f7 else 0xc67178f2

private def initializeStep (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (write64 (context+i.toUInt64*8) (initial i.toUInt64)) fun s _ => .done s acc
def «begin» (context : UInt64) : Action :=
  if validContext context then
  .bind (write64 (context+720) 0) fun s _ => if s = 0 then
  .boundedFoldU64 8 initializeStep 8 0 context 0 0 0 fun s _ => if s = 0 then
  .bind (write64 (context+640) 0) fun s _ => if s = 0 then
  .bind (write64 (context+648) 0) fun s _ => if s = 0 then
  write64 (context+720) magic else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0
private def readBE32 (address : UInt64) : Action :=
  .bind (read8 address) fun s a => if s = 0 then
  .bind (read8 (address+1)) fun s b => if s = 0 then
  .bind (read8 (address+2)) fun s c => if s = 0 then
  .bind (read8 (address+3)) fun s d => if s = 0 then
  .done 0 ((a <<< 24) ||| (b <<< 16) ||| (c <<< 8) ||| d)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def scheduleStep (i _ : UInt32) (acc context block _ _ : UInt64) : Action :=
  let t := i.toUInt64
  .bind (if t < 16 then readBE32 (block+t*4) else
    .bind (read64 (context+128+(t-2)*8)) fun s a => if s = 0 then
    .bind (read64 (context+128+(t-7)*8)) fun s b => if s = 0 then
    .bind (read64 (context+128+(t-15)*8)) fun s c => if s = 0 then
    .bind (read64 (context+128+(t-16)*8)) fun s d => if s = 0 then
    .done 0 ((small1 a+b+small0 c+d) &&& mask)
    else .done s 0 else .done s 0 else .done s 0 else .done s 0)
    fun s word => if s = 0 then
  .bind (write64 (context+128+t*8) word) fun s _ => .done s acc else .done s 0
private def copyWorking (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (read64 (context+i.toUInt64*8)) fun s word => if s = 0 then
  .bind (write64 (context+64+i.toUInt64*8) word) fun s _ => .done s acc else .done s 0
private def roundStep (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (read64 (context+64)) fun s a => if s = 0 then
  .bind (read64 (context+72)) fun s b => if s = 0 then
  .bind (read64 (context+80)) fun s c => if s = 0 then
  .bind (read64 (context+88)) fun s d => if s = 0 then
  .bind (read64 (context+96)) fun s e => if s = 0 then
  .bind (read64 (context+104)) fun s f => if s = 0 then
  .bind (read64 (context+112)) fun s g => if s = 0 then
  .bind (read64 (context+120)) fun s h => if s = 0 then
  .bind (read64 (context+128+i.toUInt64*8)) fun s word => if s = 0 then
  let t1 := (h+large1 e+choose e f g+constant i.toUInt64+word) &&& mask
  let t2 := (large0 a+majority a b c) &&& mask
  .bind (write64 (context+64) ((t1+t2) &&& mask)) fun s _ => if s = 0 then
  .bind (write64 (context+72) a) fun s _ => if s = 0 then
  .bind (write64 (context+80) b) fun s _ => if s = 0 then
  .bind (write64 (context+88) c) fun s _ => if s = 0 then
  .bind (write64 (context+96) ((d+t1) &&& mask)) fun s _ => if s = 0 then
  .bind (write64 (context+104) e) fun s _ => if s = 0 then
  .bind (write64 (context+112) f) fun s _ => if s = 0 then
  .bind (write64 (context+120) g) fun s _ => .done s acc
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def addWorking (i _ : UInt32) (acc context _ _ _ : UInt64) : Action :=
  .bind (read64 (context+i.toUInt64*8)) fun s old => if s = 0 then
  .bind (read64 (context+64+i.toUInt64*8)) fun s word => if s = 0 then
  .bind (write64 (context+i.toUInt64*8) ((old+word) &&& mask)) fun s _ => .done s acc
  else .done s 0 else .done s 0
private def compress (context block : UInt64) : Action :=
  .boundedFoldU64 64 scheduleStep 64 0 context block 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 8 copyWorking 8 0 context 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 64 roundStep 64 0 context 0 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 8 addWorking 8 0 context 0 0 0 fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0
private def copyBytesStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (read8 (source+i.toUInt64)) fun s byte => if s = 0 then
  .bind (write8 (target+i.toUInt64) byte) fun s _ => .done s acc else .done s 0
private def blocksStep (i _ : UInt32) (acc context source _ _ : UInt64) : Action :=
  .bind (compress context (source+i.toUInt64*64)) fun s _ => .done s acc
private def updateRest (context source bytes : UInt64) : Action :=
  .boundedFoldU64 64 blocksStep (bytes/64).toUInt32 0 context source 0 0 fun s _ => if s = 0 then
  .boundedFoldU64 64 copyBytesStep (bytes%64).toUInt32 0 (source+bytes/64*64) (context+656) 0 0 fun s _ =>
  if s = 0 then write64 (context+648) (bytes%64) else .done s 0 else .done s 0
/-- At most4096 bytes per call; split updates preserve ordinary SHA padding.
Range/alias checks precede context reads; total/used/phase checks precede data.
Private workspace may be partially changed on an I/O fault. -/
def update (context source bytes : UInt64) : Action :=
  if validContext context then if validSpan source bytes then
  if separate context contextBytes source bytes then
  if maximumUpdate < bytes then .done exhausted 0 else
  .bind (read64 (context+720)) fun s phase => if s = 0 then
  .bind (read64 (context+640)) fun s total => if s = 0 then
  .bind (read64 (context+648)) fun s used => if s = 0 then
  if phase = magic then if used < 64 then if used = total%64 then
  if total ≤ maximumMessage then if bytes ≤ maximumMessage-total then
  .bind (write64 (context+720) 0) fun s _ => if s = 0 then
  let take := if bytes < 64-used then bytes else 64-used
  .bind (if used = 0 then updateRest context source bytes else
    .boundedFoldU64 64 copyBytesStep take.toUInt32 0 source (context+656+used) 0 0 fun s _ => if s = 0 then
    if used+take = 64 then
      .bind (compress context (context+656)) fun s _ => if s = 0 then
      updateRest context (source+take) (bytes-take) else .done s 0
    else write64 (context+648) (used+take)
    else .done s 0) fun s _ => if s = 0 then
  .bind (write64 (context+640) (total+bytes)) fun s _ => if s = 0 then
  write64 (context+720) magic else .done s 0 else .done s 0
  else .done s 0
  else .done exhausted 0 else .done wrongState 0
  else .done wrongState 0 else .done wrongState 0 else .done wrongState 0
  else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0
private def zeroStep (i _ : UInt32) (acc target _ _ _ : UInt64) : Action :=
  .bind (write8 (target+i.toUInt64) 0) fun s _ => .done s acc
private def lengthStep (i _ : UInt32) (acc target bits _ _ : UInt64) : Action :=
  .bind (write8 (target+i.toUInt64) ((bits >>> ((7-i.toUInt64)*8)) &&& 255)) fun s _ => .done s acc
private def outputStep (i _ : UInt32) (acc context output _ _ : UInt64) : Action :=
  let n := i.toUInt64
  .bind (read64 (context+n/4*8)) fun s word => if s = 0 then
  .bind (write8 (output+n) ((word >>> ((3-n%4)*8)) &&& 255)) fun s _ => .done s acc else .done s 0
def finish (context output : UInt64) : Action :=
  if validContext context then if validSpan output 32 then
  if separate context contextBytes output 32 then
  .bind (read64 (context+720)) fun s phase => if s = 0 then
  .bind (read64 (context+640)) fun s total => if s = 0 then
  .bind (read64 (context+648)) fun s used => if s = 0 then
  if phase = magic then if total ≤ maximumMessage then if used < 64 then if used = total%64 then
  -- Poison the stream before any padding/output mutation; begin is required
  -- after failure and repeated finish cannot append another padding block.
  .bind (write64 (context+720) 0) fun s _ => if s = 0 then
  .bind (write8 (context+656+used) 128) fun s _ => if s = 0 then
  .boundedFoldU64 64 zeroStep (63-used).toUInt32 0 (context+657+used) 0 0 0 fun s _ => if s = 0 then
  .bind (if used < 56 then .done 0 0 else
    .bind (compress context (context+656)) fun s _ => if s = 0 then
    .boundedFoldU64 64 zeroStep 64 0 (context+656) 0 0 0 fun s _ => .done s 0 else .done s 0)
    fun s _ => if s = 0 then
  .boundedFoldU64 8 lengthStep 8 0 (context+712) (total*8) 0 0 fun s _ => if s = 0 then
  .bind (compress context (context+656)) fun s _ => if s = 0 then
  .boundedFoldU64 32 outputStep 32 0 context output 0 0 fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done wrongState 0 else .done wrongState 0 else .done wrongState 0 else .done wrongState 0
  else .done s 0 else .done s 0 else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0
def hash (context source bytes output : UInt64) : Action :=
  if maximumUpdate < bytes then .done exhausted 0 else
  if validContext context then if validSpan source bytes then if validSpan output 32 then
  if separate context contextBytes source bytes then if separate context contextBytes output 32 then
  .bind («begin» context) fun s _ => if s = 0 then
  .bind (update context source bytes) fun s _ => if s = 0 then finish context output else .done s 0 else .done s 0
  else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0 else .done invalid 0

end Lemma.Crypto.SHA256
