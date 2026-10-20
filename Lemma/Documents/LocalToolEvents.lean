import Lemma.Services.Arithmetic.ProtocolV9

/-! Local exact-tool provenance uses eight rows within the existing64-row
Doc8 event arena. Prepared is write-ahead uncertainty, applied is a local edit,
never checker evidence or a remote AI presentation claim. -/
namespace Lemma.Documents.LocalToolEvents
open Lemma.Core0.Memory Lemma.User
private def read (p o : UInt64) : Action := Memory.read64 (p+o)
private def write (p o v : UInt64) : Action := Memory.write64 (p+o) v

/-- The accumulator keeps the entire request domain. Payload-row skipping uses
one separate caller-owned scratch word, so high request bits are never packed
or truncated. Only actual kind8 headers contribute to the maximum. -/
private def freshRequestStep (i _ : UInt32) (acc buffer count scratch format : UInt64) : Action :=
  if count ≤ i.toUInt64 then .done 0 acc else
  .bind (read scratch 0) fun s skip => if s = 0 then
  if 0 < skip then .bind (write scratch 0 (skip-1)) fun s _ => .done s acc else
  let entry := buffer+832+i.toUInt64*16
  .bind (read entry 8) fun s desc => if s = 0 then
  if desc &&& 255 = 7 then
    if format = 1 then .done 234 0 else if count < i.toUInt64+4 then .done 234 0 else
    .bind (write scratch 0 3) fun s _ => .done s acc
  else if desc &&& 255 = 8 then
    if format = 3 then if count < i.toUInt64+8 then .done 234 0 else
    .bind (read entry 24) fun s request => if s = 0 then
    if request = 0 then .done 234 0 else if 0x7ffffffffffffffe < request then .done 234 0 else
    .bind (write scratch 0 7) fun s _ => if s = 0 then
    .done 0 (if acc < request then request else acc) else .done s 0
    else .done s 0 else .done 234 0
  else .done 0 acc else .done s 0 else .done s 0

/-- Choose a new operation identity after both the caller's volatile counter
and every durable local-tool identity, including unresolved preparations and
all terminal scopes. Exact replay continues to use the stored old identity.
Numerical exhaustion returns235 before changing document or caller counter.
Scratch may alias a request reserved word which the subsequent encoder clears. -/
def freshRequestID (buffer candidate scratch : UInt64) : Action :=
  if candidate = 0 then .done 235 0 else if 0x7ffffffffffffffe < candidate then .done 235 0 else
  .bind (read buffer 192) fun s count => if s = 0 then
  .bind (read buffer 208) fun s format => if s = 0 then
  if 64 < count then .done 235 0 else
  if (if format = 1 then true else if format = 2 then true else format = 3) = true then
  .bind (write scratch 0 0) fun s _ => if s = 0 then
  .boundedFoldU64 64 freshRequestStep 64 (candidate-1) buffer count scratch format fun s greatest => if s = 0 then
  if greatest < 0x7ffffffffffffffe then .done 0 (greatest+1) else .done 235 0
  else .done s 0 else .done s 0 else .done 234 0 else .done s 0 else .done s 0

def descriptor (scope outcome : UInt64) : UInt64 :=
  (8 : UInt64) ||| ((1 : UInt64) <<< 8) ||| (scope <<< 16) ||| ((8 : UInt64) <<< 24) ||| (outcome <<< 32)

def knownSource (source edition node crc : UInt64) : Bool :=
  if source = 0 then if edition ||| node ||| crc = 0 then true else false else
  if source = 60000 then false else if source = 60001 then false else if 65535 < source then false else if edition = 0 then false else if 0xffffffff < edition then false else
  if node = 0 then false else if 16 < node then false else
  if 0xffffffff < crc then false else true

