import Lemma.Core0.Memory
import Lemma.Kernel.Memory.Access
import Lemma.Platform.LemmaSim.IO

/-! Product10 integrity-only successor policy for core0-boot-v0.1.
Paper-v2 hardware compatibility is distinct from Product7; metadata/journal
formats stay v1. Historical Product7 source remains available unchanged.
CRC32 is corruption detection, not authentication. No anti-rollback claim.
The guest owns selection, attempt publication, image loading and installation.
-/
namespace Lemma.Boot.ProductExecuted
open Lemma.Core0.Memory

def crcBit (crc : UInt64) : UInt64 :=
  if crc &&& 1 = 0 then crc >>> 1 else (crc >>> 1) ^^^ 0xedb88320
def crcByte (crc byte : UInt64) : UInt64 :=
  let c := crc ^^^ (byte &&& 255)
  crcBit (crcBit (crcBit (crcBit (crcBit (crcBit (crcBit (crcBit c)))))))
def crcWord (crc word : UInt64) : UInt64 :=
  let c := crcByte crc word
  let c := crcByte c (word >>> 8)
  let c := crcByte c (word >>> 16)
  let c := crcByte c (word >>> 24)
  let c := crcByte c (word >>> 32)
  let c := crcByte c (word >>> 40)
  let c := crcByte c (word >>> 48)
  crcByte c (word >>> 56)
def crcInitial : UInt64 := 0xffffffff
def crcFinish (crc : UInt64) : UInt64 := crc ^^^ 0xffffffff

def sectorBytes : UInt64 := 512
def slotSectors : UInt64 := 32768
def mediumSectors : UInt64 := 65544
def slotFirst (slot : UInt64) : UInt64 := if slot = 0 then 8 else 32776
def maximumSegments : UInt64 := 8
def imageMagic : UInt64 := 0x31474d49414d454c
def metadataMagic : UInt64 := 0x31444d42414d454c
def formatVersion : UInt64 := 1
def compatibility : UInt64 := 0x000a000300010001
def maximumAttempts : UInt64 := 3
def noTrial : UInt64 := 2
def ramFirst : UInt64 := 0x80000000
-- Loader scratch and stack are outside the loaded image range and frame pool.
def ramLimit : UInt64 := 0x81f00000
def scratch : UInt64 := 0x81fc0000
def headerBuffer : UInt64 := scratch + 0x1000
def metadata0Buffer : UInt64 := scratch + 0x2000
def metadata1Buffer : UInt64 := scratch + 0x3000
def romStackTop : UInt64 := 0x82000000
def discoveryBase : UInt64 := 0x87e00000
def discoveryLimit : UInt64 := 3072

def validSpan (start bytes first limit : UInt64) : Bool :=
  if start < first then false else
  if limit < start then false else bytes ≤ limit - start
def validSegment (offset fileBytes memoryBytes destination : UInt64) : Bool :=
  if offset &&& 511 = 0 then
  if destination &&& 7 = 0 then
  if memoryBytes = 0 then false else
  if memoryBytes < fileBytes then false else
  if validSpan offset fileBytes 4096 (slotSectors * 512) then
    validSpan destination memoryBytes ramFirst ramLimit
  else false else false else false
def validDiscovery (bytes checksum : UInt64) : Bool :=
  if 40 ≤ bytes then if bytes ≤ discoveryLimit then checksum ≤ 0xffffffff else false else false
def discoveryWordValid (word bytes : UInt64) : Bool :=
  if word &&& 0xffffffff = 0xedfe0dd0 then
    let a : UInt64 := (word >>> 56) &&& (255 : UInt64)
    let b : UInt64 := (word >>> 48) &&& (255 : UInt64)
    let c : UInt64 := (word >>> 40) &&& (255 : UInt64)
    let d : UInt64 := (word >>> 32) &&& (255 : UInt64)
    let size : UInt64 := a ||| (b <<< 8) ||| (c <<< 16) ||| (d <<< 24)
    size = bytes
  else false
def disjoint (a an b bn : UInt64) : Bool :=
  if a ≤ b then an ≤ b - a else bn ≤ a - b
def headerFieldsValid (magic version identity binding segments entry : UInt64) : Bool :=
  if magic = imageMagic then
  if version = formatVersion then
  if identity = 0 then false else
  if binding = compatibility then
  if segments = 0 then false else
  if maximumSegments < segments then false else
  if entry &&& 3 = 0 then validSpan entry 4 ramFirst 0x80010000 else false
  else false else false else false

