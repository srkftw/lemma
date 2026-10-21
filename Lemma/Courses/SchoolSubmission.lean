import Lemma.Courses.PackageWorkspace
import Lemma.Documents.Ink
import Lemma.Multimodal.SchoolPacket
import Lemma.Services.Store.Client
import Lemma.User.CapabilityConsole
import Lemma.Courses.SchoolStream

/-! Guest-origin school submission/2. Eight private pages freeze metadata and
stream original immutable Store chunks. Every pump admits at most one IPC
transition or one bounded Console write. Versions23/24 retain16-byte K1
chunks; version25 explicitly enables School wire S1 with up to96 payload bytes. Stream completion is transport output,
never school admission or proof. Phase1..4 preflights raw headers/EOF;
5..10 writes frozen metadata;11..16 publishes the pending pointer;
20..25 streams bytes;26 awaits a school ACK;27..28 emit terminal receipts;
29 is terminal;30 retains failure;
40..43 restores pointer/metadata;45 polls ACK;46..47 pauses/aborts staging.
The queue pointer follows the metadata Commit;
no bytes leave before both actual Store receipts. A lost Commit is never retried.
-/
namespace Lemma.Courses.SchoolSubmission
open Lemma.Core0.Memory Lemma.User Lemma.Services.Store

def magic : UInt64 := 0x31425553534d454c
def version : UInt64 := 2
def headerBytes : UInt64 := 256
def maximumBytes : UInt64 := 262144
def maximumChunks : UInt64 := 512
def metadataCapacity : UInt64 := 24576
def queuePrefix : UInt64 := 0x5351000000000000
def pointerObject : UInt64 := 0x5350000000000001
def pointerMagic : UInt64 := 0x3151544f534d454c
def ackObject : UInt64 := 0x5350000000000002
def ackMagic : UInt64 := 0x314b4341534d454c
def arena : UInt64 := 0x380000
def outgoing : UInt64 := arena+0x400
def incoming : UInt64 := arena+0x500
def chunkHeader : UInt64 := arena+0x600
def lengths : UInt64 := arena+0x7000
def pointer : UInt64 := arena+0x700
def metadata : UInt64 := arena+0x1000
private def malformed : UInt8 := 240
private def resourceLimit : UInt8 := 242
private def field (buffer offset : UInt64) : Action := Memory.read64 (buffer+offset)
private def write (buffer offset value : UInt64) : Action := Memory.write64 (buffer+offset) value
private def get (offset : UInt64) : Action := field arena offset
private def put (offset value : UInt64) : Action := write arena offset value
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def bad : Action := .done malformed 0
private def equal (buffer offset expected : UInt64) : Action :=
  .bind (field buffer offset) fun s actual => if s = 0 then
  if actual = expected then .done 0 0 else bad else .done s 0
private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (field source (i.toUInt64*8)) fun s value => if s = 0 then
  .bind (write target (i.toUInt64*8) value) fun s _ => .done s acc else .done s 0
private def copy (source target bytes : UInt64) : Action :=
  if bytes%8 = 0 then if bytes ≤ metadataCapacity then
  .boundedFoldU64 3072 copyStep (bytes/8).toUInt32 0 source target 0 0 fun s _ => .done s bytes
  else bad else bad
private def zeroStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  .bind (put (i.toUInt64*8) 0) fun s _ => .done s acc
private def allocateStep (i _ : UInt32) (acc _ _ _ _ : UInt64) : Action :=
  let address := arena+i.toUInt64*4096
  .bind (Syscall.allocatePage address) fun s actual => if s = 0 then
  if actual = address then .done 0 (acc+1) else .done malformed acc else .done s acc
private def releaseStep (i _ : UInt32) (acc count _ _ _ : UInt64) : Action :=
  .bind (Syscall.releasePage (arena+(count-1-i.toUInt64)*4096)) fun s _ => .done s acc
private def releaseAllocated (count : UInt64) (original : UInt8) : Action :=
  if count ≤ 8 then
  .boundedFoldU64 8 releaseStep count.toUInt32 0 count 0 0 0 fun s _ =>
  if s = 0 then .done original 0 else .done s 0 else bad

/-- Called once after mount Ready. The caller reserves the returned one-million
request-ID suffix from its own counter before any other client can reuse it. -/
def initializeQueue (endpoint console firstRequest : UInt64) : Action :=
  if firstRequest = 0 then bad else if Format.maximumSequence-1000000 < firstRequest then .done resourceLimit 0 else
  .boundedFoldU64 8 allocateStep 8 0 0 0 0 0 fun s count => if s = 0 then
  if count = 8 then
  .boundedFoldU64 48 zeroStep 48 0 0 0 0 0 fun s _ => if s = 0 then
  .bind (put 8 endpoint) fun s _ => if s = 0 then
  .bind (put 16 console) fun s _ => if s = 0 then
  .bind (put 24 firstRequest) fun s _ => if s = 0 then
  .bind (put 32 (firstRequest+1000000)) fun s _ => if s = 0 then .done 0 (firstRequest+999999) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else bad else releaseAllocated count s

/-- Selected only by the version25 guest after fresh queue initialization.
The durable pointer/envelope stay version2; this changes Console framing only. -/
def enableWire96 : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  .bind (get 336) fun s enabled => if s = 0 then
  if phase = 0 then if enabled = 0 then put 336 1 else bad else bad
  else .done s 0 else .done s 0

