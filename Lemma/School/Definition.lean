import Lemma.School.Authoring
import Lemma.School.Store

/-! Reusable school definitions are independent of a live deployment. This pure
package contains immutable publications, permitted reusable model references and
closed resource/policy requirements. It carries no learner history, grant,
credential, lease, execution generation or deployment identity. -/
namespace Lemma.School.Definition
open Lean

structure PublishedUnit where
  definition : Authoring.Unit
  policy : Nat
  artifact : String
  deriving Repr, ToJson, FromJson

structure ModelRelease where
  version : Nat
  artifact : String
  /-- Dependency artifacts; the parameter artifact is named separately above. -/
  artifacts : Array String
  rights : String
  reusable : Bool
  deriving Repr, ToJson, FromJson

structure Package where
  schema : String := "lemma-school-package/1"
  version : String := "0.1.0"
  publications : Array PublishedUnit := #[]
  models : Array ModelRelease := #[]
  selectedModel : Option Nat := none
  budgets : Budgets := {}
  tutorPolicy : String := "lemma-authored-assistance/1"
  learnerModel : String := "school-linear-q10-v1 with baseline"
  requiredProvider : String := "local"
  requiredWorkerProfile : String := "core0-v0.5"
  permissions : String := "closed; explicit per-school grants"
  deriving ToJson, FromJson

private def require (condition : Bool) (message : String) : Except String Unit :=
  if condition then .ok () else .error message

/-- Required immutable artifact bytes, excluding explicitly external source
texts referenced by source registries. The installer must verify/copy each byte
artifact before committing publications; this pure function does no file I/O. -/
def references (package : Package) : Array String :=
  let refs := package.publications.foldl (fun refs unit =>
    if refs.contains unit.artifact then refs else refs.push unit.artifact) #[]
  package.models.foldl (fun refs model =>
    (#[model.artifact] ++ model.artifacts).foldl (fun refs digest =>
      if refs.contains digest then refs else refs.push digest) refs) refs

def validate (package : Package) : Except String Unit := do
  require (package.schema == "lemma-school-package/1" && package.version == "0.1.0")
    "unsupported reusable school package schema/version"
  require (package.tutorPolicy == "lemma-authored-assistance/1") "unsupported tutor policy requirement"
  require (package.learnerModel == "school-linear-q10-v1 with baseline") "unsupported learner model requirement"
  require (package.requiredProvider == "local") "unsupported package provider requirement"
  require (package.requiredWorkerProfile == "core0-v0.5") "unsupported package worker profile requirement"
  require (package.permissions == "closed; explicit per-school grants") "package cannot transfer live permissions or grant authority"
  require (Store.validBudgets package.budgets) "unsupported package resource budgets"
  require (package.publications.size ≤ 128 && package.models.size ≤ 32)
    "package exceeds v0.1 publication/model count limits"
  let mut publications : Array (UInt64 × UInt64) := #[]
  for publication in package.publications do
    let identity := (publication.definition.course.identity, publication.definition.course.edition)
    require (!publications.contains identity) "duplicate course identity/edition in school package"
    publications := publications.push identity
    require (publication.policy > 0 && publication.policy ≤ 0x7ffffffffffffffe) "invalid publication policy version"
    let bytes ← Authoring.compile publication.definition
    require (publication.artifact == Digest.sha256Bytes bytes)
      s!"publication {identity.1}/{identity.2}: artifact differs from compiled authoring definition"
  let mut modelVersions : Array Nat := #[]
  for model in package.models do
    require model.reusable "package model was not explicitly marked reusable"
    require (model.version > 0 && model.version ≤ 0x7ffffffffffffffe && !modelVersions.contains model.version)
      "invalid or duplicate package model version"
    modelVersions := modelVersions.push model.version
    require (Digest.valid model.artifact && model.artifacts.all Digest.valid) "invalid package model artifact reference"
    require (model.artifacts.size > 0 && model.artifacts.size ≤ 32 && !model.artifacts.contains model.artifact)
      "model release needs 1..32 dependency artifacts, with its parameter artifact named separately"
    require (!model.rights.isEmpty && model.rights.utf8ByteSize ≤ 4096) "model release rights/provenance statement is required"
  if let some selected := package.selectedModel then
    require (modelVersions.contains selected) "selected model is not an included reusable release"
  require ((references package).size ≤ 1024) "package immutable artifact closure exceeds v0.1 bound"

private def rejectUnknown : Nat → Json → Json → String → Except String Unit
  | 0, _, _, path => .error s!"school package nesting exceeds decoding budget at {path}"
  | fuel+1, supplied, canonical, path => do
    match supplied, canonical with
    | .obj fields, .obj allowed =>
      for (key,value) in fields.toList do
        let expected ← match allowed.get? key with
          | some found => pure found
          | none => throw s!"unsupported school package field {path}.{key}; live state and credentials are excluded"
        rejectUnknown fuel value expected (path ++ "." ++ key)
    | .arr values, .arr expected =>
      if values.size != expected.size then throw s!"package array differs at {path}"
      for index in [:values.size] do
        rejectUnknown fuel values[index]! expected[index]! s!"{path}[{index}]"
    | _, _ => pure ()

/-- All supported teacher/developer package fields round-trip through one typed
representation; unrecognized extensions are rejected, never silently dropped. -/
def decode (value : Json) : Except String Package := do
  let package : Package ← fromJson? value
  rejectUnknown 64 value (toJson package) "package"
  validate package
  return package

/-- Extract immutable definitions and only explicitly reusable model releases.
Operational records and source-resolver deployment paths are not copied from
state. Owner locations already in a source manifest remain external metadata. -/
def fromState (state : State) : Except String Package := do
  let mut publications : Array PublishedUnit := #[]
  for row in state.allLatest "publication" do
    let definition ← field row.data "definition" >>= Authoring.decode
    let policy ← nat row.data "policy"
    let artifact ← str row.data "artifact"
    publications := publications.push {definition, policy, artifact}
  let mut models : Array ModelRelease := #[]
  for row in state.allLatest "model" do
    if flag row.data "reusable" then
      let artifact ← str row.data "artifact"
      let dependencies := row.artifacts.foldl (fun refs digest =>
        if digest == artifact || refs.contains digest then refs else refs.push digest) #[]
      models := models.push {
        version := ← nat row.data "version", artifact, artifacts := dependencies,
        rights := ← str row.data "rights", reusable := true }
  let selectedModel := (state.latest "model-selection" "active").bind fun row =>
    let selected := optionalNat row.data "version"
    if models.any (fun model => model.version == selected) then some selected else none
  let package : Package := {publications, models, selectedModel, budgets := state.budgets}
  validate package
  return package

end Lemma.School.Definition
