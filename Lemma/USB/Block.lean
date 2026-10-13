import Lemma.USB.Controller
import Lemma.USB.BlockProtocol
import Lemma.Platform.LemmaSim.MachineServices

/-! One asynchronous opaque sector transaction over the actual USB bulk slots.
Only a validated independent peer receipt completes an operation. USB ACKs do
not imply persistence. Errors quarantine the owned frame and sequence; a later
new request cannot overwrite an uncertain transaction. -/
namespace Lemma.USB.Block
open Lemma.Core0.Memory Lemma.Kernel.Memory
def mmio : UInt64 := 0x10010a00
def state : UInt64 := 0x804f0000
def pending : UInt8 := 168
def busy : UInt8 := 162
def corruptCompletion : UInt8 := 165
def poisoned : UInt8 := 167
private def get (o : UInt64) : Action := Access.read64 (state+o)
private def put (o v : UInt64) : Action := Access.write64 (state+o) v
-- handle/base/capacity/tx cursor/rx cursor/request/reserved/poison/sequence/
-- writer/phase/tx bytes/sector. Frame request128, reply768, bounce1536.
private def quarantine : Action := .bind (put 56 1) fun s _ => if s = 0 then .done corruptCompletion 0 else .done s 0
private def copyStep (i _count : UInt32) (source target _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (source+i.toUInt64*8)) fun s value => if s = 0 then
  .bind (Access.write64 (target+i.toUInt64*8) value) fun s _ => .done s source else .done s 0
private def copySector (source target : UInt64) : Action :=
  .boundedFoldU64 64 copyStep 64 source target 0 0 0 fun s _ => .done s 0
private def headerStep (i _count : UInt32) (base kind writer sequence offset : UInt64) : Action :=
  .bind (Access.write64 (base+128+i.toUInt64*8) (BlockProtocol.headerWord i.toUInt64 kind writer sequence offset)) fun s _ => .done s base
private def crcStep (i _count : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (address+i.toUInt64*8)) fun s word => if s = 0 then
  .done 0 (BlockProtocol.crcWord acc word) else .done s 0
private def checksum (address length : UInt64) : Action :=
  if (if length % 8 = 0 then (if length ≤ 576 then true else false) else false) then
  .boundedFoldU64 72 crcStep (length/8).toUInt32 0 address 0 0 0 fun s crc => .done s crc else .done 163 0

def bounce : Action := .bind (get 0) fun s handle => if s = 0 then
  .bind (Frames.resolvePurpose 1 handle 1) fun s base => if s = 0 then .done 0 (base+1536) else .done s 0 else .done s 0
def capacity : Action := get 16
def context : Action := get 0

def prepare : Action :=
  .bind (Controller.initialize mmio) fun s _ => if s = 0 then
  .bind (Frames.allocate 1 1) fun s handle => if s = 0 then
  .bind (Frames.resolvePurpose 1 handle 1) fun s base => if s = 0 then
  .bind (put 0 handle) fun s _ => if s = 0 then
  .bind (put 8 base) fun s _ => if s = 0 then
  .bind (put 16 0) fun s _ => if s = 0 then
  .bind (put 24 0) fun s _ => if s = 0 then
  .bind (put 32 0) fun s _ => if s = 0 then
  .bind (put 40 0) fun s _ => if s = 0 then
  .bind (put 56 0) fun s _ => if s = 0 then
  .bind (put 64 0) fun s _ => if s = 0 then
  .bind (put 72 0) fun s _ => if s = 0 then
  .bind (put 80 0) fun s _ => if s = 0 then .done 0 handle else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def beginHello : Action :=
  .bind (get 8) fun s base => if s = 0 then
  .bind (Access.write64 (base+128) BlockProtocol.helloMagic) fun s _ => if s = 0 then
  .bind (put 24 0) fun s _ => if s = 0 then
  .bind (put 32 0) fun s _ => if s = 0 then
  .bind (put 88 8) fun s _ => if s = 0 then put 80 1 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def sendPart (handle cursor total : UInt64) : Action :=
  if cursor < total then
  let length := if total-cursor < 64 then total-cursor else 64
  .bind (Controller.submitOwned mmio 1 handle (128+cursor) length) fun s _ =>
  if s = Controller.busy then .done pending 0 else if s = 0 then
  .bind (put 24 (cursor+length)) fun s _ => if s = 0 then .done pending 0 else .done s 0
  else .done s 0
  else .bind (put 80 2) fun s _ => if s = 0 then .done pending 0 else .done s 0

