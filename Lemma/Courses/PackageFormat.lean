/-! `lemma-course-package/1` is a bounded, immutable instructional artifact.
The CRC detects corruption; it is not authentication, a license grant or proof
evidence. Text is ASCII plus LF in this first format. No executable code enters
a package. Source/edition/rights anchors are mandatory literal data. -/
namespace Lemma.Courses.PackageFormat

def magic : UInt64 := 0x315352554f434d4c
def version : UInt64 := 1
def headerBytes : UInt64 := 128
def entryBytes : UInt64 := 192
def maximumBytes : UInt64 := 32768
def maximumEntries : UInt64 := 16
def maximumTextBytes : UInt64 := 16384
def maximumFieldBytes : UInt64 := 512
def maximumIdentity : UInt64 := 65535
def maximumEdition : UInt64 := 0xffffffff
def malformed : UInt8 := 240
def unsupported : UInt8 := 241
def resourceLimit : UInt8 := 242
def integrityFailure : UInt8 := 243
def selectionAbsent : UInt8 := 244

/-- A separate high object-key range inside an already authorized Store
namespace. Notebook page, ink and submission keys never use this prefix. -/
def object (identity edition : UInt64) : UInt64 :=
  (0x4350000000000000 : UInt64) ||| (identity <<< 32) ||| edition

def spanOffset (span : UInt64) : UInt64 := span &&& 0xffffffff
def spanLength (span : UInt64) : UInt64 := span >>> 32
def span (offset length : UInt64) : UInt64 := offset ||| (length <<< 32)

def crcBit (value : UInt64) : UInt64 :=
  if value &&& 1 = 1 then (value >>> 1) ^^^ 0xedb88320 else value >>> 1

/-- CRC32/ISO-HDLC, reflected polynomial, initial/final XOR ffffffff. -/
def crcByte (state byte : UInt64) : UInt64 :=
  let value := state ^^^ (byte &&& 255)
  let value := crcBit value
  let value := crcBit value
  let value := crcBit value
  let value := crcBit value
  let value := crcBit value
  let value := crcBit value
  let value := crcBit value
  crcBit value

def textByteValid (byte : UInt64) : UInt64 :=
  if byte = 10 then 1 else if 32 ≤ byte then if byte ≤ 126 then 1 else 0 else 0

/-- Earlier-node masks bound both separate graphs and exclude cycles/self
edges. A pedagogical edge does not create a logical prerequisite. -/
def prerequisitesValid (mask ordinal : UInt64) : UInt64 :=
  if ordinal < maximumEntries then if mask < ((1 : UInt64) <<< ordinal) then 1 else 0 else 0

/-- This package version references the existing exact, original goals only:
1 = 1/2+1/3 in Q; 2 = (x+1)^2 in Q[x]; 3 = explicitly unsupported.
An authored explanation/worked/review node carries no checker authority. -/
def referenceStatus (kind goal checker domain assumptions budget : UInt64) : UInt8 :=
  if kind = 0 then unsupported else if 4 < kind then unsupported else
  if kind = 3 then
    if assumptions = 0 then
    if goal = 1 then
      if checker = 0x0001000000000001 then if domain = 1 then if budget = 8 then 0 else malformed else malformed else unsupported
    else if goal = 2 then
      if checker = 0x0001000000000001 then if domain = 2 then if budget = 8 then 0 else malformed else malformed else unsupported
    else if goal = 3 then
      if checker ||| budget = 0 then if domain = 3 then 0 else malformed else malformed
    else unsupported
    else unsupported
  else if goal ||| checker ||| domain ||| assumptions ||| budget = 0 then 0 else malformed

end Lemma.Courses.PackageFormat