private def halt (status : UInt8) : Action :=
  .bind (put 192 status.toUInt64) fun s _ => if s = 0 then
  .bind (put 0 30) fun s _ => if s = 0 then .done status 0 else .done s 0 else .done s 0

/-- Begin copies only the owned immutable source. Errors never advance a phase.
The separately stored operation tuple is the sole authority for its later poll. -/
private def beginOp (operation object offset count source nextPhase : UInt64) : Action :=
  .bind (get 8) fun s endpoint => if s = 0 then
  .bind (get 24) fun s request => if s = 0 then
  .bind (get 32) fun s limit => if s = 0 then
  .bind (get 264) fun s override => if s = 0 then
  .bind (if override = 0 then get 88 else .done 0 override) fun s ns => if s = 0 then
  .bind (get 96) fun s queue => if s = 0 then
  if request < limit then
  .bind (put 24 (request+1)) fun s _ => if s = 0 then
  .bind (Client.beginCall endpoint outgoing operation ns object
    (if operation = 5 then 0 else queue &&& 0x0000ffffffffffff) offset count source request) fun status pending =>
  if status = 0 then if pending = 0 then halt IPCABI.invalidTransaction else
  .bind (put 40 pending) fun s _ => if s = 0 then
  .bind (put 48 request) fun s _ => if s = 0 then
  .bind (put 56 operation) fun s _ => if s = 0 then
  .bind (put 64 object) fun s _ => if s = 0 then
  .bind (put 72 offset) fun s _ => if s = 0 then
  .bind (put 80 count) fun s _ => if s = 0 then put 0 nextPhase else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt status else .done s 0
  else halt resourceLimit
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def pollOp : Action :=
  .bind (get 40) fun s pending => if s = 0 then
  .bind (get 48) fun s request => if s = 0 then
  .bind (get 56) fun s operation => if s = 0 then
  .bind (get 64) fun s object => if s = 0 then
  .bind (get 264) fun s override => if s = 0 then
  .bind (if override = 0 then get 88 else .done 0 override) fun s ns => if s = 0 then
  .bind (get 80) fun s count => if s = 0 then
  Client.pollCall pending incoming operation ns object request count
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def responseCount (expected : UInt64) : Action := equal (incoming+64) 56 expected
private def responseDetail (expected : UInt64) : Action := equal (incoming+64) 48 expected
private def record (tag a b c d : UInt64) : Action :=
  .bind (get 16) fun s console => if s = 0 then CapabilityConsole.record console tag a b c d else .done s 0


/-- A queued edition is immutable: restore accepts its own original contract.
The successor increases capacity without rewriting a pending v1 envelope. -/
private def envelopeChunks (v : UInt64) : UInt64 := if v = 1 then 8 else if v = version then maximumChunks else 0
private def envelopeMetadata (v : UInt64) : UInt64 := if v = 1 then 16384 else if v = version then metadataCapacity else 0
private def envelopeBounds (chunks bytes : UInt64) : Action :=
  .bind (field metadata 8) fun s v => if s = 0 then
  if chunks ≤ envelopeChunks v then if bytes ≤ envelopeMetadata v then .done 0 0
  else .done resourceLimit 0 else .done resourceLimit 0 else .done s 0

private def validateHeader : Action :=
  .bind (field metadata 0) fun s tag => if s = 0 then
  .bind (field metadata 8) fun s v => if s = 0 then
  .bind (field metadata 32) fun s frontier => if s = 0 then
  .bind (field metadata 40) fun s ns => if s = 0 then
  .bind (field metadata 48) fun s page => if s = 0 then
  .bind (field metadata 56) fun s revision => if s = 0 then
  .bind (field metadata 64) fun s course => if s = 0 then
  .bind (field metadata 72) fun s edition => if s = 0 then
  .bind (field metadata 80) fun s node => if s = 0 then
  .bind (field metadata 88) fun s crc => if s = 0 then
  .bind (field metadata 96) fun s policy => if s = 0 then
  .bind (field metadata 104) fun s kind => if s = 0 then
  .bind (field metadata 112) fun s now => if s = 0 then
  if tag = magic then
  if (if v = 1 then (1 : UInt64) else if v = version then 1 else 0) = 1 then
  if frontier < 0x0000fffffffffffe then
  if Protocol.namespaceValid ns = 1 then
  if 0 < page then
  if page ≤ 64 then
  if 0 < revision then
  if 0 < course then
  if course ≤ 65535 then
  if 0 < edition then
  if edition ≤ 0xffffffff then
  if 0 < node then
  if node ≤ 16 then
  if crc ≤ 0xffffffff then
  if 0 < policy then
  if (if kind = 1 then (1 : UInt64) else if kind = 2 then 1 else 0) = 1 then
  .bind (equal (metadata+128) 0 Lemma.Multimodal.SchoolPacket.magic) fun s _ => if s = 0 then
  .bind (equal (metadata+128) 8 1) fun s _ => if s = 0 then
  .bind (equal (metadata+128) 72 policy) fun s _ => if s = 0 then
  .bind (equal (metadata+128) 88 course) fun s _ => if s = 0 then
  .bind (equal (metadata+128) 96 edition) fun s _ => if s = 0 then
  .bind (field (metadata+128) 48) fun s binding => if s = 0 then
  .bind (field (metadata+128) 56) fun s generation => if s = 0 then
  .bind (field (metadata+128) 64) fun s deadline => if s = 0 then
  .bind (field (metadata+128) 80) fun s session => if s = 0 then
  if 0 < binding then if 0 < generation then if 0 < session then if now ≤ deadline then
  .bind (put 88 ns) fun s _ => if s = 0 then
  .bind (put 96 (queuePrefix ||| (frontier+1))) fun s _ => if s = 0 then
  .bind (put 248 frontier) fun s _ => .done s 0
  else .done s 0 else .done s 0
  else bad else bad else bad else bad
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else bad
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def validateTyped : Action :=
  .bind (field metadata 104) fun s kind => if s = 0 then
  if kind = 2 then .done 0 0 else
  .bind (PackageWorkspace.snapshotSelection (metadata+256) chunkHeader) fun s _ => if s = 0 then
  .bind (field metadata 64) fun s course => if s = 0 then
  .bind (field metadata 72) fun s edition => if s = 0 then
  .bind (field metadata 80) fun s node => if s = 0 then
  .bind (field metadata 88) fun s crc => if s = 0 then
  .bind (field metadata 56) fun s revision => if s = 0 then
  .bind (equal chunkHeader 16 course) fun s _ => if s = 0 then
  .bind (equal chunkHeader 24 edition) fun s _ => if s = 0 then
  .bind (equal chunkHeader 32 crc) fun s _ => if s = 0 then
  .bind (equal chunkHeader 40 node) fun s _ => if s = 0 then
  .bind (equal chunkHeader 120 revision) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- Freeze the exact current revision before yielding. The parent must pass