def metadataFieldsValid (magic version generation confirmedSlot confirmedId
    trialSlot trialId attempts limit : UInt64) : Bool :=
  if magic = metadataMagic then
  if version = formatVersion then
  if generation = 0 then false else
  if generation = 0xffffffffffffffff then false else
  if confirmedSlot < 2 then
  if confirmedId = 0 then false else
  if limit = maximumAttempts then
    if trialSlot = noTrial then (if trialId = 0 then attempts = 0 else false) else
    if trialSlot < 2 then
    if trialSlot = confirmedSlot then false else
    if trialId = 0 then false else attempts ≤ maximumAttempts
    else false
  else false else false else false else false

-- 0/1 select a metadata sector. 2 means recovery; 3 means conflicting peers.
-- Equal-generation metadata needs full byte equality, not equal CRC values.
def chooseMetadata (valid0 valid1 generation0 generation1 equalBytes : UInt64) : UInt64 :=
  if valid0 = 1 then
    if valid1 = 1 then
      if generation0 < generation1 then 1 else
      if generation1 < generation0 then 0 else
      if equalBytes = 1 then 0 else 3
    else 0
  else if valid1 = 1 then 1 else 2

-- These are selection decisions only. A trial is never handed off before the
-- incremented record has actually completed WRITE followed by BARRIER.
def chooseImage (confirmedSlot trialSlot attempts : UInt64) : UInt64 :=
  if trialSlot < 2 then
    if attempts < maximumAttempts then trialSlot else confirmedSlot
  else confirmedSlot
def needsAttempt (trialSlot attempts : UInt64) : Bool :=
  if trialSlot < 2 then attempts < maximumAttempts else false
def nextMetadataSector (selected : UInt64) : UInt64 := if selected = 0 then 1 else 0
def inactiveSlot (confirmedSlot : UInt64) : UInt64 := if confirmedSlot = 0 then 1 else 0
def canConfirm (bootSlot bootIdentity trialSlot trialIdentity : UInt64) : Bool :=
  if bootSlot < 2 then
  if bootSlot = trialSlot then
    if bootIdentity = trialIdentity then if bootIdentity = 0 then false else true else false
  else false
  else false

private def crcStep (index count : UInt32) (crc base _ _ _ : UInt64) : Action :=
  if index < count then
    .bind (Lemma.Kernel.Memory.Access.read64 (base + index.toUInt64 * 8)) fun s word =>
    if s = 0 then .done 0 (crcWord crc word) else .done s 0
  else .done 0 crc
def sectorChecksum (base : UInt64) : Action :=
  .boundedFoldU64 63 crcStep 63 crcInitial base 0 0 0 fun s crc =>
    if s = 0 then .done 0 (crcFinish crc) else .done s 0

-- Controller register contract. PIO is bounded to a retained 512-byte buffer;
-- the underlying transport supplies raw bytes, outcome/count and a barrier.
def nvBase : UInt64 := 0x10012000
def nvMagic : UInt64 := 0x564e424c
def unavailable : UInt8 := 210
def malformed : UInt8 := 211
def ioFailure : UInt8 := 212
def timeout : UInt8 := 213
def conflict : UInt8 := 214
def recovery : UInt8 := 215
def pending : UInt8 := 216
def wrongReceipt : UInt8 := 217
private def readReg (offset : UInt64) : Action :=
  Lemma.Platform.LemmaSim.IO.read64 (nvBase + offset)
private def writeReg (offset value : UInt64) : Action :=
  Lemma.Platform.LemmaSim.IO.write64 (nvBase + offset) value
private def validKind (kind : UInt64) : Bool :=
  if kind = 1 then true else if kind = 2 then true else kind = 3
private def validSector (kind sector : UInt64) : Bool :=
  if kind = 3 then true else sector < mediumSectors
private def completeState (state : UInt64) : Bool :=
  if state = 2 then true else state = 3
private def matchingRequest (completed request : UInt64) : Bool :=
  if completed = request then if request = 0 then false else true else false
private def submittedRequest (s : UInt8) (request : UInt64) : Bool :=
  if s = pending then if request = 0 then false else true else false
private def cancellationStatus (s : UInt8) : Bool :=
  if s = 0 then true else s = Status.budgetExceeded
private def scratchSpan (address : UInt64) : Bool :=
  if address &&& 7 = 0 then validSpan address 512 scratch (scratch+0x4000) else false
private def invalidGeneration (generation : UInt64) : Bool :=
  if generation = 0 then true else generation = 0xffffffffffffffff
private def expectedHeader (magic version identity binding segments entry expected : UInt64) : Bool :=
  if identity = expected then headerFieldsValid magic version identity binding segments entry else false
private def alignedFullWord (address limit : UInt64) : Bool :=
  if address &&& 7 = 0 then 8 ≤ limit - address else false
private def activeSegment (index count : UInt32) (segments : UInt64) : Bool :=
  if index < count then index.toUInt64 < segments else false

