import Lemma.Radio.WiFi.Queue
import Lemma.USB.BlockProtocol

/-! One owned opaque READ512 over the CommonOFDM DATA prerequisite.
The context stays pinned until a complete independent companion-v1 reply has
passed identity, shape and CRC checks. Packet delivery alone never publishes a
result. This privileged client is not a User capability or a durable write.
All per-operation state lives in the owned context, including partial replies.
-/
namespace Lemma.Radio.WiFi.Block
open Lemma.Core0.Memory Lemma.Kernel.Memory
open Lemma.USB

def magic : UInt64 := 0x3152444d46495743
def pending : UInt8 := 216
def invalid : UInt8 := 217
def poisoned : UInt8 := 218
def peerError : UInt8 := 219
def requestOffset : UInt64 := 128
def replyOffset : UInt64 := 768
def resultOffset : UInt64 := 1536
def fragmentLength (cursor total : UInt64) : UInt64 :=
 if cursor < total then if total-cursor < 16 then total-cursor else 16 else 0
def replyShape (length error : UInt64) : Bool :=
 if error = 0 then if length = 512 then true else false
 else if error ≤ 4095 then if length = 0 then true else false else false
def receivePosition (cursor total : UInt64) : Bool :=
 if total = 584 then if cursor ≤ 576 then if cursor % 16 = 0 then true else false else false
 else if total = 72 then if cursor = 64 then true else false else false

-- Context words: magic,phase,TX cursor,RX cursor,writer,offset,poison,RX armed,
-- packet handle,result published,in-flight TX length,reply total,peer error.
-- Phases:0 fresh,1 sending,2 receiving,3 validated result. Poison never clears.
private def get (frame offset : UInt64) : Action := Access.read64 (frame+offset)
private def put (frame offset value : UInt64) : Action := Access.write64 (frame+offset) value
private def quarantine (frame status : UInt64) : Action :=
 .bind (put frame 48 status) fun s _ => if s = 0 then .done poisoned status else .done s 0
private def clearStep (i _count : UInt32) (frame _ _ _ _ : UInt64) : Action :=
 .bind (put frame (i.toUInt64*8) 0) fun s _ => .done s frame

/-- Allocate a new private context. A failed initialization returns its retained
handle with the error so a caller can release it before any operation starts. -/
def create : Action :=
 .bind (Frames.allocate 1 Frames.dataPurpose) fun s handle => if s = 0 then
 .bind (Frames.resolvePurpose 1 handle Frames.dataPurpose) fun s frame => if s = 0 then
 .boundedFoldU64 16 clearStep 16 frame 0 0 0 0 fun s _ => if s = 0 then
 .bind (put frame 0 magic) fun s _ => .done s handle else .done s handle
 else .done s handle else .done s 0

private def checked (handle : UInt64) : Action :=
 .bind (Frames.resolvePurpose 1 handle Frames.dataPurpose) fun s frame => if s = 0 then
 .bind (get frame 0) fun s found => if s = 0 then
 .bind (get frame 48) fun s poison => if s = 0 then
 if found = magic then if poison = 0 then .done 0 frame else .done poisoned poison
 else .done invalid 0 else .done s 0 else .done s 0 else .done s 0

private def headerStep (i _count : UInt32) (frame writer offset _ _ : UInt64) : Action :=
 .bind (Access.write64 (frame+requestOffset+i.toUInt64*8)
   (BlockProtocol.headerWord i.toUInt64 0 writer 0 offset)) fun s _ => .done s frame
private def crcStep (i _count : UInt32) (crc address _ _ _ : UInt64) : Action :=
 .bind (Access.read64 (address+i.toUInt64*8)) fun s word => if s = 0 then
 .done 0 (BlockProtocol.crcWord crc word) else .done s 0
private def checksum (address bytes : UInt64) : Action :=
 if bytes ≤ 576 then if bytes % 8 = 0 then
 .boundedFoldU64 72 crcStep (bytes/8).toUInt32 0 address 0 0 0 fun s crc => .done s crc
 else .done invalid 0 else .done invalid 0

private def publishRequest (frame writer offset : UInt64) : Action :=
 .boundedFoldU64 8 headerStep 8 frame writer offset 0 0 fun s _ => if s = 0 then
 .bind (checksum (frame+requestOffset) 64) fun s crc => if s = 0 then
 .bind (Access.write64 (frame+requestOffset+64) crc) fun s _ => if s = 0 then
 .bind (put frame 32 writer) fun s _ => if s = 0 then
 .bind (put frame 40 offset) fun s _ => if s = 0 then
 .bind (put frame 88 584) fun s _ => if s = 0 then put frame 8 1 else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Start once on a fresh context and an empty trusted packet queue. The
