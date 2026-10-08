import examples.foundation.MonitorProtocol
import examples.foundation.TimerConformance

/-!
A single-address-space diagnostic monitor compiled through Core0 v0.7.
All requests arrive over UART after boot. The foreground never calls the ISR:
the unchanged Timer.dispatch root is reached only by the audited machine vector.
Protocol scratch, the user buffer, lifetime counters and the timer ring are
disjoint fixed intervals. This is checked access, not hardware isolation.
-/
namespace Lemma.Examples.Foundation.Monitor

open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Device.Support

def validBufferRange (offset length : UInt64) : Bool :=
  if offset ≤ 3840 then length ≤ 3840 - offset else false

/-- The interactive monitor deliberately rejects sub-millisecond periods.
One-tick rearming can keep MTIP continuously asserted across return and starve
the foreground. This tested command policy is narrower than Core0's timer API;
it is not a worst-case interrupt-latency or hard-real-time guarantee. -/
def validPeriod (period : UInt64) : Bool :=
  if 10000 ≤ period then period ≤ 1000000 else false

def validFixedQuanta (quanta : UInt64) : Bool := quanta ≤ 4096

def validDelta (delta : UInt64) : Bool :=
  if 0 < delta then delta ≤ 256 else false

def validWorkGoal (before delta : UInt64) : Bool :=
  if validDelta delta then before < 1000000 - delta else false

def scalarEvaluation (selector left right : UInt64) : UInt64 :=
  if selector = 0 then left + right else left ^^^ right

def payloadWord (offset : UInt64) : Action :=
  Action.load64 RegionId.scratch (16 + offset) fun s v => Action.done s v

/-- Public response status is separate from the enclosing Action's successful
transmission status. Malformed bounded requests remain synchronized. -/
def reply (status : UInt8) (requestId v0 v1 v2 v3 : UInt64) : Action :=
  if status = 0 then Protocol.sendResponse status requestId v0 v1 v2 v3
  else
    Action.bind (Timer.increment 136 1) fun s _ =>
      if s = 0 then Protocol.sendResponse status requestId v0 v1 v2 v3
      else Action.done s 0

def errorReply (status : UInt8) (requestId : UInt64) : Action :=
  reply status requestId 0 0 0 0

def restoreReply (old : UInt64) (status : UInt8) (requestId v0 v1 v2 v3 : UInt64) : Action :=
  Action.irqRestore (old = 1) fun s _ =>
    if s = 0 then reply status requestId v0 v1 v2 v3 else Action.done s 0

def irqCount : Action :=
  Action.irqSaveDisable fun s old =>
    if s = 0 then
      Action.bind (Timer.readWord 0) fun rs count => Timer.restoreResult old rs count
    else Action.done s 0

def fillStep (index _count : UInt32) (acc offset byteWord _c2 _c3 : UInt64) : Action :=
  Action.store8 RegionId.scratch (256 + offset + index.toUInt64) byteWord.toUInt8 fun s =>
    if s = 0 then Action.done 0 (acc + byteWord) else Action.done s 0

def checksumStep (index _count : UInt32) (acc offset _c1 _c2 _c3 : UInt64) : Action :=
  Action.load8 RegionId.scratch (256 + offset + index.toUInt64) fun s byte =>
    if s = 0 then Action.done 0 (acc + byte) else Action.done s 0

