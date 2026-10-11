import Lemma.Ink.Rasterizer
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only independent integer coverage oracle and production Action probe.
The oracle uses signed integer dot/cross products and scans the whole tile.
It does not call Geometry.covered or the production clipping/packing code.
No oracle, managed memory or host Action executor enters a target image. -/
namespace InkReference
open Lemma.Core0.Memory

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  contextReads : Nat := 0
  pixelsVisited : Nat := 0
  surfaceBytes : UInt64 := 0
  byteWrites : Array UInt64 := #[]

def context : UInt64 := 0x40000
def tile : UInt64 := 0x41000
def surface : UInt64 := 0x50000
def readWord (state : State) (address : UInt64) : UInt64 := state.words.getD address 0
def writeWord (state : State) (address value : UInt64) : State :=
  { state with words := state.words.insert address value }
def readByte (state : State) (address : UInt64) : UInt64 :=
  (readWord state (address - address % 8) >>> (address % 8 * 8)) &&& 255
def writeByte (state : State) (address value : UInt64) : State :=
  let shift := address % 8 * 8
  let word := readWord state (address - address % 8)
  writeWord state (address - address % 8)
    ((word &&& ~~~((255 : UInt64) <<< shift)) ||| ((value &&& 255) <<< shift))

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s value => pure (s, value)
  | .bind first next =>
    let (s, value) ← execute state first
    execute state (next s value)
  | .boundedFoldU64 budget step count initial a b c d next =>
    if budget < count.toNat then execute state (next 9 initial) else
    state.modify fun s => { s with pixelsVisited := s.pixelsVisited + count.toNat }
    let mut value := initial
    let mut status : UInt8 := 0
    for i in [:count.toNat] do
      if status == 0 then
        let result ← execute state (step i.toUInt32 count value a b c d)
        status := result.1
        value := result.2
    execute state (next status value)
  | .platform op a b _ _ _ _ next =>
    if !((context ≤ a && a < context + 64) || (tile ≤ a && a < tile + 512) ||
         (surface ≤ a && a < surface + (← state.get).surfaceBytes)) then
      throw <| IO.userError "ink probe escaped caller-owned spans"
    match op with
    | .virtualRead64 =>
      if a % 8 != 0 then throw <| IO.userError "unaligned context read"
      if context ≤ a && a < context + 64 then
        state.modify fun s => { s with contextReads := s.contextReads + 1 }
      execute state (next 0 (readWord (← state.get) a))
    | .virtualRead8 => execute state (next 0 (readByte (← state.get) a))
    | .virtualWrite8 =>
      state.modify fun s => { writeByte s a b with byteWrites := s.byteWrites.push a }
      execute state (next 0 0)
    | _ => throw <| IO.userError "unexpected ink probe primitive"
  | _ => throw <| IO.userError "unexpected ink probe Action"

def require (condition : Bool) (message : String) : IO Unit :=
  if condition then pure () else throw <| IO.userError message

def integer (value : UInt64) : Int := Int.ofNat value.toNat

def reference (x y x0 y0 x1 y1 p0 p1 nominal maximum : UInt64) : Bool := Id.run do
  let dx := integer x1 - integer x0
  let dy := integer y1 - integer y0
  let px := integer x - integer x0
  let py := integer y - integer y0
  let length := dx * dx + dy * dy
  let dot := dx * px + dy * py
  let projection := max 0 (min length dot)
  let pressure := if length == 0 then integer p0 else
    if p0 ≤ p1 then integer p0 + (integer p1 - integer p0) * projection / length
    else integer p0 - (integer p0 - integer p1) * projection / length
  let width := if maximum == 0 then integer nominal else
    integer nominal * (integer maximum + 3 * pressure) / (4 * integer maximum)
  let radius := width / 2
  if length == 0 || projection == 0 then
    return px * px + py * py ≤ radius * radius / 65536
  if projection == length then
    let px := integer x - integer x1
    let py := integer y - integer y1
    return px * px + py * py ≤ radius * radius / 65536
  let cross := dx * py - dy * px
  return cross * cross ≤ radius * radius * length / 65536

