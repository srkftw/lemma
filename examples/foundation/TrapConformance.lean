import examples.foundation.DeviceConformanceSupport
import Lemma.Core0.Trap

/-!
The two genuine elaborated roots for Gate 7: a no-argument foreground Action
and a nine-word trap dispatcher.  Only the structured machine primitive knows
the frame address.  Compiled Lean receives snapshots and approved site pairs,
checks policy, records observations, and chooses an explicit continuation.
-/

namespace Lemma.Examples.Foundation.Trap

open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Device.Support

/-- Gate 7 returns only to one of two fixed four-byte instruction sites.  On
entry MPP must be M, MPRV/MIE/MPIE clear, and no interrupt source enabled.
Other WARL/status bits are not incorrectly assumed to be zero. -/
def resumeAddress (cause pc mstatus tval mie ecallSite ecallResume
    breakSite breakResume : UInt64) : UInt64 :=
  if (mstatus &&& 0x21888) = 0x1800 then
    if mie = 0 then
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

def writeEvent (offset value : UInt64) : Action :=
  Action.store64 RegionId.events offset value fun status => Action.done status 0

def recordSnapshot (cause pc mstatus tval mie : UInt64) : Action :=
  Action.bind (writeEvent 8 cause) fun s0 _ =>
    if s0 = 0 then
      Action.bind (writeEvent 16 pc) fun s1 _ =>
        if s1 = 0 then
          Action.bind (writeEvent 24 mstatus) fun s2 _ =>
            if s2 = 0 then
              Action.bind (writeEvent 32 tval) fun s3 _ =>
                if s3 = 0 then writeEvent 40 mie else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

/-- A bounded compiled-source fatal diagnostic.  The machine glue will finish
with status 18 after this Action returns; no retry of the faulting PC occurs. -/
def fatalDiagnostic (cause pc mstatus tval mie : UInt64) : Action :=
  Action.bind (sendResponse Status.unexpectedTrap 0x7001 cause) fun s0 _ =>
    if s0 = 0 then
      Action.bind (sendResponse Status.unexpectedTrap 0x7002 pc) fun s1 _ =>
        if s1 = 0 then
          Action.bind (sendResponse Status.unexpectedTrap 0x7003 mstatus) fun s2 _ =>
            if s2 = 0 then
              Action.bind (sendResponse Status.unexpectedTrap 0x7004 tval) fun s3 _ =>
                if s3 = 0 then
                  Action.bind (sendResponse Status.unexpectedTrap 0x7005 mie) fun s4 _ =>
                    if s4 = 0 then
                      Action.bind drain fun _ _ => Action.done Status.unexpectedTrap 0
                    else Action.done s4 0
                else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

/-- The ninth argument crosses the RV64 stack-argument boundary.  Scenario 4
deliberately traps inside this compiled dispatcher after the machine latch has
been cleared, exercising the stackless double-fault terminator. -/
def dispatch (cause pc mstatus tval mie ecallSite ecallResume
    breakSite breakResume : UInt64) : Action :=
  Action.bind (recordSnapshot cause pc mstatus tval mie) fun snapshotStatus _ =>
    if snapshotStatus = 0 then
      Action.load64 RegionId.events 0 fun countStatus count =>
        if countStatus = 0 then
          Action.bind (writeEvent 0 (count + 1)) fun writeStatus _ =>
            if writeStatus = 0 then
              Action.load64 RegionId.input 16 fun readStatus scenario =>
                if readStatus = 0 then
                  if scenario = 4 then
                    Action.trapEcall fun _ _ => Action.done Status.contextMismatch 0
                  else
                    let resume := resumeAddress cause pc mstatus tval mie
                      ecallSite ecallResume breakSite breakResume
                    if resume = 0 then fatalDiagnostic cause pc mstatus tval mie
                    else Action.done Status.ok resume
                else Action.done readStatus 0
            else Action.done writeStatus 0
        else Action.done countStatus 0
    else Action.done snapshotStatus 0

def mix (index : UInt32) (accumulator : UInt64) : UInt64 :=
  ((accumulator ^^^ index.toUInt64) * (0x100000001b3 : UInt64)) + (index.toUInt64 <<< 17)

