import examples.foundation.TrapConformance
import Lemma.Core0.Timer

/-!
Gate 8's compiled single-hart timer policy and foreground computation.
All shared words are checked volatile RAM. Foreground ring operations execute
with global MIE saved/masked; the non-nested ISR is its only other writer.
Hardware-entry counts never include skipped nominal periods or host activity.
-/
namespace Lemma.Examples.Foundation.Timer

open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Device.Support

def timerCause : UInt64 := 0x8000000000000007
def maximumTime : UInt64 := 0x7fffffffffffffff
def missingEvent : UInt8 := 21
def invalidDeadline : UInt8 := 22
def ringCapacity : UInt64 := 16
def workQuantum : UInt32 := 128

/-- Header: IRQ count, spurious, head, tail, overflow, skipped, active,
deadline, period, last ISR time, catch-up steps, last consumed sequence,
last consumed time, integrity flag, completed work quanta, sync count.
The ring starts at 256; sixteen 32-byte records end at 768. -/
def readWord (offset : UInt64) : Action :=
  Action.load64 RegionId.events offset fun s v => Action.done s v

def writeWord (offset value : UInt64) : Action :=
  Action.store64 RegionId.events offset value fun s => Action.done s 0

def increment (offset amount : UInt64) : Action :=
  Action.bind (readWord offset) fun s v =>
    if s = 0 then writeWord offset (v + amount) else Action.done s 0