retained context pin prevents release throughout transmission and reception.
Allocation failure precedes that pin; later failure retains ownership. -/
def beginRead (handle writer offset : UInt64) : Action :=
 if BlockProtocol.validRequest 0 writer 0 offset = true then
 .bind (checked handle) fun s frame => if s = 0 then
 .bind (get frame 8) fun s phase => if s = 0 then
 .bind (get frame 64) fun s packet => if s = 0 then
 if phase = 0 then if packet = 0 then
 .bind (Frames.mappingCount 1 handle) fun s pins => if s = 0 then
 if pins = 0 then
 .bind Queue.valid fun s count => if s = 0 then
 if count = 0 then
 .bind (Frames.allocate 1 Frames.dataPurpose) fun s packet => if s = 0 then
 .bind (put frame 64 packet) fun s _ => if s = 0 then
 .bind (Frames.pin 1 handle) fun s _ => if s = 0 then
 .bind (publishRequest frame writer offset) fun s _ => if s = 0 then .done pending handle
 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64
 else .done s packet else .done s 0
 else .done Controller.busy 0 else .done s 0
 else .done Controller.busy 0 else .done s 0
 else .done Controller.busy 0 else .done Controller.busy 0
 else .done s 0 else .done s 0 else .done s 0 else .done invalid 0

private def copyByteStep (i _count : UInt32) (source target _ _ _ : UInt64) : Action :=
 .bind (Access.read8 (source+i.toUInt64)) fun s value => if s = 0 then
 .bind (Access.write8 (target+i.toUInt64) value) fun s _ => .done s source else .done s 0
private def send (base frame packet cursor : UInt64) : Action :=
 let length := fragmentLength cursor 72
 .bind (Frames.resolvePurpose 1 packet Frames.dataPurpose) fun s buffer => if s = 0 then
 .boundedFoldU64 16 copyByteStep length.toUInt32 (frame+requestOffset+cursor) buffer 0 0 0 fun s _ => if s = 0 then
 .bind (Queue.enqueue 1 packet 0 length 93) fun s _ => if s = 0 then
 .bind (put frame 80 length) fun s _ => if s = 0 then
 .bind (Queue.kick base) fun s _ => if s = 0 then .done pending cursor
 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64
 else .done s 0 else .done s 0 else .done s 0

private def finishTX (base frame packet cursor : UInt64) : Action :=
 .bind (Queue.complete base) fun s actual => if s = 0 then
 if actual = packet then
 .bind (get frame 80) fun s length => if s = 0 then
 if length = fragmentLength cursor 72 then
 .bind (put frame 16 (cursor+length)) fun s _ => if s = 0 then
 .bind (put frame 80 0) fun s _ => if s = 0 then
 .bind (Controller.acknowledge base 1) fun s _ => if s = 0 then .done pending (cursor+length)
 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64
 else quarantine frame invalid.toUInt64 else .done s 0
 else quarantine frame invalid.toUInt64 else if s = Controller.busy then .done pending cursor else quarantine frame s.toUInt64

private def transmit (base frame packet : UInt64) : Action :=
 .bind (get frame 16) fun s cursor => if s = 0 then
 if cursor < 72 then
 if cursor % 16 = 0 then
 .bind (Queue.read 16) fun s active => if s = 0 then
 if active = 1 then finishTX base frame packet cursor
 else if active = 0 then send base frame packet cursor else quarantine frame invalid.toUInt64
 else .done s 0 else quarantine frame invalid.toUInt64
 else if cursor = 72 then
 .bind (put frame 8 2) fun s _ => if s = 0 then .done pending cursor else quarantine frame s.toUInt64
 else quarantine frame invalid.toUInt64 else .done s 0

private def headerReply (frame : UInt64) : Action :=
 .bind (get frame 32) fun s writer => if s = 0 then
 .bind (get frame 40) fun s offset => if s = 0 then
 .bind (Access.read64 (frame+replyOffset)) fun s found => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+8)) fun s version => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+16)) fun s kind => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+24)) fun s actualWriter => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+32)) fun s sequence => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+40)) fun s actualOffset => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+48)) fun s length => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+56)) fun s error => if s = 0 then
 if found = BlockProtocol.magic then if version = 1 then if kind = 3 then
 if actualWriter = writer then if sequence = 0 then if actualOffset = offset then
 if replyShape length error = true then
 .bind (put frame 96 error) fun s _ => if s = 0 then put frame 88 (72+length) else .done s 0
 else quarantine frame invalid.toUInt64 else quarantine frame invalid.toUInt64
 else quarantine frame invalid.toUInt64 else quarantine frame invalid.toUInt64
 else quarantine frame invalid.toUInt64 else quarantine frame invalid.toUInt64
 else quarantine frame invalid.toUInt64
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def copyWordStep (i _count : UInt32) (frame _ _ _ _ : UInt64) : Action :=
 .bind (Access.read64 (frame+replyOffset+64+i.toUInt64*8)) fun s value => if s = 0 then
 .bind (Access.write64 (frame+resultOffset+i.toUInt64*8) value) fun s _ => .done s frame else .done s 0