def checkCase (words : Array UInt64) (tx ty width height : UInt64) (pattern : Bool) : IO Nat := do
  require (words.size == 8) "literal context length"
  let mut initial : State := {}
  for i in [:8] do
    initial := writeWord initial (context + i.toUInt64 * 8) words[i]!
  for i in [:512] do
    initial := writeByte initial (tile + i.toUInt64)
      (if pattern then (i.toUInt64 * 37 + 11) % 256 else 255)
  let state ← IO.mkRef initial
  let result ← execute state (Lemma.Ink.Rasterizer.segment context tile tx ty width height)
  require (result.1 == 0) "production rasterizer rejected valid literal context"
  let actual ← state.get
  require (actual.contextReads == 16 && actual.pixelsVisited ≤ 1024) "cached bounded context/pixel work"
  let x0 := words[0]! * (width - 1) / 0x1000000
  let y0 := words[1]! * (height - 1) / 0x1000000
  let x1 := words[2]! * (width - 1) / 0x1000000
  let y1 := words[3]! * (height - 1) / 0x1000000
  let mut changed : UInt64 := 0
  for i in [:1024] do
    let x := tx + i.toUInt64 % 32
    let y := ty + i.toUInt64 / 32
    let address := tile + i.toUInt64 / 2
    let byte := readByte initial address
    let before := if i % 2 == 0 then byte >>> 4 else byte &&& 15
    let ink := x < width && y < height &&
      reference x y x0 y0 x1 y1 words[4]! words[5]! words[6]! words[7]!
    let expected := if ink then 0 else before
    let byte := readByte actual address
    let observed := if i % 2 == 0 then byte >>> 4 else byte &&& 15
    require (observed == expected) s!"independent full tile mismatch pixel{i} geometry{width}x{height}"
    if expected != before then changed := changed + 1
  require (changed == result.2) "dirty count differs from literal initial pixels"
  pure actual.pixelsVisited

def q (pixel dimension : UInt64) : UInt64 :=
  (pixel * 0x1000000 + dimension - 2) / (dimension - 1)

def checkSurfaceCase (words : Array UInt64) (tx ty width height : UInt64) : IO Unit := do
  let stride := (width + 1) / 2
  let mut initial : State := { surfaceBytes := stride * height }
  for i in [:8] do initial := writeWord initial (context + i.toUInt64 * 8) words[i]!
  -- Seed the tile plus adjacent row bytes, rather than allocate the whole
  -- screen in this host fixture. Every actual write is separately bounded.
  for row in [:32] do
    let y := ty + row.toUInt64
    if y < height then
      let left := if tx = 0 then 0 else tx / 2 - 1
      let right := min stride (tx / 2 + 17)
      for offset in [left.toNat:right.toNat] do
        let byteIndex := y * stride + offset.toUInt64
        let pattern := (byteIndex * 37 + 11) % 256
        let packed := if width % 2 = 1 && offset.toUInt64 + 1 = stride then pattern ||| 15 else pattern
        initial := writeByte initial (surface + byteIndex) packed
  let state ← IO.mkRef initial
  let result ← execute state (Lemma.Ink.Rasterizer.segmentSurface context surface tx ty width height)
  require (result.1 == 0) "direct surface rejected literal context"
  let actual ← state.get
  require (actual.contextReads == 16 && actual.pixelsVisited ≤ 1024) "direct bounded context/pixel work"
  let x0 := words[0]! * (width - 1) / 0x1000000
  let y0 := words[1]! * (height - 1) / 0x1000000
  let x1 := words[2]! * (width - 1) / 0x1000000
  let y1 := words[3]! * (height - 1) / 0x1000000
  let mut changed : UInt64 := 0
  for i in [:1024] do
    let x := tx + i.toUInt64 % 32
    let y := ty + i.toUInt64 / 32
    if x < width && y < height then
      let address := surface + y * stride + x / 2
      let before := readByte initial address
      let before := if x % 2 == 0 then before >>> 4 else before &&& 15
      let ink := reference x y x0 y0 x1 y1 words[4]! words[5]! words[6]! words[7]!
      let expected := if ink then 0 else before
      let observed := readByte actual address
      let observed := if x % 2 == 0 then observed >>> 4 else observed &&& 15
      require (observed == expected) "independent direct surface pixel mismatch"
      if expected != before then changed := changed + 1
  for address in actual.byteWrites do
    let offset := address - surface
    let y := offset / stride
    let x := offset % stride * 2
    require (surface ≤ address && address < surface + stride * height &&
             tx ≤ x && x < tx + 32 && ty ≤ y && y < ty + 32) "direct write escaped clipped tile"
  for row in [:32] do
    let y := ty + row.toUInt64
    if y < height then
      if tx > 0 then
        let address := surface + y * stride + tx / 2 - 1
        require (readByte actual address == readByte initial address) "direct left row guard changed"
      if tx / 2 + 16 < stride then
        let address := surface + y * stride + tx / 2 + 16
        require (readByte actual address == readByte initial address) "direct right row guard changed"
      if width % 2 == 1 then
        require (readByte actual (surface + (y + 1) * stride - 1) &&& 15 ==
                 readByte initial (surface + (y + 1) * stride - 1) &&& 15) "unused row nibble changed"
  require (changed == result.2) "direct surface dirty count differs"

