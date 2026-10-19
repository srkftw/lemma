import Lean
import Lemma.School.Digest

/-! Bibliographic identity, edition and extraction lineage are distinct from a
file digest. Possession and verified bytes never grant redistribution rights. -/
namespace Lemma.School.SourceRegistry
open Lean

inductive Verification where
  | verified | ambiguous | ocrDerived | unavailable
  deriving BEq, Repr, ToJson, FromJson, Inhabited

structure Source where
  id : String
  title : String
  authors : Array String
  edition : String
  publication : String
  bibliographicStatus : Verification
  bibliographicEvidence : String
  fileDigest : String
  mediaType : String
  ownerLocation : String
  rights : String
  deriving Repr, ToJson, FromJson

structure Extraction where
  method : String
  toolVersion : String
  inputDigest : String
  outputDigest : String
  parentOutputDigest : Option String := none
  deriving Repr, ToJson, FromJson

structure Anchor where
  id : String
  sourceId : String
  edition : String
  fileDigest : String
  pdfPageIndex : Option Nat := none
  printedPageLabel : Option String := none
  sectionLabel : String
  exercise : Option String := none
  verification : Verification
  evidence : String
  extraction : Option Extraction := none
  deriving Repr, ToJson, FromJson

structure Registry where
  format : String := "lemma-source-registry/1"
  sources : Array Source
  deriving Repr, ToJson, FromJson

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

def validate (registry : Registry) : Except String Unit := do
  require (registry.format == "lemma-source-registry/1") "unsupported source registry format"
  require (registry.sources.size > 0 && registry.sources.size ≤ 128) "registry requires 1..128 sources"
  let mut ids : Array String := #[]
  for source in registry.sources do
    require (!source.id.isEmpty && !ids.contains source.id) s!"missing or duplicate source id: {source.id}"
    ids := ids.push source.id
    require (!source.title.isEmpty && !source.edition.isEmpty && !source.rights.isEmpty) s!"source {source.id}: title, edition and rights are required"
    require (Digest.valid source.fileDigest) s!"source {source.id}: invalid SHA-256"
    require (!source.ownerLocation.isEmpty) s!"source {source.id}: owner resolver is missing"
    if source.bibliographicStatus == .verified then
      require (!source.bibliographicEvidence.isEmpty) s!"source {source.id}: verified bibliography needs evidence"

def validateAnchor (registry : Registry) (anchor : Anchor) : Except String Unit := do
  require (!anchor.id.isEmpty) "source anchor id is empty"
  let source ← match registry.sources.find? (fun source => source.id == anchor.sourceId) with
    | some source => pure source
    | none => throw s!"anchor {anchor.id}: unknown source {anchor.sourceId}"
  require (anchor.edition == source.edition && anchor.fileDigest == source.fileDigest)
    s!"anchor {anchor.id}: edition/file identity differs from registered source"
  require (!anchor.sectionLabel.isEmpty || anchor.pdfPageIndex.isSome) s!"anchor {anchor.id}: no source context locator"
  if anchor.pdfPageIndex.isSome then
    require (source.mediaType == "application/pdf") s!"anchor {anchor.id}: PDF page index requires PDF source"
  if anchor.verification == .verified then
    require (!anchor.evidence.isEmpty) s!"anchor {anchor.id}: verified context needs inspection evidence"
  if anchor.verification == .ocrDerived then
    require anchor.extraction.isSome s!"anchor {anchor.id}: OCR match needs extraction lineage"
  if let some extraction := anchor.extraction then
    require (extraction.inputDigest == source.fileDigest) s!"anchor {anchor.id}: extraction input is a different edition/file"
    require (Digest.valid extraction.outputDigest) s!"anchor {anchor.id}: extraction output digest invalid"
    require (!extraction.method.isEmpty && !extraction.toolVersion.isEmpty) s!"anchor {anchor.id}: extraction method/version missing"
    if let some parent := extraction.parentOutputDigest then
      require (Digest.valid parent) s!"anchor {anchor.id}: extraction parent digest invalid"

/-- Resolve explicitly owner-configured bytes only. Missing source is recoverable;
lookup never downloads a text or guesses a neighbouring edition. -/
def resolve (source : Source) : IO System.FilePath := do
  let path := System.FilePath.mk source.ownerLocation
  if !(← path.pathExists) then throw (IO.userError s!"MissingSource: configure owner source {source.id} at {source.ownerLocation}")
  if (← Digest.sha256File path) != source.fileDigest then
    throw (IO.userError s!"SourceIdentityMismatch: {source.id}; expected edition {source.edition}")
  return path

end Lemma.School.SourceRegistry