def initializeCountersStep (index _count : UInt32) (_acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Timer.writeWord (128 + index.toUInt64 * 8) 0

def initializeMonitor : Action :=
  Action.bind (Timer.initializeState 10000) fun ts _ =>
    if ts = 0 then
      Action.boundedFoldU64 4 initializeCountersStep 4 0 0 0 0 0 fun cs _ =>
        if cs = 0 then
          Action.boundedFoldU64 3840 fillStep 3840 0 0 0 0 0 fun s v => Action.done s v
        else Action.done cs 0
    else Action.done ts 0

def statusReply (requestId : UInt64) : Action :=
  Action.bind (Timer.readWord 128) fun s0 requests =>
    if s0 = 0 then
      Action.bind (Timer.readWord 136) fun s1 errors =>
        if s1 = 0 then
          Action.bind (Timer.readWord 144) fun s2 recoveries =>
            if s2 = 0 then
              Action.bind (Timer.readWord 152) fun s3 checksum =>
                if s3 = 0 then reply 0 requestId requests errors recoveries checksum
                else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

def fillBuffer (requestId offset length byteWord : UInt64) : Action :=
  if byteWord ≤ 255 then
    if validBufferRange offset length then
      Action.checkWriteRange RegionId.scratch (256 + offset) length fun rs =>
        if rs = 0 then
          Action.boundedFoldU64 3840 fillStep length.toUInt32 0 offset byteWord 0 0 fun s sum =>
            if s = 0 then reply 0 requestId length sum offset 0
            else errorReply s requestId
        else errorReply rs requestId
    else errorReply Status.outOfBounds requestId
  else errorReply Status.malformedFrame requestId

def fillRequest (requestId : UInt64) : Action :=
  Action.bind (payloadWord 0) fun s0 offset =>
    if s0 = 0 then
      Action.bind (payloadWord 8) fun s1 length =>
        if s1 = 0 then
          Action.bind (payloadWord 16) fun s2 byteWord =>
            if s2 = 0 then fillBuffer requestId offset length byteWord else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

def checksumBuffer (requestId offset length : UInt64) : Action :=
  if validBufferRange offset length then
    Action.checkReadRange RegionId.scratch (256 + offset) length fun rs =>
      if rs = 0 then
        Action.boundedFoldU64 3840 checksumStep length.toUInt32 0 offset 0 0 0 fun s sum =>
          if s = 0 then reply 0 requestId sum length offset 0
          else errorReply s requestId
      else errorReply rs requestId
  else errorReply Status.outOfBounds requestId

def checksumRequest (requestId : UInt64) : Action :=
  Action.bind (payloadWord 0) fun s0 offset =>
    if s0 = 0 then
      Action.bind (payloadWord 8) fun s1 length =>
        if s1 = 0 then checksumBuffer requestId offset length else Action.done s1 0
    else Action.done s0 0

def simpleEvaluation (requestId selector left right : UInt64) : Action :=
  Action.bind irqCount fun s0 before =>
    if s0 = 0 then
      let result := scalarEvaluation selector left right
      Action.bind irqCount fun s1 after =>
        if s1 = 0 then reply 0 requestId result 0 before after else Action.done s1 0
    else Action.done s0 0

def fixedEvaluation (requestId seed quanta : UInt64) : Action :=
  if validFixedQuanta quanta then
    Action.bind irqCount fun s0 before =>
      if s0 = 0 then
        Action.boundedFoldU64 4096 Timer.controlStep quanta.toUInt32 seed 0 0 0 0 fun s checksum =>
          if s = 0 then
            Action.bind irqCount fun s1 after =>
              if s1 = 0 then
                Action.bind (Timer.writeWord 152 checksum) fun ws _ =>
                  if ws = 0 then reply 0 requestId checksum quanta before after
                  else Action.done ws 0
              else Action.done s1 0
          else errorReply s requestId
      else Action.done s0 0
  else errorReply Status.invalidLength requestId

def finishRequiredEvaluation (requestId checksum before delta : UInt64) : Action :=
  Action.bind (Timer.readWord 112) fun qs quanta =>
    if qs = 0 then
      Action.bind irqCount fun cs after =>
        if cs = 0 then
          if before + delta ≤ after then
            Action.bind (Timer.writeWord 152 checksum) fun rs _ =>
              if rs = 0 then reply 0 requestId checksum quanta before after else Action.done rs 0
          else reply Status.missingTimerEvent requestId after 0 0 0
        else Action.done cs 0
    else Action.done qs 0

def completeRequiredEvaluation (requestId seed before delta : UInt64) : Action :=
  Action.bind (Timer.writeWord 112 0) fun ws _ =>
    if ws = 0 then
      Action.boundedFoldU64 1000000 Timer.workStep 1000000 seed (before + delta) 0 0 0 fun s checksum =>
        if s = Status.iterationStop then finishRequiredEvaluation requestId checksum before delta
        else if s = 0 then finishRequiredEvaluation requestId checksum before delta
        else errorReply s requestId
    else Action.done ws 0

def requiredEvaluation (requestId seed delta : UInt64) : Action :=
  if validDelta delta then
    Action.irqSaveDisable fun ms old =>
      if ms = 0 then
        Action.bind (Timer.readWord 0) fun cs before =>
          if cs = 0 then
            Action.bind (Timer.readWord 48) fun as active =>
              if as = 0 then
                if active = 1 then
                  if validWorkGoal before delta then
                    Action.irqRestore (old = 1) fun rs _ =>
                      if rs = 0 then completeRequiredEvaluation requestId seed before delta
                      else Action.done rs 0
                  else restoreReply old Status.invalidLength requestId 0 0 0 0
                else restoreReply old Status.missingTimerEvent requestId before 0 0 0
              else Timer.restoreResult old as 0
          else Timer.restoreResult old cs 0
      else Action.done ms 0
  else errorReply Status.invalidLength requestId

def selectEvaluation (requestId selector left right reserved : UInt64) : Action :=
  if reserved = 0 then
    if selector = 0 then simpleEvaluation requestId selector left right
    else if selector = 1 then simpleEvaluation requestId selector left right
    else if selector = 2 then fixedEvaluation requestId left right
    else if selector = 3 then requiredEvaluation requestId left right
    else errorReply Status.unsupportedCommand requestId
  else errorReply Status.malformedFrame requestId

def evalRequest (requestId : UInt64) : Action :=
  Action.bind (payloadWord 0) fun s0 selector =>
    if s0 = 0 then
      Action.bind (payloadWord 8) fun s1 left =>
        if s1 = 0 then
          Action.bind (payloadWord 16) fun s2 right =>
            if s2 = 0 then
              Action.bind (payloadWord 24) fun s3 reserved =>
                if s3 = 0 then selectEvaluation requestId selector left right reserved
                else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

def runTrap (mode : UInt64) : Action :=
  if mode = 0 then Action.trapEcall fun s mask => Action.done s mask
  else Action.trapBreakpoint fun s mask => Action.done s mask

def finishTrap (requestId before syncBefore mask : UInt64) : Action :=
  Action.irqSaveDisable fun ms old =>
    if ms = 0 then
      Action.bind (Timer.readWord 120) fun ss syncAfter =>
        if ss = 0 then
          Action.bind (Timer.readWord 0) fun cs after =>
            if cs = 0 then
              if syncAfter = syncBefore + 1 then
                Action.bind (Timer.increment 144 1) fun is _ =>
                  if is = 0 then restoreReply old 0 requestId mask 1 before after
                  else Timer.restoreResult old is 0
              else restoreReply old Status.contextMismatch requestId mask 0 0 0
            else Timer.restoreResult old cs 0
        else Timer.restoreResult old ss 0
    else Action.done ms 0

def trapTest (requestId mode : UInt64) : Action :=
  if mode ≤ 1 then
    Action.irqSaveDisable fun ms old =>
      if ms = 0 then
        Action.bind (Timer.readWord 120) fun ss syncBefore =>
          if ss = 0 then
            Action.bind (Timer.readWord 0) fun cs before =>
              if cs = 0 then
                Action.irqRestore (old = 1) fun rs _ =>
                  if rs = 0 then
                    Action.bind (runTrap mode) fun ts mask =>
                      if ts = 0 then
                        if mask = 0 then finishTrap requestId before syncBefore mask
                        else reply Status.contextMismatch requestId mask 0 0 0
                      else errorReply ts requestId
                  else Action.done rs 0
              else Timer.restoreResult old cs 0
          else Timer.restoreResult old ss 0
      else Action.done ms 0
  else errorReply Status.unsupportedCommand requestId

def trapRequest (requestId : UInt64) : Action :=
  Action.bind (payloadWord 0) fun s mode =>
    if s = 0 then trapTest requestId mode else Action.done s 0

/-- Arming failure cannot leave an active interrupt source behind a recoverable
response. The caller's old global MIE is restored only after MTIE is cleared. -/
def startFailure (old requestId : UInt64) (status : UInt8) (detail : UInt64) : Action :=
  Action.timerSetInterrupt false fun ss _ =>
    if ss = 0 then
      Action.timerSetCompare 0xffffffffffffffff fun ps _ =>
        if ps = 0 then
          Action.bind (Timer.writeWord 48 0) fun ws _ =>
            if ws = 0 then restoreReply old status requestId detail 0 0 0
            else Timer.restoreResult old ws 0
        else Timer.restoreResult old ps 0
    else Timer.restoreResult old ss 0

def completeStart (old requestId period : UInt64) : Action :=
  Action.boundedFoldU64 1024 Timer.pendingStep 1024 0 0 0 0 0 fun ps pending =>
    if Timer.witnessedPending ps pending then
      Action.bind (Timer.readWord 0) fun bs before =>
        if bs = 0 then
          if before = 0 then
            Action.timerProbe fun ts mask =>
              if ts = 0 then
                if mask = 0 then
                  Action.bind (Timer.readWord 0) fun cs count =>
                    if cs = 0 then
                      if 0 < count then
                        Action.bind (Timer.readWord 56) fun ds deadline =>
                          if ds = 0 then
                            Action.irqRestore true fun rs _ =>
                              if rs = 0 then reply 0 requestId count period deadline 0
                              else startFailure old requestId rs 0
                          else startFailure old requestId ds 0
                      else startFailure old requestId Status.missingTimerEvent count
                    else startFailure old requestId cs 0
                else startFailure old requestId Status.contextMismatch mask
              else startFailure old requestId ts mask
          else startFailure old requestId Status.contextMismatch before
        else startFailure old requestId bs 0
    else
      if ps = 0 then startFailure old requestId Status.missingTimerEvent 0
      else startFailure old requestId ps 0

def configureStart (old requestId period : UInt64) : Action :=
  Action.timerSetInterrupt false fun ss _ =>
    if ss = 0 then
      Action.bind (Timer.initializeState period) fun is _ =>
        if is = 0 then
          Action.timerReadTime fun ts now =>
            if ts = 0 then
              if Timer.validPeriodTime period now then
                Action.bind (Timer.writeWord 56 now) fun ds _ =>
                  if ds = 0 then
                    Action.bind (Timer.writeWord 48 1) fun ws _ =>
                      if ws = 0 then
                        Action.timerSetCompare now fun cs _ =>
                          if cs = 0 then
                            Action.timerSetInterrupt true fun es _ =>
                              if es = 0 then completeStart old requestId period
                              else startFailure old requestId es 0
                          else startFailure old requestId cs 0
                      else startFailure old requestId ws 0
                  else startFailure old requestId ds 0
              else startFailure old requestId Status.invalidDeadline 0
            else startFailure old requestId ts 0
        else startFailure old requestId is 0
    else startFailure old requestId ss 0

def startTimer (requestId period : UInt64) : Action :=
  if validPeriod period then
    Action.irqSaveDisable fun ms old =>
      if ms = 0 then
        Action.bind (Timer.readWord 48) fun rs active =>
          if rs = 0 then
            if active = 1 then restoreReply old Status.invalidLength requestId 0 0 0 0
            else if active = 0 then configureStart old requestId period
            else restoreReply old Status.contextMismatch requestId active 0 0 0
          else Timer.restoreResult old rs 0
      else Action.done ms 0
  else errorReply Status.invalidDeadline requestId

def startRequest (requestId : UInt64) : Action :=
  Action.bind (payloadWord 0) fun s period =>
    if s = 0 then startTimer requestId period else Action.done s 0

def exitReply (requestId count : UInt64) : Action :=
  Action.bind (Timer.readWord 128) fun rs requests =>
    if rs = 0 then
      Action.bind (Timer.readWord 144) fun ss recoveries =>
        if ss = 0 then
          Action.bind (reply 0 requestId requests recoveries count 0) fun ps _ =>
            if ps = 0 then Action.done Status.iterationStop 0 else Action.done ps 0
        else Action.done ss 0
    else Action.done rs 0

def stopMismatch (old requestId before after : UInt64) (exiting : Bool) : Action :=
  Action.irqRestore (old = 1) fun rs _ =>
    if rs = 0 then
      if exiting then
        Action.bind (Protocol.sendResponse Status.contextMismatch requestId before after 0 0) fun ps _ =>
          if ps = 0 then Action.done Status.contextMismatch before else Action.done ps 0
      else reply Status.contextMismatch requestId before after 0 0
    else Action.done rs 0

def finishStopped (old requestId before after pending : UInt64) (exiting : Bool) : Action :=
  if before = after then
    Action.bind Timer.checkGuards fun gs guard =>
      if gs = 0 then
        Action.irqRestore (old = 1) fun rs _ =>
          if rs = 0 then
            if exiting then exitReply requestId after
            else reply 0 requestId before after 0 pending
          else Action.done rs 0
      else stopMismatch old requestId guard 0 exiting
  else stopMismatch old requestId before after exiting

def stoppedWork (old requestId before : UInt64) (exiting : Bool) : Action :=
  Action.irqRestore true fun rs _ =>
    if rs = 0 then
      Action.boundedFoldU64 8 Timer.controlStep 8 before 0 0 0 0 fun ws checksum =>
        if ws = 0 then
          -- A volatile private witness keeps the bounded shutdown work live
          -- even though the public STOP response contains counts, not a fold.
          Action.bind (Timer.writeWord 160 checksum) fun witnessStatus _ =>
            if witnessStatus = 0 then
              Action.irqSaveDisable fun ms _ =>
                if ms = 0 then
                  Action.bind (Timer.readWord 0) fun cs after =>
                    if cs = 0 then
                      Action.timerReadPending fun ps pending =>
                        if ps = 0 then finishStopped old requestId before after pending exiting
                        else Timer.restoreResult old ps 0
                    else Timer.restoreResult old cs 0
                else Action.done ms 0
            else Timer.restoreResult old witnessStatus 0
        else Timer.restoreResult old ws 0
    else Action.done rs 0

def stopTimer (requestId : UInt64) (exiting : Bool) : Action :=
  Action.irqSaveDisable fun ms old =>
    if ms = 0 then
      Action.timerSetInterrupt false fun ss _ =>
        if ss = 0 then
          Action.timerSetCompare 0xffffffffffffffff fun ps _ =>
            if ps = 0 then
              Action.bind (Timer.writeWord 48 0) fun as _ =>
                if as = 0 then
                  Action.bind (Timer.readWord 0) fun cs before =>
                    if cs = 0 then stoppedWork old requestId before exiting
                    else Timer.restoreResult old cs 0
                else Timer.restoreResult old as 0
            else Timer.restoreResult old ps 0
        else Timer.restoreResult old ss 0
    else Action.done ms 0

def tickWords (old requestId o0 o1 o2 o3 : UInt64) : Action :=
  Action.bind (Timer.readWord o0) fun s0 v0 =>
    if s0 = 0 then
      Action.bind (Timer.readWord o1) fun s1 v1 =>
        if s1 = 0 then
          Action.bind (Timer.readWord o2) fun s2 v2 =>
            if s2 = 0 then
              Action.bind (Timer.readWord o3) fun s3 v3 =>
                if s3 = 0 then restoreReply old 0 requestId v0 v1 v2 v3
                else Timer.restoreResult old s3 0
            else Timer.restoreResult old s2 0
        else Timer.restoreResult old s1 0
    else Timer.restoreResult old s0 0

def finishRecord (old requestId sequence time pc cause : UInt64) (pop : Bool) : Action :=
  Action.bind (Timer.readWord 88) fun ss lastSequence =>
    if ss = 0 then
      Action.bind (Timer.readWord 96) fun ts lastTime =>
        if ts = 0 then
          if Timer.validRecord sequence time pc cause lastSequence lastTime then
            Action.bind Timer.checkGuards fun gs _ =>
              if gs = 0 then
                if pop then
                  Action.bind Timer.consumeOne fun cs _ =>
                    if cs = 0 then restoreReply old 0 requestId sequence time pc cause
                    else Timer.restoreResult old cs 0
                else restoreReply old 0 requestId sequence time pc cause
              else restoreReply old Status.contextMismatch requestId sequence 0 0 0
          else restoreReply old Status.contextMismatch requestId sequence 0 0 0
        else Timer.restoreResult old ts 0
    else Timer.restoreResult old ss 0

def readRecord (old requestId base : UInt64) (pop : Bool) : Action :=
  Action.bind (Timer.readWord base) fun s0 sequence =>
    if s0 = 0 then
      Action.bind (Timer.readWord (base + 8)) fun s1 time =>
        if s1 = 0 then
          Action.bind (Timer.readWord (base + 16)) fun s2 pc =>
            if s2 = 0 then
              Action.bind (Timer.readWord (base + 24)) fun s3 cause =>
                if s3 = 0 then finishRecord old requestId sequence time pc cause pop
                else Timer.restoreResult old s3 0
            else Timer.restoreResult old s2 0
        else Timer.restoreResult old s1 0
    else Timer.restoreResult old s0 0

def tickRecord (old requestId index : UInt64) (pop : Bool) : Action :=
  Action.bind (Timer.readWord 16) fun hs head =>
    if hs = 0 then
      Action.bind (Timer.readWord 24) fun ts tail =>
        if ts = 0 then
          if Timer.validRing head tail then
            if head = tail then
              if pop then
                Action.bind Timer.checkGuards fun gs _ =>
                  if gs = 0 then restoreReply old 0 requestId 0 0 0 0
                  else restoreReply old Status.contextMismatch requestId 0 0 0 0
              else restoreReply old Status.outOfBounds requestId 0 0 0 0
            else if index < head - tail then
              readRecord old requestId (256 + ((tail + index) % 16) * 32) pop
            else restoreReply old Status.outOfBounds requestId 0 0 0 0
          else restoreReply old Status.contextMismatch requestId head tail 0 0
        else Timer.restoreResult old ts 0
    else Timer.restoreResult old hs 0

def selectTicks (old requestId mode index : UInt64) : Action :=
  if mode = 3 then tickRecord old requestId index false
  else if index = 0 then
    if mode = 0 then tickWords old requestId 0 16 24 32
    else if mode = 1 then tickWords old requestId 40 8 72 56
    else if mode = 2 then tickWords old requestId 48 64 88 96
    else if mode = 4 then tickRecord old requestId 0 true
    else restoreReply old Status.unsupportedCommand requestId 0 0 0 0
  else
    if mode ≤ 4 then restoreReply old Status.outOfBounds requestId 0 0 0 0
    else restoreReply old Status.unsupportedCommand requestId 0 0 0 0

def ticksRequest (requestId : UInt64) : Action :=
  Action.bind (payloadWord 0) fun ms mode =>
    if ms = 0 then
      Action.bind (payloadWord 8) fun is index =>
        if is = 0 then
          Action.irqSaveDisable fun ss old =>
            if ss = 0 then selectTicks old requestId mode index else Action.done ss 0
        else Action.done is 0
    else Action.done ms 0

def dispatchKnown (requestId command : UInt64) : Action :=
  if command = 1 then reply 0 requestId Protocol.helloTag 7 1 0x3ff
  else if command = 2 then statusReply requestId
  else if command = 3 then evalRequest requestId
  else if command = 4 then fillRequest requestId
  else if command = 5 then checksumRequest requestId
  else if command = 6 then trapRequest requestId
  else if command = 7 then startRequest requestId
  else if command = 8 then stopTimer requestId false
  else if command = 9 then ticksRequest requestId
  else stopTimer requestId true

def dispatchRequest (requestId command length : UInt64) : Action :=
  let expected := Protocol.expectedLength command
  if expected = 255 then errorReply Status.unsupportedCommand requestId
  else if length = expected then dispatchKnown requestId command
  else errorReply Status.invalidLength requestId

def checkedHeader (magic : UInt32) (version flags command length requestId : UInt64) : Action :=
  Action.bind (Timer.increment 128 1) fun cs _ =>
    if cs = 0 then
      if Protocol.validHeader magic version flags then dispatchRequest requestId command length
      else errorReply Status.malformedFrame requestId
    else Action.done cs 0

def parseHeader : Action :=
  Action.load32 RegionId.scratch 0 fun s0 magic =>
    if s0 = 0 then
      Action.load8 RegionId.scratch 4 fun s1 version =>
        if s1 = 0 then
          Action.load8 RegionId.scratch 5 fun s2 command =>
            if s2 = 0 then
              Action.load8 RegionId.scratch 6 fun s3 length =>
                if s3 = 0 then
                  Action.load8 RegionId.scratch 7 fun s4 flags =>
                    if s4 = 0 then
                      Action.load64 RegionId.scratch 8 fun s5 requestId =>
                        if s5 = 0 then checkedHeader magic.toUInt32 version flags command length requestId
                        else Action.done s5 0
                    else Action.done s4 0
                else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

def handleRequest : Action :=
  Action.bind receiveHeader fun hs _ =>
    if hs = 0 then
      Action.load8 RegionId.scratch 6 fun ls length =>
        if ls = 0 then
          if length ≤ Protocol.maximumPayload then
            Action.bind (Protocol.receivePayload length.toUInt32) fun ps _ =>
              if ps = 0 then parseHeader else Action.done ps 0
          else Action.done Status.invalidLength 0
        else Action.done ls 0
    else Action.done hs 0

def sessionStep (_index _count : UInt32) (acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.bind handleRequest fun s v =>
    if s = 0 then Action.done 0 (acc + 1) else Action.done s v

/-- Every terminal receive/transmit/budget error masks delivery and parks the
timer before returning a failing status to the fixed machine finisher. -/
def terminalCleanup (status : UInt8) : Action :=
  Action.irqSaveDisable fun ms _ =>
    if ms = 0 then
      Action.timerSetInterrupt false fun ss _ =>
        if ss = 0 then
          Action.timerSetCompare 0xffffffffffffffff fun ps _ =>
            if ps = 0 then
              Action.bind (Timer.writeWord 48 0) fun ws _ =>
                if ws = 0 then Action.done status 0 else Action.done ws 0
            else Action.done ps 0
        else Action.done ss 0
    else Action.done ms 0

def serve : Action :=
  Action.boundedFoldU64 256 sessionStep Protocol.sessionBudget 0 0 0 0 0 fun s _ =>
    if s = Status.iterationStop then
      Action.bind drain fun ds _ =>
        if ds = 0 then terminalCleanup 0 else terminalCleanup ds
    else if s = 0 then terminalCleanup Status.budgetExceeded
    else terminalCleanup s

def foreground : Action :=
  Action.bind initializeMonitor fun is _ =>
    if is = 0 then
      Action.uartEnableAndResetFifo fun fs =>
        if fs = 0 then
          Action.bind Protocol.sendReady fun rs _ =>
            if rs = 0 then serve else terminalCleanup rs
        else terminalCleanup fs
    else terminalCleanup is

end Lemma.Examples.Foundation.Monitor