def «initialize» : Action :=
  .bind (readReg 0) fun s magic => if s = 0 then
  if magic = nvMagic then
  .bind (readReg 8) fun s version => if s = 0 then
  if version = 1 then
  .bind (readReg 16) fun s capacity => if s = 0 then
  if mediumSectors ≤ capacity then .done 0 capacity else .done unavailable 0
  else .done s 0 else .done unavailable 0 else .done s 0
  else .done unavailable 0 else .done s 0

-- State0 is idle,1 pending,2 complete,3 cancelled completion. Reading a state
-- never drives an operation forward. ACK is required before the next request.
def submit (kind sector : UInt64) : Action :=
  if validKind kind then
  if validSector kind sector then
  .bind (readReg 24) fun s state => if s = 0 then
  if state = 0 then
  .bind (writeReg 32 sector) fun s _ => if s = 0 then
  .bind (writeReg 40 kind) fun s _ => if s = 0 then
  .bind (readReg 48) fun s request => if s = 0 then
  if request = 0 then .done wrongReceipt 0 else .done pending request
  else .done s 0 else .done s 0 else .done s 0
  else .done pending 0 else .done s 0
  else .done malformed 0 else .done malformed 0

def finish (request : UInt64) : Action :=
  .bind (readReg 24) fun s state => if s = 0 then
  if state = 1 then .done pending request else
  if completeState state then
  .bind (readReg 56) fun s completed => if s = 0 then
  if matchingRequest completed request then
  .bind (readReg 64) fun s result => if s = 0 then
  .bind (readReg 72) fun s bytes => if s = 0 then
  if state = 3 then .done ioFailure bytes else
  if result = 0 then .done 0 bytes else .done ioFailure bytes
  else .done s 0 else .done s 0
  else .done wrongReceipt 0 else .done s 0
  else .done wrongReceipt 0 else .done s 0
def acknowledge (request : UInt64) : Action := writeReg 80 request
def cancel (request : UInt64) : Action := writeReg 88 request

-- read/write buffer is not available while a request is pending. The policy
-- must consume the exact matching completion before using returned bytes.
def bufferRead (index : UInt64) : Action :=
  if index < 64 then readReg (0x200 + index * 8) else .done malformed 0
def bufferWrite (index word : UInt64) : Action :=
  if index < 64 then writeReg (0x200 + index * 8) word else .done malformed 0

private def waitStep (_ _ : UInt32) (_ request _ _ _ : UInt64) : Action :=
  .bind (finish request) fun s count =>
  if s = pending then .done 0 0 else
  if s = 0 then .done Status.iterationStop (count + 1) else .done s count
-- This bounds guest work. It is not a promise that a stalled/disconnected
-- physical peer or backing file must complete. Timed-out work is cancelled and
-- remains busy until its captured external outcome has become quiescent.
def transaction (kind sector : UInt64) : Action :=
  .bind (submit kind sector) fun s request =>
  if submittedRequest s request then
    .boundedFoldU64 100000 waitStep 100000 0 request 0 0 0 fun s bytes =>
    if s = Status.iterationStop then
      if bytes = (if kind = 3 then 1 else 513) then
        .bind (acknowledge request) fun s _ => if s = 0 then .done 0 request else .done s 0
      else .done ioFailure bytes
    else if cancellationStatus s then
      .bind (cancel request) fun _ _ => .done timeout request
    else .bind (acknowledge request) fun _ _ => .done s bytes
  else .done s request

private def readBufferStep (index count : UInt32) (_ destination _ _ _ : UInt64) : Action :=
  if index < count then
    .bind (bufferRead index.toUInt64) fun s word => if s = 0 then
    Lemma.Kernel.Memory.Access.write64 (destination + index.toUInt64 * 8) word
    else .done s 0 else .done 0 0
def readSector (sector destination : UInt64) : Action :=
  if scratchSpan destination then
  .bind (transaction 1 sector) fun s _ => if s = 0 then
  .boundedFoldU64 64 readBufferStep 64 0 destination 0 0 0 fun s _ => .done s 0
  else .done s 0 else .done malformed 0

private def stageBufferStep (index count : UInt32) (_ source _ _ _ : UInt64) : Action :=
  if index < count then
    .bind (Lemma.Kernel.Memory.Access.read64 (source + index.toUInt64 * 8)) fun s word =>
    if s = 0 then bufferWrite index.toUInt64 word else .done s 0 else .done 0 0
def writeSector (sector source : UInt64) : Action :=
  if scratchSpan source then
  .boundedFoldU64 64 stageBufferStep 64 0 source 0 0 0 fun s _ => if s = 0 then
  transaction 2 sector else .done s 0 else .done malformed 0

private def readWord (base index : UInt64) : Action :=
  Lemma.Kernel.Memory.Access.read64 (base + index * 8)