def clearStep (index _count : UInt32) (_acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  writeWord (index.toUInt64 * 8) 0

def initializeState (period : UInt64) : Action :=
  Action.boundedFoldU64 16 clearStep 16 0 0 0 0 0 fun s _ =>
    if s = 0 then
      Action.bind (writeWord 64 period) fun p _ =>
        if p = 0 then
          Action.bind (writeWord 240 0x4c4d3852494e4701) fun g _ =>
            if g = 0 then writeWord 768 0x4c4d3852494e4702 else Action.done g 0
        else Action.done p 0
    else Action.done s 0

def validPc (pc : UInt64) : Bool :=
  if 0x80000000 ≤ pc then
    if pc < 0x807f0000 then (pc &&& 3) = 0 else false
  else false

def timerPolicy (cause pc mstatus tval mie : UInt64) : Bool :=
  if cause = timerCause then
    if validPc pc then
      if (mstatus &&& 0x21888) = 0x1880 then
        if mie = 0x80 then tval = 0 else false
      else false
    else false
  else false

def validInterruptEnable (mie : UInt64) : Bool :=
  if mie = 0 then true else mie = 0x80

/-- Synchronous recovery remains restricted to the same explicit four-byte
sites, but MPIE and MTIE may reflect an enabled foreground timer. -/
def syncResume (cause pc mstatus tval mie ecallSite ecallResume
    breakSite breakResume : UInt64) : UInt64 :=
  if (mstatus &&& 0x21808) = 0x1800 then
    if validInterruptEnable mie then
      if cause = 11 then
        if pc = ecallSite then
          if tval = 0 then ecallResume else 0
        else 0
      else if cause = 3 then
        if pc = breakSite then
          if tval = 0 then breakResume
          else if tval = pc then breakResume
          else 0
        else 0
      else 0
    else 0
  else 0

def validRing (head tail : UInt64) : Bool :=
  if tail ≤ head then head - tail ≤ ringCapacity else false

def validPeriodTime (period now : UInt64) : Bool :=
  if 0 < period then
    if period ≤ 1000000 then now ≤ maximumTime - period else false
  else false

def validRecord (sequence now pc cause lastSequence lastTime : UInt64) : Bool :=
  if lastSequence < sequence then
    if lastTime ≤ now then
      if validPc pc then cause = timerCause else false
    else false
  else false

def initialDeadline (scenario now : UInt64) : UInt64 :=
  if scenario = 2 then 0 else now

def shutdownQuanta (scenario : UInt64) : UInt32 :=
  if scenario = 3 then 512 else 1

def retainedRecords (head : UInt64) : UInt64 :=
  if head < ringCapacity then head else ringCapacity

def shouldConsume (scenario : UInt64) (index : UInt32) : Bool :=
  if scenario = 4 then (index &&& 3) = 0 else false

def validGuards (low high : UInt64) : Bool :=
  if low = 0x4c4d3852494e4701 then high = 0x4c4d3852494e4702 else false

def ringDrained (head tail count overflow : UInt64) : Bool :=
  if head = tail then count = head + overflow else false

def witnessedPending (status : UInt8) (pending : UInt64) : Bool :=
  if status = Status.iterationStop then pending = 1 else false

def enqueue (sequence now pc : UInt64) : Action :=
  Action.bind (readWord 16) fun hs head =>
    if hs = 0 then
      Action.bind (readWord 24) fun ts tail =>
        if ts = 0 then
          if validRing head tail then
            if head - tail < ringCapacity then
              let base := 256 + (head % ringCapacity) * 32
              Action.bind (writeWord base sequence) fun s0 _ =>
                if s0 = 0 then
                  Action.bind (writeWord (base + 8) now) fun s1 _ =>
                    if s1 = 0 then
                      Action.bind (writeWord (base + 16) pc) fun s2 _ =>
                        if s2 = 0 then
                          Action.bind (writeWord (base + 24) timerCause) fun s3 _ =>
                            if s3 = 0 then writeWord 16 (head + 1) else Action.done s3 0
                        else Action.done s2 0
                    else Action.done s1 0
                else Action.done s0 0
            else increment 32 1
          else Action.done Status.contextMismatch head
        else Action.done ts 0
    else Action.done hs 0

/-- Constant-work catch-up: reset phase to now+period, recording missed nominal
periods rather than replaying them or pretending they were hardware entries.
The admitted half-range leaves addition nonwrapping. -/
def rearm (now : UInt64) : Action :=
  Action.bind (readWord 64) fun ps period =>
    if ps = 0 then
      if validPeriodTime period now then
        Action.bind (readWord 56) fun ds deadline =>
          if ds = 0 then
            if deadline ≤ now then
              Action.bind (increment 40 ((now - deadline) / period)) fun ss _ =>
                if ss = 0 then
                  Action.bind (writeWord 80 1) fun cs _ =>
                    if cs = 0 then
                      Action.bind (writeWord 56 (now + period)) fun ws _ =>
                        if ws = 0 then Action.timerSetCompare (now + period) fun s v => Action.done s v
                        else Action.done ws 0
                    else Action.done cs 0
                else Action.done ss 0
            else
              Action.bind (increment 8 1) fun ss _ =>
                if ss = 0 then Action.timerSetCompare deadline fun s v => Action.done s v
                else Action.done ss 0
          else Action.done ds 0
      else Action.done invalidDeadline now
    else Action.done ps 0

def interrupt (pc : UInt64) : Action :=
  Action.bind (readWord 48) fun activeStatus active =>
    if activeStatus = 0 then
      if active = 1 then
        Action.timerReadTime fun clockStatus now =>
          if clockStatus = 0 then
            Action.bind (readWord 0) fun countStatus count =>
              if countStatus = 0 then
                if count < 1000000 then
                  Action.bind (writeWord 0 (count + 1)) fun ws _ =>
                    if ws = 0 then
                      Action.bind (writeWord 72 now) fun ns _ =>
                        if ns = 0 then
                          Action.bind (enqueue (count + 1) now pc) fun es _ =>
                            if es = 0 then rearm now else Action.done es 0
                        else Action.done ns 0
                    else Action.done ws 0
                else Action.done Status.budgetExceeded count
              else Action.done countStatus 0
          else Action.done clockStatus 0
      else Action.done Status.unexpectedTrap pc
    else Action.done activeStatus 0

def dispatch (cause pc mstatus tval mie ecallSite ecallResume
    breakSite breakResume : UInt64) : Action :=
  if timerPolicy cause pc mstatus tval mie then
    Action.bind (interrupt pc) fun s _ => Action.done s pc
  else
    let resume := syncResume cause pc mstatus tval mie ecallSite ecallResume breakSite breakResume
    if resume = 0 then
      Lemma.Examples.Foundation.Trap.fatalDiagnostic cause pc mstatus tval mie
    else
      Action.bind (increment 120 1) fun s _ => Action.done s resume

/-- Caller holds global MIE masked; the ISR cannot publish a partially read
record. Drop gaps are permitted, but sequence/time must progress monotonically. -/
def consumeOne : Action :=
  Action.bind (readWord 16) fun hs head =>
    if hs = 0 then
      Action.bind (readWord 24) fun ts tail =>
        if ts = 0 then
          if validRing head tail then
            if tail = head then Action.done 0 0
            else
              let base := 256 + (tail % ringCapacity) * 32
              Action.bind (readWord base) fun ss sequence =>
                if ss = 0 then
                  Action.bind (readWord (base + 8)) fun ns now =>
                    if ns = 0 then
                      Action.bind (readWord (base + 16)) fun ps pc =>
                        if ps = 0 then
                          Action.bind (readWord (base + 24)) fun cs cause =>
                            if cs = 0 then
                              Action.bind (readWord 88) fun ls lastSequence =>
                                if ls = 0 then
                                  Action.bind (readWord 96) fun ls2 lastTime =>
                                    if ls2 = 0 then
                                      if validRecord sequence now pc cause lastSequence lastTime then
                                        Action.bind (writeWord 88 sequence) fun w0 _ =>
                                          if w0 = 0 then
                                            Action.bind (writeWord 96 now) fun w1 _ =>
                                              if w1 = 0 then writeWord 24 (tail + 1) else Action.done w1 0
                                          else Action.done w0 0
                                      else Action.done Status.contextMismatch sequence
                                    else Action.done ls2 0
                                else Action.done ls 0
                            else Action.done cs 0
                        else Action.done ps 0
                    else Action.done ns 0
                else Action.done ss 0
          else Action.done Status.contextMismatch head
        else Action.done ts 0
    else Action.done hs 0

def restoreResult (old : UInt64) (status : UInt8) (value : UInt64) : Action :=
  Action.irqRestore (old = 1) fun s _ =>
    if s = 0 then Action.done status value else Action.done s 0

def consumeCritical : Action :=
  Action.irqSaveDisable fun s old =>
    if s = 0 then
      Action.bind consumeOne fun result value => restoreResult old result value
    else Action.done s 0

def mixStep (index _count : UInt32) (acc outer _c1 _c2 _c3 : UInt64) : Action :=
  Action.done 0 (Lemma.Examples.Foundation.Trap.mix (outer.toUInt32 * workQuantum + index) acc)

def controlStep (index _count : UInt32) (acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.boundedFoldU64 128 mixStep workQuantum acc index.toUInt64 0 0 0 fun s v => Action.done s v

def workBody (index : UInt32) (acc : UInt64) : Action :=
  Action.bind (controlStep index 0 acc 0 0 0 0) fun s v =>
    if s = 0 then
      Action.bind (writeWord 112 (index.toUInt64 + 1)) fun ws _ =>
        if ws = 0 then Action.done 0 v else Action.done ws 0
    else Action.done s v

def workStep (index _count : UInt32) (acc goal scenario _c2 _c3 : UInt64) : Action :=
  Action.bind (readWord 0) fun s count =>
    if s = 0 then
      if goal ≤ count then Action.done Status.iterationStop acc
      else
        if shouldConsume scenario index then
          Action.bind consumeCritical fun cs _ =>
            if cs = 0 then workBody index acc else Action.done cs 0
        else workBody index acc
    else Action.done s 0

def pendingStep (_index _count : UInt32) (_acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.timerReadPending fun s pending =>
    if s = 0 then
      if pending = 1 then Action.done Status.iterationStop 1 else Action.done 0 0
    else Action.done s 0

def failure (status : UInt8) (value : UInt64) : Action :=
  Action.bind (sendResponse status 0x81ff value) fun s _ =>
    if s = 0 then Action.bind drain fun _ _ => Action.done status value
    else Action.done s 0

def checkGuards : Action :=
  Action.bind (readWord 240) fun s0 low =>
    if s0 = 0 then
      Action.bind (readWord 768) fun s1 high =>
        if s1 = 0 then
          if validGuards low high then Action.done 0 0
          else Action.done Status.contextMismatch 1
        else Action.done s1 0
    else Action.done s0 0

def statValue (index : UInt32) (checksum iterations pending before after : UInt64) : Action :=
  if index = 0 then Action.done 0 checksum
  else if index = 1 then Action.done 0 iterations
  else if index = 2 then readWord 0
  else if index = 3 then readWord 16
  else if index = 4 then readWord 24
  else if index = 5 then readWord 32
  else if index = 6 then readWord 40
  else if index = 7 then readWord 8
  else if index = 8 then readWord 80
  else if index = 9 then Action.done 0 0
  else if index = 10 then Action.done 0 pending
  else if index = 11 then Action.done 0 before
  else if index = 12 then Action.done 0 after
  else if index = 13 then checkGuards
  else if index = 14 then readWord 88
  else if index = 15 then readWord 96
  else if index = 16 then readWord 72
  else if index = 17 then readWord 56
  else if index = 18 then Action.timerReadTime fun s v => Action.done s v
  else if index = 19 then Action.timerReadPending fun s v => Action.done s v
  else
    Action.bind (readWord 16) fun s head =>
      if s = 0 then
        if 0 < head then
          readWord (256 + ((head - 1) % ringCapacity) * 32 + (index.toUInt64 - 20) * 8)
        else Action.done Status.contextMismatch head
      else Action.done s 0

def statStep (index _count : UInt32) (checksum iterations pending before after : UInt64) : Action :=
  Action.bind (statValue index checksum iterations pending before after) fun s value =>
    if s = 0 then
      Action.bind (sendResponse 0 (0x8101 + index.toUInt64) value) fun ss _ => Action.done ss checksum
    else Action.done s 0

def dumpStep (index _count : UInt32) (_acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.bind (readWord (256 + index.toUInt64 * 8)) fun s value =>
    if s = 0 then sendResponse 0 (0x8200 + index.toUInt64) value
    else Action.done s 0

def emitStats (checksum iterations pending before after : UInt64) : Action :=
  Action.boundedFoldU64 24 statStep 24 checksum iterations pending before after fun s _ =>
    if s = 0 then
      Action.bind (readWord 16) fun hs head =>
        if hs = 0 then
          let records := retainedRecords head
          Action.boundedFoldU64 64 dumpStep (records * 4).toUInt32 0 0 0 0 0 fun ds _ =>
            if ds = 0 then drain else Action.done ds 0
        else Action.done hs 0
    else Action.done s 0

def drainStep (_index _count : UInt32) (_acc _c0 _c1 _c2 _c3 : UInt64) : Action := consumeOne

def validateRing : Action :=
  Action.boundedFoldU64 16 drainStep 16 0 0 0 0 0 fun s _ =>
    if s = 0 then
      Action.bind (readWord 0) fun cs count =>
        if cs = 0 then
          Action.bind (readWord 16) fun hs head =>
            if hs = 0 then
              Action.bind (readWord 24) fun ts tail =>
                if ts = 0 then
                  Action.bind (readWord 32) fun os overflow =>
                    if os = 0 then
                      if ringDrained head tail count overflow then checkGuards
                      else Action.done Status.contextMismatch count
                    else Action.done os 0
                else Action.done ts 0
            else Action.done hs 0
        else Action.done cs 0
    else Action.done s 0

def finish (seed checksum goal pending scenario : UInt64) : Action :=
  Action.irqSaveDisable fun maskStatus _ =>
    if maskStatus = 0 then
      Action.timerSetInterrupt false fun stopStatus _ =>
        if stopStatus = 0 then
          Action.timerSetCompare 0xffffffffffffffff fun parkStatus _ =>
            if parkStatus = 0 then
              Action.bind (writeWord 48 0) fun activeStatus _ =>
                if activeStatus = 0 then
                  Action.bind (readWord 0) fun beforeStatus before =>
                    if beforeStatus = 0 then
                      if goal ≤ before then
                        Action.irqRestore true fun restoreStatus _ =>
                          if restoreStatus = 0 then
                            let shutdownWork := shutdownQuanta scenario
                            Action.boundedFoldU64 512 controlStep shutdownWork seed 0 0 0 0 fun ws _ =>
                              if ws = 0 then
                                Action.irqSaveDisable fun ms _ =>
                                  if ms = 0 then
                                    Action.bind (readWord 0) fun afterStatus after =>
                                      if afterStatus = 0 then
                                        if after = before then
                                          Action.bind (readWord 112) fun is iterations =>
                                            if is = 0 then
                                              Action.boundedFoldU64 1000000 controlStep iterations.toUInt32 seed 0 0 0 0 fun referenceStatus reference =>
                                                if referenceStatus = 0 then
                                                  if reference = checksum then
                                                    Action.bind validateRing fun ringStatus _ =>
                                                      if ringStatus = 0 then emitStats checksum iterations pending before after
                                                      else Action.done ringStatus 0
                                                  else failure Status.contextMismatch checksum
                                                else Action.done referenceStatus 0
                                            else Action.done is 0
                                        else failure Status.contextMismatch after
                                      else Action.done afterStatus 0
                                  else Action.done ms 0
                              else Action.done ws 0
                          else Action.done restoreStatus 0
                      else failure missingEvent before
                    else Action.done beforeStatus 0
                else Action.done activeStatus 0
            else Action.done parkStatus 0
        else Action.done stopStatus 0
    else Action.done maskStatus 0

def runWork (seed goal pending scenario : UInt64) : Action :=
  Action.irqRestore true fun enableStatus _ =>
    if enableStatus = 0 then
      Action.boundedFoldU64 1000000 workStep 1000000 seed goal scenario 0 0 fun workStatus checksum =>
        if workStatus = Status.iterationStop then finish seed checksum goal pending scenario
        else if workStatus = 0 then finish seed checksum goal pending scenario
        else Action.done workStatus checksum
    else Action.done enableStatus 0

/-- Observe actual pending state while the dispatcher count is still zero,
then enable MIE only inside the full-register asynchronous probe. -/
def pendingAndProbe (seed goal scenario : UInt64) : Action :=
  Action.boundedFoldU64 1024 pendingStep 1024 0 0 0 0 0 fun pendingStatus pending =>
    if witnessedPending pendingStatus pending then
      Action.bind (readWord 0) fun cs before =>
        if cs = 0 then
          if before = 0 then
            Action.timerProbe fun probeStatus mask =>
              if probeStatus = 0 then
                if mask = 0 then
                  Action.bind (readWord 0) fun countStatus count =>
                    if countStatus = 0 then
                      if 0 < count then runWork seed goal pending scenario
                      else failure missingEvent count
                    else Action.done countStatus 0
                else failure Status.contextMismatch mask
              else Action.done probeStatus mask
          else failure Status.contextMismatch before
        else Action.done cs 0
    else
      if pendingStatus = 0 then failure missingEvent 0
      else Action.done pendingStatus pending

def arm (seed goal period scenario : UInt64) : Action :=
  Action.irqSaveDisable fun maskStatus _ =>
    if maskStatus = 0 then
      Action.timerSetInterrupt false fun stopStatus _ =>
        if stopStatus = 0 then
          Action.bind (initializeState period) fun initStatus _ =>
            if initStatus = 0 then
              Action.timerReadTime fun timeStatus now =>
                if timeStatus = 0 then
                  if now ≤ maximumTime - period then
                    let deadline := initialDeadline scenario now
                    Action.bind (writeWord 56 deadline) fun ds _ =>
                      if ds = 0 then
                        Action.bind (writeWord 48 1) fun activeStatus _ =>
                          if activeStatus = 0 then
                            Action.timerSetCompare deadline fun compareStatus _ =>
                              if compareStatus = 0 then
                                Action.timerSetInterrupt true fun enableStatus _ =>
                                  if enableStatus = 0 then pendingAndProbe seed goal scenario
                                  else Action.done enableStatus 0
                              else Action.done compareStatus 0
                          else Action.done activeStatus 0
                      else Action.done ds 0
                  else Action.done invalidDeadline now
                else Action.done timeStatus 0
            else Action.done initStatus 0
        else Action.done stopStatus 0
    else Action.done maskStatus 0

def selectScenario (seed goal period scenario : UInt64) : Action :=
  if goal = 0 then Action.done Status.invalidLength 0
  else if 512 < goal then Action.done Status.invalidLength 0
  else if period = 0 then Action.done invalidDeadline period
  else if 1000000 < period then Action.done invalidDeadline period
  else if 4 < scenario then Action.done Status.malformedFrame 0
  else arm seed goal period scenario

def foreground : Action :=
  Action.uartEnableAndResetFifo fun fifoStatus =>
    if fifoStatus = 0 then
      Action.bind sendReady fun readyStatus _ =>
        if readyStatus = 0 then
          Action.load64 RegionId.input 0 fun seedStatus seed =>
            if seedStatus = 0 then
              Action.load64 RegionId.input 8 fun goalStatus goal =>
                if goalStatus = 0 then
                  Action.load64 RegionId.input 16 fun periodStatus period =>
                    if periodStatus = 0 then
                      Action.load64 RegionId.input 24 fun scenarioStatus scenario =>
                        if scenarioStatus = 0 then selectScenario seed goal period scenario
                        else Action.done scenarioStatus 0
                    else Action.done periodStatus 0
                else Action.done goalStatus 0
            else Action.done seedStatus 0
        else Action.done readyStatus 0
    else Action.done fifoStatus 0

end Lemma.Examples.Foundation.Timer
