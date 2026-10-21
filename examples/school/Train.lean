import Lemma.Numerics.Linear
import Lemma.School.Store

open Lean Lemma.Numerics Lemma.Numerics.Linear

/-! Executable hosted reference: bounded JSONL ingestion, sequential minibatches,
momentum SGD and recoverable checkpoints. sha256sum is used only as a host byte
identity operation; all data construction and numerical semantics are Lean. -/
namespace Lemma.School.Training

structure Manifest where
  schema : String := "lemma-synthetic-risk-dataset/v1"
  source : String := "redistributable formula fixture; synthetic pipeline evidence only"
  grant : String := "CC0-1.0 synthetic numeric rows"
  labelOrigin : String := "synthetic independent-outcome risk = 0.1 + 0.6*errorRate + 0.3*gap"
  transformation : String := "examples/school/Train.lean:fixture/0.1.0"
  transformationDigest : String
  featureOrder : Array String := #["recent-independent-error-rate", "normalized-review-gap"]
  preprocessing : String := "fixed unit scaling, no fitted preprocessing; missing features reject to baseline"
  splitPolicy : String := "fixed disjoint session groups before fitting; no assisted labels"
  order : String := "manifest id order, batches of four, sequential epochs without shuffling"
  trainDigest : String
  evaluationDigest : String
  trainIds : Array String
  evaluationIds : Array String
  trainGroups : Array String
  evaluationGroups : Array String
  deriving FromJson, ToJson