private def writeWord (base index word : UInt64) : Action :=
  Lemma.Kernel.Memory.Access.write64 (base + index * 8) word
private def reservedStep (index count : UInt32) (valid base first _ _ : UInt64) : Action :=
  if index < count then
    .bind (readWord base (first + index.toUInt64)) fun s word => if s = 0 then
    .done 0 (if word = 0 then valid else 0) else .done s 0 else .done 0 valid
def verifySector (base : UInt64) : Action :=
  .bind (sectorChecksum base) fun s checksum => if s = 0 then
  .bind (readWord base 63) fun s expected => if s = 0 then
  if checksum = expected then .done 0 0 else .done malformed 0
  else .done s 0 else .done s 0

def validateMetadata (base : UInt64) : Action :=
  .bind (verifySector base) fun s _ => if s = 0 then
  .bind (readWord base 0) fun s magic => if s = 0 then
  .bind (readWord base 1) fun s version => if s = 0 then
  .bind (readWord base 2) fun s generation => if s = 0 then
  .bind (readWord base 3) fun s confirmedSlot => if s = 0 then
  .bind (readWord base 4) fun s confirmedId => if s = 0 then
  .bind (readWord base 5) fun s trialSlot => if s = 0 then
  .bind (readWord base 6) fun s trialId => if s = 0 then
  .bind (readWord base 7) fun s attempts => if s = 0 then
  .bind (readWord base 8) fun s limit => if s = 0 then
  if metadataFieldsValid magic version generation confirmedSlot confirmedId trialSlot trialId attempts limit then
    .boundedFoldU64 54 reservedStep 54 1 base 9 0 0 fun s valid => if s = 0 then
    if valid = 1 then .done 0 generation else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

-- Publish into the other metadata sector, after a caller has populated all
-- fields and zeroed reserved words. A write receipt alone is never durable.
def publishMetadata (currentSector staged : UInt64) : Action :=
  .bind (readWord staged 2) fun s generation => if s = 0 then
  if invalidGeneration generation then .done malformed 0 else
  .bind (sectorChecksum staged) fun s checksum => if s = 0 then
  .bind (writeWord staged 63 checksum) fun s _ => if s = 0 then
  .bind (validateMetadata staged) fun s _ => if s = 0 then
  .bind (writeSector (nextMetadataSector currentSector) staged) fun s _ => if s = 0 then
  .bind (transaction 3 0) fun s _ => if s = 0 then
  .done 0 (nextMetadataSector currentSector)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0

private def overlapStep (index count : UInt32) (valid base destination memoryBytes _ : UInt64) : Action :=
  if index < count then
  .bind (readWord base (8 + index.toUInt64 * 5 + 2)) fun s previousBytes => if s = 0 then
  .bind (readWord base (8 + index.toUInt64 * 5 + 3)) fun s previousDestination => if s = 0 then
  .done 0 (if disjoint destination memoryBytes previousDestination previousBytes then valid else 0)
  else .done s 0 else .done s 0 else .done 0 valid

private def segmentStep (index count : UInt32) (entryFound base segments entry _ : UInt64) : Action :=
  if index < count then
  let first := 8 + index.toUInt64 * 5
  .bind (readWord base first) fun s offset => if s = 0 then
  .bind (readWord base (first + 1)) fun s fileBytes => if s = 0 then
  .bind (readWord base (first + 2)) fun s memoryBytes => if s = 0 then
  .bind (readWord base (first + 3)) fun s destination => if s = 0 then
  .bind (readWord base (first + 4)) fun s checksum => if s = 0 then
  if index.toUInt64 < segments then
    if validSegment offset fileBytes memoryBytes destination then
    if checksum ≤ 0xffffffff then
    .boundedFoldU64 8 overlapStep index 1 base destination memoryBytes 0 fun s valid => if s = 0 then
      if valid = 1 then
        .done 0 (if validSpan entry 4 destination (destination + fileBytes) then 1 else entryFound)
      else .done malformed 0 else .done s 0
    else .done malformed 0 else .done malformed 0
  else if offset ||| fileBytes ||| memoryBytes ||| destination ||| checksum = 0 then .done 0 entryFound
    else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 entryFound

