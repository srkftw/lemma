import Lean

/-! Hosted numerical reference binding. FloatArray owns contiguous binary64 storage;
the upstream hosted Lean runtime is explicitly required. This is a small bounded
operator library, not a freestanding tensor runtime or a general AD compiler. -/
namespace Lemma.Numerics

inductive DType where | f64 deriving Repr, BEq
inductive Layout where | rowMajor deriving Repr, BEq

structure Shape where
  rows : Nat
  cols : Nat
  deriving Repr, BEq

structure Tensor where
  shape : Shape
  dtype : DType := .f64
  layout : Layout := .rowMajor
  storage : FloatArray

def maximumElements : Nat := 4096

def Tensor.checked (shape : Shape) (values : Array Float) : Except String Tensor := do
  if shape.rows == 0 || shape.cols == 0 then throw "tensor dimensions must be positive"
  if shape.rows > maximumElements / shape.cols then throw "tensor allocation exceeds 4096 binary64 elements"
  if shape.rows * shape.cols != values.size then throw "tensor shape/storage size mismatch"
  unless values.all Float.isFinite do throw "tensor contains NaN or infinity"
  return { shape, storage := values.foldl FloatArray.push .empty }

def Tensor.values (tensor : Tensor) : Array Float := tensor.storage.data

def Tensor.validate (tensor : Tensor) : Except String Unit := do
  let _ ← Tensor.checked tensor.shape tensor.values
  return ()

def Tensor.add (left right : Tensor) : Except String Tensor := do
  left.validate
  right.validate
  unless left.shape == right.shape do throw "add requires identical shapes"
  Tensor.checked left.shape (left.values.zipWith (· + ·) right.values)

def Tensor.hadamard (left right : Tensor) : Except String Tensor := do
  left.validate
  right.validate
  unless left.shape == right.shape do throw "multiply requires identical shapes"
  Tensor.checked left.shape (left.values.zipWith (· * ·) right.values)

def Tensor.dot (left right : Tensor) : Except String Float := do
  left.validate
  right.validate
  unless left.shape == right.shape && left.shape.rows == 1 do
    throw "dot requires equal row vectors"
  let result := (left.values.zipWith (· * ·) right.values).foldl (· + ·) 0.0
  unless result.isFinite do throw "dot produced a nonfinite result"
  return result

def unsupported (operation : String) : Except String Tensor :=
  .error s!"unsupported numerical operator '{operation}' in hosted-linear-v1"

end Lemma.Numerics
