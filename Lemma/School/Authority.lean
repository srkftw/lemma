import Lemma.School.Store
import Lemma.School.Client
import Lemma.School.Observation
import Lemma.School.Authoring
import Lemma.School.Definition
import Lemma.School.LearnerChoice
import Lemma.School.LocalProvider
import Lemma.School.Review
import Lemma.School.Admission
import Lemma.School.Submission
import Lemma.School.Recommendation
import Lemma.School.ReviewRender
import Lemma.School.Delivery
import Lemma.Documents.Mathematics

/-! One local database-oriented authority. Every decision below is maintained
Lean; the host launcher only locks processes and conveys opaque JSON bytes. -/
namespace Lemma.School.Authority
open Lean System Store

private def need (condition : Bool) (message : String) : IO Unit :=
  unless condition do fail message
private def freshDestination (path : FilePath) : IO Unit := do
  if ← path.pathExists then
    need ((← path.metadata).type == .dir) "destination is not a directory"
    for entry in ← path.readDir do
      need (entry.fileName == "authority.lock") "destination must be fresh; only its process lock may exist"
private def hex (bytes : ByteArray) : String :=
  String.ofList <| bytes.data.toList.flatMap fun b =>
    let digit (n : Nat) : Char := Char.ofNat (if n < 10 then 48+n else 87+n)
    [digit (b.toNat / 16),digit (b.toNat % 16)]
private def stableRequest (request : Json) : Json :=
  match request.getObj? with | .ok fields => Json.obj (fields.erase "now") | .error _ => request
private def key (course revision : Nat) : String := s!"{course}.{revision}"
private def wireInt (value : Int) : Nat :=
  if value < 0 then 18446744073709551616 - value.natAbs else value.toNat
private def wordsToBytes (values : Array Nat) : ByteArray := Id.run do
  let mut bytes := ByteArray.empty
  for value in values do
    for i in [:8] do bytes := bytes.push ((value >>> (8*i)).toUInt8)
  return bytes
private def enrollmentKey (learner : String) (course revision : Nat) : String := s!"{learner}.{course}.{revision}"
private def publication (state : State) (course revision : Nat) : IO Record :=
  lift <| (state.latest "publication" (key course revision)).toExcept "course publication absent"
private def enrolled (state : State) (actor : String) (course revision : Nat) : IO Unit :=
  need ((state.latest "enrollment" (enrollmentKey actor course revision)).any (fun row => !flag row.data "revoked")) "learner is not enrolled in this publication or enrollment revoked"
private def definition (row : Record) : IO Authoring.Unit :=
  lift <| (field row.data "definition" >>= Authoring.decode)
private def recordResult (row : Record) : Json :=
  object [("sequence",toJson row.sequence),("record",toJson row)]