def validateImageHeader (base expectedIdentity : UInt64) : Action :=
  .bind (verifySector base) fun s _ => if s = 0 then
  .bind (readWord base 0) fun s magic => if s = 0 then
  .bind (readWord base 1) fun s version => if s = 0 then
  .bind (readWord base 2) fun s identity => if s = 0 then
  .bind (readWord base 3) fun s binding => if s = 0 then
  .bind (readWord base 4) fun s segments => if s = 0 then
  .bind (readWord base 5) fun s entry => if s = 0 then
  if expectedHeader magic version identity binding segments entry expectedIdentity then
  .bind (readWord base 6) fun s discoveryBytes => if s = 0 then
  .bind (readWord base 7) fun s discoveryCRC => if s = 0 then
  if validDiscovery discoveryBytes discoveryCRC then
  .boundedFoldU64 15 reservedStep 15 1 base 48 0 0 fun s valid => if s = 0 then
  if valid = 1 then
  .boundedFoldU64 8 segmentStep 8 0 base segments entry 0 fun s found => if s = 0 then
  if found = 1 then .done 0 entry else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def tailStep (index count : UInt32) (crc destination word _ _ : UInt64) : Action :=
  if index < count then
    let byte := (word >>> (index.toUInt64 * 8)) &&& 255
    .bind (Lemma.Kernel.Memory.Access.write8 (destination + index.toUInt64) byte) fun s _ =>
    if s = 0 then .done 0 (crcByte crc byte) else .done s 0 else .done 0 crc
private def copyWordStep (index count : UInt32) (crc fileBytes destination position _ : UInt64) : Action :=
  if index < count then
  let offset := position + index.toUInt64 * 8
  if offset < fileBytes then
    .bind (bufferRead index.toUInt64) fun s word => if s = 0 then
    if 8 ≤ fileBytes - offset then
      .bind (Lemma.Kernel.Memory.Access.write64 (destination + offset) word) fun s _ =>
      if s = 0 then .done 0 (crcWord crc word) else .done s 0
    else .boundedFoldU64 7 tailStep (fileBytes - offset).toUInt32 crc (destination + offset) word 0 0
      fun s crc => .done s crc
    else .done s 0 else .done 0 crc else .done 0 crc
private def fileSectorStep (index count : UInt32) (crc first fileBytes destination _ : UInt64) : Action :=
  if index < count then
  .bind (transaction 1 (first + index.toUInt64)) fun s _ => if s = 0 then
  .boundedFoldU64 64 copyWordStep 64 crc fileBytes destination (index.toUInt64 * 512) 0 fun s crc => .done s crc
  else .done s 0 else .done 0 crc

private def loadDiscovery (slot bytes checksum : UInt64) : Action :=
  .bind (transaction 1 (slotFirst slot+1)) fun s _ => if s = 0 then
  .bind (bufferRead 0) fun s first => if s = 0 then
  if discoveryWordValid first bytes then
  .boundedFoldU64 6 fileSectorStep ((bytes+511)/512).toUInt32 crcInitial
    (slotFirst slot+1) bytes discoveryBase 0 fun s crc => if s = 0 then
  if crcFinish crc = checksum then .done 0 0 else .done malformed 0
  else .done s 0 else .done malformed 0 else .done s 0 else .done s 0

private def zeroTailStep (index count : UInt32) (_ destination _ _ _ : UInt64) : Action :=
  if index < count then Lemma.Kernel.Memory.Access.write8 (destination + index.toUInt64) 0 else .done 0 0
private def zeroWordStep (index count : UInt32) (_ first limit _ _ : UInt64) : Action :=
  if index < count then
    let address := first + index.toUInt64 * 8
    if address < limit then
      if alignedFullWord address limit then
        Lemma.Kernel.Memory.Access.write64 address 0
      else .boundedFoldU64 8 zeroTailStep ((limit-address).toUInt32) 0 address 0 0 0 fun s _ => .done s 0
    else .done 0 0 else .done 0 0
private def zeroBlockStep (index count : UInt32) (_ first limit _ _ : UInt64) : Action :=
  if index < count then
    let address := first + index.toUInt64 * 512
    let remaining := limit - address
    .boundedFoldU64 64 zeroWordStep 64 0 address (if 512 ≤ remaining then address+512 else limit) 0 0 fun s _ => .done s 0
  else .done 0 0

private def loadSegmentStep (index count : UInt32) (_ slot segments _ _ : UInt64) : Action :=
  if activeSegment index count segments then
  let first := 8 + index.toUInt64 * 5
  .bind (readWord headerBuffer first) fun s offset => if s = 0 then
  .bind (readWord headerBuffer (first+1)) fun s fileBytes => if s = 0 then
  .bind (readWord headerBuffer (first+2)) fun s memoryBytes => if s = 0 then
  .bind (readWord headerBuffer (first+3)) fun s destination => if s = 0 then
  .bind (readWord headerBuffer (first+4)) fun s expected => if s = 0 then
  .boundedFoldU64 32768 fileSectorStep ((fileBytes+511)/512).toUInt32 crcInitial
    (slotFirst slot + offset/512) fileBytes destination 0 fun s crc => if s = 0 then
  if crcFinish crc = expected then
    -- Byte tails are zeroed before the next aligned block. No stale image BSS
    -- or previously failed trial bytes may become visible at handoff.
    let bss := destination + fileBytes
    let limit := destination + memoryBytes
    let lead := if bss &&& 7 = 0 then 0 else 8 - (bss &&& 7)
    let lead := if lead ≤ limit - bss then lead else limit - bss
    .boundedFoldU64 7 zeroTailStep lead.toUInt32 0 bss 0 0 0 fun s _ => if s = 0 then
    .boundedFoldU64 65536 zeroBlockStep ((limit-bss-lead+511)/512).toUInt32 0
      (bss+lead) limit 0 0 fun s _ => .done s 0
    else .done s 0
  else .done malformed 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 0

