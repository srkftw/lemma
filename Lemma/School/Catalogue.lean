import Lean
import Lemma.School.Digest

/-! Strict, bounded JSON string-list ingestion in hosted Lean. Raw originals are
immutable sources; proposed curricular relations have their own review records.
No catalogue row becomes a lesson or an inferred prerequisite. -/
namespace Lemma.School.Catalogue
open Lean

-- These are admitted storage/decoding budgets, never expected corpus counts.
def importVersion : String := "lemma-topic-import/1"
def maximumTokenBytes : Nat := 65536
def maximumSourceBytes : Nat := 536870912
def maximumRecords : Nat := 1000000

def validKey (key : String) : Bool :=
  !key.isEmpty && key.length ≤ 80 && key.toList.all (fun c => c.isAlphanum && c.toNat < 128 || c == '-' || c == '_')

structure Record where
  position : Nat
  original : String
  numberLabel : String
  originalUtf8Sha256 : String
  validation : String := "valid-json-string"
  deriving Repr, ToJson, FromJson

structure Manifest where
  format : String := "lemma-topic-catalogue/1"
  importer : String := importVersion
  sourceKey : String
  sourceDigest : String
  sourceBytes : Nat
  recordsDigest : String
  records : Nat
  originalName : String
  rights : String
  deriving Repr, ToJson, FromJson

structure ImportReceipt where
  manifest : Manifest
  directory : String
  reused : Bool
  deriving Repr, ToJson, FromJson

structure LocatedRecord where
  sourceDigest : String
  recordId : String
  record : Record
  deriving Repr, ToJson, FromJson

structure SearchPage where
  sourceDigest : String
  query : String
  offset : Nat
  limit : Nat
  matchCount : Nat
  records : Array LocatedRecord
  deriving Repr, ToJson, FromJson

/-- Cross-revision correspondence is a reviewed proposal, never raw identity. -/
structure Relation where
  fromRecordId : String
  toRecordId : String
  kind : String
  origin : String
  status : String := "unresolved"
  confidencePermille : Option Nat := none
  reviewHistory : Array String := #[]
  deriving Repr, ToJson, FromJson

def recordId (digest : String) (position : Nat) : String := s!"sha256:{digest}#{position}"

def numberLabel (original : String) : String :=
  String.ofList (original.toList.takeWhile fun c => c.isDigit)

private def record (position : Nat) (original : String) : Record :=
  { position, original, numberLabel := numberLabel original, originalUtf8Sha256 := Digest.sha256String original }

private inductive Phase where
  | start | first | value | quoted | afterValue | closed
  deriving BEq, Inhabited
private structure Scanner where
  phase : Phase := .start
  token : ByteArray := ByteArray.empty
  escaped : Bool := false
  count : Nat := 0
  deriving Inhabited

private def whitespace (byte : UInt8) : Bool := byte == 32 || byte == 10 || byte == 13 || byte == 9

private def optionResult {α : Type} (value : Option α) (error : String) : Except String α :=
  match value with
  | some found => .ok found
  | none => .error error

private def feed (state : Scanner) (byte : UInt8) : Except String (Scanner × Option String) := do
  if state.phase == .quoted then
    if state.token.size ≥ maximumTokenBytes then throw "source string exceeds 65536 encoded bytes"
    let token := state.token.push byte
    if byte == 34 && !state.escaped then
      let text ← optionResult (String.fromUTF8? token) "invalid UTF-8 in source string"
      let json ← Json.parse text
      let original ← json.getStr?
      if state.count ≥ maximumRecords then throw "catalogue exceeds 1000000 records"
      return ({ state with phase := .afterValue, token := ByteArray.empty, count := state.count+1 }, some original)
    return ({ state with token, escaped := byte == 92 && !state.escaped }, none)
  if whitespace byte then return (state, none)
  match state.phase with
  | .start =>
    if byte != 91 then throw "catalogue must be a JSON array of strings"
    return ({ state with phase := .first }, none)
  | .first =>
    if byte == 93 then return ({ state with phase := .closed }, none)
    if byte != 34 then throw "catalogue row must be a JSON string"
    return ({ state with phase := .quoted, token := ByteArray.empty.push byte, escaped := false }, none)
  | .value =>
    if byte != 34 then throw "expected a JSON string after comma (trailing commas are invalid)"
    return ({ state with phase := .quoted, token := ByteArray.empty.push byte, escaped := false }, none)
  | .afterValue =>
    if byte == 44 then return ({ state with phase := .value }, none)
    if byte == 93 then return ({ state with phase := .closed }, none)
    throw "expected comma or closing bracket after source string"
  | .closed => throw "unexpected bytes after catalogue array"
  | .quoted => throw "internal scanner state"