disjoint source spans outside this arena; original work remains untouched. -/
def start (header workspace inkPage : UInt64) : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  if (if phase = 0 then (1 : UInt64) else if phase = 29 then 1 else 0) = 1 then
  .bind (copy header metadata 256) fun s _ => if s = 0 then
  .bind (validateHeader) fun s _ => if s = 0 then
  .bind (field metadata 40) fun s ns => if s = 0 then
  .bind (field metadata 48) fun s page => if s = 0 then
  .bind (field metadata 56) fun s revision => if s = 0 then
  .bind (copy workspace (metadata+256) PackageWorkspace.bytes) fun s _ => if s = 0 then
  .bind (PackageWorkspace.validate (metadata+256) ns page) fun s _ => if s = 0 then
  .bind (equal (metadata+256+PackageWorkspace.inner) 40 revision) fun s _ => if s = 0 then
  .bind (validateTyped) fun s _ => if s = 0 then
  .bind (Lemma.Documents.Ink.encodePage inkPage (metadata+3968)) fun s indexBytes => if s = 0 then
  .bind (equal (metadata+3968) 24 page) fun s _ => if s = 0 then
  .bind (field (metadata+3968) 32) fun s chunks => if s = 0 then
  .bind (envelopeBounds chunks (3968+indexBytes)) fun checked _ => if checked = 0 then
  .bind (put 120 chunks) fun s _ => if s = 0 then
  .bind (put 104 (3968+indexBytes)) fun s _ => if s = 0 then
  .bind (put 112 (3968+indexBytes)) fun s _ => if s = 0 then
  .bind (put 128 0) fun s _ => if s = 0 then
  .bind (put 152 0) fun s _ => if s = 0 then
  .bind (put 184 1) fun s _ => if s = 0 then
  .bind (put 192 0) fun s _ => if s = 0 then
  .bind (write metadata 232 headerBytes) fun s _ => if s = 0 then
  .bind (write metadata 240 PackageWorkspace.bytes) fun s _ => if s = 0 then
  .bind (write metadata 248 indexBytes) fun s _ => if s = 0 then
  .bind (get 96) fun s queue => if s = 0 then
  .bind (write metadata 24 queue) fun s _ => if s = 0 then
  .bind (put 264 0) fun s _ => if s = 0 then
  .bind (put 208 0) fun s _ => if s = 0 then
  .bind (put 0 1) fun s _ => if s = 0 then
  .done 0 queue
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done checked 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done Protocol.busy 0
  else .done s 0


private def preflightStart : Action :=
  .bind (get 128) fun s index => if s = 0 then
  .bind (get 120) fun s count => if s = 0 then
  if index < count then
  .bind (field (metadata+3968+128+index*24) 0) fun s object => if s = 0 then
  beginOp 5 object 0 128 0 2
  else .done s 0
  else
  .bind (get 112) fun s total => if s = 0 then
  .bind (write metadata 16 total) fun s _ => if s = 0 then
  .bind (put 144 0) fun s _ => if s = 0 then
  .bind (get 208) fun s restored => if s = 0 then
  if restored = 1 then
  .bind (get 296) fun s expected => if s = 0 then
  if total = expected then put 0 20 else halt malformed else .done s 0
  else put 0 5
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def preflightPoll : Action :=
  .bind pollOp fun status _ =>
    if status = IPCABI.wouldBlock then .done 0 0 else
  if status = Protocol.busy then put 0 1 else if status = 0 then
  .bind (responseCount 128) fun s _ => if s = 0 then
  .bind (copy (Client.responseData incoming) chunkHeader 128) fun s _ => if s = 0 then
  .bind (field metadata 48) fun s page => if s = 0 then
  .bind (get 128) fun s index => if s = 0 then
  .bind (field (metadata+3968+128+index*24) 8) fun s stroke => if s = 0 then
  .bind (Lemma.Documents.Ink.validateChunkHeader chunkHeader page stroke) fun s bytes => if s = 0 then
  .bind (get 112) fun s total => if s = 0 then
  if total ≤ maximumBytes-bytes then
  .bind (write lengths (index*8) bytes) fun s _ => if s = 0 then
  .bind (put 136 bytes) fun s _ => if s = 0 then
  .bind (put 112 (total+bytes)) fun s _ => if s = 0 then
  put 0 3
  else .done s 0 else .done s 0 else .done s 0
  else halt resourceLimit
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt status