private def append (state : State) (kind id actor : String) (now : Nat)
    (data : Json) (refs : Array String := #[]) : IO (State × Json) := do
  let next ← lift (state.add kind id actor now data refs)
  return (next,recordResult next.records.back!)
private def checkTime (state : State) (request : Json) : IO Nat := do
  let now ← if state.clockModel == "controlled-ms" then pure (optionalNat request "now" state.clock)
    else do
      need (!(field request "now").isOk) "explicit now requires controlled-ms school clock"
      schedulingNow state
  need (now >= state.clock && now <= 0x7ffffffffffffffe) "authority clock rollback/range rejected"
  return now
private def permitted (state : State) (actor action resource : String) : IO Unit :=
  lift (state.authorize actor action resource)

private def consentKey (learner resource : String) : String :=
  Digest.sha256String (toJson #[learner,resource]).compress

private def consentFor (state : State) (observation : Observation.Observation) : IO Observation.Consent := do
  let row ← lift <| ((state.latest "consent" (consentKey observation.learner observation.id)).orElse
    (fun _ => state.latest "consent" (consentKey observation.learner observation.sourceId))).toExcept "observation consent absent"
  lift (fromJson? row.data)

private def due (state : State) (actor : String) (now : Nat) : Json :=
  toJson <| (state.allLatest "review").filter (fun r => optionalStr r.data "learner" == actor &&
    optionalNat r.data "due" > 0 && optionalNat r.data "due" <= now && Review.active r)

private def copyExport (root destination : FilePath) (state : State) (sourceRecords : Nat) : IO Unit := do
  need (!(← destination.pathExists)) "export destination already exists"
  IO.FS.createDirAll destination
  for digest in state.references do
    let bytes ← readBounded (artifactPath root digest) state.budgets.maxArtifactBytes
    let copied ← putBytes destination bytes state.budgets.maxArtifactBytes
    need (copied == digest) "export artifact identity differs"
  commit destination state
  IO.FS.writeFile (destination / "export.json") ((object [
    ("schema",toJson "lemma-school-export/1"),("school",toJson state.school),
    ("deployment",toJson state.deployment),("generation",toJson state.generation),
    ("snapshot",toJson (← Digest.sha256File (destination / "state.json"))),
    ("selection",toJson "committed-history-prefix"),("throughSequence",toJson state.records.size),
    ("sourceRecords",toJson sourceRecords),
    ("artifacts",toJson state.references),
    ("externalSources",toJson "Source registries retain owner locations and digests; textbook/source bytes are not automatically bundled. Resolve explicitly after restore."),
    ("mode",toJson "offline-authority; stop the original before restoring")]).compress ++ "\n")
  barrier "file" (destination / "export.json")
  syncDirectoryAndParent destination

private def writeDefinition (root destination : FilePath) (package : Definition.Package) : IO Unit := do
  lift (Definition.validate package)
  need (!(← destination.pathExists)) "school package destination already exists"
  IO.FS.createDirAll destination
  for digest in Definition.references package do
    requireArtifact root digest package.budgets.maxArtifactBytes
    let copied ← putBytes destination (← readBounded (artifactPath root digest) package.budgets.maxArtifactBytes) package.budgets.maxArtifactBytes
    need (copied == digest) "definition artifact differs during copy"
  IO.FS.writeFile (destination / "school-package.part") ((toJson package).compress ++ "\n")
  barrier "file" (destination / "school-package.part")
  IO.FS.rename (destination / "school-package.part") (destination / "school-package.json")
  syncDirectoryAndParent destination

/-- Restore copies bytes into a new directory. The caller must explicitly name
offline authority recovery; this is not independent replication. -/
def restore (destination : FilePath) (request : Json) : IO Json := do
  need (flag request "offline") "restore requires offline=true; simultaneous authorities are unsupported"
  need (!(← (destination / "state.json").pathExists)) "restore destination already initialized"
  freshDestination destination
  let source := FilePath.mk (← lift (str request "from"))
  let receipt ← readJson (source / "export.json")
  need ((← lift (str receipt "schema")) == "lemma-school-export/1") "unsupported export"
  need ((← lift (str receipt "snapshot")) == (← Digest.sha256File (source / "state.json"))) "export snapshot differs"
  let state ← load source
  need ((← lift (str request "school")) == state.school && (← lift (str request "actor")) == state.operator) "restore authority differs"
  for digest in state.references do
    let copied ← putBytes destination (← readBounded (artifactPath source digest) state.budgets.maxArtifactBytes) state.budgets.maxArtifactBytes
    need (copied == digest) "restore artifact differs"
  let next ← bindClock state true
  commit destination next
  return object [("school",toJson next.school),("generation",toJson next.generation),
    ("clockEpoch",toJson next.clockEpoch),("clockEpochSequence",toJson next.clockEpochSequence),
    ("offlineElapsed",toJson "same boot measured; unknown cross-boot time frozen"),
    ("mode",toJson "offline-restored-authority")]

private def registerModel (root : FilePath) (state : State) (actor : String) (now : Nat)
    (request : Json) : IO (State × Json) := do
  permitted state actor "publish" "school"
  let digest ← lift (str request "artifact")
  requireArtifact root digest
  let parameters ← readJson (artifactPath root digest) 16384
  need (optionalStr parameters "schema" == "lemma-linear-parameters/v1" &&
    optionalStr parameters "profile" == "school-linear-q10-v1" &&
    optionalNat parameters "dimensions" == 2 && optionalNat parameters "scale" == 1024)
    "unsupported model artifact shape or numerical profile"
  let version ← lift (nat parameters "version")
  let weights : Array Int ← lift (field parameters "quantized" >>= fromJson?)
  need (version > 0 && version <= 0x7ffffffffffffffe && weights.size == 3 && weights.all (fun w => w.natAbs <= 8192)) "model parameter range rejected"
  let id := toString version
  if let some old := state.latest "model" id then
    need (optionalStr old.data "artifact" == digest) "immutable model version conflict"
    return (state,recordResult old)
  let closure : Array String ← lift (field request "artifacts" >>= fromJson?)
  need (closure.size > 0 && closure.size <= 32 && closure.contains (optionalStr parameters "dataset"))
    "model release requires its dataset manifest in the declared artifact closure"
  for artifact in closure do requireArtifact root artifact
  let dataset ← readJson (artifactPath root (optionalStr parameters "dataset")) 65536
  need (#["lemma-synthetic-risk-dataset/v1","lemma-permitted-risk-dataset/v1"].contains (optionalStr dataset "schema"))
    "private or unknown dataset training profile unsupported"
  need (!(optionalStr dataset "source").isEmpty && !(optionalStr dataset "grant").isEmpty &&
    !(optionalStr dataset "labelOrigin").isEmpty && Digest.valid (optionalStr dataset "transformationDigest"))
    "model release requires explicit source/grant/independent-label/transformation provenance"
  for name in #["trainDigest","evaluationDigest"] do
    need (closure.contains (optionalStr dataset name)) s!"model release closure lacks {name}"
  append state "model" id actor now (object [("artifact",toJson digest),("version",toJson version),
    ("profile",toJson "school-linear-q10-v1"),("dataset",toJson (optionalStr parameters "dataset")),
    ("reusable",toJson (flag request "reusable")),("rights",toJson (optionalStr request "rights" "unresolved; owner controlled")),
    ("scope",toJson "bounded declared-data scorer; no measured educational effect")]) (#[digest] ++ closure)

def execute (root : FilePath) (state : State) (request : Json) : IO (State × Json) := do
  let now ← checkTime state request
  let request ← if optionalStr request "op" == "client" then lift (Admission.resolve state request now) else pure request
  let actor ← lift (state.checkSchool request)
  let op ← lift (str request "op")
  let state := {state with clock := now}
  if Review.handles op then return ← lift (Review.execute state actor request now)
  if Admission.handles op then return ← lift (Admission.execute state actor request now)
  match op with
  | "status" =>
    permitted state actor "read" "school"
    return (state,object [("school",toJson state.school),("deployment",toJson state.deployment),
      ("generation",toJson state.generation),("clock",toJson now),("clockModel",toJson state.clockModel),("records",toJson state.records.size),
      ("clockEpoch",toJson state.clockEpoch),("clockEpochSequence",toJson state.clockEpochSequence),
      ("offlineElapsed",toJson "same boot measured; unknown cross-boot time frozen"),
      ("provider",toJson "local"),("storage",toJson "fsync-file+rename+fsync-parent/1; requires filesystem/device barrier guarantees"),
      ("budgets",toJson state.budgets),("jobs",toJson (state.allLatest "job")),
      ("artifacts",toJson state.references),("capabilities",toJson #["local-school","course-package/1","stdio/1","rv64-linear-worker/1"] ),
      ("localProvider",LocalProvider.describe state)])
  | "node-config" | "worker-config" | "worker-health" | "node-drain" | "worker-drain" =>
    let (next,row) ← lift (LocalProvider.apply state actor now request)
    for digest in row.artifacts do requireArtifact root digest state.budgets.maxArtifactBytes
    return (next,recordResult row)
  | "provider-status" =>
    permitted state actor "read" "school"
    return (state,LocalProvider.describe state)
  | "consent" =>
    let consent : Observation.Consent ← lift (field request "consent" >>= fromJson?)
    lift (Observation.validateConsent consent)
    need (consent.school == state.school && consent.learner == actor) "consent requires the owning learner in this school"
    let id := consentKey actor consent.resource
    if let some prior := state.latest "consent" id then
      need (consent.version > optionalNat prior.data "version") "consent version must advance"
    append state "consent" id actor now (toJson consent)
  | "observation-put" =>
    let observation : Observation.Observation ← lift (field request "observation" >>= fromJson?)
    need (observation.school == state.school && observation.learner == actor && observation.execution == .live)
      "new observation must be the owning learner's acquisition; use observation-replay for replay"
    let consent ← consentFor state observation
    lift (Observation.admit consent .collection observation)
    lift (Observation.admit consent .retention observation)
    for parent in observation.parentObservationIds do
      let row ← lift <| (state.latest "observation" parent).toExcept "derived observation parent absent"
      let original : Observation.Observation ← lift (fromJson? row.data)
      need (original.school == state.school && original.learner == actor) "derived parent outside learner scope"
    let refs := observation.artifact.toArray
    for digest in refs do requireArtifact root digest
    if let some prior := state.latest "observation" observation.id then
      need (prior.data == toJson observation) "immutable observation identity conflict"
      return (state,recordResult prior)
    append state "observation" observation.id actor now (toJson observation) refs
  | "observation-replay" =>
    let id ← lift (str request "id")
    let row ← lift <| (state.latest "observation" id).toExcept "original observation absent"
    let original : Observation.Observation ← lift (fromJson? row.data)
    need (original.learner == actor) "replay outside learner scope"
    lift (Observation.admit (← consentFor state original) .processing original)
    lift (Observation.admit (← consentFor state original) .retention original)
    let executionId ← lift (str request "executionId")
    need ((state.latest "replay" executionId).isNone) "replay execution identity already used"
    let repeated ← lift (Observation.replay original executionId (← lift (nat request "executionAt")) (← lift (str request "executionClock")))
    append state "replay" executionId actor now (toJson repeated) row.artifacts
  | "observations" | "dataset-eligible" =>
    let learner := optionalStr request "learner" actor
    if learner != actor then permitted state actor (if op == "dataset-eligible" then "train" else "read") learner
    let mut selected : Array Json := #[]
    for row in state.allLatest "observation" do
      let observation : Observation.Observation ← lift (fromJson? row.data)
      if observation.learner == learner then
        let consent ← consentFor state observation
        if (if op == "dataset-eligible" then Observation.eligibleForTraining consent observation else
            (Observation.admit consent .processing observation).isOk) then
          selected := selected.push row.data
    return (state,object [("observations",toJson selected),("scope",toJson "current consent eligibility; no private-data trainer or retroactive unlearning")])
  | "grant" =>
    permitted state actor "admin" "school"
    let subject ← lift (str request "subject")
    let action ← lift (str request "action")
    let resource ← lift (str request "resource")
    need (validId subject && validId action && !resource.isEmpty && resource.utf8ByteSize <= 128) "invalid grant scope"
    append state "grant" (Digest.sha256String (toJson #[subject,action,resource]).compress) actor now request
  | "guest-submit" =>
    let bytes ← lift (Admission.uploadBytes request)
    let envelope ← lift (Submission.decode bytes)
    let pub ← publication state envelope.course envelope.edition
    let package ← readBounded (artifactPath root (optionalStr pub.data "artifact")) 32768
    need ((← lift (Submission.word package 80)).toNat == envelope.packageCRC)
      "guest submitted package CRC differs from original immutable publication"
    let digest := Digest.sha256Bytes bytes
    let (next,receipt) ← lift (Submission.admit state actor envelope digest (Submission.crc32 bytes) now)
    if next.records.size != state.records.size then
      let stored ← putBytes root bytes (min 262144 state.budgets.maxArtifactBytes)
      need (stored == digest) "guest artifact identity changed while staging"
      faultBoundary "after-artifact"
    else requireArtifact root digest
    return (next,receipt)
  | "work-upload" =>
    let bytes ← lift (Admission.uploadBytes request)
    let digest ← putBytes root bytes (min 262144 state.budgets.maxArtifactBytes)
    let id := s!"{actor}.{digest}"
    if (state.latest "work-upload" id).isSome then
      return (state,object [("digest",toJson digest),("bytes",toJson bytes.size),("state",toJson "retained-upload")])
    let next ← lift (state.add "work-upload" id actor now (object [("digest",toJson digest)]) #[digest])
    return (next,object [("digest",toJson digest),("bytes",toJson bytes.size),("state",toJson "retained-upload")])
  | "artifact-put" | "work-put" =>
    if op == "artifact-put" then permitted state actor "publish" "school"
    let path := FilePath.mk (← lift (str request "path"))
    let digest ← putFile root path state.budgets.maxArtifactBytes
    faultBoundary "after-artifact"
    return (state,object [("digest",toJson digest),("state",toJson "staged-unreferenced"),
      ("bytes",toJson (← path.metadata).byteSize)])
  | "artifact-register" =>
    permitted state actor "publish" "school"
    let digest ← lift (str request "artifact")
    requireArtifact root digest
    let kind ← lift (str request "kind")
    need (#["dataset","checkpoint","source-metadata","execution-receipt","worker-audit","worker-image","training-evidence"].contains kind)
      "unsupported artifact publication kind"
    let metadata ← lift (field request "metadata")
    need (metadata.compress.utf8ByteSize <= 4096) "artifact metadata limit"
    if let some old := state.latest "artifact" digest then
      need (old.data == stableRequest request) "immutable artifact metadata conflict"
      return (state,recordResult old)
    append state "artifact" digest actor now (stableRequest request) #[digest]
  | "publish" =>
    permitted state actor "publish" "school"
    let unit : Authoring.Unit ← match field request "definition" with
      | .ok value => lift (Authoring.decode value)
      | .error _ => do
        let path := FilePath.mk (← lift (str request "path"))
        lift (Authoring.decode (← readJson path 1048576))
    let bytes ← lift (Authoring.compile unit)
    let course := unit.course.identity.toNat
    let revision := unit.course.edition.toNat
    let id := key course revision
    let digest := Digest.sha256Bytes bytes
    let policy ← lift (nat request "policy")
    need (policy > 0 && policy <= 0x7ffffffffffffffe) "policy version must be in the admitted signed range"
    if let some old := state.latest "publication" id then
      need (optionalStr old.data "artifact" == digest && optionalNat old.data "policy" == policy &&
        (← lift (field old.data "definition")) == toJson unit) "immutable publication conflict"
      return (state,object [("reused",toJson true),("publication",toJson old)])
    let stored ← putBytes root bytes state.budgets.maxArtifactBytes
    faultBoundary "after-artifact"
    append state "publication" id actor now (object [("course",toJson course),("revision",toJson revision),
      ("policy",toJson policy),("definition",toJson unit),("artifact",toJson stored)]) #[stored]
  | "source-config" =>
    permitted state actor "publish" "school"
    let digest ← lift (str request "digest")
    let path := FilePath.mk (← lift (str request "path"))
    need (Digest.valid digest && (← path.metadata).type == .file) "source resolver requires a regular file and SHA-256"
    need ((← Digest.sha256File path) == digest) "source resolver bytes differ from declared edition digest"
    append state "source-config" digest actor now (object [("digest",toJson digest),("path",toJson path.toString)])
  | "source-resolve" =>
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    enrolled state actor course revision
    let pub ← publication state course revision
    let unit ← definition pub
    let sourceId ← lift (str request "source")
    let source ← lift <| (unit.sources.sources.find? (fun source => source.id == sourceId)).toExcept "source absent from original publication"
    let configured := state.latest "source-config" source.fileDigest
    let path := configured.map (fun row => optionalStr row.data "path") |>.getD source.ownerLocation
    let resolved ← SourceRegistry.resolve {source with ownerLocation:=path}
    return (state,object [("source",toJson source.id),("path",toJson resolved.toString),
      ("edition",toJson source.edition),("digest",toJson source.fileDigest),
      ("rights",toJson source.rights),("scope",toJson "explicit owner-local source resolution; source bytes not redistributed")])
  | "enroll" =>
    if flag request "admittedLearner" then permitted state actor "enroll" "school"
    let learner ← lift (str request "learner")
    need (validId learner) "invalid learner"
    if learner != actor then permitted state actor "enroll" "school"
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    let _ ← publication state course revision
    let id := enrollmentKey learner course revision
    if let some old := state.latest "enrollment" id then return (state,recordResult old)
    append state "enrollment" id actor now request
  | "review-artifact" | "review-render" =>
    let fields ← lift request.getObj?
    let (_,work) ← lift (Review.execute state actor (Json.obj (fields.insert "op" (toJson "review-work"))) now)
    let digest ← lift (str work "workArtifact")
    requireArtifact root digest state.budgets.maxArtifactBytes
    let bytes ← readBounded (artifactPath root digest) state.budgets.maxArtifactBytes
    if op == "review-render" then
      let rendered ← ReviewRender.render bytes
      let fields ← lift rendered.getObj?
      return (state,Json.obj (fields.insert "digest" (toJson digest)))
    return (state,object [("digest",toJson digest),("bytes",toJson bytes.size),("hex",toJson (hex bytes))])
  | "enrollment-revoke" =>
    permitted state actor "enroll" "school"
    let learner ← lift (str request "learner")
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    let id := enrollmentKey learner course revision
    let prior ← lift <| (state.latest "enrollment" id).toExcept "enrollment absent"
    let fields ← lift prior.data.getObj?
    append state "enrollment" id actor now (Json.obj (fields.insert "revoked" (toJson true)))
  | "client-course" =>
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    enrolled state actor course revision
    let pub ← publication state course revision
    let digest ← lift (str pub.data "artifact")
    let bytes ← readBounded (artifactPath root digest) 32768
    return (state,object [("package_hex",toJson (hex bytes)),("identity",toJson course),("edition",toJson revision),
      ("policy",toJson (optionalNat pub.data "policy")),("artifact",toJson digest)])
  | "join" =>
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    enrolled state actor course revision
    let pub ← publication state course revision
    let session ← lift (str request "session")
    let expires := optionalNat request "expires" (now + optionalNat request "lifetimeMs" 3600000)
    need (validId session && expires > now && expires-now <= 86400000) "session lifetime/identity rejected"
    let guestSession ← lift (nat request "guestSession")
    need (guestSession > 0) "guest ASK session required"
    if let some old := state.latest "session" session then
      need (optionalStr old.data "actor" == actor) "session belongs to another learner"
    let ask : Client.GuestAsk ← lift (field request "ask" >>= fromJson?)
    need (ask.session == guestSession) "joined guest session differs from supplied ASK"
    let reviewId := optionalStr request "reviewId"
    if !reviewId.isEmpty then
      let unit ← definition pub
      let activity ← lift <| (unit.activities.find? (fun activity => activity.node+1 == ask.task_id)).toExcept "joined review activity absent"
      lift (Review.admitResponse state actor (object [("reviewId",toJson reviewId),
        ("course",toJson course),("revision",toJson revision),("activity",toJson activity.id),
        ("id",toJson s!"pending-join-{state.records.size+1}")]) now)
    let authority := Digest.sha256String (toJson #[state.school,state.deployment]).compress
    if let some old := state.latest "session" session then
      let prior : Client.SessionBinding ← lift (fromJson? old.data)
      if prior.authority == authority && prior.generation == state.generation && prior.course == course &&
          prior.revision == revision && prior.guestSession == guestSession && !prior.cancelled && prior.expires > now then
        if let some invitation := state.latest "invitation" (toString prior.bindingRecord) then
          if (← lift (field invitation.data "ask")) == toJson ask && optionalStr invitation.data "reviewId" == reviewId then
            let digest ← lift (str invitation.data "artifact")
            let bytes ← readBounded (artifactPath root digest) 32768
            return (state,object [("binding",toJson prior),("package_hex",toJson (hex bytes)),
              ("identity",toJson (60000:Nat)),("edition",toJson ask.sequence),("reused",toJson true)])
    let binding : Client.SessionBinding := {
      school := state.school
      actor := actor
      enrollment := enrollmentKey actor course revision
      session := session
      guestSession := guestSession
      authority := authority
      bindingRecord := state.records.size+1
      course := course
      revision := revision
      policy := optionalNat pub.data "policy"
      generation := state.generation
      expires := expires }
    let bytes ← lift (Client.invitation binding ask)
    let digest ← putBytes root bytes 32768
    let next ← lift (state.add "session" session actor now (toJson binding) #[digest])
    let next ← lift (next.add "invitation" (toString binding.bindingRecord) actor now
      (object [("ask",toJson ask),("artifact",toJson digest),("bindingRecord",toJson binding.bindingRecord),("reviewId",toJson reviewId)]) #[digest])
    return (next,object [("binding",toJson binding),("package_hex",toJson (hex bytes)),
      ("identity",toJson (60000:Nat)),("edition",toJson ask.sequence)])
  | "assist" =>
    let session ← lift (str request "session")
    let row ← lift <| (state.latest "session" session).toExcept "school session absent"
    let binding : Client.SessionBinding ← lift (fromJson? row.data)
    need (binding.actor == actor) "school session actor differs"
    enrolled state actor binding.course binding.revision
    let pub ← publication state binding.course binding.revision
    let unit ← definition pub
    let ask : Client.GuestAsk ← lift (field request "ask" >>= fromJson?)
    let activity ← lift <| (unit.activities.find? (fun a => a.node+1 == ask.task_id)).toExcept "activity absent from published policy"
    let input : Client.AssistInput := {
      school := state.school
      actor := actor
      session := session
      course := optionalNat request "course" binding.course
      revision := optionalNat request "revision" binding.revision
      policy := optionalNat request "policy" binding.policy
      generation := state.generation
      now := now
      ask := ask
      independent := activity.assessment.independent }
    need (activity.assistance != .none) "published activity prohibits assistance"
    lift (Client.admit binding input)
    let joined ← lift <| (state.latest "invitation" (toString binding.bindingRecord)).toExcept "school invitation context absent"
    need ((← lift (field joined.data "ask")) == toJson ask) "guest ASK differs from the exact joined document/consent/sequence context"
    let id := s!"{session}.{ask.sequence}"
    if let some prior := state.latest "decision" id then
      need (flag request "admittedLearner") "replayed assistance sequence"
      let original : Client.AssistInput ← lift (field prior.data "input" >>= fromJson?)
      need (prior.actor == actor && toJson {original with now := now} == toJson input)
        "assistance retry differs from immutable original context"
      let digest := optionalStr prior.data "artifact"
      requireArtifact root digest 32768
      let bytes ← readBounded (artifactPath root digest) 32768
      need (Digest.sha256Bytes bytes == digest) "assistance artifact changed during retry"
      return (state,object [("decision",toJson id),("package_hex",toJson (hex bytes)),
        ("identity",toJson (60001:Nat)),("edition",toJson ask.sequence),("artifact",toJson digest),
        ("selector",(field prior.data "selector").toOption.getD Json.null),("reused",toJson true)])
    let prior := (state.allLatest "decision").filter (fun r => optionalStr r.data "session" == session)
    need (prior.all (fun r => optionalNat r.data "sequence" < ask.sequence)) "out-of-order assistance sequence"
    let hint := unit.course.nodes[activity.node]?.map (·.hint) |>.getD ""
    let selected := Recommendation.deliverySelection state actor activity.id
      binding.course binding.revision binding.policy now hint
    let bytes ← lift (Client.handleAssist binding input selected.text)
    let digest ← putBytes root bytes 32768
    let data := object [("session",toJson session),("sequence",toJson ask.sequence),
      ("input",toJson input),("artifact",toJson digest),("selector",selected.provenance),
      ("stage",toJson "decision-authored; delivery-unobserved")]
    let next ← lift (state.add "decision" id actor now data (#[digest] ++ selected.artifacts))
    return (next,object [("decision",toJson id),("package_hex",toJson (hex bytes)),
      ("identity",toJson (60001:Nat)),("edition",toJson ask.sequence),("artifact",toJson digest),
      ("selector",selected.provenance)])
  | "cancel-session" =>
    let id ← lift (str request "session")
    let row ← lift <| (state.latest "session" id).toExcept "session absent"
    let binding : Client.SessionBinding ← lift (fromJson? row.data)
    need (binding.actor == actor || actor == state.operator) "session cancellation denied"
    append state "session" id actor now (toJson {binding with cancelled:=true})
  | "delivery-observe" =>
    lift (Delivery.execute state actor request now)
  | "delivery" =>
    let id ← lift (str request "decision")
    let row ← lift <| (state.latest "decision" id).toExcept "decision absent"
    need (row.actor == actor || actor == state.operator) "delivery receipt denied"
    let stage ← lift (str request "stage")
    need (#["transport-admitted","guest-accepted","guest-rejected","panel-observed","cancelled","expired"].contains stage) "unsupported delivery stage"
    append state "delivery" s!"{id}.{state.records.size+1}" actor now request
  | "attempt" =>
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    enrolled state actor course revision
    let pub ← publication state course revision
    let unit ← definition pub
    let activityId ← lift (str request "activity")
    let activity ← lift <| (unit.activities.find? (fun a => a.id == activityId)).toExcept "activity absent"
    let id ← lift (str request "id")
    need (validId id) "invalid attempt id"
    if let some old := state.latest "attempt" id then
      need (old.actor == actor && stableRequest (← lift (field old.data "request")) == stableRequest request) "attempt idempotency conflict"
      return (state,recordResult old)
    lift (Review.admitResponse state actor request now)
    let values : Array Nat ← lift (field request "values" >>= fromJson?)
    need (values.size == 5 && values.all (· <= 99)) "typed-answer profile requires five integers in 0..99; ink remains a separate observation"
    let goal := match activity.goal with | .fractionAddition => 1 | .binomialSquare => 2 | .unsupported => 3
    let outcome := Documents.Mathematics.result goal (values[0]!.toUInt64) (values[1]!.toUInt64)
      (values[2]!.toUInt64) (values[3]!.toUInt64) (values[4]!.toUInt64) 8
    let assisted := state.records.any (fun r => r.kind == "decision" && r.actor == actor &&
      match field r.data "input" with
      | .ok input => optionalNat input "course" == course && optionalNat input "revision" == revision &&
        match field input "ask" with | .ok ask => optionalNat ask "task_id" == activity.node+1 | .error _ => false
      | .error _ => false)
    need (!(activity.assessment.independent && assisted)) "independent assessment contaminated by prior assistance; use a separate declared item"
    let mut refs := pub.artifacts
    if let .ok receipt := field request "guestReceipt" then
      need (optionalNat receipt "source" == course && optionalNat receipt "edition" == revision &&
        optionalNat receipt "task_id" == activity.node+1 && optionalNat receipt "outcome" == outcome.toNat)
        "guest receipt differs from explicit typed submission/publication/checker comparison"
    if let .ok artifact := str request "observationArtifact" then
      if flag request "admittedLearner" then
        need ((state.latest "work-upload" s!"{actor}.{artifact}").isSome) "work artifact is not owned by admitted learner"
      requireArtifact root artifact
      refs := refs.push artifact
    let data := object [("request",request),("course",toJson course),("revision",toJson revision),
      ("activity",toJson activityId),("policy",toJson (optionalNat pub.data "policy")),
      ("definition",toJson (optionalStr pub.data "artifact")),("assisted",toJson assisted),
      ("independent",toJson activity.assessment.independent),("outcome",toJson outcome.toNat),
      ("checker",toJson activity.assessment.checker),
      ("checkingScope",toJson (if goal == 3 then "unsupported; teacher review required" else "hosted exact checker; typed values only")),
      ("estimate",toJson "uncertain; no educational-effect claim"),
      ("origin",toJson (if (field request "guestReceipt").isOk then "owner-local guest observation; hosted comparison separate" else "deliberately supplied local work"))]
    let next ← lift (state.add "attempt" id actor now data refs)
    let next ← lift (Review.linkResponse next actor request now outcome.toNat)
    append next "review" id actor now (object [("learner",toJson actor),("course",toJson course),
      ("revision",toJson revision),("activity",toJson unit.review.activityId),("sourceAttempt",toJson id),
      ("reviewPolicy",toJson unit.review.version),("policy",toJson (optionalNat pub.data "policy")),
      ("due",toJson (now+unit.review.delaySeconds*1000)),("assisted",toJson assisted),
      ("recommendation",toJson (if assisted || outcome != 1 then "practice" else "later independent review")),
      ("status",toJson "due"),("disabled",toJson false)]) refs
  | "progress" =>
    let learner := optionalStr request "learner" actor
    if learner != actor then permitted state actor "read" learner
    return (state,object [("attempts",toJson (state.records.filter (fun r => r.kind == "attempt" && r.actor == learner))),
      ("due",due state learner now),("uncertainty",toJson "observations do not establish retention or mastery")])
  | "goal-set" | "interpretation-challenge" | "suggestion-override" =>
    let (next,row) ← lift (LearnerChoice.apply state actor now request)
    return (next,recordResult row)
  | "learner-choices" =>
    let choices ← lift (LearnerChoice.query state actor request)
    return (state,object [("choices",toJson choices),
      ("scope",toJson "append-only learner declarations; original evidence and course rules retained")])
  | "review-open" =>
    let id ← lift (str request "id")
    let row ← lift <| (state.latest "review" id).toExcept "scheduled review absent"
    need (optionalStr row.data "learner" == actor) "review belongs to another learner"
    need (Review.active row && optionalNat row.data "due" <= now) "review is not due or is disabled"
    let course := optionalNat row.data "course"
    let revision := optionalNat row.data "revision"
    let pub ← publication state course revision
    let unit ← definition pub
    let reviewId := optionalStr row.data "activity"
    let activity ← lift <| (unit.activities.find? (fun a => a.id == reviewId)).toExcept "original review activity absent"
    enrolled state actor course revision
    let digest ← lift (str pub.data "artifact")
    return (state,object [("identity",toJson course),("edition",toJson revision),("node",toJson activity.node),
      ("policy",toJson (optionalNat row.data "policy")),("reviewPolicy",toJson unit.review.version),
      ("package_hex",toJson (hex (← readBounded (artifactPath root digest) 32768))),
      ("assistance",toJson "independent reconstruction; actual client opening must be observed separately")])
  | "review-override" =>
    let id ← lift (str request "id")
    let row ← lift <| (state.latest "review" id).toExcept "review absent"
    need (optionalStr row.data "learner" == actor) "review belongs to another learner"
    let dueAt ← lift (nat request "due")
    let fields ← lift row.data.getObj?
    let data := Json.obj (fields.insert "due" (toJson dueAt) |>.insert "disabled" (toJson (flag request "disabled")))
    append state "review" id actor now data row.artifacts
  | "recommendation-input" =>
    let learner := optionalStr request "learner" actor
    if learner != actor then permitted state actor "read" learner
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    enrolled state learner course revision
    let pub ← publication state course revision
    let unit ← definition pub
    let activityId ← lift (str request "activity")
    let activity ← lift <| (unit.activities.find? (fun a => a.id == activityId)).toExcept "recommendation activity absent"
    need (!activity.assessment.independent && activity.assistance != .none) "recommendation prohibited during independent assessment"
    let id ← lift (str request "id")
    need (validId id) "invalid recommendation input identity"
    if let some prior := state.latest "recommendation-input" id then
      need ((← lift (field prior.data "request")) == stableRequest request) "recommendation input idempotency conflict"
      return (state,recordResult prior)
    let fields ← lift (Recommendation.prepare state learner course revision now).getObj?
    append state "recommendation-input" id actor now (Json.obj (fields.insert "request" (stableRequest request)
      |>.insert "learner" (toJson learner) |>.insert "course" (toJson course) |>.insert "revision" (toJson revision)
      |>.insert "activity" (toJson activityId) |>.insert "policy" (toJson (optionalNat pub.data "policy")))) pub.artifacts
  | "job-submit" =>
    permitted state actor "execute" "school"
    let id ← lift (str request "job")
    need (validId id) "invalid job identity"
    if let some old := state.latest "job" id then
      need (stableRequest (← lift (field old.data "request")) == stableRequest request) "job idempotency conflict"
      return (state,recordResult old)
    let className ← lift (str request "class")
    need (#["interactive","bulk","training"].contains className) "unsupported job class"
    let jobs := (state.allLatest "job").filter (fun r => #["queued","leased"].contains (optionalStr r.data "status"))
    let capacity := if className == "interactive" then state.budgets.maxQueued else state.budgets.maxQueued-state.budgets.interactiveReserve
    need (jobs.size < capacity) "queue backpressure: interactive reserve protected"
    let refs : Array String ← lift (field request "artifacts" >>= fromJson?)
    for digest in refs do requireArtifact root digest
    let input ← lift (field request "input")
    need (input.compress.utf8ByteSize <= 4096) "job input too large; stage a bounded artifact"
    if !(optionalStr input "preparation").isEmpty then
      let prepared ← lift <| (state.latest "recommendation-input" (optionalStr input "preparation")).toExcept "recommendation input absent"
      for name in #["learner","course","revision","activity","features","presenceMask"] do
        need ((← lift (field input name)) == (← lift (field prepared.data name))) "job differs from immutable recommendation input"
      need (optionalNat input "presenceMask" == 3) "missing independent evidence: retain authored baseline"
    append state "job" id actor now (object [("status",toJson "queued"),("class",toJson className),
      ("input",input),("generation",toJson state.generation),("fence",toJson (0:Nat)),
      ("retries",toJson (0:Nat)),("request",request)]) refs
  | "job-lease" =>
    permitted state actor "execute" "school"
    let id ← lift (str request "job")
    let row ← lift <| (state.latest "job" id).toExcept "job absent"
    let status := optionalStr row.data "status"
    need (status == "queued" || (status == "leased" && !state.liveLease row.data now)) "job is neither queued nor expired"
    let retries := optionalNat row.data "retries" + (if status == "leased" then 1 else 0)
    need (retries <= state.budgets.maxRetries) "job retry budget exhausted"
    let leased := (state.allLatest "job").filter (fun r => optionalStr r.data "status" == "leased" &&
      state.liveLease r.data now)
    need (leased.size < state.budgets.maxLeased) "worker capacity exhausted"
    let duration ← lift (nat request "duration")
    need (duration > 0 && duration <= state.budgets.maxLeaseMs &&
      now+duration <= 0x7ffffffffffffffe && state.bootTime now+duration <= 0x7ffffffffffffffe)
      "lease duration exceeds resource profile"
    let worker ← lift (str request "worker")
    need (validId worker) "invalid worker identity"
    let mut artifactBytes := 0
    if LocalProvider.numerical row then
      need (row.artifacts.size <= 64) "local worker job artifact closure exceeds profile"
      let mut seen : Array String := #[]
      for digest in row.artifacts do
        if !seen.contains digest then
          requireArtifact root digest state.budgets.maxArtifactBytes
          artifactBytes := artifactBytes + (← (artifactPath root digest).metadata).byteSize.toNat
          seen := seen.push digest
    let provider ← lift (LocalProvider.admitLease state actor now worker row artifactBytes)
    append state "job" id actor now (object [("status",toJson "leased"),("class",toJson (optionalStr row.data "class")),
      ("input",← lift (field row.data "input")),("request",← lift (field row.data "request")),
      ("generation",toJson state.generation),("fence",toJson (optionalNat row.data "fence"+1)),
      ("expires",toJson (now+duration)),("leaseClockEpoch",toJson state.clockEpoch),
      ("leaseBootExpires",toJson (state.bootTime now+duration)),
      ("worker",toJson worker),("ownerActor",toJson actor),
      ("provider",provider),("retries",toJson retries)]) row.artifacts
  | "job-complete" =>
    permitted state actor "execute" "school"
    let id ← lift (str request "job")
    let row ← lift <| (state.latest "job" id).toExcept "job absent"
    let generation ← lift (nat request "generation")
    let fence ← lift (nat request "fence")
    let digest ← lift (str request "result")
    need ((← lift (str request "worker")) == optionalStr row.data "worker" && actor == optionalStr row.data "ownerActor") "worker or lease owner differs"
    need (generation == state.generation && generation == optionalNat row.data "generation" &&
      fence == optionalNat row.data "fence") "stale generation or lease fence"
    if optionalStr row.data "status" == "completed" then
      need (optionalStr row.data "result" == digest) "committed result differs"
      return (state,recordResult row)
    need (optionalStr row.data "status" == "leased" && state.liveLease row.data now) "job ownership cancelled or expired"
    lift (LocalProvider.completionAllowed state row)
    requireArtifact root digest
    let declared ← lift (field row.data "input")
    if optionalStr declared "kind" == "school-linear-worker/1" then
      let observed ← readJson (artifactPath root digest) 16384
      need (optionalStr observed "job" == id && optionalNat observed "generation" == generation &&
        optionalNat observed "fence" == fence && optionalNat observed "requestId" == optionalNat declared "requestId" &&
        optionalNat observed "model" == optionalNat declared "model" &&
        optionalStr observed "imageSha256" == optionalStr declared "imageSha256" &&
        optionalStr observed "profile" == "core0-v0.5" && optionalStr observed "numericProfile" == "school-linear-q10-v1" &&
        optionalStr observed "origin" == "rv64-observed" && optionalNat observed "status" 255 == 0)
        "worker response differs from declared job, model, image or lease"
      for name in #["requestSha256","workerAuditSha256","executionReceiptSha256"] do
        need (Digest.valid (optionalStr observed name)) s!"worker response lacks bound {name}"
      let score ← lift (field observed "scoreQ20" >>= Json.getInt?)
      need (score.natAbs <= 25165824) "worker score exceeds admitted accumulation range"
      let header := ByteArray.mk #[76,77,83,56,1,0,32,0]
      let framed := header ++ wordsToBytes #[optionalNat observed "requestId",generation,fence,
        optionalNat observed "model",wireInt score]
      need (optionalStr observed "responseHex" == hex framed) "worker response framing differs from recorded scalar result"
      let release ← lift <| (state.latest "model" (toString (optionalNat observed "model"))).toExcept "worker model release absent"
      let modelDigest ← lift (str release.data "artifact")
      need (optionalStr declared "parameters" == modelDigest) "job parameter artifact differs from registered release"
      let parameters ← readJson (artifactPath root modelDigest) 16384
      let weights : Array Int ← lift (field parameters "quantized" >>= fromJson?)
      let features : Array Int ← lift (field declared "features" >>= fromJson?)
      let words : Array Nat ← lift (field observed "inputWords" >>= fromJson?)
      need (weights.size == 3 && features.size == 2 && features.all (fun f => f.natAbs <= 1024) && words.size == 9) "worker shape differs from declared numerical profile"
      let expected := #[generation,fence,optionalNat observed "model",wireInt weights[0]!,wireInt weights[1]!,
        wireInt weights[2]!,wireInt features[0]!,wireInt features[1]!,3]
      need (words == expected) "actual target input words differ from declared parameters or features"
      need (row.artifacts.contains modelDigest && row.artifacts.contains (optionalStr observed "imageSha256"))
        "job closure lacks immutable parameter or worker image bytes"
    let evidence : Array String ← match field request "evidenceArtifacts" with
      | .ok value => lift (fromJson? value)
      | .error _ => pure #[]
    need (evidence.size <= 32) "result evidence closure limit"
    for artifact in evidence do requireArtifact root artifact
    if optionalStr declared "kind" == "school-linear-worker/1" then
      let observed ← readJson (artifactPath root digest) 16384
      for name in #["requestSha256","workerAuditSha256","executionReceiptSha256"] do
        need (evidence.contains (optionalStr observed name)) s!"required worker evidence bytes absent: {name}"
    let data := object [("status",toJson "completed"),("class",toJson (optionalStr row.data "class")),
      ("input",← lift (field row.data "input")),("request",← lift (field row.data "request")),
      ("generation",toJson generation),("fence",toJson fence),("result",toJson digest),
      ("worker",toJson (optionalStr row.data "worker")),("ownerActor",toJson actor),
      ("provider",(field row.data "provider").toOption.getD Json.null),
      ("origin",toJson (optionalStr request "origin" "unverified-worker-response"))]
    append state "job" id actor now data (row.artifacts.push digest ++ evidence)
  | "model-register" => registerModel root state actor now request
  | "training-publish" =>
    permitted state actor "publish" "school"
    let output := FilePath.mk (← lift (str request "directory"))
    let dataset := FilePath.mk (← lift (str request "dataset"))
    let checkpoint := FilePath.mk (← lift (str request "checkpoint"))
    let rights ← lift (str request "rights")
    need (!rights.isEmpty && rights.utf8ByteSize <= 2048) "training publication requires explicit bounded rights/provenance"
    let parameters ← readJson (output / "parameters.json") 16384
    let manifest ← readJson (dataset / "manifest.json") 65536
    let datasetDigest ← Digest.sha256File (dataset / "manifest.json")
    let saved ← readJson checkpoint 65536
    need (optionalStr parameters "dataset" == datasetDigest && optionalStr saved "dataset" == datasetDigest &&
      (← lift (field parameters "parameterBits")) == (← lift (field saved "parameterBits")))
      "training checkpoint/parameter/dataset identity differs"
    for (name,digestName) in #[("train.jsonl","trainDigest"),("evaluation.jsonl","evaluationDigest")] do
      need ((← Digest.sha256File (dataset / name)) == optionalStr manifest digestName) "training split bytes differ from manifest"
    let mut paths := #[dataset / "manifest.json",dataset / "train.jsonl",dataset / "evaluation.jsonl",
      checkpoint,output / "evaluation.json"]
    let configuration := optionalStr parameters "trainingConfiguration" "default/0.1.0"
    if configuration != "default/0.1.0" then
      let path := FilePath.mk (← lift (str request "configuration"))
      need ((← Digest.sha256File path) == configuration) "training configuration identity differs"
      paths := paths.push path
    let mut closure := #[]
    for path in paths do closure := closure.push (← putFile root path state.budgets.maxArtifactBytes)
    let digest ← putFile root (output / "parameters.json") state.budgets.maxArtifactBytes
    registerModel root state actor now (object [("artifact",toJson digest),("artifacts",toJson closure),
      ("rights",toJson rights),("reusable",toJson (flag request "reusable"))])
  | "models" =>
    permitted state actor "read" "school"
    return (state,object [("models",toJson (state.allLatest "model")),
      ("selection",toJson (state.latest "model-selection" "active"))])
  | "model-select" | "model-rollback" =>
    permitted state actor "publish" "school"
    let version ← lift (nat request "version")
    let model ← lift <| (state.latest "model" (toString version)).toExcept "model release absent"
    append state "model-selection" "active" actor now request model.artifacts
  | "suggest" =>
    let learner := optionalStr request "learner" actor
    if learner != actor then permitted state actor "read" learner
    let course ← lift (nat request "course")
    let revision ← lift (nat request "revision")
    enrolled state learner course revision
    let pub ← publication state course revision
    let unit ← definition pub
    let activityId ← lift (str request "activity")
    let activity ← lift <| (unit.activities.find? (fun a => a.id == activityId)).toExcept "suggestion activity absent"
    need (!activity.assessment.independent && activity.assistance != .none) "learned intervention prohibited during independent assessment"
    let job ← lift (str request "job")
    let row ← lift <| (state.latest "job" job).toExcept "suggestion job absent"
    need (optionalStr row.data "status" == "completed") "suggestion requires a committed result"
    let input ← lift (field row.data "input")
    need (optionalStr input "kind" == "school-linear-worker/1") "job is not an admitted numerical worker result"
    need (optionalStr input "learner" == learner && optionalNat input "course" == course &&
      optionalNat input "revision" == revision && optionalStr input "activity" == activityId)
      "numerical job belongs to a different learner, course or activity"
    let digest ← lift (str row.data "result")
    let observed ← readJson (artifactPath root digest) 16384
    let score ← lift (field observed "scoreQ20" >>= Json.getInt?)
    let modelVersion ← lift (nat observed "model")
    let model ← lift <| (state.latest "model" (toString modelVersion)).toExcept "worker model is not a published release"
    let selection ← lift <| (state.latest "model-selection" "active").toExcept "model selection is not explicit"
    need (optionalNat selection.data "version" == modelVersion) "worker model differs from selected release"
    let choice := if score >= 524288 then "review the authored explanation, then retry permitted practice" else "try independent reconstruction at the scheduled review"
    append state "suggestion" s!"{learner}.{job}" actor now (object [("learner",toJson learner),
      ("course",toJson course),("revision",toJson revision),("policy",toJson (optionalNat pub.data "policy")),
      ("activity",toJson activityId),("job",toJson job),("model",toJson modelVersion),
      ("preparation",toJson (optionalStr input "preparation")),
      ("scoreQ20",toJson score),("suggestion",toJson choice),("overrideAllowed",toJson true),
      ("uncertainty",toJson "synthetic estimate; baseline review remains available; not mastery or educational efficacy")])
      (#[digest] ++ model.artifacts ++ pub.artifacts)
  | "job-cancel" =>
    permitted state actor "execute" "school"
    let id ← lift (str request "job")
    let row ← lift <| (state.latest "job" id).toExcept "job absent"
    need (optionalStr row.data "status" != "completed") "committed job cannot be cancelled"
    let fields ← lift row.data.getObj?
    append state "job" id actor now (Json.obj (fields.insert "status" (toJson "cancelled"))) row.artifacts
  | "job-retry" =>
    permitted state actor "execute" "school"
    let id ← lift (str request "job")
    let row ← lift <| (state.latest "job" id).toExcept "job absent"
    need (optionalStr row.data "status" == "leased" &&
      (!state.liveLease row.data now || LocalProvider.unavailable state row))
      "retry requires expired or superseded leased ownership"
    let retries := optionalNat row.data "retries"+1
    need (retries <= state.budgets.maxRetries) "retry budget exhausted"
    let fields ← lift row.data.getObj?
    append state "job" id actor now (Json.obj (fields.insert "status" (toJson "queued") |>.insert "retries" (toJson retries))) row.artifacts
  | "jobs" =>
    permitted state actor "execute" "school"
    return (state,toJson (state.allLatest "job"))
  | "reconcile" =>
    permitted state actor "execute" "school"
    let mut next := state
    for row in state.allLatest "job" do
      if optionalStr row.data "status" == "leased" && (!state.liveLease row.data now || LocalProvider.unavailable state row) then
        let fields ← lift row.data.getObj?
        let retries := optionalNat row.data "retries"+1
        let data := Json.obj (fields.insert "status" (toJson (if retries > state.budgets.maxRetries then "cancelled" else "queued")) |>.insert "retries" (toJson retries))
        next ← lift (next.add "job" row.key actor now data row.artifacts)
    return (next,object [("provider",toJson "local"),("generation",toJson next.generation),
      ("jobs",toJson (next.allLatest "job")),("localProvider",LocalProvider.describe next)])
  | "export" =>
    permitted state actor "export" "school"
    let path := FilePath.mk (← lift (str request "to"))
    let through ← if let .ok value := field request "throughSequence" then lift value.getNat?
      else pure state.records.size
    need (through <= state.records.size) "export throughSequence exceeds committed history"
    -- Prefixes retain exact immutable rows and sequence identities. Every
    -- admitted dependency precedes its consumer, so this preserves closure
    -- without fabricating a renumbered or cross-learner filtered authority.
    let selected := {state with records := state.records.extract 0 through}
    for row in selected.allLatest "observation" do
      let observation : Observation.Observation ← lift (fromJson? row.data)
      -- Present consent authorizes disclosure, even for historical prefixes.
      lift (Observation.admit (← consentFor state observation) .exportData observation)
    copyExport root path selected state.records.size
    return (state,object [("path",toJson path.toString),("artifacts",toJson selected.references.size),
      ("records",toJson selected.records.size),("throughSequence",toJson through),
      ("sourceRecords",toJson state.records.size),
      ("mode",toJson "offline-authority history selection; private records included by current administrator grant")])
  | "definition-export" =>
    permitted state actor "publish" "school"
    let package ← lift (Definition.fromState state)
    let path := FilePath.mk (← lift (str request "to"))
    writeDefinition root path package
    return (state,object [("path",toJson path.toString),("schema",toJson package.schema),
      ("digest",toJson (← Digest.sha256File (path / "school-package.json"))),
      ("publications",toJson package.publications.size),("reusableModels",toJson package.models.size),
      ("learnerRecords",toJson (0:Nat)),("deploymentIdentity",toJson "excluded")])
  | "clone" =>
    permitted state actor "publish" "school"
    let path := FilePath.mk (← lift (str request "to"))
    need (!(← (path / "state.json").pathExists)) "clone destination initialized"
    freshDestination path
    let school ← lift (str request "newSchool")
    let deployment ← lift (str request "newDeployment")
    need (validId school && school != state.school && validId deployment && deployment != state.deployment) "clone needs new school and deployment identities"
    let package ← lift (Definition.fromState state)
    writeDefinition root (path / "definition") package
    let rows := state.records.filter (fun r => r.kind == "publication" || (r.kind == "model" && flag r.data "reusable"))
    let mut next ← bindClock {school,deployment,operator:=actor,budgets:=state.budgets,clockModel:=state.clockModel}
    for row in rows do
      for digest in row.artifacts do
        let copied ← putBytes path (← readBounded (artifactPath root digest) state.budgets.maxArtifactBytes) state.budgets.maxArtifactBytes
        need (copied == digest) "clone artifact differs"
      next ← lift (next.add row.kind row.key actor 0 row.data row.artifacts)
    if let some selection := state.latest "model-selection" "active" then
      if (next.latest "model" (toString (optionalNat selection.data "version"))).isSome then
        next ← lift (next.add "model-selection" "active" actor 0 selection.data selection.artifacts)
    commit path next
    return (state,object [("school",toJson school),("path",toJson path.toString),
      ("records",toJson next.records.size),("learnerRecords",toJson (0:Nat)),("credentials",toJson "excluded"),("externalSources",toJson "owner source manifests retained; source bytes require explicit separate transfer")])
  | "gc" =>
    permitted state actor "admin" "school"
    return (state,object [("reclaimed",toJson (← gc root state))])
  | "stop" =>
    permitted state actor "admin" "school"
    return (state,object [("stopping",toJson true)])
  | _ => fail s!"unsupported school operation: {op}"

/-- Install the reusable package through exactly the maintained publication and
model admission paths. All artifact bytes precede the one authoritative commit.
The package cannot transfer live grants, deployment identity or learner records. -/
def installDefinition (destination : FilePath) (request : Json) : IO Json := do
  need (!(← (destination / "state.json").pathExists)) "definition destination already initialized"
  freshDestination destination
  let source := FilePath.mk (← lift (str request "from"))
  let package ← lift <| Definition.decode (← readJson (source / "school-package.json"))
  let school ← lift (str request "school")
  let actor ← lift (str request "actor")
  let deployment ← lift (str request "deployment")
  need (validId school && validId actor && validId deployment) "definition installation needs fresh school/actor/deployment identities"
  let clockModel := optionalStr request "clockModel" "monotonic-ms"
  let initial ← bindClock {school,operator:=actor,deployment,budgets:=package.budgets,clockModel}
  lift (Store.validateState initial)
  for digest in Definition.references package do
    requireArtifact source digest package.budgets.maxArtifactBytes
    let copied ← putBytes destination (← readBounded (artifactPath source digest) package.budgets.maxArtifactBytes) package.budgets.maxArtifactBytes
    need (copied == digest) "installed definition artifact differs"
  let mut next := initial
  for publication in package.publications do
    let (afterPublish,_) ← execute destination next (object [("op",toJson "publish"),("school",toJson school),
      ("actor",toJson actor),("policy",toJson publication.policy),("definition",toJson publication.definition)])
    next := afterPublish
  for model in package.models do
    let (afterModel,_) ← execute destination next (object [("op",toJson "model-register"),("school",toJson school),
      ("actor",toJson actor),("artifact",toJson model.artifact),("artifacts",toJson model.artifacts),
      ("rights",toJson model.rights),("reusable",toJson true)])
    need ((afterModel.latest "model" (toString model.version)).isSome) "model artifact version differs from reusable definition"
    next := afterModel
  if let some version := package.selectedModel then
    let (afterSelection,_) ← execute destination next (object [("op",toJson "model-select"),("school",toJson school),
      ("actor",toJson actor),("version",toJson version)])
    next := afterSelection
  faultBoundary "after-artifact"
  commit destination next
  return object [("school",toJson school),("deployment",toJson deployment),
    ("generation",toJson next.generation),("records",toJson next.records.size),
    ("packageDigest",toJson (← Digest.sha256File (source / "school-package.json"))),
    ("learnerRecords",toJson (0:Nat)),("grants",toJson "explicitly reconfigure in the new school")]

end Lemma.School.Authority
