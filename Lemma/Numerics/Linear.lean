import Lemma.Numerics.Tensor
import Lemma.Numerics.Quantized

namespace Lemma.Numerics.Linear
open Lean

def profile : String := "hosted-linear-f64-v1"
def quantizedProfile : String := "school-linear-q10-v1"

structure Sample where
  id : String
  group : String
  split : String
  time : Nat
  x : Array Float
  present : Array Bool
  target : Float
  independent : Bool
  deriving FromJson, ToJson, Repr

structure Parameters where
  values : Array Float := #[0.0, 0.0, 0.0]
  deriving FromJson, ToJson, Repr

def validateSample (sample : Sample) : Except String Unit := do
  unless sample.x.size == 2 && sample.present.size == 2 do
    throw "linear model needs exactly two features and two presence flags"
  unless sample.present.all id do throw "missing feature: use explainable fallback review policy"
  unless sample.independent do throw "assisted practice cannot supply independent outcome labels"
  unless sample.x.all (fun x => x.isFinite && -1.0 ≤ x && x ≤ 1.0) do
    throw "features must be finite and within [-1,1]"
  unless sample.target.isFinite && 0.0 ≤ sample.target && sample.target ≤ 1.0 do
    throw "target must be a finite independent error-risk label within [0,1]"

def validateParameters (params : Parameters) : Except String Unit := do
  unless params.values.size == 3 do throw "linear model needs two weights and one bias"
  unless params.values.all (fun p => p.isFinite && -8.0 ≤ p && p ≤ 8.0) do
    throw "parameters must be finite and within [-8,8]"

def predict (params : Parameters) (sample : Sample) : Except String Float := do
  validateSample sample
  validateParameters params
  let weights ← Tensor.checked ⟨1, 2⟩ (params.values.extract 0 2)
  let features ← Tensor.checked ⟨1, 2⟩ sample.x
  let result := (← weights.dot features) + params.values[2]!
  unless result.isFinite do throw "linear prediction produced nonfinite result"
  return result

structure Differential where
  prediction : Float
  loss : Float
  parameterGradient : Array Float
  inputGradient : Array Float
  deriving ToJson, Repr

