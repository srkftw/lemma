import examples.foundation.Conformance

/-!
Independent direct-source side of the Gate 2 exhaustive UInt8 comparison.

The functions below invoke the original elaborated Conformance declarations.
This module intentionally imports no Core0 checker, IR, or evaluator.  It writes
one canonical byte for each ordered input pair so a host byte comparison needs
no arithmetic oracle of its own.
-/

namespace Lemma.Examples.Foundation.ExhaustiveU8Source

private def appendU8Matrix (initial : ByteArray)
    (function : UInt8 → UInt8 → UInt8) : ByteArray := Id.run do
  let mut output := initial
  for x in [:256] do
    for y in [:256] do
      output := output.push (function x.toUInt8 y.toUInt8)
  pure output

private def appendBoolMatrix (initial : ByteArray)
    (function : UInt8 → UInt8 → Bool) : ByteArray := Id.run do
  let mut output := initial
  for x in [:256] do
    for y in [:256] do
      output := output.push (function x.toUInt8 y.toUInt8).toUInt8
  pure output

def resultBytes : ByteArray :=
  let output := appendU8Matrix ByteArray.empty
    Lemma.Examples.Foundation.Conformance.u8Add
  let output := appendU8Matrix output
    Lemma.Examples.Foundation.Conformance.u8Sub
  let output := appendBoolMatrix output
    Lemma.Examples.Foundation.Conformance.u8Lt
  let output := appendBoolMatrix output
    Lemma.Examples.Foundation.Conformance.u8Le
  appendBoolMatrix output Lemma.Examples.Foundation.Conformance.u8Eq

def run : IO Unit := do
  let some outputPath ← IO.getEnv "LEMMA_GATE2_EXHAUSTIVE_SOURCE_OUT"
    | throw <| IO.userError
        "LEMMA_GATE2_EXHAUSTIVE_SOURCE_OUT must name the direct-source result file"
  if outputPath.isEmpty then
    throw <| IO.userError
      "LEMMA_GATE2_EXHAUSTIVE_SOURCE_OUT must not be empty"
  unless resultBytes.size == 327680 do
    throw <| IO.userError
      s!"direct-source exhaustive evaluator produced {resultBytes.size} bytes, expected 327680"
  IO.FS.writeBinFile outputPath resultBytes
  IO.eprintln "CORE0_U8_EXHAUSTIVE_SOURCE:5:327680"

end Lemma.Examples.Foundation.ExhaustiveU8Source

def main : IO Unit :=
  Lemma.Examples.Foundation.ExhaustiveU8Source.run