private def preflightEOF : Action :=
  .bind (get 128) fun s index => if s = 0 then
  .bind (get 136) fun s bytes => if s = 0 then
  .bind (field (metadata+3968+128+index*24) 0) fun s object => if s = 0 then
  beginOp 5 object bytes 1 0 4
  else .done s 0 else .done s 0 else .done s 0


private def preflightEOFPoll : Action :=
  .bind pollOp fun status _ =>
    if status = IPCABI.wouldBlock then .done 0 0 else
  if status = Protocol.busy then put 0 3 else if status = 0 then
  .bind (responseCount 0) fun s _ => if s = 0 then
  .bind (responseDetail 1) fun s _ => if s = 0 then
  .bind (get 128) fun s index => if s = 0 then
  .bind (put 128 (index+1)) fun s _ => if s = 0 then
  put 0 1
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt status


private def preparePointer : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 152) fun s sequence => if s = 0 then
  .bind (get 184) fun s status => if s = 0 then
  .bind (get 112) fun s total => if s = 0 then
  .bind (get 104) fun s bytes => if s = 0 then
  .bind (write pointer 0 pointerMagic) fun s _ => if s = 0 then
  .bind (write pointer 8 1) fun s _ => if s = 0 then
  .bind (write pointer 16 status) fun s _ => if s = 0 then
  .bind (write pointer 24 queue) fun s _ => if s = 0 then
  .bind (write pointer 32 sequence) fun s _ => if s = 0 then
  .bind (write pointer 40 total) fun s _ => if s = 0 then
  .bind (write pointer 48 bytes) fun s _ => if s = 0 then
  .bind (get 312) fun s schoolCommit => if s = 0 then
  .bind (write pointer 56 (if status = 3 then schoolCommit else 0)) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def beginTransaction (isPointer next : UInt64) : Action :=
  .bind (put 264 2) fun s _ => if s = 0 then
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 104) fun s bytes => if s = 0 then
  if isPointer = 1 then
  .bind (preparePointer) fun s _ => if s = 0 then
  beginOp 2 pointerObject 0 64 0 next
  else .done s 0
  else beginOp 2 queue 0 bytes 0 next
  else .done s 0
  else .done s 0 else .done s 0


private def pollBegin (next : UInt64) : Action :=
  .bind pollOp fun status _ =>
    if status = IPCABI.wouldBlock then .done 0 0 else if status = Protocol.busy then put 0 (next-2) else
    if status = 0 then
  .bind (responseDetail 0) fun s _ => if s = 0 then
  .bind (put 144 0) fun s _ => if s = 0 then
  put 0 next
  else .done s 0 else .done s 0
  else halt status


private def upload (isPointer next : UInt64) : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 104) fun s bytes => if s = 0 then
  .bind (get 144) fun s offset => if s = 0 then
  let length := if isPointer = 1 then (64 : UInt64) else bytes
  let source := if isPointer = 1 then pointer else metadata
  if offset < length then beginOp 3 (if isPointer = 1 then pointerObject else queue) offset (minimum 128 (length-offset)) (source+offset) next
  else put 0 (next+1)
  else .done s 0 else .done s 0 else .done s 0


private def pollUpload (next : UInt64) : Action :=
  .bind pollOp fun status _ =>
    if status = IPCABI.wouldBlock then .done 0 0 else if status = 0 then
  .bind (get 72) fun s offset => if s = 0 then
  .bind (get 80) fun s count => if s = 0 then
  .bind (responseDetail (offset+count)) fun s _ => if s = 0 then
  .bind (put 144 (offset+count)) fun s _ => if s = 0 then
  put 0 next
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt status


private def commit (isPointer next : UInt64) : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  beginOp 4 (if isPointer = 1 then pointerObject else queue) 0 0 0 next
  else .done s 0


/-- A separate one-Console phase reports immutable acknowledged pointer bytes.
The new Commit and restored READ frontier retain distinct record tags. -/
private def terminalReceipt (tag : UInt64) : Action :=
  .bind (field pointer 24) fun s queue => if s = 0 then
  .bind (field pointer 56) fun s schoolCommit => if s = 0 then
  .bind (get 200) fun s observed => if s = 0 then
  .bind (field pointer 16) fun s state => if s = 0 then
  .bind (record tag queue schoolCommit observed state) fun s _ => if s = 0 then
  put 0 29
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def pollCommit (isPointer : UInt64) : Action :=
  .bind pollOp fun status sequence =>
    if status = IPCABI.wouldBlock then .done 0 0 else if status = 0 then
    if sequence = 0 then halt malformed else
  .bind (responseDetail 1) fun s _ => if s = 0 then
  if isPointer = 0 then
  .bind (put 152 sequence) fun s _ => if s = 0 then
  put 0 11
  else .done s 0
  else
  .bind (put 200 sequence) fun s _ => if s = 0 then
  .bind (field pointer 16) fun s committedState => if s = 0 then
  if committedState = 1 then put 0 20 else put 0 28
  else .done s 0 else .done s 0 else .done s 0
  else halt status