/-- Specialized reverse pass for dot + bias + half squared error. Its primitive
rules are d(a+b)=(1,1), d(a*b)=(b,a), d(1/2 e²)=e. It does not differentiate
through quantization, input admission, or an arbitrary Lean program. -/
def differentiate (params : Parameters) (sample : Sample) : Except String Differential := do
  let prediction ← predict params sample
  let residual := prediction - sample.target
  return {
    prediction := prediction
    loss := 0.5 * residual * residual
    parameterGradient := #[residual * sample.x[0]!, residual * sample.x[1]!, residual]
    inputGradient := #[residual * params.values[0]!, residual * params.values[1]!] }

structure Checkpoint where
  schema : String := "lemma-linear-checkpoint/v1"
  numericProfile : String := profile
  codeVersion : String := "school-linear-training/0.1.0"
  implementation : String := "independent-manual-check"
  dataset : String
  nextRecord : Nat := 0
  step : Nat := 0
  epoch : Nat := 0
  rng : UInt64 := 1
  parameters : Parameters := {}
  velocity : Array Float := #[0.0, 0.0, 0.0]
  learningRate : Float := 0.1
  momentum : Float := 0.5
  batchSize : Nat := 4
  deriving Repr

/-- JSON's display Float conversion is not an exact checkpoint codec. Persist
binary64 bit patterns so a resumed update receives exactly the saved state. -/
structure CheckpointEncoding where
  schema : String
  numericProfile : String
  codeVersion : String
  implementation : String
  dataset : String
  nextRecord : Nat
  step : Nat
  epoch : Nat
  rng : UInt64
  parameterBits : Array UInt64
  velocityBits : Array UInt64
  learningRateBits : UInt64
  momentumBits : UInt64
  batchSize : Nat
  deriving FromJson, ToJson

instance : ToJson Checkpoint where
  toJson state := toJson ({
    schema := state.schema, numericProfile := state.numericProfile,
    codeVersion := state.codeVersion, implementation := state.implementation,
    dataset := state.dataset, nextRecord := state.nextRecord, step := state.step,
    epoch := state.epoch, rng := state.rng,
    parameterBits := state.parameters.values.map Float.toBits,
    velocityBits := state.velocity.map Float.toBits,
    learningRateBits := state.learningRate.toBits, momentumBits := state.momentum.toBits,
    batchSize := state.batchSize } : CheckpointEncoding)

instance : FromJson Checkpoint where
  fromJson? json := do
    let state : CheckpointEncoding ← fromJson? json
    return {
      schema := state.schema, numericProfile := state.numericProfile,
      codeVersion := state.codeVersion, implementation := state.implementation,
      dataset := state.dataset, nextRecord := state.nextRecord, step := state.step,
      epoch := state.epoch, rng := state.rng,
      parameters := ⟨state.parameterBits.map Float.ofBits⟩,
      velocity := state.velocityBits.map Float.ofBits,
      learningRate := Float.ofBits state.learningRateBits,
      momentum := Float.ofBits state.momentumBits, batchSize := state.batchSize }

def validateCheckpoint (state : Checkpoint) (dataset : String) : Except String Unit := do
  unless state.schema == "lemma-linear-checkpoint/v1" && state.numericProfile == profile &&
      state.codeVersion == "school-linear-training/0.1.0" do throw "checkpoint version is incompatible"
  unless state.dataset == dataset do throw "checkpoint dataset digest mismatch"
  validateParameters state.parameters
  unless state.velocity.size == 3 && state.velocity.all Float.isFinite do throw "invalid optimizer state"
  unless state.learningRate == 0.1 && state.momentum == 0.5 && state.batchSize == 4 do
    throw "checkpoint optimizer configuration differs from pinned training semantics"

def update (state : Checkpoint) (batch : Array Sample) : Except String Checkpoint := do
  validateCheckpoint state state.dataset
  unless batch.size > 0 && batch.size ≤ state.batchSize do throw "batch must contain 1..4 samples"
  let mut gradient := #[0.0, 0.0, 0.0]
  for sample in batch do
    unless sample.split == "train" do throw "evaluation sample cannot enter fitting"
    let delta ← differentiate state.parameters sample
    gradient := gradient.zipWith (· + ·) delta.parameterGradient
  gradient := gradient.map (· / batch.size.toUInt64.toFloat)
  let velocity := state.velocity.zipWith (fun old g => state.momentum * old + g) gradient
  let values := state.parameters.values.zipWith (fun p v => p - state.learningRate * v) velocity
  let params : Parameters := ⟨values⟩
  validateParameters params
  return { state with parameters := params, velocity, step := state.step + 1 }

def encodeSigned (value : Int) : UInt64 :=
  if value < 0 then 0 - UInt64.ofNat value.natAbs else UInt64.ofNat value.natAbs

def decodeSigned (word : UInt64) : Int :=
  if word < 9223372036854775808 then Int.ofNat word.toNat
  else -Int.ofNat (0 - word).toNat

def quantize (value : Float) (bound : Nat) : Except String Int := do
  unless value.isFinite do throw "cannot quantize nonfinite value"
  let scaled := value * 1024.0
  let magnitude := (Float.floor (scaled.abs + 0.5)).toUInt64.toNat
  if magnitude > bound then throw "quantized value exceeds admitted signed magnitude"
  return if value < 0.0 then -Int.ofNat magnitude else Int.ofNat magnitude

def quantizedParameters (params : Parameters) : Except String (Array Int) := do
  validateParameters params
  params.values.mapM (quantize · 8192)

def quantizedPrediction (params : Parameters) (sample : Sample) : Except String Float := do
  validateSample sample
  let q ← quantizedParameters params
  let x ← sample.x.mapM (quantize · 1024)
  let score := Quantized.score (encodeSigned q[0]!) (encodeSigned q[1]!)
    (encodeSigned q[2]!) (encodeSigned x[0]!) (encodeSigned x[1]!)
  let signed := decodeSigned score
  return (if signed < 0 then -(signed.natAbs.toUInt64.toFloat)
    else signed.natAbs.toUInt64.toFloat) / 1048576.0

end Lemma.Numerics.Linear