private def validate (handle frame packet total : UInt64) : Action :=
 .bind (checksum (frame+replyOffset) (total-8)) fun s crc => if s = 0 then
 .bind (Access.read64 (frame+replyOffset+total-8)) fun s stored => if s = 0 then
 if crc = stored then
 .bind (get frame 96) fun s error => if s = 0 then
 if error = 0 then
 .boundedFoldU64 64 copyWordStep 64 frame 0 0 0 0 fun s _ => if s = 0 then
 .bind (Frames.release 1 packet) fun s _ => if s = 0 then
 .bind (put frame 64 0) fun s _ => if s = 0 then
 .bind (Frames.unpin 1 handle) fun s _ => if s = 0 then
 .bind (put frame 72 1) fun s _ => if s = 0 then
 .bind (put frame 8 3) fun s _ => if s = 0 then .done 0 handle else quarantine frame s.toUInt64
 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64
 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64
 else .bind (put frame 48 peerError.toUInt64) fun s _ => if s = 0 then .done peerError error else .done s 0
 else .done s 0 else quarantine frame invalid.toUInt64 else .done s 0 else .done s 0

private def receiveHead (base handle frame packet cursor total : UInt64) : Action :=
 .bind (Controller.receiveOwned base 1 handle (replyOffset+cursor)) fun s length => if s = 0 then
 if length = fragmentLength cursor total then
 .bind (put frame 24 (cursor+length)) fun s _ => if s = 0 then
 .bind (if cursor+length = 64 then headerReply frame else .done 0 0) fun s _ => if s = 0 then
 .bind (Controller.releaseHead base) fun s _ => if s = 0 then
 .bind (Controller.acknowledge base 2) fun s _ => if s = 0 then
 .bind (put frame 56 0) fun s _ => if s = 0 then
 .bind (get frame 88) fun s actualTotal => if s = 0 then
 if cursor+length = actualTotal then validate handle frame packet actualTotal else .done pending (cursor+length)
 else .done s 0 else quarantine frame s.toUInt64 else quarantine frame s.toUInt64
 else quarantine frame s.toUInt64 else .done s 0 else quarantine frame s.toUInt64
 else quarantine frame invalid.toUInt64 else if s = Controller.busy then .done pending cursor else quarantine frame s.toUInt64

private def receive (base handle frame packet : UInt64) : Action :=
 .bind (get frame 24) fun s cursor => if s = 0 then
 .bind (get frame 88) fun s total => if s = 0 then
 if receivePosition cursor total = true then
 .bind (get frame 56) fun s armed => if s = 0 then
 if armed = 0 then
 .bind (Controller.arm base (fragmentLength cursor total) 127) fun s _ => if s = 0 then
 .bind (put frame 56 1) fun s _ => if s = 0 then .done pending cursor else quarantine frame s.toUInt64
 else if s = Controller.busy then .done pending cursor else quarantine frame s.toUInt64
 else if armed = 1 then receiveHead base handle frame packet cursor total else quarantine frame invalid.toUInt64
 else .done s 0
 else quarantine frame invalid.toUInt64 else .done s 0 else .done s 0

/-- One bounded service step. Loss or absent peer leaves a pinned pending
context; faults and invalid replies quarantine it. There is no implicit retry,
cancel, ACK fabrication or success from the number of transferred packets. -/
def progress (base handle : UInt64) : Action :=
 .bind (checked handle) fun s frame => if s = 0 then
 .bind (get frame 8) fun s phase => if s = 0 then
 if phase = 3 then .done 0 handle else
 .bind (Frames.mappingCount 1 handle) fun s pins => if s = 0 then
 if pins = 1 then if phase = 1 then
 .bind (Controller.events base) fun s events => if s = 0 then
 if events &&& (4 : UInt64) = 0 then
 .bind (get frame 64) fun s packet => if s = 0 then transmit base frame packet else .done s 0
 else quarantine frame events else .done s 0
 else if phase = 2 then
 .bind (Controller.events base) fun s events => if s = 0 then
 if events &&& (4 : UInt64) = 0 then
 .bind (get frame 64) fun s packet => if s = 0 then receive base handle frame packet else .done s 0
 else quarantine frame events else .done s 0
 else .done invalid phase else quarantine frame invalid.toUInt64
 else .done s 0 else .done s 0 else .done s 0

/-- Return the retained owned result address only after the complete reply.
The caller remains responsible for the context handle until explicit release. -/
def result (handle : UInt64) : Action :=
 .bind (checked handle) fun s frame => if s = 0 then
 .bind (get frame 8) fun s phase => if s = 0 then
 .bind (get frame 72) fun s published => if s = 0 then
 .bind (Frames.mappingCount 1 handle) fun s pins => if s = 0 then
 if phase = 3 then if published = 1 then if pins = 0 then .done 0 (frame+resultOffset)
 else .done invalid 0 else .done invalid 0 else .done pending 0
 else .done s 0 else .done s 0 else .done s 0 else .done s 0
end Lemma.Radio.WiFi.Block