def rejectedContext (words : Array UInt64) : IO Unit := do
  let mut initial : State := {}
  for i in [:8] do
    initial := writeWord initial (context + i.toUInt64 * 8) words[i]!
  for i in [:512] do
    initial := writeByte initial (tile + i.toUInt64) 255
  let state ← IO.mkRef initial
  let result ← execute state (Lemma.Ink.Rasterizer.segment context tile 0 0 32 32)
  require (result.1 == Lemma.Ink.Rasterizer.invalid) "invalid cached context accepted"
  let actual ← state.get
  require (actual.pixelsVisited == 0) "invalid context reached the pixel loop"
  for i in [:512] do
    require (readByte actual (tile + i.toUInt64) == 255) "invalid context altered tile bytes"

def check : IO Unit := do
  -- Literal local segment visits66 pixels instead of1024 while preserving the
  -- historical64-black-pixel example, including high-even nibble packing.
  let visited ← checkCase #[0, q 10 32, q 20 32, q 10 32, 4095, 4095, 512, 4095] 0 0 32 32 false
  require (visited == 66) "literal conservative clipped bbox"
  let mut cases := 1
  for (width, height) in #[(1650,2200),(1404,1872),(4096,4096),(33,35)] do
    for brush in #[256,512,2048,8192] do
      for (p0,p1) in #[(0,4095),(4095,0),(4095,4095)] do
        for (x0,y0,x1,y1) in #[(0,0,0x1000000,0x1000000),
          (0x1000000,0,0,0x1000000),(0x800000,0x800000,0x800000,0x800000)] do
          let words := #[x0,y0,x1,y1,p0,p1,brush,4095]
          for (tx,ty) in #[(0,0),(width / 64 * 32,height / 64 * 32),
                           ((width-1)/32*32,(height-1)/32*32)] do
            discard <| checkCase words tx ty width height true
            cases := cases + 1
  discard <| checkCase #[0,0,0x1000000,0x1000000,0,0,512,0] 0 0 32 32 false
  for invalid in #[#[0x1000001,0,0,0,4095,4095,512,4095],
                   #[0,0,0,0,4095,4096,512,4095],
                   #[0,0,0,0,4095,4095,8193,4095],
                   #[0,0,0,0,4095,4095,512,65536]] do
    rejectedContext invalid
  let mut surfaces := 0
  for (width,height) in #[(1650,2200),(1404,1872),(65,67),(33,35)] do
    for brush in #[256,512,2048,8192] do
      let words := #[q 25 width,q 25 height,q (min 40 (width-1)) width,q (min 40 (height-1)) height,0,4095,brush,4095]
      for (tx,ty) in #[(0,0),(32,0),(0,32),(32,32)] do
        checkSurfaceCase words tx ty width height
        surfaces := surfaces + 1
    for (tx,ty) in #[(0,0),((width-1)/32*32,(height-1)/32*32)] do
      checkSurfaceCase #[0,0,0x1000000,0x1000000,4095,0,2048,4095] tx ty width height
      surfaces := surfaces + 1
  IO.println s!"INK_INDEPENDENT_RASTER:PASS tile_cases={cases+1} surface_cases={surfaces} cached_context_reads=16 literal_bbox_pixels={visited} oracle_scans=1024"

end InkReference
open Lean Elab Command
run_cmd liftIO InkReference.check