private def streamStart : Action :=
  .bind (put 264 0) fun s _ => if s = 0 then
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 152) fun s sequence => if s = 0 then
  .bind (get 112) fun s total => if s = 0 then
  .bind (get 88) fun s ns => if s = 0 then
  .bind (get 336) fun s wire => if s = 0 then
  .bind (if wire = 1 then
    .bind (get 16) fun s console => if s = 0 then
    SchoolStream.start console queue sequence total ns else .done s 0
    else record 0x72e queue sequence total ns) fun s _ => if s = 0 then
  .bind (put 272 0xffffffff) fun s _ => if s = 0 then
  .bind (put 160 0) fun s _ => if s = 0 then
  .bind (put 176 0) fun s _ => if s = 0 then
  .bind (put 128 0) fun s _ => if s = 0 then
  put 0 21
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def crcStep (i _ : UInt32) (crc source _ _ _ : UInt64) : Action :=
  .bind (Memory.read8 (source+i.toUInt64)) fun s value => if s = 0 then
  .done 0 (PackageFormat.crcByte crc value) else .done s 0
private def crcWords (source count : UInt64) : Action :=
  .bind (get 272) fun s crc => if s = 0 then
  .boundedFoldU64 96 crcStep count.toUInt32 crc source 0 0 0 fun s next =>
  if s = 0 then put 272 next else .done s 0 else .done s 0

private def emitWords (source available next : UInt64) : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 160) fun s offset => if s = 0 then
  .bind (get 336) fun s wire => if s = 0 then
  let count := minimum (if wire = 1 then 96 else 16) available
  .bind (if wire = 1 then
    .bind (get 16) fun s console => if s = 0 then
    SchoolStream.send console queue offset source count else .done s 0
    else
    .bind (field source 0) fun s a => if s = 0 then
    .bind (if 8 < count then field source 8 else .done 0 0) fun s b => if s = 0 then
    record 0x72f queue (offset ||| (count <<< 48)) a b
    else .done s 0 else .done s 0) fun s _ => if s = 0 then
  .bind (crcWords source count) fun s _ => if s = 0 then
  .bind (put 160 (offset+count)) fun s _ => if s = 0 then
  .bind (put 0 next) fun s _ => .done s count
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0


private def streamMetadata : Action :=
  .bind (get 176) fun s offset => if s = 0 then
  .bind (get 104) fun s bytes => if s = 0 then
  if offset < bytes then
  .bind (emitWords (metadata+offset) (bytes-offset) 21) fun s sent => if s = 0 then
  .bind (put 176 (offset+sent)) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0
  else
  .bind (put 176 0) fun s _ => if s = 0 then
  put 0 22
  else .done s 0 else .done s 0 else .done s 0


private def streamRaw : Action :=
  .bind (get 128) fun s index => if s = 0 then
  .bind (get 120) fun s count => if s = 0 then
  if index < count then
  .bind (field lengths (index*8)) fun s bytes => if s = 0 then
  .bind (get 176) fun s offset => if s = 0 then
  if offset < bytes then
  .bind (field (metadata+3968+128+index*24) 0) fun s object => if s = 0 then
  beginOp 5 object offset (minimum 128 (bytes-offset)) 0 23
  else .done s 0
  else
  .bind (put 128 (index+1)) fun s _ => if s = 0 then
  .bind (put 176 0) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else put 0 25
  else .done s 0 else .done s 0


private def streamRawPoll : Action :=
  .bind pollOp fun status _ =>
    if status = IPCABI.wouldBlock then .done 0 0 else
  if status = Protocol.busy then put 0 22 else if status = 0 then
  .bind (get 80) fun s count => if s = 0 then
  .bind (responseCount count) fun s _ => if s = 0 then
  .bind (put 216 count) fun s _ => if s = 0 then
  .bind (put 224 0) fun s _ => if s = 0 then
  put 0 24
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt status


