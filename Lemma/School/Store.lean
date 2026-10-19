import Lemma.School.Model
import Lemma.School.Digest

/-! Hosted local-filesystem binding: close + atomic rename before acknowledgement.
An OS flock in the byte/process launcher serializes the one local authority.
This establishes no fsync/power-loss or replicated-availability claim. -/
namespace Lemma.School.Store
open Lean System

def fail {α : Type} (message : String) : IO α := throw (IO.userError message)
def lift {α : Type} (result : Except String α) : IO α :=
  match result with | .ok value => pure value | .error e => fail e

def validBudgets (budgets : Budgets) : Bool :=
  budgets.maxEvents > 0 && budgets.maxEvents ≤ 100000 &&
  budgets.maxArtifactBytes > 0 && budgets.maxArtifactBytes ≤ 16777216 &&
  budgets.maxQueued > 0 && budgets.maxQueued ≤ 256 &&
  budgets.interactiveReserve < budgets.maxQueued &&
  budgets.maxLeased > 0 && budgets.maxLeased ≤ 16 &&
  budgets.maxLeaseMs > 0 && budgets.maxLeaseMs ≤ 3600000 && budgets.maxRetries ≤ 32

/-- The checksum binds bytes, while this validator rejects semantically invalid
histories even when their envelope checksum was recomputed. Neither is an
identity signature. Commit and recovery enforce the same admitted state. -/
def validateState (state : State) : Except String Unit := do
  if state.schema != "lemma-school-state/1" || !validId state.school ||
      !validId state.operator || !validId state.deployment then
    throw "unsupported or malformed school state"
  if state.clockModel != "monotonic-ms" && state.clockModel != "controlled-ms" then throw "unsupported authority clock model"
  if !validBudgets state.budgets then throw "unsupported resource budgets in stored state"
  if state.records.size > state.budgets.maxEvents || state.generation == 0 ||
      state.generation > 0x7ffffffffffffffe || state.clock > 0x7ffffffffffffffe then
    throw "state resource/generation/clock failure"
  let mut previousTime := 0
  for i in [:state.records.size] do
    let row := state.records[i]!
    if row.sequence != i+1 then throw "noncontiguous transaction history"
    if !validId row.actor || !validId row.kind || row.key.isEmpty || row.key.utf8ByteSize > 256 then
      throw s!"invalid record identity at sequence {row.sequence}"
    if row.time < previousTime || row.time > state.clock then
      throw s!"nonmonotonic or future record time at sequence {row.sequence}"
    previousTime := row.time
    if row.artifacts.any (fun digest => !Digest.valid digest) then
      throw s!"invalid artifact reference at sequence {row.sequence}"
  -- Read admission may advance the persisted monotonic clock beyond the last event.

def readBounded (path : FilePath) (limit : Nat) : IO ByteArray := do
  let metadata ← path.metadata
  if metadata.type != .file || metadata.byteSize > limit.toUInt64 then
    fail s!"file is not regular or exceeds {limit} bytes: {path}"
  let handle ← IO.FS.Handle.mk path .read
  let bytes ← handle.read (limit + 1).toUSize
  if bytes.size > limit then fail "input grew beyond admitted bound"
  return bytes

def readJson (path : FilePath) (limit : Nat := 16777216) : IO Json := do
  let bytes ← readBounded path limit
  let value ← lift <| (String.fromUTF8? bytes).toExcept "invalid UTF-8 JSON"
  lift (Json.parse value)

def artifactPath (root : FilePath) (digest : String) : FilePath := root / "artifacts" / digest

def requireArtifact (root : FilePath) (digest : String) (limit : Nat := 16777216) : IO Unit := do
  if !Digest.valid digest then fail "invalid artifact digest"
  let path := artifactPath root digest
  if !(← path.pathExists) then fail s!"missing committed artifact {digest}"
  let metadata ← path.metadata
  if metadata.type != .file || metadata.byteSize > limit.toUInt64 then
    fail s!"committed artifact exceeds admitted regular-file bound {limit}: {digest}"
  if (← Digest.sha256File path) != digest then fail s!"corrupt committed artifact {digest}"

