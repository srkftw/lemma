import examples.foundation.DeviceConformanceSupport

/-!
The single zero-argument `core0-v0.5` device root.  Header and payload bytes are
received after boot, stored through checked scratch-RAM operations, validated,
and dispatched by compiled Lean source.  The root handles exactly two requests.
-/

namespace Lemma.Examples.Foundation.Device

open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Device.Support

def dispatchAdd64 (requestId : UInt64) : Action :=
  Action.load64 RegionId.scratch 16 fun leftStatus left =>
    if leftStatus = Status.ok then
      Action.load64 RegionId.scratch 24 fun rightStatus right =>
        if rightStatus = Status.ok then
          sendResponse Status.ok requestId (left + right)
        else
          Action.done rightStatus 0
    else
      Action.done leftStatus 0

def dispatchXor64 (requestId : UInt64) : Action :=
  Action.load64 RegionId.scratch 16 fun leftStatus left =>
    if leftStatus = Status.ok then
      Action.load64 RegionId.scratch 24 fun rightStatus right =>
        if rightStatus = Status.ok then
          sendResponse Status.ok requestId (left ^^^ right)
        else
          Action.done rightStatus 0
    else
      Action.done leftStatus 0

/-- The selected branch alone performs its designated effect.  False writes
the fixed scratch marker; true emits the raw UART marker immediately before the
common response frame. -/
def dispatchBranch (requestId : UInt64) : Action :=
  Action.load8 RegionId.scratch 16 fun readStatus branchValue =>
    if readStatus = Status.ok then
      if branchValue = 0 then
        Action.store8 RegionId.scratch 64 0x5a fun writeStatus =>
          if writeStatus = Status.ok then
            sendResponse Status.ok requestId 0
          else
            Action.done writeStatus 0
      else if branchValue = 1 then
        Action.bind (sendByte 0xa5) fun markerStatus _value =>
          if markerStatus = Status.ok then
            sendResponse Status.ok requestId 1
          else
            Action.done markerStatus 0
      else
        Action.done Status.malformedFrame 0
    else
      Action.done readStatus 0

def dispatchTxStress (requestId : UInt64) : Action :=
  Action.load32 RegionId.scratch 16 fun readStatus count =>
    if readStatus = Status.ok then
      if count ≤ 65535 then
        Action.bind (sendRepeatedByte count.toUInt32 0x55) fun sendStatus _sent =>
          if sendStatus = Status.ok then
            sendResponse Status.ok requestId count
          else
            Action.done sendStatus 0
      else
        Action.done Status.invalidLength 0
    else
      Action.done readStatus 0

/-- Command-specific length validation is terminal.  An unknown command with a
bounded payload instead receives status 17 and leaves the session synchronized
for its next request. -/
def dispatchRequest (command length requestId : UInt64) : Action :=
  if command = 1 then
    if length = 16 then dispatchAdd64 requestId
    else Action.done Status.invalidLength 0
  else if command = 2 then
    if length = 16 then dispatchXor64 requestId
    else Action.done Status.invalidLength 0
  else if command = 3 then
    if length = 1 then dispatchBranch requestId
    else Action.done Status.invalidLength 0
  else if command = 4 then
    if length = 4 then dispatchTxStress requestId
    else Action.done Status.invalidLength 0
  else
    sendResponse Status.unsupportedCommand requestId 0

/-- Receive one complete bounded request into scratch RAM and dispatch it. -/
def handleRequest : Action :=
  Action.bind receiveHeader fun headerStatus _headerBytes =>
    if headerStatus = Status.ok then
      Action.load32 RegionId.scratch 0 fun magicStatus magic =>
        if magicStatus = Status.ok then
          Action.load8 RegionId.scratch 4 fun versionStatus version =>
            if versionStatus = Status.ok then
              Action.load8 RegionId.scratch 5 fun commandStatus command =>
                if commandStatus = Status.ok then
                  Action.load8 RegionId.scratch 6 fun lengthStatus length =>
                    if lengthStatus = Status.ok then
                      Action.load8 RegionId.scratch 7 fun flagsStatus flags =>
                        if flagsStatus = Status.ok then
                          Action.load64 RegionId.scratch 8 fun idStatus requestId =>
                            if idStatus = Status.ok then
                              if length ≤ 16 then
                                Action.bind (receivePayload length.toUInt32)
                                  fun payloadStatus _payloadBytes =>
                                    if payloadStatus = Status.ok then
                                      if magic = 0x36514d4c then
                                        if version = 1 then
                                          if flags = 0 then
                                            dispatchRequest command length requestId
                                          else
                                            Action.done Status.malformedFrame 0
                                        else
                                          Action.done Status.malformedFrame 0
                                      else
                                        Action.done Status.malformedFrame 0
                                    else
                                      Action.done payloadStatus 0
                              else
                                Action.done Status.invalidLength 0
                            else
                              Action.done idStatus 0
                        else
                          Action.done flagsStatus 0
                    else
                      Action.done lengthStatus 0
                else
                  Action.done commandStatus 0
            else
              Action.done versionStatus 0
        else
          Action.done magicStatus 0
    else
      Action.done headerStatus 0

/-- Initialize FIFO state, publish the compiled READY banner, serve exactly two
runtime requests from one boot, drain the transmitter, and return to the fixed
machine finisher. -/
def deviceSession : Action :=
  Action.uartEnableAndResetFifo fun fifoStatus =>
    if fifoStatus = Status.ok then
      Action.bind sendReady fun readyStatus _readyBytes =>
        if readyStatus = Status.ok then
          Action.bind handleRequest fun firstStatus _firstValue =>
            if firstStatus = Status.ok then
              Action.bind handleRequest fun secondStatus _secondValue =>
                if secondStatus = Status.ok then
                  Action.bind drain fun drainStatus _drainValue =>
                    Action.done drainStatus 0
                else
                  Action.done secondStatus 0
            else
              Action.done firstStatus 0
        else
          Action.done readyStatus 0
    else
      Action.done fifoStatus 0

end Lemma.Examples.Foundation.Device