private def streamRawEmit : Action :=
  .bind (get 216) fun s count => if s = 0 then
  .bind (get 224) fun s offset => if s = 0 then
  if offset < count then
  .bind (emitWords (Client.responseData incoming+offset) (count-offset) 24) fun s sent => if s = 0 then
  .bind (put 224 (offset+sent)) fun s _ => if s = 0 then
  .done 0 0
  else .done s 0 else .done s 0
  else
  .bind (get 176) fun s rawOffset => if s = 0 then
  .bind (put 176 (rawOffset+count)) fun s _ => if s = 0 then
  put 0 22
  else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def streamEnd : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 152) fun s sequence => if s = 0 then
  .bind (get 112) fun s total => if s = 0 then
  .bind (get 160) fun s actual => if s = 0 then
  if actual = total then
  .bind (get 272) fun s crc => if s = 0 then
  .bind (put 280 (crc ^^^ 0xffffffff)) fun s _ => if s = 0 then
  .bind (record 0x730 queue sequence total 0) fun s _ => if s = 0 then
  put 0 26
  else .done s 0 else .done s 0
  else .done s 0
  else halt malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def restorePointer : Action :=
  .bind (field pointer 0) fun s tag => if s = 0 then
  .bind (field pointer 8) fun s v => if s = 0 then
  .bind (field pointer 16) fun s status => if s = 0 then
  .bind (field pointer 24) fun s queue => if s = 0 then
  .bind (field pointer 32) fun s sequence => if s = 0 then
  .bind (field pointer 40) fun s total => if s = 0 then
  .bind (field pointer 48) fun s bytes => if s = 0 then
  .bind (field pointer 56) fun s reserved => if s = 0 then
  if tag = pointerMagic then
  if v = 1 then
  if 0 < status then
  if status ≤ 3 then
  if queue >>> 48 = 0x5351 then
  if 0 < (queue &&& 0x0000ffffffffffff) then
  if 0 < sequence then
  if sequence ≤ Format.maximumSequence then
  if 3968 ≤ bytes then
  if bytes ≤ metadataCapacity then
  if bytes%8 = 0 then
  if bytes ≤ total then
  if total ≤ maximumBytes then
  if (if status = 3 then if 0 < reserved then if reserved ≤ Format.maximumSequence then (1 : UInt64) else 0 else 0 else if reserved = 0 then 1 else 0) = 1 then
  .bind (put 296 total) fun s _ => if s = 0 then
  .bind (put 312 reserved) fun s _ => if s = 0 then
  .bind (put 96 queue) fun s _ => if s = 0 then
  .bind (put 152 sequence) fun s _ => if s = 0 then
  .bind (put 112 total) fun s _ => if s = 0 then
  .bind (put 104 bytes) fun s _ => if s = 0 then
  .bind (put 184 status) fun s _ => if s = 0 then
  .bind (put 144 0) fun s _ => if s = 0 then
  if status = 1 then put 0 42 else put 0 27
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else halt malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def restorePointerPoll : Action :=
  .bind pollOp fun status sequence =>
  if status = IPCABI.wouldBlock then .done 0 0 else
  if status = Protocol.busy then put 0 40 else
  if status = Format.notFound then
  .bind (put 264 0) fun s _ => if s = 0 then
  put 0 0
  else .done s 0
  else if status = 0 then
  .bind (responseCount 64) fun s _ => if s = 0 then
  .bind (put 200 sequence) fun s _ => if s = 0 then
  .bind (copy (Client.responseData incoming) pointer 64) fun s _ => if s = 0 then
  restorePointer
  else .done s 0 else .done s 0 else .done s 0
  else halt status


private def restoreMetadata : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  .bind (get 144) fun s offset => if s = 0 then
  .bind (get 104) fun s bytes => if s = 0 then
  if offset < bytes then beginOp 5 queue offset (minimum 128 (bytes-offset)) 0 43 else
  .bind (get 96) fun s expectedQueue => if s = 0 then
  .bind (get 112) fun s expectedTotal => if s = 0 then
  .bind (equal metadata 24 expectedQueue) fun s _ => if s = 0 then
  .bind (equal metadata 16 expectedTotal) fun s _ => if s = 0 then
  .bind (validateHeader) fun s _ => if s = 0 then
  .bind (get 96) fun s derivedQueue => if s = 0 then
  if derivedQueue = expectedQueue then
  .bind (get 88) fun s ns => if s = 0 then
  .bind (field metadata 48) fun s page => if s = 0 then
  .bind (PackageWorkspace.validate (metadata+256) ns page) fun s _ => if s = 0 then
  .bind (validateTyped) fun s _ => if s = 0 then
  .bind (field metadata 248) fun s indexBytes => if s = 0 then
  .bind (equal metadata 232 headerBytes) fun s _ => if s = 0 then
  .bind (equal metadata 240 PackageWorkspace.bytes) fun s _ => if s = 0 then
  .bind (Lemma.Documents.Ink.encodedPageBytes (metadata+3968)) fun s actualIndexBytes => if s = 0 then
  .bind (equal (metadata+3968) 8 Lemma.Documents.Ink.pageRecordVersion) fun s _ => if s = 0 then
  .bind (equal (metadata+3968) 24 page) fun s _ => if s = 0 then
  .bind (field (metadata+3968) 32) fun s chunks => if s = 0 then
  if indexBytes = actualIndexBytes then
  if bytes = 3968+indexBytes then
  .bind (envelopeBounds chunks bytes) fun checked _ => if checked = 0 then
  .bind (put 120 chunks) fun s _ => if s = 0 then
  .bind (put 264 0) fun s _ => if s = 0 then
  .bind (put 112 bytes) fun s _ => if s = 0 then
  .bind (put 128 0) fun s _ => if s = 0 then
  put 0 1
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt checked
  else halt malformed
  else halt malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt malformed
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0


