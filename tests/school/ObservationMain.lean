import Lemma.School.Observation
open Lean Lemma.School
open Observation

private def base : Observation := {
  id := "observation-1", executionId := "observation-1", school := "school-a", learner := "learner-a",
  modality := .ink, sourceClass := .syntheticFixture, sourceId := "fixture-ink",
  acquiredAt := 100, acquisitionClock := "device-tick", missingness := .present,
  artifact := some (Digest.sha256String "synthetic-ink"), origin := .synthetic,
  execution := .live, executionAt := 200, executionClock := "device-tick" }
private def consent : Consent := {
  version := 1, school := "school-a", learner := "learner-a", resource := "fixture-ink",
  collection := true, processing := true, retention := true, training := true }

def main : IO Unit := do
  let repeated ← IO.ofExcept (Observation.replay base "execution-replay-1" 10 "replay-clock")
  let missing := {base with missingness := .absent "optional sensor not attached", artifact := none}
  let derived := {base with sourceClass := .derived, origin := .derived, parentObservationIds := #[base.id]}
  IO.println (Json.mkObj [
    ("live-valid",toJson (Observation.validate base).isOk),
    ("replay-valid",toJson (Observation.validate repeated).isOk),
    ("replay-preserves",toJson (repeated.id == base.id && repeated.acquiredAt == base.acquiredAt &&
      repeated.acquisitionClock == base.acquisitionClock && repeated.artifact == base.artifact &&
      repeated.origin == base.origin && repeated.sourceClass == base.sourceClass)),
    ("replay-execution-distinct",toJson (repeated.executionId != base.executionId && repeated.execution == .replay && repeated.executionClock == "replay-clock")),
    ("missing-valid",toJson (Observation.validate missing).isOk),
    ("missing-bytes-rejected",toJson !(Observation.validate {missing with artifact := base.artifact}).isOk),
    ("present-without-bytes-rejected",toJson !(Observation.validate {base with artifact := none}).isOk),
    ("synthetic-measured-rejected",toJson !(Observation.validate {base with origin := .measured}).isOk),
    ("derived-valid",toJson (Observation.validate derived).isOk),
    ("derived-missing-lineage-rejected",toJson !(Observation.validate {derived with parentObservationIds := #[]}).isOk),
    ("collection-allowed",toJson (Observation.admit consent .collection base).isOk),
    ("upload-independent",toJson !(Observation.admit consent .upload base).isOk),
    ("export-independent",toJson !(Observation.admit consent .exportData base).isOk),
    ("training-eligible",toJson (Observation.eligibleForTraining consent base)),
    ("revocation-effective",toJson !(Observation.eligibleForTraining {consent with version := 2, revoked := true} base)),
    ("processing-independent",toJson !(Observation.eligibleForTraining {consent with processing := false} base)),
    ("retention-independent",toJson !(Observation.eligibleForTraining {consent with retention := false} base)),
    ("missing-not-training",toJson !(Observation.eligibleForTraining consent missing)),
    ("cross-school-rejected",toJson !(Observation.admit {consent with school := "school-b"} .collection base).isOk),
    ("cross-learner-rejected",toJson !(Observation.admit {consent with learner := "learner-b"} .collection base).isOk),
    ("cross-resource-rejected",toJson !(Observation.admit {consent with resource := "another-source"} .collection base).isOk),
    ("same-clock-rollback-rejected",toJson !(Observation.replay base "replay-2" 50 "device-tick").isOk)]).compress
