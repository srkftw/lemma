import examples.foundation.MemoryConformanceSupport

/-!
Ordinary elaborated Lean declarations for the `core0-v0.4` fixed-memory corpus.
All target work begins in these declarations; the compiler does not substitute
hardcoded fill/checksum/copy implementations.
-/

namespace Lemma.Examples.Foundation.Memory

open Lemma.Core0.Memory
open Lemma.Examples.Foundation.Memory.Support

def load8Value (region : UInt8) (offset : UInt64) : Action :=
  Action.load8 region offset fun status value => Action.done status value

def load32Value (region : UInt8) (offset : UInt64) : Action :=
  Action.load32 region offset fun status value => Action.done status value

def load64Value (region : UInt8) (offset : UInt64) : Action :=
  Action.load64 region offset fun status value => Action.done status value

def store8Status (region : UInt8) (offset : UInt64) (value : UInt8) : Action :=
  Action.store8 region offset value fun status => Action.done status 0

def store32Status (region : UInt8) (offset : UInt64) (value : UInt32) : Action :=
  Action.store32 region offset value fun status => Action.done status 0

def store64Status (region : UInt8) (offset value : UInt64) : Action :=
  Action.store64 region offset value fun status => Action.done status 0

def roundTrip8 (region : UInt8) (offset : UInt64) (value : UInt8) : Action :=
  Action.store8 region offset value fun status =>
    if status = 0 then
      Action.load8 region offset fun loadStatus loaded => Action.done loadStatus loaded
    else Action.done status 0

def roundTrip32 (region : UInt8) (offset : UInt64) (value : UInt32) : Action :=
  Action.store32 region offset value fun status =>
    if status = 0 then
      Action.load32 region offset fun loadStatus loaded => Action.done loadStatus loaded
    else Action.done status 0

def roundTrip64 (region : UInt8) (offset value : UInt64) : Action :=
  Action.store64 region offset value fun status =>
    if status = 0 then
      Action.load64 region offset fun loadStatus loaded => Action.done loadStatus loaded
    else Action.done status 0

def eventWidth (useByte : Bool) (offset value : UInt64) : Action :=
  if useByte = true then
    Action.store8 4 offset value.toUInt8 fun status => Action.done status 0
  else
    Action.store32 4 offset value.toUInt32 fun status => Action.done status 0

def overlapLow32 (region : UInt8) (offset value : UInt64) : Action :=
  Action.store64 region offset value fun status =>
    if status = 0 then
      Action.load32 region offset fun loadStatus loaded => Action.done loadStatus loaded
    else Action.done status 0

def overlapHigh32 (region : UInt8) (offset value : UInt64) : Action :=
  Action.store64 region offset value fun status =>
    if status = 0 then
      Action.load32 region (offset + 4) fun loadStatus loaded => Action.done loadStatus loaded
    else Action.done status 0

def overlapByte (region : UInt8) (offset : UInt64) (value : UInt32) : Action :=
  Action.store32 region offset value fun status =>
    if status = 0 then
      Action.load8 region offset fun firstStatus first =>
        if firstStatus = 0 then
          Action.load8 region (offset + 3) fun lastStatus last =>
            Action.done lastStatus (first ||| (last <<< 8))
        else Action.done firstStatus 0
    else Action.done status 0

def readRange (region : UInt8) (offset length : UInt64) : Action :=
  Action.checkReadRange region offset length fun status => Action.done status 0

def writeRange (region : UInt8) (offset length : UInt64) : Action :=
  Action.checkWriteRange region offset length fun status => Action.done status 0

def overflowBounds (write : Bool) (region : UInt8) (offset value : UInt64) : Action :=
  if write = true then
    Action.store64 region offset value fun status => Action.done status 0
  else
    Action.load8 region offset fun status loaded => Action.done status loaded

def alignment (wide : Bool) (region : UInt8) (offset : UInt64) : Action :=
  if wide = true then
    Action.load64 region offset fun status value => Action.done status value
  else
    Action.load32 region offset fun status value => Action.done status value

def reservedDenied (write : Bool) (region : UInt8) (offset : UInt64) : Action :=
  if write = true then
    Action.store8 region offset 0xaa fun status => Action.done status 0
  else
    Action.load8 region offset fun status value => Action.done status value

def deviceDenied (write : Bool) (region : UInt8) (offset : UInt64) : Action :=
  if write = true then
    Action.store8 region offset 0x55 fun status => Action.done status 0
  else
    Action.load8 region offset fun status value => Action.done status value

def unknownDenied (region : UInt8) (offset : UInt64) : Action :=
  Action.load8 region offset fun status value => Action.done status value

def helperCopyNonOverlap (sourceRegion : UInt8) (sourceOffset : UInt64)
    (destinationRegion : UInt8) (destinationOffset : UInt64) : Action :=
  copyExactly16 sourceRegion sourceOffset destinationRegion destinationOffset

def branchWrite (toScratch : Bool) (offset : UInt64) (value : UInt8) : Action :=
  if toScratch = true then
    Action.store8 1 offset value fun status =>
      Action.done status (if status = 0 then value.toUInt64 else 0)
  else
    Action.store8 3 offset value fun status =>
      Action.done status (if status = 0 then value.toUInt64 else 0)

def foldWrite (count : UInt32) (offset : UInt64) (value : UInt8) : Action :=
  Action.boundedFoldU64 16 incrementingWriteStep count 0 1 offset value.toUInt64 0
    fun status sum => Action.done status sum

/-- Bounded byte fill.  Success returns the wrapping sum of bytes actually written. -/
def bufferFill (region : UInt8) (offset : UInt64) (count : UInt32)
    (value : UInt8) : Action :=
  Action.checkWriteRange region offset count.toUInt64 fun rangeStatus =>
    if rangeStatus = 0 then
      Action.boundedFoldU64 256 fillStep count 0 region.toUInt64 offset value.toUInt64 0
        fun status sum => Action.done status sum
    else Action.done rangeStatus 0

/-- Bounded little byte checksum using wrapping `UInt64` addition. -/
def byteChecksum (region : UInt8) (offset : UInt64) (count : UInt32) : Action :=
  Action.checkReadRange region offset count.toUInt64 fun rangeStatus =>
    if rangeStatus = 0 then
      Action.boundedFoldU64 256 checksumStep count 0 region.toUInt64 offset 0 0
        fun status sum => Action.done status sum
    else Action.done rangeStatus 0

/-- Small memmove-style copy.  The callback selects descending indices exactly
when same-region ranges overlap with the destination above the source. -/
def overlapCopy (sourceRegion : UInt8) (sourceOffset : UInt64)
    (destinationRegion : UInt8) (destinationOffset : UInt64) (count : UInt32) : Action :=
  Action.checkReadRange sourceRegion sourceOffset count.toUInt64 fun readStatus =>
    if readStatus = 0 then
      Action.checkWriteRange destinationRegion destinationOffset count.toUInt64 fun writeStatus =>
        if writeStatus = 0 then
          Action.boundedFoldU64 256 copyStep count 0 sourceRegion.toUInt64 sourceOffset
            destinationRegion.toUInt64 destinationOffset fun status sum =>
              Action.done status sum
        else Action.done writeStatus 0
    else Action.done readStatus 0

end Lemma.Examples.Foundation.Memory