private def unwrap {α : Type} (result : Except String α) : IO α :=
  match result with
  | .ok value => pure value
  | .error error => throw (IO.userError error)

private def parseJson {α : Type} [FromJson α] (text : String) : IO α :=
  unwrap (Json.parse text >>= fromJson?)

private def revisionPath (root : System.FilePath) (sourceKey revision : String) : IO System.FilePath := do
  if !validKey sourceKey then throw (IO.userError "source key requires 1..80 ASCII letters, digits, - or _")
  if !Digest.valid revision then throw (IO.userError "revision must be lowercase SHA-256")
  return root / "catalogues" / sourceKey / revision

/-- Validate the immutable manifest and both byte artifacts before returning data.
This is content integrity and provenance, not signature authentication. -/
def inspect (root : System.FilePath) (sourceKey revision : String) : IO Manifest := do
  let directory ← revisionPath root sourceKey revision
  let bytes ← IO.FS.withFile (directory / "manifest.json") .read (fun handle => handle.read 16385)
  if bytes.size > 16384 then throw (IO.userError "catalogue manifest exceeds budget")
  let raw ← unwrap (optionResult (String.fromUTF8? bytes) "invalid manifest UTF-8")
  let manifest : Manifest ← parseJson raw
  if manifest.format != "lemma-topic-catalogue/1" || manifest.importer != importVersion ||
      manifest.sourceKey != sourceKey || manifest.sourceDigest != revision ||
      manifest.records == 0 || manifest.records > maximumRecords || manifest.sourceBytes > maximumSourceBytes then
    throw (IO.userError "incompatible or malformed catalogue manifest")
  if (← Digest.sha256File (directory / "source.json")) != revision then
    throw (IO.userError "catalogue original source digest mismatch")
  if (← Digest.sha256File (directory / "records.jsonl")) != manifest.recordsDigest then
    throw (IO.userError "catalogue record artifact digest mismatch")
  return manifest

/-- Import into a fresh staging directory, retain exact original bytes and row
order, and publish by atomic directory rename. Different digests never replace
history. A failed import leaves no visible revision and removes its staging bytes.
Process-crash orphan staging reclamation belongs to the operator store boundary. -/
def importFile (root : System.FilePath) (sourceKey : String) (input : System.FilePath)
    (rights : String := "Owner-supplied source; redistribution rights unverified") : IO ImportReceipt := do
  if !validKey sourceKey then throw (IO.userError "invalid source key")
  let parent := root / "catalogues" / sourceKey
  IO.FS.createDirAll parent
  let staging := parent / s!".staging-{← IO.monoMsNow}-{← IO.rand 0 1000000000}"
  IO.FS.createDir staging
  try
    let (count, sourceBytes, digest) ← IO.FS.withFile input .read fun source =>
      IO.FS.withFile (staging / "source.json") .write fun original =>
        IO.FS.withFile (staging / "records.jsonl") .write fun rows => do
          let mut scanner : Scanner := {}
          let mut hashing : Digest.State := {}
          let mut position := 0
          repeat
            let chunk ← source.read 65536
            if chunk.isEmpty then break
            if hashing.bytes + chunk.size > maximumSourceBytes then throw (IO.userError "catalogue source exceeds 512MiB")
            original.write chunk
            hashing := Digest.update hashing chunk
            for byte in chunk.data do
              let (next, emitted) ← unwrap (feed scanner byte)
              scanner := next
              if let some value := emitted then
                rows.putStr ((toJson (record position value)).compress ++ "\n")
                position := position + 1
          if scanner.phase != .closed then throw (IO.userError "truncated catalogue JSON")
          if position == 0 then throw (IO.userError "empty catalogue cannot satisfy a source import")
          return (position, hashing.bytes, Digest.finish hashing)
    let destination := parent / digest
    if ← destination.pathExists then
      let manifest ← inspect root sourceKey digest
      IO.FS.removeDirAll staging
      return { manifest, directory := destination.toString, reused := true }
    let manifest : Manifest := {
      sourceKey, sourceDigest := digest, sourceBytes, records := count,
      recordsDigest := ← Digest.sha256File (staging / "records.jsonl"),
      originalName := input.fileName.getD "source.json", rights }
    IO.FS.writeFile (staging / "manifest.json") ((toJson manifest).pretty ++ "\n")
    IO.FS.rename staging destination
    return { manifest, directory := destination.toString, reused := false }
  catch error =>
    if ← staging.pathExists then IO.FS.removeDirAll staging
    throw error

