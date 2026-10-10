/-! Version1 integer ink geometry. All arithmetic intermediates fit UInt64 for
validated geometry≤4096 and pressure≤65535. No floating point or target runtime.
Normalized coordinates are separate from the raw controller provenance. -/
namespace Lemma.Ink.Geometry

def coordinateMaximum : UInt64 := 0x1000000
def dimensionMaximum : UInt64 := 4096
def validDimension (dimension : UInt64) : Bool :=
  if 0 < dimension then if dimension ≤ dimensionMaximum then true else false else false

def pixel (normalized dimension : UInt64) : UInt64 :=
  if dimension = 0 then 0 else
  let q := if coordinateMaximum < normalized then coordinateMaximum else normalized
  q * (dimension - 1) / coordinateMaximum

def normalized (raw maximum : UInt64) : UInt64 :=
  if maximum = 0 then 0 else
  if maximum < raw then coordinateMaximum else raw * coordinateMaximum / maximum

def difference (a b : UInt64) : UInt64 := if a ≤ b then b - a else a - b

def square (value : UInt64) : UInt64 := value * value

/-- Width is Q8 pixels. Pressure0 retains a quarter-width contact; full pressure
uses the nominal width. A capability with pressureMaximum0 uses nominal width
without claiming measured pressure. -/
def pressureWidth (nominal pressure pressureMaximum : UInt64) : UInt64 :=
  if pressureMaximum = 0 then nominal else
  let p := if pressureMaximum < pressure then pressureMaximum else pressure
  nominal * (pressureMaximum + 3 * p) / (4 * pressureMaximum)

/-- The closest segment point's pressure, with integer linear interpolation.
The caller supplies a clamped numerator0..denominator. -/
def interpolatedPressure (first last numerator denominator : UInt64) : UInt64 :=
  if denominator = 0 then first else
  if first ≤ last then first + (last - first) * numerator / denominator
  else first - (first - last) * numerator / denominator

def sameSign (a b c d : UInt64) : Bool :=
  if a ≤ b then if c ≤ d then true else false
  else if d < c then true else false

/-- Signed products are represented as positive/negative magnitudes, avoiding a
signed ABI. The dot product clamps projection to an endpoint. Interior coverage
uses exact cross-product distance, with division on the bound to avoid overflow.
There is no pixel traversal whose cost depends on notebook history. -/
def covered (x y x0 y0 x1 y1 p0 p1 nominal pressureMaximum : UInt64) : Bool :=
  let dx := difference x0 x1
  let dy := difference y0 y1
  let px := difference x0 x
  let py := difference y0 y
  let xx := dx * px
  let yy := dy * py
  let positive := (if sameSign x0 x1 x0 x = true then xx else 0) +
    (if sameSign y0 y1 y0 y = true then yy else 0)
  let negative := (if sameSign x0 x1 x0 x = true then 0 else xx) +
    (if sameSign y0 y1 y0 y = true then 0 else yy)
  let length := square dx + square dy
  let projection := if positive ≤ negative then 0 else
    if length < positive - negative then length else positive - negative
  let pressure := interpolatedPressure p0 p1 projection length
  let radius := pressureWidth nominal pressure pressureMaximum / 2
  let radiusSquared := square radius
  if length = 0 then if square px + square py ≤ radiusSquared / 65536 then true else false else
  if projection = 0 then if square px + square py ≤ radiusSquared / 65536 then true else false else
  if projection = length then
    if square (difference x1 x) + square (difference y1 y) ≤ radiusSquared / 65536 then true else false
  else
    let a := dx * py
    let b := dy * px
    let crossPositive := (if sameSign x0 x1 y0 y = true then a else 0) +
      (if sameSign y0 y1 x0 x = true then 0 else b)
    let crossNegative := (if sameSign x0 x1 y0 y = true then 0 else a) +
      (if sameSign y0 y1 x0 x = true then b else 0)
    if square (difference crossPositive crossNegative) ≤ radiusSquared * length / 65536 then true else false

end Lemma.Ink.Geometry