def validate (event revision page : UInt64) : Action :=
  .bind (read event 0) fun s pre => if s = 0 then
  .bind (read event 8) fun s desc => if s = 0 then
  .bind (read event 16) fun s post => if s = 0 then
  .bind (read event 24) fun s request => if s = 0 then
  .bind (read event 32) fun s service => if s = 0 then
  .bind (read event 40) fun s source => if s = 0 then
  .bind (read event 48) fun s edition => if s = 0 then
  .bind (read event 56) fun s node => if s = 0 then
  .bind (read event 64) fun s crc => if s = 0 then
  .bind (read event 72) fun s object => if s = 0 then
  .bind (read event 80) fun s oldN => if s = 0 then
  .bind (read event 88) fun s oldD => if s = 0 then
  .bind (read event 96) fun s newN => if s = 0 then
  .bind (read event 104) fun s newD => if s = 0 then
  .bind (read event 112) fun s session => if s = 0 then
  .bind (read event 120) fun s policy => if s = 0 then
  let scope := (desc >>> 16) &&& 255
  let outcome := desc >>> 32
  if desc = descriptor scope outcome then
  if pre = 0 then .done 234 0 else if revision < pre then .done 234 0 else
  if 0x7ffffffffffffffe < request then .done 234 0 else if request = 0 then .done 234 0 else
  if service = Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity then
  if knownSource source edition node crc = true then
  if object = (0x504b000000000000 ||| page) then
  if 99 < oldN then .done 234 0 else if oldD = 0 then .done 234 0 else if 99 < oldD then .done 234 0 else
  if 0x7ffffffffffffffe < session then .done 234 0 else if 0x7ffffffffffffffe < policy then .done 234 0 else
  if (if session = 0 then (if policy = 0 then true else false) else if policy = 0 then false else true) = true then
  if scope = 1 then if outcome ||| post ||| newN ||| newD = 0 then .done 0 0 else .done 234 0
  else if scope = 3 then if post ||| newN ||| newD = 0 then
    if 3 ≤ outcome then if outcome ≤ 5 then .done 0 0 else .done 234 0 else .done 234 0 else .done 234 0
  else if scope = 2 then if (if outcome = 1 then true else outcome = 2) = true then
    if pre < 0x7ffffffffffffffe then if post = pre+1 then if post ≤ revision then
    .bind (Lemma.Services.Arithmetic.ReductionV1.calculate oldN oldD 34) fun s packed => if s = 0 then
    if newN = ((packed >>> 32) &&& 0x7fffffff) then if newD = packed &&& 0xffffffff then
    if outcome = (if newN = oldN then if newD = oldD then 2 else 1 else 1) then .done 0 0 else .done 234 0
    else .done 234 0 else .done 234 0 else .done s 0
    else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done 234 0
  else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Copy the exact original request identity into the bounded prepared row.
The original publication CRC is caller-owned validated context, not arithmetic.
Both reserved words remain zero in the copied service request. -/
def prepare (event request crc : UInt64) : Action :=
  .bind (read request 56) fun s value0 => if s = 0 then
  .bind (read request 96) fun s value24 => if s = 0 then
  .bind (read request 24) fun s value40 => if s = 0 then
  .bind (read request 32) fun s value48 => if s = 0 then
  .bind (read request 48) fun s value56 => if s = 0 then
  .bind (read request 40) fun s value72 => if s = 0 then
  .bind (read request 80) fun s value80 => if s = 0 then
  .bind (read request 88) fun s value88 => if s = 0 then
  .bind (read request 104) fun s value112 => if s = 0 then
  .bind (read request 112) fun s value120 => if s = 0 then
  .bind (write event 0 value0) fun s _ => if s = 0 then
  .bind (write event 24 value24) fun s _ => if s = 0 then
  .bind (write event 40 value40) fun s _ => if s = 0 then
  .bind (write event 48 value48) fun s _ => if s = 0 then
  .bind (write event 56 value56) fun s _ => if s = 0 then
  .bind (write event 72 value72) fun s _ => if s = 0 then
  .bind (write event 80 value80) fun s _ => if s = 0 then
  .bind (write event 88 value88) fun s _ => if s = 0 then
  .bind (write event 112 value112) fun s _ => if s = 0 then
  .bind (write event 120 value120) fun s _ => if s = 0 then
  .bind (write event 8 (descriptor 1 0)) fun s _ => if s = 0 then
  .bind (write event 16 (0)) fun s _ => if s = 0 then
  .bind (write event 32 (Lemma.Services.Arithmetic.ProtocolV9.serviceIdentity)) fun s _ => if s = 0 then
  .bind (write event 64 (crc)) fun s _ => if s = 0 then
  .bind (write event 96 (0)) fun s _ => if s = 0 then
  .bind (write event 104 (0)) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def compareStep (i _ : UInt32) (acc a b normalized _ : UInt64) : Action :=
  .bind (read a (i.toUInt64*8)) fun s x => if s = 0 then
  .bind (read b (i.toUInt64*8)) fun s y => if s = 0 then
  let mask : UInt64 := if normalized = 0 then 0xffffffffffffffff else
    if i = 1 then 0x00000000ff00ffff else if i = 2 then 0 else
    if i = 12 then 0 else if i = 13 then 0 else 0xffffffffffffffff
  .done 0 (acc ||| ((x ^^^ y) &&& mask)) else .done s 0 else .done s 0