def controlStep (index _count : UInt32) (accumulator _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.done Status.ok (mix index accumulator)

/-- The live mixed word must survive both real traps.  Primitive-return masks
are computed from snapshots of all 31 writable integer registers and canaries. -/
def interruptedStep (index _count : UInt32) (accumulator _c0 _c1 _c2 _c3 : UInt64) : Action :=
  let mixed := mix index accumulator
  Action.trapEcall fun ecallStatus ecallMask =>
    if ecallStatus = 0 then
      if ecallMask = 0 then
        Action.trapBreakpoint fun breakStatus breakMask =>
          if breakStatus = 0 then
            if breakMask = 0 then Action.done Status.ok mixed
            else Action.done Status.contextMismatch breakMask
          else Action.done breakStatus breakMask
      else Action.done Status.contextMismatch ecallMask
    else Action.done ecallStatus ecallMask

/-- A permanent distinguishing case for every earlier denial class, plus
private trap/probe region IDs which do not acquire ordinary RAM authority. -/
def denial (index : UInt32) : Action :=
  if index = 0 then Action.load8 255 0 fun s v => Action.done s v
  else if index = 1 then Action.load8 RegionId.stack 0 fun s v => Action.done s v
  else if index = 2 then Action.store64 RegionId.image 0 123 fun s => Action.done s 0
  else if index = 3 then Action.load8 RegionId.uart 0 fun s v => Action.done s v
  else if index = 4 then Action.store32 RegionId.finisher 0 123 fun s => Action.done s 0
  else if index = 5 then Action.store8 RegionId.input 0 123 fun s => Action.done s 0
  else if index = 6 then Action.load8 RegionId.events 0 fun s v => Action.done s v
  else if index = 7 then Action.load64 RegionId.scratch 0xffffffffffffffff fun s v => Action.done s v
  else if index = 8 then Action.store8 RegionId.scratch 4096 123 fun s => Action.done s 0
  else if index = 9 then Action.checkWriteRange RegionId.scratch 4080 0xffffffffffffffff fun s => Action.done s 0
  else if index = 10 then Action.load32 RegionId.scratch 1 fun s v => Action.done s v
  else if index = 11 then
    Action.boundedFoldU64 0 controlStep 1 77 0 0 0 0 fun s v => Action.done s v
  else if index = 12 then Action.load64 0x72 0 fun s v => Action.done s v
  else Action.store64 0x73 0 123 fun s => Action.done s 0

def denialStatus (index : UInt32) : UInt8 :=
  if index = 0 then 1
  else if index ≤ 2 then 2
  else if index ≤ 4 then 3
  else if index = 5 then 5
  else if index = 6 then 6
  else if index ≤ 9 then 7
  else if index = 10 then 8
  else if index = 11 then 9
  else 1

def denialStep (index _count : UInt32) (accumulator _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.bind (denial index) fun status value =>
    if status = denialStatus index then
      if index = 11 then
        if value = 77 then Action.done 0 (accumulator + 1)
        else Action.done Status.contextMismatch value
      else
        if value = 0 then Action.done 0 (accumulator + 1)
        else Action.done Status.contextMismatch value
    else Action.done Status.contextMismatch status.toUInt64

def denialBattery : Action :=
  Action.store8 RegionId.scratch 4080 0x77 fun guardStatus =>
    if guardStatus = 0 then
      Action.load64 RegionId.events 0 fun beforeStatus beforeCount =>
        if beforeStatus = 0 then
          Action.boundedFoldU64 14 denialStep 14 0 0 0 0 0 fun foldStatus accepted =>
            if foldStatus = 0 then
              Action.load64 RegionId.events 0 fun afterStatus afterCount =>
                if afterStatus = 0 then
                  Action.load8 RegionId.scratch 4080 fun readStatus guardValue =>
                    if readStatus = 0 then
                      if beforeCount = afterCount then
                        if guardValue = 0x77 then Action.done 0 accepted
                        else Action.done Status.contextMismatch guardValue
                      else Action.done Status.contextMismatch afterCount
                    else Action.done readStatus 0
                else Action.done afterStatus 0
            else Action.done foldStatus accepted
        else Action.done beforeStatus 0
    else Action.done guardStatus 0

def resultFrames (checksum trapCount denied contextMask : UInt64) : Action :=
  Action.bind (sendResponse 0 0x7101 checksum) fun s0 _ =>
    if s0 = 0 then
      Action.bind (sendResponse 0 0x7102 trapCount) fun s1 _ =>
        if s1 = 0 then
          Action.bind (sendResponse 0 0x7103 denied) fun s2 _ =>
            if s2 = 0 then
              Action.bind (sendResponse 0 0x7104 contextMask) fun s3 _ =>
                if s3 = 0 then drain else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

def runFolds (seed : UInt64) (count : UInt32) : Action :=
  Action.boundedFoldU64 64 controlStep count seed 0 0 0 0 fun controlStatus control =>
    if controlStatus = 0 then
      Action.boundedFoldU64 64 interruptedStep count seed 0 0 0 0 fun interruptedStatus interrupted =>
        if interruptedStatus = 0 then
          if control = interrupted then
            Action.bind denialBattery fun denialStatus denied =>
              if denialStatus = 0 then
                Action.load64 RegionId.events 0 fun countStatus trapCount =>
                  if countStatus = 0 then resultFrames interrupted trapCount denied 0
                  else Action.done countStatus 0
              else Action.done denialStatus denied
          else Action.done Status.contextMismatch interrupted
        else
          Action.bind (sendResponse interruptedStatus 0x71ff interrupted) fun _ _ =>
            Action.bind drain fun _ _ => Action.done interruptedStatus interrupted
    else Action.done controlStatus control

def selectScenario (seed count scenario : UInt64) : Action :=
  if scenario = 1 then
    Action.trapUnexpectedEcall fun _ _ => Action.done Status.contextMismatch 0
  else if scenario = 2 then
    Action.trapIllegalInstruction fun _ _ => Action.done Status.contextMismatch 0
  else if scenario = 4 then
    Action.trapEcall fun _ _ => Action.done Status.contextMismatch 0
  else if scenario = 0 then
    if count ≤ 0xffffffff then runFolds seed count.toUInt32
    else Action.done Status.invalidLength 0
  else Action.done Status.malformedFrame 0

def foreground : Action :=
  Action.uartEnableAndResetFifo fun fifoStatus =>
    if fifoStatus = 0 then
      Action.bind sendReady fun readyStatus _ =>
        if readyStatus = 0 then
          Action.bind (writeEvent 0 0) fun initStatus _ =>
            if initStatus = 0 then
              Action.load64 RegionId.input 0 fun seedStatus seed =>
                if seedStatus = 0 then
                  Action.load64 RegionId.input 8 fun countStatus count =>
                    if countStatus = 0 then
                      Action.load64 RegionId.input 16 fun scenarioStatus scenario =>
                        if scenarioStatus = 0 then selectScenario seed count scenario
                        else Action.done scenarioStatus 0
                    else Action.done countStatus 0
                else Action.done seedStatus 0
            else Action.done initStatus 0
        else Action.done readyStatus 0
    else Action.done fifoStatus 0

end Lemma.Examples.Foundation.Trap
