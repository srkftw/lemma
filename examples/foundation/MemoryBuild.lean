import examples.foundation.MemoryConformance
import Lemma.Compiler.Test.MemoryExport

open Lemma.Examples.Foundation.Memory

#core0_export_memory_suite [
  load8Value,
  load32Value,
  load64Value,
  store8Status,
  store32Status,
  store64Status,
  roundTrip8,
  roundTrip32,
  roundTrip64,
  eventWidth,
  overlapLow32,
  overlapHigh32,
  overlapByte,
  readRange,
  writeRange,
  overflowBounds,
  alignment,
  reservedDenied,
  deviceDenied,
  unknownDenied,
  helperCopyNonOverlap,
  branchWrite,
  foldWrite,
  bufferFill,
  byteChecksum,
  overlapCopy
]
