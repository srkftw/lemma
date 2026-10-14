import Lemma.Courses.PackageFormat

/-! Typed authoring declarations and encoding run on hosted Lean. These types
are package data, not a target runtime extension. The independent guest decoder
consumes the resulting bounded bytes through ordinary checked User memory. -/
namespace Lemma.Courses.Package
open PackageFormat

inductive Goal where
  | fractionAddition
  | binomialSquare
  | unsupported
  deriving BEq, Repr, Inhabited

inductive Kind where
  | explanation
  | worked
  | exercise (goal : Goal)
  | review
  deriving BEq, Repr, Inhabited

structure Node where
  kind : Kind
  title : String
  body : String
  exampleText : String := ""
  worked : String := ""
  exercise : String := ""
  hint : String := ""
  sourceAnchor : String
  review : String := ""
  logicalPrerequisites : Array Nat := #[]
  pedagogicalPrerequisites : Array Nat := #[]
  deriving Repr, Inhabited

structure Course where
  identity : UInt64
  edition : UInt64
  title : String
  sourceAnchor : String
  editionAnchor : String
  rightsAnchor : String
  nodes : Array Node
  deriving Repr

inductive Error where
  | malformed (detail : String)
  | unsupported (detail : String)
  | resourceLimit (detail : String)
  deriving Repr

def Error.render : Error → String
  | .malformed text => s!"Malformed: {text}"
  | .unsupported text => s!"Unsupported: {text}"
  | .resourceLimit text => s!"ResourceLimit: {text}"

private def text (value : String) (required : Bool) : Except Error ByteArray := do
  let bytes := value.toUTF8
  if required && bytes.isEmpty then throw (.malformed "required text anchor is empty")
  if bytes.size > maximumFieldBytes.toNat then throw (.resourceLimit "text field exceeds 512 bytes")
  if bytes.data.any (fun byte => textByteValid byte.toUInt64 != 1) then
    throw (.unsupported "package-v1 text supports ASCII and LF only")
  return bytes

private def mask (edges : Array Nat) (ordinal : Nat) : Except Error UInt64 := do
  let mut result : UInt64 := 0
  for edge in edges do
    if edge >= ordinal then throw (.malformed "prerequisite is not an earlier node")
    let bit := (1 : UInt64) <<< edge.toUInt64
    if result &&& bit != 0 then throw (.malformed "duplicate prerequisite")
    result := result ||| bit
  return result

private def putWord (bytes : ByteArray) (offset : Nat) (value : UInt64) : ByteArray :=
  (List.range 8).foldl (fun output i => output.set! (offset + i) ((value >>> (i.toUInt64 * 8)).toUInt8)) bytes

private def appendText (image : ByteArray) (bytes : ByteArray) : ByteArray :=
  bytes.data.foldl (fun output byte => output.push byte) image

private def references (kind : Kind) : UInt64 × UInt64 × UInt64 × UInt64 × UInt64 :=
  match kind with
  | .explanation => (1,0,0,0,0)
  | .worked => (2,0,0,0,0)
  | .review => (4,0,0,0,0)
  | .exercise .fractionAddition => (3,1,0x0001000000000001,1,8)
  | .exercise .binomialSquare => (3,2,0x0001000000000001,2,8)
  | .exercise .unsupported => (3,3,0,3,0)

/-- Encode canonical contiguous text spans and a full-image corruption checksum.
All limits and semantic references are checked before returning any artifact. -/
def encode (course : Course) : Except Error ByteArray := do
  if course.identity == 0 || course.identity > maximumIdentity then throw (.malformed "identity must be 1..65535")
  if course.edition == 0 || course.edition > maximumEdition then throw (.malformed "edition is out of range")
  if course.nodes.isEmpty then throw (.malformed "course has no nodes")
  if course.nodes.size > maximumEntries.toNat then throw (.resourceLimit "course exceeds sixteen nodes")
  let fixedBytes := headerBytes.toNat + entryBytes.toNat * course.nodes.size
  let mut image := ByteArray.mk (Array.replicate fixedBytes 0)
  for (offset,value) in #[(0,magic),(8,version),(24,course.identity),(32,course.edition),
      (40,course.nodes.size.toUInt64),(48,entryBytes),(56,headerBytes),(64,fixedBytes.toUInt64)] do
    image := putWord image offset value
  for (offset,value) in #[(96,course.title),(104,course.sourceAnchor),(112,course.editionAnchor),(120,course.rightsAnchor)] do
    let bytes ← text value true
    image := putWord image offset (span image.size.toUInt64 bytes.size.toUInt64)
    image := appendText image bytes
  for ordinal in [:course.nodes.size] do
    let node := course.nodes[ordinal]!
    let entry := headerBytes.toNat + ordinal * entryBytes.toNat
    let (kind,goal,checker,domain,budget) := references node.kind
    let logical ← mask node.logicalPrerequisites ordinal
    let pedagogical ← mask node.pedagogicalPrerequisites ordinal
    for (offset,value) in #[(0,ordinal.toUInt64 + 1),(8,kind),(16,goal),(24,checker),(32,domain),
        (48,logical),(56,pedagogical),(64,ordinal.toUInt64 + 1),(72,budget)] do
      image := putWord image (entry + offset) value
    let values := #[node.title,node.body,node.exampleText,node.worked,node.exercise,node.hint,node.sourceAnchor,node.review]
    for field in [:values.size] do
      let bytes ← text values[field]! (field == 0 || field == 1 || field == 6 || (kind == 3 && field == 4))
      image := putWord image (entry + 112 + field * 8) (span image.size.toUInt64 bytes.size.toUInt64)
      image := appendText image bytes
  let textBytes := image.size - fixedBytes
  if textBytes > maximumTextBytes.toNat || image.size > maximumBytes.toNat then
    throw (.resourceLimit "package text/image exceeds its declared bounds")
  image := putWord image 16 image.size.toUInt64
  image := putWord image 72 textBytes.toUInt64
  let crc := image.data.foldl (fun state byte => crcByte state byte.toUInt64) 0xffffffff ^^^ 0xffffffff
  image := putWord image 80 crc
  image := putWord image 88 (crc ^^^ 0xffffffff)
  return image

end Lemma.Courses.Package
