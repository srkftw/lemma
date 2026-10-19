import Lemma.School.Model
import Lemma.School.Digest

/-! Permissioned observation metadata. Origins describe how evidence arose;
execution describes live delivery or replay. Neither estimates psychological
state, grants sensor activation, nor implies eligibility for private training. -/
namespace Lemma.School.Observation
open Lean

inductive Modality where
  | ink | text | voice | image | gaze | eeg | physiology
  deriving BEq, Repr, ToJson, FromJson, Inhabited
inductive SourceClass where
  | device | userProvided | derived | syntheticFixture
  deriving BEq, Repr, ToJson, FromJson, Inhabited
inductive Origin where
  | measured | derived | synthetic
  deriving BEq, Repr, ToJson, FromJson, Inhabited
inductive Execution where
  | live | replay
  deriving BEq, Repr, ToJson, FromJson, Inhabited
inductive Missingness where
  | present
  | absent (reason : String)
  deriving BEq, Repr, ToJson, FromJson, Inhabited

structure Observation where
  schema : String := "lemma-observation/1"
  id : String
  executionId : String
  school : String
  learner : String
  modality : Modality
  sourceClass : SourceClass
  sourceId : String
  acquiredAt : Nat
  acquisitionClock : String
  calibration : Option String := none
  quality : Option String := none
  missingness : Missingness
  artifact : Option String := none
  origin : Origin
  parentObservationIds : Array String := #[]
  execution : Execution
  executionAt : Nat
  executionClock : String
  replayOf : Option String := none
  deriving Repr, ToJson, FromJson

inductive Operation where
  | collection | processing | upload | retention | training | exportData
  deriving BEq, Repr, ToJson, FromJson, Inhabited

structure Consent where
  schema : String := "lemma-observation-consent/1"
  version : Nat
  school : String
  learner : String
  resource : String
  collection : Bool := false
  processing : Bool := false
  upload : Bool := false
  retention : Bool := false
  training : Bool := false
  exportAllowed : Bool := false
  revoked : Bool := false
  deriving Repr, ToJson, FromJson

private def require (condition : Bool) (detail : String) : Except String Unit :=
  if condition then .ok () else .error detail
private def optionalMetadata (value : Option String) : Bool :=
  value.all (fun text => !text.isEmpty && text.utf8ByteSize ≤ 512)

def validate (observation : Observation) : Except String Unit := do
  require (observation.schema == "lemma-observation/1") "unsupported observation schema"
  require (#[observation.id,observation.executionId,observation.school,observation.learner,
    observation.sourceId,observation.acquisitionClock,observation.executionClock].all validId) "invalid observation identity or clock context"
  require (observation.acquiredAt ≤ 0x7ffffffffffffffe && observation.executionAt ≤ 0x7ffffffffffffffe)
    "observation timestamp exceeds admitted clock range"
  require (optionalMetadata observation.calibration && optionalMetadata observation.quality) "calibration/quality metadata is empty or exceeds 512 bytes"
  require (observation.parentObservationIds.size ≤ 16 && observation.parentObservationIds.all validId) "invalid or excessive observation lineage"
  if observation.origin == .derived then
    require (!observation.parentObservationIds.isEmpty) "derived observation needs parent observation lineage"
  if observation.sourceClass == .syntheticFixture then
    require (observation.origin == .synthetic) "synthetic source cannot become measured evidence"
  if observation.sourceClass == .derived then
    require (observation.origin == .derived) "derived source requires derived origin"
  match observation.missingness, observation.artifact with
  | .present, some digest => require (Digest.valid digest) "present observation artifact needs lowercase SHA-256"
  | .present, none => throw "present observation has no artifact"
  | .absent reason, none => require (!reason.isEmpty && reason.utf8ByteSize ≤ 512) "missing observation needs a bounded explicit reason"
  | .absent _, some _ => throw "missing observation must not contain measurement bytes"
  match observation.execution with
  | .live =>
    require (observation.executionId == observation.id && observation.replayOf.isNone) "live observation execution identity/replay metadata differs"
  | .replay =>
    require (observation.executionId != observation.id && observation.replayOf == some observation.id)
      "replay must retain original observation identity and name a distinct execution"
  if observation.acquisitionClock == observation.executionClock then
    require (observation.acquiredAt ≤ observation.executionAt) "execution precedes acquisition in the same clock"

/-- Replay creates execution provenance only. It retains the exact acquisition,
origin, source, missingness and artifact identity, including synthetic origin. -/
def replay (original : Observation) (executionId : String) (executionAt : Nat)
    (executionClock : String) : Except String Observation := do
  validate original
  let repeated := {original with
    execution := .replay, executionId, executionAt, executionClock, replayOf := some original.id}
  validate repeated
  return repeated

def validateConsent (consent : Consent) : Except String Unit := do
  require (consent.schema == "lemma-observation-consent/1" && consent.version > 0 && consent.version ≤ 0x7ffffffffffffffe)
    "unsupported consent schema/version"
  require (#[consent.school,consent.learner,consent.resource].all validId) "invalid consent scope"

/-- The caller supplies the latest durable consent version. Grants are distinct:
upload never implies training, collection never implies retention or export. -/
def admit (consent : Consent) (operation : Operation) (observation : Observation) : Except String Unit := do
  validate observation
  validateConsent consent
  require (!consent.revoked) "observation consent revoked"
  require (consent.school == observation.school && consent.learner == observation.learner &&
    (consent.resource == observation.id || consent.resource == observation.sourceId)) "observation is outside consent school/learner/resource scope"
  let allowed := match operation with
    | .collection => consent.collection
    | .processing => consent.processing
    | .upload => consent.upload
    | .retention => consent.retention
    | .training => consent.training
    | .exportData => consent.exportAllowed
  require allowed s!"observation operation is not consented: {repr operation}"

/-- Eligibility is rebuilt against current grants. This does not promise deletion
from previously fitted artifacts or implement a private-data training loader. -/
def eligibleForTraining (consent : Consent) (observation : Observation) : Bool :=
  observation.missingness == .present &&
  (admit consent .training observation).isOk &&
  (admit consent .processing observation).isOk &&
  (admit consent .retention observation).isOk

end Lemma.School.Observation