/-- Low byte is found row+1; high bytes skip payload rows. Mode1 requires
prepared context; mode0 exact duplicates only, rejecting changed same-scope
request identities. No event payload can masquerade as a standalone hint. -/
private def findStep (i _ : UInt32) (acc buffer count event mode : UInt64) : Action :=
  if count ≤ i.toUInt64 then .done 0 acc else
  if (0 : UInt64) < (acc &&& 255) then .done 0 acc else
  if (0 : UInt64) < (acc >>> 8) then .done 0 (acc-256) else
  let entry := buffer+832+i.toUInt64*16
  .bind (read entry 8) fun s desc => if s = 0 then
  if desc &&& 255 = 7 then .done 0 (3*256) else
  if desc &&& 255 = 8 then
    .bind (read entry 24) fun s oldRequest => if s = 0 then
    .bind (read event 24) fun s request => if s = 0 then
    if oldRequest = request then
      .bind (read entry 8) fun s oldDesc => if s = 0 then
      .bind (read event 8) fun s newDesc => if s = 0 then
      let oldScope := (oldDesc >>> 16) &&& 255
      let newScope := (newDesc >>> 16) &&& 255
      if mode = 2 then
        if (if newScope = 1 then true else if 2 ≤ oldScope then true else false) = true then .done 234 0 else .done 0 (7*256)
      else
      if (if mode = 0 then if 2 ≤ oldScope then if 2 ≤ newScope then if oldScope = newScope then false else true else false else false else false) = true then .done 234 0 else
      if (if mode = 1 then (if oldScope = 1 then true else false) else if oldScope = newScope then true else false) = true then
      .boundedFoldU64 16 compareStep 16 0 entry event mode 0 fun s difference => if s = 0 then
      if difference = 0 then .done 0 (i.toUInt64+1) else .done 234 0 else .done s 0
      else .done 0 (7*256) else .done s 0 else .done s 0
    else .done 0 (7*256) else .done s 0 else .done s 0
  else .done 0 acc else .done s 0

/-- A cold history cannot contain duplicate preparations or any two terminal
rows for a request. Exact retries return an existing row instead of appending. -/
def validatePrior (buffer count event : UInt64) : Action :=
  .boundedFoldU64 64 findStep 64 0 buffer count event 2 fun s _ => .done s 0

def requirePrepared (buffer count event : UInt64) : Action :=
  .boundedFoldU64 64 findStep 64 0 buffer count event 1 fun s found => if s = 0 then
  if (0 : UInt64) < (found &&& 255) then .done 0 0 else .done 234 0 else .done s 0
private def copyStep (i _ : UInt32) (acc source output _ _ : UInt64) : Action :=
  .bind (read source (i.toUInt64*8)) fun s value => if s = 0 then
  .bind (write output (i.toUInt64*8) value) fun s _ => .done s acc else .done s 0

def append (buffer event : UInt64) : Action :=
  .bind (read buffer 40) fun s revision => if s = 0 then
  .bind (read buffer 32) fun s page => if s = 0 then
  .bind (read buffer 48) fun s goal => if s = 0 then
  .bind (read buffer 208) fun s format => if s = 0 then
  .bind (read buffer 192) fun s count => if s = 0 then
  .bind (read event 8) fun s desc => if s = 0 then
  let scope := (desc >>> 16) &&& 255
  if goal = 1 then if (if format = 1 then true else if format = 2 then true else format = 3) = true then
  if count ≤ 64 then
  .bind (validate event revision page) fun s _ => if s = 0 then
  .bind (if scope = 1 then .done 0 0 else requirePrepared buffer count event) fun s _ => if s = 0 then
  .boundedFoldU64 64 findStep 64 0 buffer count event 0 fun s found => if s = 0 then
  if (0 : UInt64) < (found &&& 255) then .done 0 (found &&& 255) else
  if (if scope = 1 then 48 else 56) < count then .done 235 0 else
  .boundedFoldU64 16 copyStep 16 0 event (buffer+832+count*16) 0 0 fun s _ => if s = 0 then
  .bind (write buffer 208 3) fun s _ => if s = 0 then
  .bind (write buffer 192 (count+8)) fun s _ => if s = 0 then .done 0 (count+1) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 234 0 else .done 234 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
end Lemma.Documents.LocalToolEvents