def loadImage (slot identity : UInt64) : Action :=
  if slot < 2 then
  .bind (readSector (slotFirst slot) headerBuffer) fun s _ => if s = 0 then
  .bind (validateImageHeader headerBuffer identity) fun s entry => if s = 0 then
  .bind (readWord headerBuffer 6) fun s discoveryBytes => if s = 0 then
  .bind (readWord headerBuffer 7) fun s discoveryCRC => if s = 0 then
  .bind (loadDiscovery slot discoveryBytes discoveryCRC) fun s _ => if s = 0 then
  .bind (readWord headerBuffer 4) fun s segments => if s = 0 then
  .boundedFoldU64 8 loadSegmentStep 8 0 slot segments 0 0 fun s _ =>
  if s = 0 then .done 0 entry else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done malformed 0

private def compareMetadataStep (index count : UInt32) (equal left right _ _ : UInt64) : Action :=
  if index < count then
  .bind (readWord left index.toUInt64) fun s a => if s = 0 then
  .bind (readWord right index.toUInt64) fun s b => if s = 0 then
  .done 0 (if a = b then equal else 0) else .done s 0 else .done s 0 else .done 0 equal
private def readMetadata (sector buffer : UInt64) : Action :=
  .bind (readSector sector buffer) fun s _ => if s = 0 then validateMetadata buffer else .done s 0
private def confirmedImage (slot identity : UInt64) : Action :=
  .bind (loadImage slot identity) fun s entry =>
  if s = 0 then .done 0 entry else .done recovery 0

-- The running image may confirm only the exact trial observed by ROM. This
-- record lives outside the payload and metadata cleared by the image startup.
def contextMagic : UInt64 := 0x31585443414d454c
private def publishContext (slot identity generation trial entry : UInt64) : Action :=
  .bind (writeWord scratch 0 contextMagic) fun s _ => if s = 0 then
  .bind (writeWord scratch 1 1) fun s _ => if s = 0 then
  .bind (writeWord scratch 2 slot) fun s _ => if s = 0 then
  .bind (writeWord scratch 3 identity) fun s _ => if s = 0 then
  .bind (writeWord scratch 4 generation) fun s _ => if s = 0 then
  .bind (writeWord scratch 5 trial) fun s _ => if s = 0 then .done 0 entry
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
private def confirmedContext (slot identity generation : UInt64) : Action :=
  .bind (confirmedImage slot identity) fun s entry => if s = 0 then
  publishContext slot identity generation 0 entry else .done s 0
private def olderConfirmed (base : UInt64) : Action :=
  .bind (readWord base 2) fun s generation => if s = 0 then
  .bind (readWord base 3) fun s slot => if s = 0 then
  .bind (readWord base 4) fun s identity => if s = 0 then
  confirmedContext slot identity generation else .done s 0 else .done s 0 else .done s 0

private def bootRecord (sector base : UInt64) : Action :=
  .bind (readWord base 2) fun s generation => if s = 0 then
  .bind (readWord base 3) fun s confirmedSlot => if s = 0 then
  .bind (readWord base 4) fun s confirmedId => if s = 0 then
  .bind (readWord base 5) fun s trialSlot => if s = 0 then
  .bind (readWord base 6) fun s trialId => if s = 0 then
  .bind (readWord base 7) fun s attempts => if s = 0 then
  if needsAttempt trialSlot attempts then
    .bind (writeWord base 2 (generation+1)) fun s _ => if s = 0 then
    .bind (writeWord base 7 (attempts+1)) fun s _ => if s = 0 then
    .bind (publishMetadata sector base) fun s _ =>
    if s = 0 then
      .bind (loadImage trialSlot trialId) fun s entry =>
      if s = 0 then publishContext trialSlot trialId (generation+1) 1 entry
      else confirmedContext confirmedSlot confirmedId (generation+1)
    else confirmedContext confirmedSlot confirmedId generation
    else .done s 0 else .done s 0
  else confirmedContext confirmedSlot confirmedId generation
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