def byteDigest (path : System.FilePath) : IO String := do
  let result ← IO.Process.output { cmd := "sha256sum", args := #[path.toString] }
  unless result.exitCode == 0 do throw <| IO.userError "host byte digest operation failed"
  let digest := result.stdout.take 64 |>.toString
  unless digest.length == 64 do throw <| IO.userError "host returned malformed digest"
  return digest

def readJson [FromJson α] (path : System.FilePath) : IO α := do
  let handle ← IO.FS.Handle.mk path .read
  let mut bytes := ByteArray.empty
  let mut ended := false
  while bytes.size ≤ 65536 && !ended do
    let chunk ← handle.read ((min 512 (65537 - bytes.size)).toUSize)
    if chunk.isEmpty then ended := true
    else bytes := bytes ++ chunk
  unless bytes.size ≤ 65536 do throw <| IO.userError "JSON manifest/checkpoint exceeds 64 KiB"
  let some text := String.fromUTF8? bytes | throw <| IO.userError "JSON manifest/checkpoint is not UTF-8"
  let json ← IO.ofExcept (Json.parse text)
  IO.ofExcept (fromJson? json)

def writeAtomic [ToJson α] (path : System.FilePath) (value : α) : IO Unit := do
  let temporary := path.toString ++ ".pending"
  IO.FS.writeFile temporary ((toJson value).compress ++ "\n")
  Lemma.School.Store.barrier "file" temporary
  IO.FS.rename temporary path
  Lemma.School.Store.syncDirectoryAndParent (path.parent.getD ".")

structure Stream where
  handle : IO.FS.Handle
  chunk : ByteArray := .empty
  position : Nat := 0
  line : ByteArray := .empty

def decodeLine (bytes : ByteArray) : IO String :=
  match String.fromUTF8? bytes with
  | some value => pure value
  | none => throw <| IO.userError "dataset row is not UTF-8"

partial def nextLine (stream : Stream) : IO (Option String × Stream) := do
  if stream.position ≥ stream.chunk.size then
    let chunk ← stream.handle.read 512
    if chunk.isEmpty then
      if stream.line.isEmpty then return (none, stream)
      return (some (← decodeLine stream.line), { stream with line := .empty })
    nextLine { stream with chunk, position := 0 }
  else
    let byte := stream.chunk[stream.position]!
    let next := { stream with position := stream.position + 1 }
    if byte == 10 then
      return (some (← decodeLine stream.line), { next with line := .empty })
    if stream.line.size ≥ 2048 then throw <| IO.userError "dataset row exceeds 2048-byte decoding limit"
    nextLine { next with line := stream.line.push byte }

def parseSample (line : String) : IO Sample := do
  let json ← IO.ofExcept (Json.parse line)
  let value : Sample ← IO.ofExcept (fromJson? json)
  IO.ofExcept (validateSample value)
  return value

def validateManifest (manifest : Manifest) : Except String Unit := do
  unless #["lemma-synthetic-risk-dataset/v1","lemma-permitted-risk-dataset/v1"].contains manifest.schema do
    throw "unsupported dataset schema"
  unless !manifest.source.isEmpty && manifest.source.utf8ByteSize <= 2048 &&
      !manifest.grant.isEmpty && manifest.grant.utf8ByteSize <= 2048 &&
      !manifest.labelOrigin.isEmpty && manifest.labelOrigin.utf8ByteSize <= 2048 &&
      manifest.featureOrder == #["recent-independent-error-rate","normalized-review-gap"] &&
      Lemma.School.Digest.valid manifest.transformationDigest do
    throw "dataset needs bounded source/grant/label provenance, transformation SHA256 and the supported feature order"
  unless manifest.trainIds.size > 0 && manifest.trainIds.size ≤ 4096 &&
      manifest.evaluationIds.size > 0 && manifest.evaluationIds.size ≤ 4096 do
    throw "dataset split must have 1..4096 rows"
  unless manifest.trainIds.size % 4 == 0 do throw "training split must align to four-row batches"
  if manifest.trainGroups.any (fun group => manifest.evaluationGroups.contains group) then
    throw "group leakage across fitting/evaluation split"
  if manifest.trainIds.any (fun id => manifest.evaluationIds.contains id) then
    throw "record leakage across fitting/evaluation split"
  unless manifest.trainIds.toList.eraseDups.length == manifest.trainIds.size &&
      manifest.evaluationIds.toList.eraseDups.length == manifest.evaluationIds.size do
    throw "dataset record identities must be distinct within each split"

def validateRow (sample : Sample) (ids groups : Array String) (split : String) (index : Nat) : IO Unit := do
  unless ids[index]? == some sample.id && groups.contains sample.group && sample.split == split do
    throw <| IO.userError s!"dataset ordering/group/split mismatch at record {index}"

def validateSplit (path : System.FilePath) (ids groups : Array String) (split : String) : IO Unit := do
  let handle ← IO.FS.Handle.mk path .read
  let mut stream : Stream := ⟨handle, .empty, 0, .empty⟩
  for index in [:ids.size] do
    let (some line, next) ← nextLine stream | throw <| IO.userError "dataset split truncated"
    stream := next
    validateRow (← parseSample line) ids groups split index
  let (last, _) ← nextLine stream
  unless last.isNone do throw <| IO.userError "dataset split has undeclared trailing records"

def batchAt (path : System.FilePath) (manifest : Manifest) (cursor : Nat) : IO (Array Sample) := do
  unless cursor < manifest.trainIds.size && cursor % 4 == 0 do
    throw <| IO.userError "checkpoint cursor is outside an admitted batch boundary"
  let handle ← IO.FS.Handle.mk path .read
  let mut stream : Stream := ⟨handle, .empty, 0, .empty⟩
  let mut batch := #[]
  for index in [:cursor + 4] do
    let (some line, next) ← nextLine stream | throw <| IO.userError "training file truncated"
    stream := next
    let sample ← parseSample line
    validateRow sample manifest.trainIds manifest.trainGroups "train" index
    if index ≥ cursor then batch := batch.push sample
  return batch

def fixture (directory : System.FilePath) (count : Nat := 16) : IO Unit := do
  IO.FS.createDirAll directory
  let mut train := #[]
  let mut evaluation := #[]
  for i in [:count] do
    let x := (i % 4).toUInt64.toFloat / 4.0
    let y := ((i / 4) % 4).toUInt64.toFloat / 4.0
    train := train.push ({
      id := s!"train-{i}", group := s!"synthetic-train-session-{i}",
      split := "train", time := i, x := #[x,y], present := #[true,true],
      target := 0.1 + 0.6*x + 0.3*y, independent := true } : Sample)
  for i in [:8] do
    let x := (i % 4).toUInt64.toFloat / 4.0 + 0.125
    let y := (i / 4).toUInt64.toFloat / 2.0 + 0.125
    evaluation := evaluation.push ({
      id := s!"heldout-{i}", group := s!"synthetic-heldout-session-{i}",
      split := "evaluation", time := 100 + i, x := #[x,y], present := #[true,true],
      target := 0.1 + 0.6*x + 0.3*y, independent := true } : Sample)
  let trainPath := directory / "train.jsonl"
  let evalPath := directory / "evaluation.jsonl"
  IO.FS.writeFile trainPath (String.join (train.toList.map (fun s => (toJson s).compress ++ "\n")))
  IO.FS.writeFile evalPath (String.join (evaluation.toList.map (fun s => (toJson s).compress ++ "\n")))
  let manifest : Manifest := {
    transformationDigest := ← byteDigest "examples/school/Train.lean",
    trainDigest := ← byteDigest trainPath,
    evaluationDigest := ← byteDigest evalPath,
    trainIds := train.map (·.id), evaluationIds := evaluation.map (·.id),
    trainGroups := train.map (·.group), evaluationGroups := evaluation.map (·.group) }
  writeAtomic (directory / "manifest.json") manifest
  IO.println s!"SYNTHETIC_DATASET {← byteDigest (directory / "manifest.json")}"

structure Evaluation where
  samples : Nat
  modelMse : Float
  baselineMse : Float
  quantizedMse : Float
  maximumQuantizationDeviation : Float
  baseline : String := "fixed 0.5 risk; explainable due/error review remains operational fallback"
  scope : String := "synthetic held-out session groups; no educational improvement claim"
  deriving ToJson

def evaluate (path : System.FilePath) (manifest : Manifest) (params : Parameters) : IO Evaluation := do
  let handle ← IO.FS.Handle.mk path .read
  let mut stream : Stream := ⟨handle, .empty, 0, .empty⟩
  let mut loss := 0.0
  let mut baseline := 0.0
  let mut quantizedLoss := 0.0
  let mut deviation := 0.0
  for i in [:manifest.evaluationIds.size] do
    let (some line, next) ← nextLine stream | throw <| IO.userError "evaluation split truncated"
    stream := next
    let sample ← parseSample line
    validateRow sample manifest.evaluationIds manifest.evaluationGroups "evaluation" i
    let prediction ← IO.ofExcept (predict params sample)
    let quantized ← IO.ofExcept (quantizedPrediction params sample)
    let e := prediction - sample.target
    let b := 0.5 - sample.target
    let q := quantized - sample.target
    loss := loss + e*e
    baseline := baseline + b*b
    quantizedLoss := quantizedLoss + q*q
    deviation := max deviation (prediction - quantized).abs
  let (last, _) ← nextLine stream
  unless last.isNone do throw <| IO.userError "evaluation split has undeclared trailing records"
  let n := manifest.evaluationIds.size.toUInt64.toFloat
  return {
    samples := manifest.evaluationIds.size, modelMse := loss/n,
    baselineMse := baseline/n, quantizedMse := quantizedLoss/n,
    maximumQuantizationDeviation := deviation }

structure Configuration where
  schema : String := "lemma-school-linear-training-config/1"
  modelVersion : Nat
  learningRate : Float := 0.1
  momentum : Float := 0.5
  deriving FromJson, ToJson

def validateConfiguration (configuration : Configuration) : Except String Unit := do
  unless configuration.schema == "lemma-school-linear-training-config/1" &&
      configuration.modelVersion > 0 && configuration.modelVersion <= 0x7ffffffffffffffe do
    throw "training configuration requires supported schema and positive model version"
  unless configuration.learningRate.isFinite && 0.0 < configuration.learningRate && configuration.learningRate <= 0.25 &&
      configuration.momentum.isFinite && 0.0 <= configuration.momentum && configuration.momentum <= 0.95 do
    throw "training configuration requires learningRate (0,0.25] and momentum [0,0.95]"

def train (directory checkpointPath output : System.FilePath) (steps delay : Nat)
    (configurationPath : Option System.FilePath := none) : IO Unit := do
  let configuration : Option Configuration ← match configurationPath with
    | none => pure none
    | some path => do
      let configuration : Configuration ← readJson path
      IO.ofExcept (validateConfiguration configuration)
      pure (some configuration)
  let manifest : Manifest ← readJson (directory / "manifest.json")
  IO.ofExcept (validateManifest manifest)
  unless (← byteDigest (directory / "train.jsonl")) == manifest.trainDigest &&
      (← byteDigest (directory / "evaluation.jsonl")) == manifest.evaluationDigest do
    throw <| IO.userError "dataset bytes do not match their fixed pre-fitting manifest"
  validateSplit (directory / "train.jsonl") manifest.trainIds manifest.trainGroups "train"
  validateSplit (directory / "evaluation.jsonl") manifest.evaluationIds manifest.evaluationGroups "evaluation"
  let identity ← byteDigest (directory / "manifest.json")
  let configurationIdentity ← match configurationPath with
    | none => pure "default/0.1.0"
    | some path => byteDigest path
  let implementation := (← byteDigest "examples/school/Train.lean") ++
    (← byteDigest "Lemma/Numerics/Linear.lean") ++ (← byteDigest "Lemma/Numerics/Tensor.lean")
    ++ configurationIdentity
  let mut state : Checkpoint ← if ← checkpointPath.pathExists then readJson checkpointPath
    else match configuration with
      | none => pure { dataset := identity, implementation }
      | some config => pure {
          dataset := identity
          implementation := implementation
          codeVersion := "school-linear-training/0.2.0"
          learningRate := config.learningRate
          momentum := config.momentum }
  IO.ofExcept (validateCheckpoint state identity)
  unless state.implementation == implementation &&
      state.nextRecord == (state.step * 4) % manifest.trainIds.size &&
      state.epoch == (state.step * 4) / manifest.trainIds.size do
    throw <| IO.userError "checkpoint implementation or exact update/cursor/epoch identity mismatch"
  unless steps ≤ 100000 && state.step ≤ steps do throw <| IO.userError "total update bound must be currentStep..100000"
  while state.step < steps do
    let batch ← batchAt (directory / "train.jsonl") manifest state.nextRecord
    state ← IO.ofExcept (update state batch)
    let next := state.nextRecord + batch.size
    state := { state with
      nextRecord := if next == manifest.trainIds.size then 0 else next,
      epoch := if next == manifest.trainIds.size then state.epoch + 1 else state.epoch }
    writeAtomic checkpointPath state
    if delay > 0 then IO.sleep delay.toUInt32
  let evaluation ← evaluate (directory / "evaluation.jsonl") manifest state.parameters
  let q ← IO.ofExcept (quantizedParameters state.parameters)
  IO.FS.createDirAll output
  writeAtomic (output / "parameters.json") (Json.mkObj [
    ("schema", toJson "lemma-linear-parameters/v1"), ("profile", toJson quantizedProfile),
    ("trainingProfile", toJson profile), ("version", toJson (configuration.map (·.modelVersion) |>.getD state.step)),
    ("trainingConfiguration",toJson configurationIdentity),("datasetSchema",toJson manifest.schema),
    ("dataset", toJson identity), ("parameters", toJson state.parameters),
    ("parameterBits", toJson (state.parameters.values.map Float.toBits)),
    ("quantized", toJson q), ("scale", toJson (1024 : Nat)),
    ("dimensions", toJson (2 : Nat)), ("missingness", toJson "mask must be 3; otherwise fallback")])
  writeAtomic (output / "evaluation.json") evaluation
  IO.println ((toJson evaluation).compress)

def close (left right : Float) : Bool := (left - right).abs < 0.000000001

def rejected (result : Except String α) : Bool :=
  match result with | .error _ => true | .ok _ => false

def checks : IO Unit := do
  let sample : Sample := {
    id := "independent-hand-example", group := "manual", split := "train",
    time := 0, x := #[0.5,0.25], present := #[true,true], target := 0.75, independent := true }
  let params : Parameters := ⟨#[2.0,-1.0,0.5]⟩
  let tensor ← IO.ofExcept (Tensor.checked ⟨1,2⟩ #[2.0,3.0])
  let other ← IO.ofExcept (Tensor.checked ⟨1,2⟩ #[4.0,5.0])
  unless (← IO.ofExcept (tensor.add other)).values == #[6.0,8.0] &&
      (← IO.ofExcept (tensor.hadamard other)).values == #[8.0,15.0] &&
      close (← IO.ofExcept (tensor.dot other)) 23.0 && rejected (unsupported "fft") do
    throw <| IO.userError "independent bounded tensor operator checks failed"
  let differential ← IO.ofExcept (differentiate params sample)
  -- Independently derived: 2/2 - 1/4 + 1/2 = 5/4; residual 1/2;
  -- loss 1/8, gradient (1/4,1/8,1/2), input gradient (1,-1/2).
  unless close differential.prediction 1.25 && close differential.loss 0.125 &&
      (differential.parameterGradient.zipWith close #[0.25,0.125,0.5]).all id do
    throw <| IO.userError "independent forward/gradient expected values failed"
  unless differential.inputGradient.zipWith close #[1.0,-0.5] |>.all id do
    throw <| IO.userError "independent input gradient expected values failed"
  let state : Checkpoint := { dataset := "manual", parameters := params }
  let updated ← IO.ofExcept (update state #[sample])
  unless updated.parameters.values.zipWith close #[1.975,-1.0125,0.45] |>.all id do
    throw <| IO.userError "independent momentum-SGD first update failed"
  for i in [:3] do
    let eps := 0.000001
    let plus := ⟨params.values.set! i (params.values[i]! + eps)⟩
    let minus := ⟨params.values.set! i (params.values[i]! - eps)⟩
    let hi ← IO.ofExcept (differentiate plus sample)
    let lo ← IO.ofExcept (differentiate minus sample)
    unless ((hi.loss - lo.loss)/(2.0*eps) - differential.parameterGradient[i]!).abs < 0.00000001 do
      throw <| IO.userError "supplementary finite difference gradient failed"
  unless rejected (Tensor.checked ⟨2,2⟩ #[1.0]) &&
      rejected (Tensor.checked ⟨4097,1⟩ #[]) &&
      rejected (Tensor.checked ⟨1,1⟩ #[0.0/0.0]) &&
      rejected (validateSample { sample with present := #[true,false] }) &&
      rejected (quantize 8.001 8192) do throw <| IO.userError "invalid shape/bounds/nonfinite/missingness checks failed"
  unless (← IO.ofExcept (quantize (-0.00048828125) 8192)) == -1 &&
      Quantized.validSigned (encodeSigned (-8192)) 8192 &&
      !Quantized.validSigned (encodeSigned (-8193)) 8192 &&
      decodeSigned (Quantized.score (encodeSigned (-8192)) 8192 (encodeSigned (-8192)) 1024
        (encodeSigned (-1024))) == -25165824 do throw <| IO.userError "fixed-point signed edges failed"
  IO.println "NUMERICS_CHECKS_PASS independent forward/gradient/update; finite difference; shape/bounds/nonfinite/missingness; signed quantization edges"

end Lemma.School.Training

def main (args : List String) : IO UInt32 := do
  try
    match args with
    | ["fixture", directory] => Lemma.School.Training.fixture directory
    | ["fixture-large", directory] => Lemma.School.Training.fixture directory 512
    | ["check"] => Lemma.School.Training.checks
    | ["train", directory, checkpoint, output, steps, delay] =>
      let some steps := steps.toNat? | throw <| IO.userError "steps must be a natural number"
      let some delay := delay.toNat? | throw <| IO.userError "delay must be a natural number"
      Lemma.School.Training.train directory checkpoint output steps delay
    | ["train-config", directory, checkpoint, output, steps, configuration] =>
      let some steps := steps.toNat? | throw <| IO.userError "steps must be a natural number"
      Lemma.School.Training.train directory checkpoint output steps 0 (some configuration)
    | ["evaluate", directory, checkpoint, output] =>
      let state : Checkpoint ← Lemma.School.Training.readJson checkpoint
      Lemma.School.Training.train directory checkpoint output state.step 0
    | ["evaluate-config", directory, checkpoint, output, configuration] =>
      let state : Checkpoint ← Lemma.School.Training.readJson checkpoint
      Lemma.School.Training.train directory checkpoint output state.step 0 (some configuration)
    | _ => throw <| IO.userError "usage: Train.lean fixture DIRECTORY | check | train DATASET CHECKPOINT OUTPUT TOTAL_STEPS DELAY_MS"
    return 0
  catch error =>
    IO.eprintln s!"NUMERICS_FAIL {error}"
    return 1
