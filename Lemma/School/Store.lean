import Lemma.School.Model
import Lemma.School.Digest

/-! Hosted local-filesystem binding: file and directory barriers around rename.
An OS flock in the byte/process launcher serializes the one local authority.
The host primitive only fsyncs the path chosen here. No physical power-loss or
replicated-availability claim follows from operating-system barrier success. -/
namespace Lemma.School.Store
open Lean System

def fail {α : Type} (message : String) : IO α := throw (IO.userError message)
def lift {α : Type} (result : Except String α) : IO α :=
  match result with | .ok value => pure value | .error e => fail e

/-- The selected Linux host binding identifies its monotonic clock domain.
The explicit TEST pair is only a synthetic host-clock stimulus, never wall time. -/
def hostClock : IO (String × Nat) := do
  let testEpoch ← IO.getEnv "LEMMA_SCHOOL_TEST_BOOT_ID"
  let testTime ← IO.getEnv "LEMMA_SCHOOL_TEST_MONO_MS"
  match testEpoch,testTime with
  | some epoch,some time =>
    if !validId epoch then fail "invalid test boot identity"
    return (epoch,← lift (time.toNat?.toExcept "invalid test monotonic time"))
  | none,none =>
    let epoch := (← IO.FS.readFile "/proc/sys/kernel/random/boot_id").trimAscii.toString
    if !validId epoch then fail "host boot identity unavailable"
    return (epoch,← IO.monoMsNow)
  | _,_ => fail "synthetic host clock requires both explicit TEST bindings"

/-- Bind/rebase before admission. Each new clock epoch or authority start fences
all previous workers. Unmeasurable offline elapsed time is never guessed. -/
def bindClock (state : State) (restart : Bool := false) : IO State := do
  -- Old binaries must reject the changed scheduling interpretation. Records
  -- and snapshot envelopes stay unchanged; opening explicitly migrates state.
  let state := {state with schema := "lemma-school-state/2"}
  if state.clockModel == "controlled-ms" then
    return {state with generation := state.generation + (if restart then 1 else 0)}
  let (epoch,time) ← hostClock
  if state.clockEpoch != epoch then
    let fence := restart || !state.clockEpoch.isEmpty || state.clock > 0 || !state.records.isEmpty
    return {state with
      clockEpoch := epoch
      clockEpochSequence := state.clockEpochSequence + 1
      clockAnchor := time
      clockBase := state.clock
      generation := state.generation + (if fence then 1 else 0)}
  if time < state.clockAnchor then fail "host monotonic rollback within boot epoch"
  let now := state.clockBase + time - state.clockAnchor
  if now < state.clock || now > 0x7ffffffffffffffe then fail "logical scheduling clock rollback/range"
  return {state with clock := now, generation := state.generation + (if restart then 1 else 0)}

def schedulingNow (state : State) : IO Nat := do
  let (epoch,time) ← hostClock
  if epoch != state.clockEpoch || time < state.clockAnchor then fail "host clock epoch changed during execution"
  return state.clockBase + time - state.clockAnchor

