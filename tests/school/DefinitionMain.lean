import Lemma.School.Definition
import Lemma.School.FixtureUnit
open Lean Lemma.School

private def liveState : Except String State := do
  let unit := FixtureUnit.unit
  let bytes ← Authoring.compile unit
  let publicModel := Digest.sha256String "permitted-model-descriptor-fixture"
  let dataset := Digest.sha256String "permitted-dataset-descriptor-fixture"
  let privateModel := Digest.sha256String "private-model-descriptor-fixture"
  let state : State := {school := "private-school-unique", deployment := "live-deployment-unique", operator := "live-owner-unique"}
  let state ← state.add "publication" "801.1" state.operator 1 (object [
    ("definition",toJson unit),("policy",toJson (1:Nat)),("artifact",toJson (Digest.sha256Bytes bytes))]) #[Digest.sha256Bytes bytes]
  let state ← state.add "model" "1" state.operator 2 (object [
    ("version",toJson (1:Nat)),("artifact",toJson publicModel),("reusable",toJson true),
    ("rights",toJson "Original descriptor fixture, explicit local reuse")]) #[publicModel,dataset]
  let state ← state.add "model" "2" state.operator 3 (object [
    ("version",toJson (2:Nat)),("artifact",toJson privateModel),("reusable",toJson false),
    ("rights",toJson "Private descriptor; no reuse")]) #[privateModel]
  let state ← state.add "model-selection" "active" state.operator 4 (object [("version",toJson (2:Nat))]) #[privateModel]
  let state ← state.add "attempt" "private-attempt-unique" "private-learner-unique" 5
    (object [("privateWork",toJson "secret-private-learner-work-unique")])
  let state ← state.add "grant" "private-grant-unique" state.operator 6
    (object [("credential",toJson "secret-live-credential-unique")])
  state.add "source-config" (Digest.sha256String "source") state.operator 7
    (object [("path",toJson "/private/deployment/source-resolver-unique")])

private def addField (json : Json) (name : String) (value : Json) : Json :=
  match json.getObj? with
  | .ok fields => .obj (fields.insert name value)
  | .error _ => json

def main (arguments : List String) : IO Unit := do
  let state ← IO.ofExcept liveState
  let package ← IO.ofExcept (Definition.fromState state)
  if arguments == ["emit"] then
    IO.println (toJson package).pretty
    return
  let publicSelection ← IO.ofExcept (state.add "model-selection" "active" state.operator 8 (object [("version",toJson (1:Nat))]))
  let publicPackage ← IO.ofExcept (Definition.fromState publicSelection)
  let publication ← IO.ofExcept (package.publications[0]?.toExcept "test publication missing")
  let model ← IO.ofExcept (package.models[0]?.toExcept "test model missing")
  let changedDefinition := {publication.definition with course := {publication.definition.course with title := "different authored content"}}
  let originalModel ← IO.ofExcept ((state.latest "model" "1").toExcept "model fixture missing")
  let dependencies := (Array.range 32).map (fun i => Digest.sha256String s!"dependency-{i}")
  let maximalState ← IO.ofExcept (state.add "model" "1" state.operator 8 originalModel.data (#[model.artifact] ++ dependencies))
  let maximal ← IO.ofExcept (Definition.fromState maximalState)
  let maximalModel ← IO.ofExcept (maximal.models[0]?.toExcept "maximal model missing")
  let json := toJson package
  let suppliedPublication := addField (toJson publication) "credentials" (toJson "forbidden")
  let nested := addField json "publications" (toJson #[suppliedPublication])
  let roundtrip := match Definition.decode json with
    | .ok decoded => toJson decoded == json
    | .error _ => false
  let checks : List (String × Json) := [
    ("roundtrip",toJson roundtrip),
    ("one-publication",toJson (package.publications.size == 1)),
    ("reusable-only",toJson (package.models.size == 1 && model.version == 1)),
    ("private-selection-excluded",toJson package.selectedModel.isNone),
    ("public-selection-retained",toJson (publicPackage.selectedModel == some 1)),
    ("closure-deduplicated",toJson ((Definition.references package).size == 3)),
    ("parameter-not-duplicated-in-dependencies",toJson (!model.artifacts.contains model.artifact)),
    ("maximal-admitted-dependency-closure-retained",toJson (maximalModel.artifacts.size == 32 && (Definition.references maximal).size == 34)),
    ("top-live-field-rejected",toJson !(Definition.decode (addField json "deployment" (toJson "live"))).isOk),
    ("nested-live-field-rejected",toJson !(Definition.decode nested).isOk),
    ("provider-rejected",toJson !(Definition.validate {package with requiredProvider := "remote-unimplemented"}).isOk),
    ("worker-profile-rejected",toJson !(Definition.validate {package with requiredWorkerProfile := "arbitrary-worker"}).isOk),
    ("policy-rejected",toJson !(Definition.validate {package with tutorPolicy := "unknown-policy"}).isOk),
    ("learner-model-rejected",toJson !(Definition.validate {package with learnerModel := "unknown-model"}).isOk),
    ("permissions-rejected",toJson !(Definition.validate {package with permissions := "grant-everything"}).isOk),
    ("budget-rejected",toJson !(Definition.validate {package with budgets := {maxEvents := 0}}).isOk),
    ("version-rejected",toJson !(Definition.validate {package with version := "99"}).isOk),
    ("artifact-binding-rejected",toJson !(Definition.validate {package with publications := #[{publication with artifact := Digest.sha256String "different artifact"}]}).isOk),
    ("definition-drift-rejected",toJson !(Definition.validate {package with publications := #[{publication with definition := changedDefinition}]}).isOk),
    ("duplicate-publication-rejected",toJson !(Definition.validate {package with publications := #[publication,publication]}).isOk),
    ("private-model-rejected",toJson !(Definition.validate {package with models := #[{model with reusable := false}]}).isOk),
    ("missing-model-selection-rejected",toJson !(Definition.validate {package with selectedModel := some 99}).isOk),
    ("duplicate-model-rejected",toJson !(Definition.validate {package with models := #[model,model]}).isOk),
    ("rights-required",toJson !(Definition.validate {package with models := #[{model with rights := ""}]}).isOk)]
  IO.println (Json.mkObj checks).compress
