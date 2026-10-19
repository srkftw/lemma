/-! school-linear-q10-v1. Two signed two's-complement Q10 weights, bias,
and features. Input bounds make modular UInt64 accumulation an exact encoding
of the signed integer result (absolute value at most 25165824). Output is Q20;
there is no rounding inside inference and no derivative of quantization. -/
namespace Lemma.Numerics.Quantized

def validSigned (word bound : UInt64) : Bool :=
  if word ≤ bound then true else (0 - bound) ≤ word

def validParameters (w0 w1 bias : UInt64) : Bool :=
  if validSigned w0 8192 then
    if validSigned w1 8192 then validSigned bias 8192 else false
  else false

def validFeatures (x0 x1 mask : UInt64) : Bool :=
  if mask = 3 then
    if validSigned x0 1024 then validSigned x1 1024 else false
  else false

def score (w0 w1 bias x0 x1 : UInt64) : UInt64 :=
  w0 * x0 + w1 * x1 + bias * 1024

end Lemma.Numerics.Quantized