private def foldRecords {α : Type} (path : System.FilePath) (expectedCount : Nat) (initial : α)
    (visit : α → Record → IO α) : IO α := do
  IO.FS.withFile path .read fun handle => do
    let mut result := initial
    let mut line := ByteArray.empty
    let mut expected := 0
    repeat
      let chunk ← handle.read 65536
      if chunk.isEmpty then break
      for byte in chunk.data do
        if byte == 10 then
          let text ← unwrap (optionResult (String.fromUTF8? line) "invalid record UTF-8")
          let row : Record ← parseJson text
          if row.position != expected || row.validation != "valid-json-string" ||
              row.originalUtf8Sha256 != Digest.sha256String row.original || row.numberLabel != numberLabel row.original then
            throw (IO.userError s!"invalid record at position {expected}")
          result ← visit result row
          expected := expected+1
          line := ByteArray.empty
        else
          if line.size > maximumTokenBytes*6+1024 then throw (IO.userError "record line exceeds decoding budget")
          line := line.push byte
    if !line.isEmpty then throw (IO.userError "truncated record artifact")
    if expected != expectedCount then throw (IO.userError "record count differs from manifest")
    return result

def search (root : System.FilePath) (sourceKey revision query : String) (offset : Nat := 0)
    (limit : Nat := 20) : IO SearchPage := do
  if limit == 0 || limit > 100 || query.utf8ByteSize > 1024 then throw (IO.userError "search requires page size 1..100 and query <=1024 bytes")
  let manifest ← inspect root sourceKey revision
  let directory ← revisionPath root sourceKey revision
  let normalized := query.toLower
  let (matchCount, selected) ← foldRecords (directory / "records.jsonl") manifest.records (0, (#[] : Array LocatedRecord)) fun (count, selected) row => do
    if normalized.isEmpty || (row.original.toLower.splitOn normalized).length > 1 then
      let selected := if count ≥ offset && selected.size < limit then
        selected.push { sourceDigest := revision, recordId := recordId revision row.position, record := row } else selected
      return (count+1, selected)
    return (count, selected)
  if matchCount > manifest.records then throw (IO.userError "record count exceeds manifest")
  return { sourceDigest := revision, query, offset, limit, matchCount, records := selected }

def lookup (root : System.FilePath) (sourceKey revision : String) (position : Nat) : IO LocatedRecord := do
  let manifest ← inspect root sourceKey revision
  if position ≥ manifest.records then throw (IO.userError "catalogue position is out of range")
  let directory ← revisionPath root sourceKey revision
  let found ← foldRecords (directory / "records.jsonl") manifest.records (none : Option Record) fun found row =>
    pure (if row.position == position then some row else found)
  match found with
  | some row => return { sourceDigest := revision, recordId := recordId revision position, record := row }
  | none => throw (IO.userError "manifest refers to a missing record")

/-- CLI can also be called by the school's operator command dispatcher. -/
def cli (arguments : List String) : IO UInt32 := do
  match arguments with
  | ["import",root,key,input] =>
    IO.println ((toJson (← importFile root key input)).pretty)
  | ["search",root,key,revision,query,offset,limit] =>
    let offset ← unwrap (optionResult offset.toNat? "invalid offset")
    let limit ← unwrap (optionResult limit.toNat? "invalid limit")
    IO.println ((toJson (← search root key revision query offset limit)).pretty)
  | ["lookup",root,key,revision,position] =>
    let position ← unwrap (optionResult position.toNat? "invalid position")
    IO.println ((toJson (← lookup root key revision position)).pretty)
  | ["inspect",root,key,revision] => IO.println ((toJson (← inspect root key revision)).pretty)
  | _ => throw (IO.userError "catalogue: import ROOT KEY INPUT | search ROOT KEY SHA QUERY OFFSET LIMIT | lookup ROOT KEY SHA POSITION | inspect ROOT KEY SHA")
  return 0

end Lemma.School.Catalogue