private def restoreMetadataPoll : Action :=
  .bind pollOp fun status _ =>
    if status = IPCABI.wouldBlock then .done 0 0 else
  if status = Protocol.busy then put 0 42 else if status = 0 then
  .bind (get 72) fun s offset => if s = 0 then
  .bind (get 80) fun s count => if s = 0 then
  .bind (responseCount count) fun s _ => if s = 0 then
  .bind (copy (Client.responseData incoming) (metadata+offset) count) fun s _ => if s = 0 then
  .bind (put 144 (offset+count)) fun s _ => if s = 0 then
  put 0 42
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else halt status


/-- Actual local receipts only; the integrating Notebook merges this floor
before deriving a new append-only queue identity. No new Saved is asserted. -/
def frontier : Action :=
  .bind (get 152) fun s queue => if s = 0 then
  .bind (get 200) fun s pointer => if s = 0 then
  .done 0 (if queue < pointer then pointer else queue) else .done s 0 else .done s 0

def restore (ns : UInt64) : Action :=
  if Protocol.namespaceValid ns = 1 then
  .bind (get 0) fun s phase => if s = 0 then
  if phase = 0 then
  .bind (put 88 ns) fun s _ => if s = 0 then
  .bind (put 208 1) fun s _ => if s = 0 then
  .bind (put 264 2) fun s _ => if s = 0 then
  put 0 40
  else .done s 0 else .done s 0 else .done s 0
  else .done Protocol.busy 0
  else .done s 0
  else bad


def retry : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  .bind (get 152) fun s sequence => if s = 0 then
  .bind (get 184) fun s desired => if s = 0 then
  if (if phase = 26 then (1 : UInt64) else if phase = 45 then 1 else 0) = 1 then
  if 0 < sequence then if desired = 1 then put 304 1 else bad else bad
  else .done Protocol.busy 0
  else .done s 0 else .done s 0 else .done s 0

private def changeState (queue status : UInt64) : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  .bind (get 96) fun s current => if s = 0 then
  .bind (get 152) fun s sequence => if s = 0 then
  if phase = 26 then if queue = current then if 0 < sequence then
  .bind (put 184 status) fun s _ => if s = 0 then
  put 0 11
  else .done s 0
  else bad else bad else .done Protocol.busy 0
  else .done s 0 else .done s 0 else .done s 0

/-- Cancellation withdraws only a pending local attempt after an emitted stream.
It cannot retract previously admitted school work; that is a separate request. -/
def cancel (queue : UInt64) : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  .bind (get 96) fun s actual => if s = 0 then
  .bind (get 184) fun s desired => if s = 0 then
  if queue = actual then if phase = 0 then bad else if phase = 27 then bad else if phase = 28 then bad else
  if phase = 29 then bad else if phase = 30 then bad else if desired = 3 then bad else
  put 184 2 else bad else .done s 0 else .done s 0 else .done s 0

/-- Called only after the integrating service admits a bound school commit ACK.
The value is not a transport receipt, checker result, or assessment. -/
def acknowledge (queue schoolCommit : UInt64) : Action :=
  if schoolCommit = 0 then bad else if Format.maximumSequence < schoolCommit then bad else
  .bind (put 312 schoolCommit) fun s _ => if s = 0 then changeState queue 3 else .done s 0


private def ackReady : Action :=
  .bind Syscall.time fun s now => if s = 0 then
  .bind (get 288) fun s next => if s = 0 then
  if now < next then .done 0 0 else
  if 0xffffffffffffffff-5000000 < now then halt resourceLimit else
  .bind (put 288 (now+5000000)) fun s _ => if s = 0 then
  .bind (put 264 2) fun s _ => if s = 0 then
  beginOp 5 ackObject 0 64 0 45
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def ackPoll : Action :=
  .bind pollOp fun status _ =>
  if status = IPCABI.wouldBlock then .done 0 0 else
  .bind (put 264 0) fun s _ => if s = 0 then
  .bind (put 0 26) fun s _ => if s = 0 then
  if status = Protocol.busy then .done 0 0 else
  if status = Format.notFound then .done 0 0 else if status = 0 then
  .bind (responseCount 64) fun s _ => if s = 0 then
  .bind (copy (Client.responseData incoming) chunkHeader 64) fun s _ => if s = 0 then
  .bind (field chunkHeader 0) fun s tag => if s = 0 then
  .bind (field chunkHeader 8) fun s version => if s = 0 then
  .bind (field chunkHeader 16) fun s queue => if s = 0 then
  .bind (field chunkHeader 24) fun s schoolCommit => if s = 0 then
  .bind (field chunkHeader 32) fun s localCommit => if s = 0 then
  .bind (field chunkHeader 40) fun s checksum => if s = 0 then
  .bind (field chunkHeader 48) fun s a => if s = 0 then
  .bind (field chunkHeader 56) fun s b => if s = 0 then
  .bind (get 96) fun s actualQueue => if s = 0 then
  .bind (get 152) fun s actualLocal => if s = 0 then
  .bind (get 280) fun s actualCRC => if s = 0 then
  if tag = ackMagic then if version = 1 then if queue = actualQueue then
  if localCommit = actualLocal then if checksum = actualCRC then if a ||| b = 0 then
     .bind (get 184) fun s desired => if s = 0 then
    if desired = 1 then acknowledge queue schoolCommit else .done 0 0 else .done s 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else halt status else .done s 0 else .done s 0