/-- Only a host fsync primitive. Lean owns every ordering and rename decision. -/
def barrier (kind : String) (path : FilePath) : IO Unit := do
  let helper := (← IO.getEnv "LEMMA_SCHOOL_FS_BARRIER").getD "scripts/school_fs_barrier.py"
  let python := (← IO.getEnv "LEMMA_SCHOOL_FS_PYTHON").getD "python3"
  let result ← IO.Process.output {cmd := python, args := #[helper,kind,path.toString]}
  if result.exitCode != 0 then fail s!"storage {kind} barrier failed: {result.stderr}"

def syncParent (path : FilePath) : IO Unit :=
  barrier "directory" (path.parent.getD ".")

/-- Batch independent OS calls at the same already-selected policy boundary;
the primitive still makes no ordering, rename or acknowledgement decision. -/
def barriers (paths : Array (String × FilePath)) : IO Unit := do
  -- Sixteen PATH_MAX-size names stay below the Linux per-argument bound.
  for index in [:(paths.size+15)/16] do
    let chunk := paths.extract (index*16) (min paths.size (index*16+16))
    let encoded := toJson (chunk.map (fun (kind,path) => (kind,path.toString)))
    barrier "batch" (FilePath.mk encoded.compress)

def syncDirectoryAndParent (path : FilePath) : IO Unit :=
  barriers #[("directory",path),("directory",path.parent.getD ".")]

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
  if !#["lemma-school-state/1","lemma-school-state/2"].contains state.schema || !validId state.school ||
      !validId state.operator || !validId state.deployment then
    throw "unsupported or malformed school state"
  if state.clockModel != "monotonic-ms" && state.clockModel != "controlled-ms" then throw "unsupported authority clock model"
  if (!state.clockEpoch.isEmpty && (!validId state.clockEpoch || state.clockEpochSequence == 0)) ||
      state.clockAnchor > 0x7ffffffffffffffe || state.clockBase > state.clock then
    throw "invalid clock epoch/anchor"
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
  syncDirectoryAndParent root
  let dest := artifactPath root digest
  if ← dest.pathExists then
    requireArtifact root digest limit
  else
    let stage := root / "staging" / (digest ++ ".part")
    IO.FS.writeBinFile stage bytes
    if (← Digest.sha256File stage) != digest then fail "staged artifact verification failed"
    barrier "file" stage
    IO.FS.rename stage dest
    barriers #[("directory",root / "artifacts"),("directory",root / "staging")]
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

def commit (root : FilePath) (state : State) (validatedArtifacts : Array String := #[]) : IO Unit := do
  lift (validateState state)
  let mut newBarriers := #[]
  for digest in state.references do
    -- Only the mutex-owning cached authority supplies this set. Artifacts are
    -- immutable there; startup/recovery/export always revalidate the closure.
    if !validatedArtifacts.contains digest then
      requireArtifact root digest state.budgets.maxArtifactBytes
      newBarriers := newBarriers.push ("file",artifactPath root digest)
  if !newBarriers.isEmpty then
    barriers (newBarriers.push ("directory",root / "artifacts"))
  let payload := toJson state
  let envelope := object [("schema",toJson "lemma-school-snapshot/1"),
    ("digest",toJson (Digest.sha256String payload.compress)), ("payload",payload)]
  let text := envelope.compress ++ "\n"
  if text.utf8ByteSize > 16777216 then fail "snapshot resource limit"
  IO.FS.createDirAll root
  IO.FS.writeFile (root / "transaction.part") text
  barrier "file" (root / "transaction.part")
  faultBoundary "before-commit"
  IO.FS.rename (root / "transaction.part") (root / "state.json")
  syncDirectoryAndParent root
  faultBoundary "after-commit"

/-- The derived structure decoder requires every field, even fields with Lean
constructor defaults. Supply only the four absent legacy clock fields after
checking the original payload checksum; malformed present fields still reject. -/
def decodeState (payload : Json) : Except String State := do
  if (← str payload "schema") != "lemma-school-state/1" then return ← fromJson? payload
  let mut fields ← payload.getObj?
  for (name,value) in #[("clockEpoch",toJson ""),("clockEpochSequence",toJson (0:Nat)),
      ("clockAnchor",toJson (0:Nat)),("clockBase",toJson (0:Nat))] do
    if !(field payload name).isOk then fields := fields.insert name value
  fromJson? (Json.obj fields)

def load (root : FilePath) : IO State := do
  let envelope ← readJson (root / "state.json")
  if (← lift (str envelope "schema")) != "lemma-school-snapshot/1" then fail "unsupported snapshot schema"
  let payload ← lift (field envelope "payload")
  if (← lift (str envelope "digest")) != Digest.sha256String payload.compress then fail "snapshot integrity failure"
  let state ← lift (decodeState payload)
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
  let state ← bindClock {school,operator,deployment,budgets,clockModel}
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
