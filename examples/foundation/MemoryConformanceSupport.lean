import Lemma.Core0.Memory

/-! Closed Action helpers and fold callbacks used by the Gate 5 source corpus. -/

namespace Lemma.Examples.Foundation.Memory.Support

open Lemma.Core0.Memory

def fillStep (_index _count : UInt32) (accumulator contextRegion contextOffset
    contextByte _unused : UInt64) : Action :=
  let region := contextRegion.toUInt8
  let byte := contextByte.toUInt8
  Action.store8 region (contextOffset + _index.toUInt64) byte fun status =>
    if status = 0 then
      Action.done 0 (accumulator + byte.toUInt64)
    else
      Action.done status accumulator

def incrementingWriteStep (index _count : UInt32) (accumulator _contextRegion
    contextOffset contextByte _unused : UInt64) : Action :=
  let byte := (contextByte.toUInt8 + index.toUInt8)
  Action.store8 1 (contextOffset + index.toUInt64) byte fun status =>
    if status = 0 then
      Action.done 0 (accumulator + byte.toUInt64)
    else
      Action.done status accumulator

def checksumStep (index _count : UInt32) (accumulator contextRegion contextOffset
    _context2 _context3 : UInt64) : Action :=
  Action.load8 contextRegion.toUInt8 (contextOffset + index.toUInt64) fun status byte =>
    if status = 0 then
      Action.done 0 (accumulator + byte)
    else
      Action.done status accumulator

def copyStep (index count : UInt32) (accumulator sourceRegion sourceOffset
    destinationRegion destinationOffset : UInt64) : Action :=
  let sameRegion := decide (sourceRegion.toUInt8 = destinationRegion.toUInt8)
  let destinationAfterSource := decide (sourceOffset < destinationOffset)
  let overlaps := decide (destinationOffset < sourceOffset + count.toUInt64)
  let backwards :=
    if sameRegion = true then
      if destinationAfterSource = true then overlaps else false
    else false
  let position :=
    if backwards = true then (count - 1 - index).toUInt64 else index.toUInt64
  Action.load8 sourceRegion.toUInt8 (sourceOffset + position) fun readStatus byte =>
    if readStatus = 0 then
      Action.store8 destinationRegion.toUInt8 (destinationOffset + position)
          byte.toUInt8 fun writeStatus =>
        if writeStatus = 0 then
          Action.done 0 (accumulator + byte)
        else
          Action.done writeStatus accumulator
    else
      Action.done readStatus accumulator

/-- A real transitive Action helper.  The root calling this declaration has no
direct load/store node; its effects are inherited through this dependency and the
statically resolved `copyStep` loop body. -/
def copyExactly16 (sourceRegion : UInt8) (sourceOffset : UInt64)
    (destinationRegion : UInt8) (destinationOffset : UInt64) : Action :=
  Action.checkReadRange sourceRegion sourceOffset 16 fun readStatus =>
    if readStatus = 0 then
      Action.checkWriteRange destinationRegion destinationOffset 16 fun writeStatus =>
        if writeStatus = 0 then
          Action.boundedFoldU64 16 copyStep 16 0 sourceRegion.toUInt64 sourceOffset
            destinationRegion.toUInt64 destinationOffset fun status sum =>
              Action.done status sum
        else
          Action.done writeStatus 0
    else
      Action.done readStatus 0

end Lemma.Examples.Foundation.Memory.Support
