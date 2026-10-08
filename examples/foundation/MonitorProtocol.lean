import examples.foundation.DeviceConformanceSupport

/-!
The bounded `lemma-monitor-v1` wire format. Parsing and formatting are ordinary
elaborated source; only the existing four closed UART Actions touch the device.
The 16-byte request header and at most 32 payload bytes occupy scratch 0..47.
Responses stage four words in output RAM and send a fixed 48-byte frame.
-/
namespace Lemma.Examples.Foundation.Monitor.Protocol

open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Device.Support

def helloTag : UInt64 := 0x31304e4f4d4d454c
def requestMagic : UInt32 := 0x39514d4c
def maximumPayload : UInt64 := 32
def sessionBudget : UInt32 := 256

def validHeader (magic : UInt32) (version flags : UInt64) : Bool :=
  if magic = requestMagic then
    if version = 1 then flags = 0 else false
  else false

def expectedLength (command : UInt64) : UInt64 :=
  if command = 1 then 0
  else if command = 2 then 0
  else if command = 3 then 32
  else if command = 4 then 24
  else if command = 5 then 16
  else if command = 6 then 8
  else if command = 7 then 8
  else if command = 8 then 0
  else if command = 9 then 16
  else if command = 10 then 0
  else 255

def readyByte (index : UInt32) : UInt8 :=
  if index = 0 then 0x4c
  else if index = 1 then 0x45
  else if index = 2 then 0x4d
  else if index = 3 then 0x4d
  else if index = 4 then 0x41
  else if index = 5 then 0x5f
  else if index = 6 then 0x4d
  else if index = 7 then 0x4f
  else if index = 8 then 0x4e
  else if index = 9 then 0x49
  else if index = 10 then 0x54
  else if index = 11 then 0x4f
  else if index = 12 then 0x52
  else if index = 13 then 0x2f
  else if index = 14 then 0x31
  else if index = 15 then 0x0a
  else if index = 16 then 0x52
  else if index = 17 then 0x45
  else if index = 18 then 0x41
  else if index = 19 then 0x44
  else if index = 20 then 0x59
  else 0x0a

def readyStep (index _count : UInt32) (acc _c0 _c1 _c2 _c3 : UInt64) : Action :=
  Action.bind (sendByte (readyByte index)) fun s _ =>
    if s = 0 then Action.done 0 (acc + 1) else Action.done s 0

def sendReady : Action :=
  Action.boundedFoldU64 22 readyStep 22 0 0 0 0 0 fun s n => Action.done s n

def receivePayload (count : UInt32) : Action :=
  Action.boundedFoldU64 32 receiveIntoStep count 0 RegionId.scratch.toUInt64 16 1 0
    fun s n => Action.done s n

def responseHeaderByte (index : UInt32) (status : UInt8) (requestId : UInt64) : UInt8 :=
  if index = 0 then 0x4c
  else if index = 1 then 0x4d
  else if index = 2 then 0x53
  else if index = 3 then 0x39
  else if index = 4 then 1
  else if index = 5 then status
  else if index = 6 then 32
  else if index = 7 then 0
  else (requestId >>> ((index.toUInt64 - 8) * 8)).toUInt8

def responseByte (index : UInt32) (status : UInt8) (requestId : UInt64) : Action :=
  if index < 16 then Action.done 0 (responseHeaderByte index status requestId).toUInt64
  else Action.load8 RegionId.output (index.toUInt64 - 16) fun s v => Action.done s v

def responseStep (index _count : UInt32) (acc status requestId _c2 _c3 : UInt64) : Action :=
  Action.bind (responseByte index status.toUInt8 requestId) fun bs byte =>
    if bs = 0 then
      Action.bind (sendByte byte.toUInt8) fun s _ =>
        if s = 0 then Action.done 0 (acc + 1) else Action.done s 0
    else Action.done bs 0

def sendResponse (status : UInt8) (requestId v0 v1 v2 v3 : UInt64) : Action :=
  Action.store64 RegionId.output 0 v0 fun s0 =>
    if s0 = 0 then
      Action.store64 RegionId.output 8 v1 fun s1 =>
        if s1 = 0 then
          Action.store64 RegionId.output 16 v2 fun s2 =>
            if s2 = 0 then
              Action.store64 RegionId.output 24 v3 fun s3 =>
                if s3 = 0 then
                  Action.boundedFoldU64 48 responseStep 48 0 status.toUInt64 requestId 0 0
                    fun s n => Action.done s n
                else Action.done s3 0
            else Action.done s2 0
        else Action.done s1 0
    else Action.done s0 0

end Lemma.Examples.Foundation.Monitor.Protocol