def boot : Action :=
  .bind «initialize» fun s _ => if s = 0 then
  .bind (readMetadata 0 metadata0Buffer) fun s0 generation0 =>
  .bind (readMetadata 1 metadata1Buffer) fun s1 generation1 =>
  .boundedFoldU64 64 compareMetadataStep 64 1 metadata0Buffer metadata1Buffer 0 0 fun s equal =>
  if s = 0 then
    let chosen := chooseMetadata (if s0 = 0 then 1 else 0) (if s1 = 0 then 1 else 0)
      generation0 generation1 equal
    if chosen < 2 then
      .bind (bootRecord chosen (if chosen = 0 then metadata0Buffer else metadata1Buffer)) fun s entry =>
      if s = 0 then .done 0 entry else
      if chosen = 0 then
        if s1 = 0 then olderConfirmed metadata1Buffer else .done recovery 0
      else if s0 = 0 then olderConfirmed metadata0Buffer else .done recovery 0
    else if chosen = 3 then .done conflict 0 else .done recovery 0
  else .done s 0 else .done s 0

-- Recovery/installation asks the same checked media/metadata policy for a
-- fresh selector. Failed reads cannot authorize erasing an unknown peer.
def selectedMetadata : Action :=
  .bind (readMetadata 0 metadata0Buffer) fun s0 generation0 =>
  .bind (readMetadata 1 metadata1Buffer) fun s1 generation1 =>
  if s0 = 0 then
    .boundedFoldU64 64 compareMetadataStep 64 1 metadata0Buffer metadata1Buffer 0 0 fun s equal =>
    if s = 0 then .done 0 (chooseMetadata 1 (if s1 = 0 then 1 else 0) generation0 generation1 equal)
    else .done s 0
  else if s1 = 0 then .done 0 1 else
  if s0 = malformed then
    if s1 = malformed then .done 0 2 else .done ioFailure 0
  else .done ioFailure 0

private def checksumTailStep (index count : UInt32) (crc word _ _ _ : UInt64) : Action :=
  if index < count then .done 0 (crcByte crc (word >>> (index.toUInt64*8))) else .done 0 crc
private def checksumWordStep (index count : UInt32) (crc fileBytes position _ _ : UInt64) : Action :=
  if index < count then
  let offset := position + index.toUInt64*8
  if offset < fileBytes then
    .bind (bufferRead index.toUInt64) fun s word => if s = 0 then
    if 8 ≤ fileBytes-offset then .done 0 (crcWord crc word) else
    .boundedFoldU64 7 checksumTailStep (fileBytes-offset).toUInt32 crc word 0 0 0 fun s crc => .done s crc
    else .done s 0 else .done 0 crc else .done 0 crc
private def verifyFileSectorStep (index count : UInt32) (crc first fileBytes _ _ : UInt64) : Action :=
  if index < count then
  .bind (transaction 1 (first+index.toUInt64)) fun s _ => if s = 0 then
  .boundedFoldU64 64 checksumWordStep 64 crc fileBytes (index.toUInt64*512) 0 0 fun s crc => .done s crc
  else .done s 0 else .done 0 crc
private def verifyDiscovery (slot bytes checksum : UInt64) : Action :=
  .bind (transaction 1 (slotFirst slot+1)) fun s _ => if s = 0 then
  .bind (bufferRead 0) fun s first => if s = 0 then
  if discoveryWordValid first bytes then
  .boundedFoldU64 6 verifyFileSectorStep ((bytes+511)/512).toUInt32 crcInitial
    (slotFirst slot+1) bytes 0 0 fun s crc => if s = 0 then
  if crcFinish crc = checksum then .done 0 0 else .done malformed 0
  else .done s 0 else .done malformed 0 else .done s 0 else .done s 0
private def verifySegmentStep (index count : UInt32) (_ slot segments _ _ : UInt64) : Action :=
  if activeSegment index count segments then
  let first := 8+index.toUInt64*5
  .bind (readWord headerBuffer first) fun s offset => if s = 0 then
  .bind (readWord headerBuffer (first+1)) fun s fileBytes => if s = 0 then
  .bind (readWord headerBuffer (first+4)) fun s expected => if s = 0 then
  .boundedFoldU64 32768 verifyFileSectorStep ((fileBytes+511)/512).toUInt32 crcInitial
    (slotFirst slot+offset/512) fileBytes 0 0 fun s crc => if s = 0 then
  if crcFinish crc = expected then .done 0 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done 0 0
def verifyImage (slot identity : UInt64) : Action :=
  if slot < 2 then
  .bind (readSector (slotFirst slot) headerBuffer) fun s _ => if s = 0 then
  .bind (validateImageHeader headerBuffer identity) fun s entry => if s = 0 then
  .bind (readWord headerBuffer 6) fun s discoveryBytes => if s = 0 then
  .bind (readWord headerBuffer 7) fun s discoveryCRC => if s = 0 then
  .bind (verifyDiscovery slot discoveryBytes discoveryCRC) fun s _ => if s = 0 then
  .bind (readWord headerBuffer 4) fun s segments => if s = 0 then
  .boundedFoldU64 8 verifySegmentStep 8 0 slot segments 0 0 fun s _ =>
  if s = 0 then .done 0 entry else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done malformed 0