def putBytes (root : FilePath) (bytes : ByteArray) (limit : Nat) : IO String := do
  if bytes.size > limit then fail "artifact resource limit"
  let digest := Digest.sha256Bytes bytes
  IO.FS.createDirAll (root / "artifacts")
  IO.FS.createDirAll (root / "staging")
  let dest := artifactPath root digest
  if ← dest.pathExists then
    requireArtifact root digest limit
  else
    let stage := root / "staging" / (digest ++ ".part")
    IO.FS.writeBinFile stage bytes
    if (← Digest.sha256File stage) != digest then fail "staged artifact verification failed"
    IO.FS.rename stage dest
  return digest

def putFile (root : FilePath) (path : FilePath) (limit : Nat) : IO String := do
  putBytes root (← readBounded path limit) limit

/-- A diagnostic pause occurs only after the actual boundary. The test harness
can SIGKILL the real authority here; no expected-success state is injected. -/
def faultBoundary (phase : String) : IO Unit := do
  if (← IO.getEnv "LEMMA_SCHOOL_TEST_CUT") == some phase then
    let err ← IO.getStderr
    err.putStrLn s!"SCHOOL_BOUNDARY {phase}"
    err.flush
    IO.sleep 60000

def commit (root : FilePath) (state : State) : IO Unit := do
  lift (validateState state)
  for digest in state.references do requireArtifact root digest state.budgets.maxArtifactBytes
  let payload := toJson state
  let envelope := object [("schema",toJson "lemma-school-snapshot/1"),
    ("digest",toJson (Digest.sha256String payload.compress)), ("payload",payload)]
  let text := envelope.compress ++ "\n"
  if text.utf8ByteSize > 16777216 then fail "snapshot resource limit"
  IO.FS.createDirAll root
  IO.FS.writeFile (root / "transaction.part") text
  faultBoundary "before-commit"
  IO.FS.rename (root / "transaction.part") (root / "state.json")
  faultBoundary "after-commit"

def load (root : FilePath) : IO State := do
  let envelope ← readJson (root / "state.json")
  if (← lift (str envelope "schema")) != "lemma-school-snapshot/1" then fail "unsupported snapshot schema"
  let payload ← lift (field envelope "payload")
  if (← lift (str envelope "digest")) != Digest.sha256String payload.compress then fail "snapshot integrity failure"
  let state : State ← lift (fromJson? payload)
  lift (validateState state)
  for digest in state.references do requireArtifact root digest state.budgets.maxArtifactBytes
  return state

def initSchool (root : FilePath) (request : Json) : IO State := do
  if ← (root / "state.json").pathExists then fail "school already initialized"
  let school ← lift (str request "school")
  let operator ← lift (str request "actor")
  let deployment ← lift (str request "deployment")
  if !validId school || !validId operator || !validId deployment then fail "invalid school/actor/deployment identity"
  let budgets : Budgets ← match field request "budgets" with
    | .ok value => lift (fromJson? value)
    | .error _ => pure {}
  if !validBudgets budgets then fail "unsupported resource budgets"
  let provider := optionalStr request "provider" "local"
  if provider != "local" then fail s!"unsupported provider: {provider}"
  let clockModel := optionalStr request "clockModel" "monotonic-ms"
  let state : State := {school,operator,deployment,budgets,clockModel}
  commit root state
  return state

def gc (root : FilePath) (state : State) : IO Nat := do
  let mut reclaimed := 0
  for directory in #[root / "staging", root / "artifacts"] do
    if ← directory.pathExists then
      for entry in ← directory.readDir do
        if directory.fileName == some "staging" || !state.references.contains entry.fileName then
          if (← entry.path.metadata).type == .file then
            IO.FS.removeFile entry.path
            reclaimed := reclaimed + 1
  let staged := root / "transaction.part"
  if ← staged.pathExists then IO.FS.removeFile staged
  return reclaimed

end Lemma.School.Store