private def activePump : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  if phase = 0 then .done 0 0 else
  if phase = 1 then preflightStart else if phase = 2 then preflightPoll else
  if phase = 3 then preflightEOF else if phase = 4 then preflightEOFPoll else
  if phase = 5 then beginTransaction 0 6 else if phase = 6 then pollBegin 7 else
  if phase = 7 then upload 0 8 else if phase = 8 then pollUpload 7 else
  if phase = 9 then commit 0 10 else if phase = 10 then pollCommit 0 else
  if phase = 11 then beginTransaction 1 12 else if phase = 12 then pollBegin 13 else
  if phase = 13 then upload 1 14 else if phase = 14 then pollUpload 13 else
  if phase = 15 then commit 1 16 else if phase = 16 then pollCommit 1 else
  if phase = 20 then streamStart else if phase = 21 then streamMetadata else
  if phase = 22 then streamRaw else if phase = 23 then streamRawPoll else
  if phase = 24 then streamRawEmit else if phase = 25 then streamEnd else
  if phase = 27 then terminalReceipt 0x734 else if phase = 28 then terminalReceipt 0x733 else
  if phase = 40 then beginOp 5 pointerObject 0 64 0 41 else if phase = 41 then restorePointerPoll else
  if phase = 42 then restoreMetadata else if phase = 43 then restoreMetadataPoll else
  if phase = 45 then ackPoll else
  if phase = 26 then ackReady else if phase = 29 then .done 0 0 else
  if phase = 30 then .done 0 0 else bad
  else .done s 0

/-- A cancellation waits for the one in-flight IPC to reach its terminal
boundary, then persists withdrawal. It suppresses remaining Console bytes.
A retry intent coalesces while the mailbox read is outstanding. -/
private def normalPump : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  .bind (get 184) fun s desired => if s = 0 then
  if desired = 2 then
    if (if phase = 1 then (1 : UInt64) else if phase = 3 then 1 else if phase = 5 then 1 else 0) = 1 then put 0 29 else
    if (if phase = 20 then (1 : UInt64) else if phase = 21 then 1 else if phase = 22 then 1 else
        if phase = 24 then 1 else if phase = 25 then 1 else if phase = 26 then 1 else 0) = 1 then put 0 11 else activePump
  else if phase = 26 then
    .bind (get 304) fun s retry => if s = 0 then
    if retry = 1 then
      .bind (put 304 0) fun s _ => if s = 0 then put 0 20 else .done s 0
    else activePump else .done s 0
  else activePump else .done s 0 else .done s 0

/-- The parent requests suspension before starting its next ordinary Store
write. A positive value means it must keep deferring that Begin while pumping
this helper. Immutable metadata and raw references survive suspension. -/
def writerActive : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  .done 0 (if phase = 2 then 1 else if phase = 4 then 1 else
    if 6 ≤ phase then if phase ≤ 10 then 1 else
      if 12 ≤ phase then if phase ≤ 16 then 1 else
        if phase = 23 then 1 else if phase = 41 then 1 else if phase = 43 then 1 else
        if phase = 45 then 1 else if phase = 47 then 1 else 0
      else 0
    else 0)
  else .done s 0

def suspend : Action :=
  .bind (put 320 1) fun s _ => if s = 0 then writerActive else .done s 0

def resume : Action :=
  .bind (put 320 0) fun s _ => if s = 0 then
  .bind (get 0) fun s phase => if s = 0 then
  if phase = 46 then
    .bind (get 328) fun s phase => if s = 0 then put 0 phase else .done s 0
  else .done 0 0 else .done s 0 else .done s 0
private def pauseAt (next : UInt64) : Action :=
  .bind (put 328 next) fun s _ => if s = 0 then put 0 46 else .done s 0
private def suspendStage (next isPointer : UInt64) : Action :=
  .bind (get 96) fun s queue => if s = 0 then
  .bind (put 328 next) fun s _ => if s = 0 then
  beginOp 9 (if isPointer = 1 then pointerObject else queue) 0 0 0 47
  else .done s 0 else .done s 0
private def suspendPoll : Action :=
  .bind pollOp fun status _ =>
  if status = IPCABI.wouldBlock then .done 0 0 else
  if (if status = 0 then (1 : UInt64) else if status = Protocol.wrongOwner then 1 else 0) = 1 then
    .bind (put 144 0) fun s _ => if s = 0 then put 0 46 else .done s 0
  else halt status

/-- Only uncommitted confirmed staging is aborted. An in-flight Commit must
settle through its original poll; no abort can erase acknowledged metadata. -/
def pump : Action :=
  .bind (get 0) fun s phase => if s = 0 then
  if phase = 47 then suspendPoll else if phase = 46 then .done 0 0 else
  .bind (get 320) fun s requested => if s = 0 then
  if requested = 1 then
    if phase = 1 then pauseAt 1 else if phase = 3 then pauseAt 3 else
    if phase = 5 then pauseAt 5 else if phase = 11 then pauseAt 11 else
    if phase = 22 then pauseAt 22 else if phase = 26 then pauseAt 26 else
    if phase = 40 then pauseAt 40 else if phase = 42 then pauseAt 42 else
    if phase = 7 then suspendStage 5 0 else if phase = 9 then suspendStage 5 0 else
    if phase = 13 then suspendStage 11 1 else if phase = 15 then suspendStage 11 1 else normalPump
  else normalPump else .done s 0 else .done s 0

end Lemma.Courses.SchoolSubmission