-- The owner-authorized transport may stage opaque image sectors, but cannot
-- write the confirmed slot or metadata directly through this installer API.
def installSector (confirmedSlot targetSlot relativeSector source : UInt64) : Action :=
  if confirmedSlot < 2 then
  if targetSlot = inactiveSlot confirmedSlot then
  if relativeSector < slotSectors then writeSector (slotFirst targetSlot+relativeSector) source
  else .done malformed 0 else .done malformed 0 else .done malformed 0
def finishInstall (currentSector metadataBase identity : UInt64) : Action :=
  .bind (validateMetadata metadataBase) fun s generation => if s = 0 then
  .bind (readWord metadataBase 3) fun s confirmedSlot => if s = 0 then
  .bind (transaction 3 0) fun s _ => if s = 0 then
  .bind (verifyImage (inactiveSlot confirmedSlot) identity) fun s _ => if s = 0 then
  .bind (readWord metadataBase 5) fun s trialSlot => if s = 0 then
  .bind (readWord metadataBase 6) fun s trialIdentity => if s = 0 then
  -- A lost publication receipt must not restart the attempt budget. This
  -- fresh record and verified image already describe this exact transaction.
  if canConfirm (inactiveSlot confirmedSlot) identity trialSlot trialIdentity then
    .done 0 currentSector
  else
  .bind (writeWord metadataBase 2 (generation+1)) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 5 (inactiveSlot confirmedSlot)) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 6 identity) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 7 0) fun s _ => if s = 0 then
  publishMetadata currentSector metadataBase
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
def confirm (currentSector metadataBase : UInt64) : Action :=
  .bind (validateMetadata metadataBase) fun s generation => if s = 0 then
  .bind (readWord scratch 0) fun s magic => if s = 0 then
  if magic = contextMagic then
  .bind (readWord scratch 1) fun s version => if s = 0 then
  if version = 1 then
  .bind (readWord scratch 2) fun s bootSlot => if s = 0 then
  .bind (readWord scratch 3) fun s bootIdentity => if s = 0 then
  .bind (readWord scratch 4) fun s bootGeneration => if s = 0 then
  if bootGeneration = generation then
  .bind (readWord scratch 5) fun s trial => if s = 0 then
  if trial = 1 then
  .bind (readWord metadataBase 5) fun s trialSlot => if s = 0 then
  .bind (readWord metadataBase 6) fun s trialIdentity => if s = 0 then
  if canConfirm bootSlot bootIdentity trialSlot trialIdentity then
  .bind (writeWord metadataBase 2 (generation+1)) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 3 bootSlot) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 4 bootIdentity) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 5 noTrial) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 6 0) fun s _ => if s = 0 then
  .bind (writeWord metadataBase 7 0) fun s _ => if s = 0 then
  publishMetadata currentSector metadataBase
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done wrongReceipt 0 else .done s 0 else .done s 0
  else .done wrongReceipt 0 else .done s 0 else .done wrongReceipt 0
  else .done s 0 else .done s 0 else .done s 0
  else .done wrongReceipt 0 else .done s 0 else .done wrongReceipt 0
  else .done s 0 else .done s 0

private def clearMetadataStep (index count : UInt32) (_ base _ _ _ : UInt64) : Action :=
  if index < count then writeWord base index.toUInt64 0 else .done 0 0
-- Only the immutable recovery transport may establish a first confirmed
-- image. Existing valid or conflicting metadata rejects this operation.
-- Payload durability and integrity precede both metadata publications.
def establishRecoveryImage (slot identity : UInt64) : Action :=
  if slot < 2 then
  .bind selectedMetadata fun s selected => if s = 0 then
  if selected = 2 then
  .bind (transaction 3 0) fun s _ => if s = 0 then
  .bind (verifyImage slot identity) fun s _ => if s = 0 then
  .boundedFoldU64 64 clearMetadataStep 64 0 metadata0Buffer 0 0 0 fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 0 metadataMagic) fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 1 formatVersion) fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 2 1) fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 3 slot) fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 4 identity) fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 5 noTrial) fun s _ => if s = 0 then
  .bind (writeWord metadata0Buffer 8 maximumAttempts) fun s _ => if s = 0 then
  .bind (publishMetadata 1 metadata0Buffer) fun s _ => if s = 0 then
  publishMetadata 0 metadata0Buffer
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done wrongReceipt 0 else .done s 0 else .done malformed 0

end Lemma.Boot.ProductExecuted