private def validateHello (base amount : UInt64) : Action :=
  if amount = 32 then
  .bind (Access.read64 (base+768)) fun s magic => if s = 0 then
  .bind (Access.read64 (base+776)) fun s writer => if s = 0 then
  .bind (Access.read64 (base+784)) fun s sequence => if s = 0 then
  .bind (Access.read64 (base+792)) fun s bytes => if s = 0 then
  if (if magic = BlockProtocol.helloMagic then (if (if (if writer = 0 then false else true) then (if (if (if sequence = 0 then false else true) then (if (if sequence < 0xffffffffffffffff then (if bytes = BlockProtocol.capacity then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
  .bind (put 72 writer) fun s _ => if s = 0 then
  .bind (put 64 sequence) fun s _ => if s = 0 then
  .bind (put 16 (bytes/512)) fun s _ => if s = 0 then
  .bind (put 80 0) fun s _ => if s = 0 then .done 0 (bytes/512) else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else quarantine else .done s 0 else .done s 0 else .done s 0 else .done s 0 else quarantine

private def receiptWordStep (i _count : UInt32) (base _ _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (base+192+i.toUInt64*8)) fun s expected => if s = 0 then
  .bind (Access.read64 (base+832+i.toUInt64*8)) fun s actual => if s = 0 then
  if expected = actual then .done 0 base else quarantine
  else .done s 0 else .done s 0
private def validateWritePayload (base : UInt64) : Action :=
  .boundedFoldU64 64 receiptWordStep 64 base 0 0 0 0 fun s _ => .done s 0

private def validateReply (base amount request writer sequence sector : UInt64) : Action :=
  if (if 72 ≤ amount then (if (if amount ≤ 584 then (if amount % 8 = 0 then true else false) else false) then true else false) else false) then
  .bind (Access.read64 (base+768)) fun s magic => if s = 0 then
  .bind (Access.read64 (base+776)) fun s version => if s = 0 then
  .bind (Access.read64 (base+784)) fun s kind => if s = 0 then
  .bind (Access.read64 (base+792)) fun s actualWriter => if s = 0 then
  .bind (Access.read64 (base+800)) fun s actualSequence => if s = 0 then
  .bind (Access.read64 (base+808)) fun s offset => if s = 0 then
  .bind (Access.read64 (base+816)) fun s length => if s = 0 then
  .bind (Access.read64 (base+824)) fun s error => if s = 0 then
  .bind (checksum (base+768) (amount-8)) fun s crc => if s = 0 then
  .bind (Access.read64 (base+768+amount-8)) fun s stored => if s = 0 then
  if (if magic = BlockProtocol.magic then (if (if version = 1 then (if (if kind = 3 then (if (if actualWriter = writer then (if (if actualSequence = (if request = 1 then 0 else sequence) then (if (if offset = sector*512 then (if (if length = amount-72 then (if (if error ≤ 4095 then (if crc = stored then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then true else false) else false) then
  if (if error = 0 then false else true) then quarantine else
  if (if request = 1 then (if length = 512 then true else false) else if request = 2 then (if length = 512 then true else false) else if request = 5 then (if length = 0 then true else false) else false) then
  .bind (if request = 2 then validateWritePayload base else .done 0 0) fun s _ => if s = 0 then
  .bind (if request = 1 then copySector (base+832) (base+1536) else .done 0 0) fun s _ => if s = 0 then
  .bind (if (if request = 1 then false else true) then put 64 (sequence+1) else .done 0 0) fun s _ => if s = 0 then
  .bind (put 40 0) fun s _ => if s = 0 then
  .bind (put 80 0) fun s _ => if s = 0 then .done 0 request else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else quarantine else quarantine
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else quarantine

private def receivePart (handle base cursor request : UInt64) : Action :=
  if cursor ≤ 576 then
  .bind (Controller.receiveOwned mmio 2 handle (768+cursor) (if 584-cursor < 64 then 584-cursor else 64)) fun s length =>
  if s = Controller.busy then .done pending 0 else if s = 0 then
  .bind (put 32 (cursor+length)) fun s _ => if s = 0 then
  if length = 64 then .done pending 0 else
  if request = 0 then validateHello base (cursor+length) else
  .bind (get 72) fun s writer => if s = 0 then
  .bind (get 64) fun s sequence => if s = 0 then
  .bind (get 96) fun s sector => if s = 0 then validateReply base (cursor+length) request writer sequence sector else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else quarantine

/-- One bounded controller service step. A caller may run unrelated services
between steps. It never waits on the external peer or advances a transaction
from USB delivery alone. -/
def progress : Action :=
  .bind (Controller.serviceSetup mmio) fun control _ =>
  if (if (if control = 0 then false else true) then (if (if control = Controller.busy then false else true) then true else false) else false) then .done control 0 else
  .bind (Controller.read mmio 40) fun s events => if s = 0 then
  .bind (Controller.write mmio 40 events) fun s _ => if s = 0 then
  .bind (get 56) fun s poison => if s = 0 then
  if (if poison = 0 then false else true) then .done poisoned 0 else
  .bind (Controller.read mmio 16) fun s connected => if s = 0 then
  .bind (get 40) fun s request => if s = 0 then
  .bind (get 80) fun s phase => if s = 0 then
  if connected &&& 8 = 0 then
    if (if phase = 0 then false else true) then .bind (put 56 1) fun s _ => if s = 0 then .done poisoned 0 else .done s 0
    else .done pending 0
  else if phase = 0 then
    .bind (get 16) fun s sectors => if s = 0 then
    if sectors = 0 then .bind beginHello fun s _ => if s = 0 then .done pending 0 else .done s 0 else .done 0 0
    else .done s 0
  else
  .bind (get 0) fun s handle => if s = 0 then
  .bind (Frames.resolvePurpose 1 handle 1) fun s base => if s = 0 then
  if phase = 1 then
    .bind (Controller.read mmio 16) fun s controller => if s = 0 then
    if (if controller &&& 128 = 0 then false else true) then .done pending 0 else
    .bind (get 24) fun s cursor => if s = 0 then
    .bind (get 88) fun s total => if s = 0 then sendPart handle cursor total else .done s 0 else .done s 0 else .done s 0
  else if phase = 2 then
    .bind (get 32) fun s cursor => if s = 0 then receivePart handle base cursor request else .done s 0
  else quarantine
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def awaitStep (_i _count : UInt32) (_acc _ _ _ _ : UInt64) : Action :=
  .bind progress fun s _ => if s = pending then
  .bind (Lemma.Kernel.MachineServices.rearmRelative 1000) fun s _ => if s = 0 then
  .bind Lemma.Kernel.MachineServices.wait fun s _ => .done s 0 else .done s 0
  else if s = 0 then
  .bind capacity fun s sectors => if s = 0 then
  if (if sectors = 0 then false else true) then .done Status.iterationStop sectors else .done 0 0 else .done s 0
  else .done s 0

def «initialize» : Action := .bind prepare fun s _ => if s = 0 then
  -- One second of virtual timer waits is a negotiation resource bound; actual
  -- controller/service work adds its measured cycles. Exhaustion is failure.
  .boundedFoldU64 10000 awaitStep 10000 0 0 0 0 0 fun s sectors =>
  if s = Status.iterationStop then .done 0 sectors else if s = 0 then .done 160 0 else .done s 0
  else .done s 0

private def publish (kind sector base writer sequence : UInt64) : Action :=
  let protocolKind := if kind = 4 then 2 else kind
  let offset := if kind = 4 then 0 else sector*512
  .boundedFoldU64 8 headerStep 8 base protocolKind writer sequence offset fun s _ => if s = 0 then
  .bind (if kind = 1 then copySector (base+1536) (base+192) else .done 0 0) fun s _ => if s = 0 then
  let total := BlockProtocol.requestBytes protocolKind
  .bind (checksum (base+128) (total-8)) fun s crc => if s = 0 then
  .bind (Access.write64 (base+128+total-8) crc) fun s _ => if s = 0 then
  .bind (put 24 0) fun s _ => if s = 0 then
  .bind (put 32 0) fun s _ => if s = 0 then
  .bind (put 88 total) fun s _ => if s = 0 then
  .bind (put 96 (if kind = 4 then 0 else sector)) fun s _ => if s = 0 then
  .bind (put 40 (kind+1)) fun s _ => if s = 0 then
  .bind (put 80 1) fun s _ => if s = 0 then .done 0 sequence else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

def submit (kind sector : UInt64) : Action :=
  if (if kind = 0 then true else if (if kind = 1 then true else if kind = 4 then true else false) then true else false) then
  .bind (get 56) fun s poison => if s = 0 then
  if poison = 0 then
  .bind (get 40) fun s request => if s = 0 then
  if request = 0 then
  .bind (get 80) fun s phase => if s = 0 then
  if phase = 0 then
  .bind (get 16) fun s sectors => if s = 0 then
  if (if 0 < sectors then (if ((if kind = 4 then true else if sector < sectors then true else false)) then true else false) else false) then
  .bind (get 72) fun s writer => if s = 0 then
  .bind (get 64) fun s sequence => if s = 0 then
  if (if 0 < sequence then (if sequence < 0xffffffffffffffff then true else false) else false) then
  .bind (get 0) fun s handle => if s = 0 then
  .bind (Frames.resolvePurpose 1 handle 1) fun s base => if s = 0 then
  publish kind sector base writer sequence
  else .done s 0 else .done s 0
  else .done 163 0 else .done s 0 else .done s 0
  else .done 163 0 else .done s 0
  else .done busy 0 else .done s 0
  else .done busy 0 else .done s 0
  else .done poisoned 0 else .done s 0
  else .done 163 0

def finish : Action := progress
end Lemma.USB.Block
