import Lemma.Ink.Surface
import Lean.Elab.Command

/-! Host-only transfer and pixel equivalence checks. They exercise the actual
Action syntax, with literal bytes and the unchanged scalar pixel routine as
references. They do not replace freestanding execution or controller output. -/
namespace SurfaceWords
open Lemma.Core0.Memory Lemma.Ink

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message

structure State where
  bytes : Array UInt8
  wordReads : Nat := 0
  wordWrites : Nat := 0

def origin : UInt64 := 0x10000
def endAddress : UInt64 := 0x320000

partial def execute (memory : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => pure (status,value)
  | .bind first next =>
    let (status,value) ← execute memory first
    execute memory (next status value)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "fold exceeds its declared bound"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let pair ← execute memory (step i.toUInt32 count value a b c d)
        status := pair.1
        value := pair.2
    execute memory (next status value)
  | .platform op address value _ _ _ _ next =>
    let length := if op = .virtualRead64 || op = .virtualWrite64 then 8 else 1
    require (origin ≤ address && address ≤ endAddress - length) "out-of-bounds transfer"
    if length = 8 then require (address % 8 = 0) "unaligned word transfer"
    let index := (address - origin).toNat
    match op with
    | .virtualRead8 | .virtualRead64 =>
      let state ← memory.get
      let mut result : UInt64 := 0
      for i in [:length.toNat] do
        result := result ||| (state.bytes[index+i]!.toUInt64 <<< (i*8).toUInt64)
      if length = 8 then memory.modify fun s => {s with wordReads := s.wordReads+1}
      execute memory (next 0 result)
    | .virtualWrite8 | .virtualWrite64 =>
      memory.modify fun s => Id.run do
        let mut bytes := s.bytes
        for i in [:length.toNat] do
          bytes := bytes.set! (index+i) ((value >>> (i*8).toUInt64) &&& 255).toUInt8
        return {s with bytes, wordWrites := s.wordWrites + (if length = 8 then 1 else 0)}
      execute memory (next 0 0)
    | _ => throw <| IO.userError "unexpected operation in surface fixture"
  | _ => throw <| IO.userError "unexpected Action in surface fixture"

def newMemory : IO (IO.Ref State) :=
  IO.mkRef {bytes := Array.replicate (endAddress-origin).toNat 0xa5}

def checkBackground (width height : UInt64) (words : Bool) : IO Unit := do
  let memory ← newMemory
  let result ← execute memory (Surface.background width height)
  let stride := (width+1)/2
  require (result = (0,stride*height)) "background status/length differs"
  let state ← memory.get
  require ((state.wordWrites > 0) = words) "aligned/fallback path differs"
  for offset in [:(stride*height).toNat] do
    let x := (offset.toUInt64 % stride)*2
    let y := offset.toUInt64/stride
    let high := Surface.backgroundPixel x y width height
    let low := if width ≤ x+1 then 15 else Surface.backgroundPixel (x+1) y width height
    require (state.bytes[(Surface.framebuffer-origin).toNat+offset]! = ((high <<< 4) ||| low).toUInt8)
      s!"background byte differs at {width}/{height}/{offset}"
  require (state.bytes[(Surface.framebuffer-origin+stride*height).toNat]! = 0xa5)
    "background changed its following byte"

def checkTile (width height x y : UInt64) (words : Bool) : IO Unit := do
  let memory ← newMemory
  let stride := (width+1)/2
  memory.modify fun s => {s with bytes := s.bytes.mapIdx fun index _ => (index*37+11).toUInt8}
  let initial ← memory.get
  require ((← execute memory (Surface.loadTile x y width height)) = (0,0)) "loadTile status differs"
  let loaded ← memory.get
  require ((loaded.wordReads = 64 && loaded.wordWrites = 64) = words) "loadTile path differs"
  for i in [:512] do
    let px := x + (i%16).toUInt64*2
    let py := y + (i/16).toUInt64
    let expected := if height ≤ py || width ≤ px then 255 else
      initial.bytes[(Surface.framebuffer-origin+py*stride+px/2).toNat]!
    require (loaded.bytes[(Surface.tile-origin).toNat+i]! = expected) "tile row/edge padding differs"
  require ((← execute memory (Surface.storeTile x y width height)) = (0,0)) "storeTile status differs"
  let stored ← memory.get
  require ((stored.wordReads = 128 && stored.wordWrites = 128) = words) "storeTile path differs"
  for i in [:stored.bytes.size] do
    if i < (Surface.tile-origin).toNat || (Surface.tile-origin).toNat+512 ≤ i then
      require (stored.bytes[i]! = initial.bytes[i]!) "round trip changed a neighbor or row stride"

def check : IO Unit := do
  -- Literal margins, horizontal rules, and odd-width final padding.
  require (Surface.backgroundCanvasWord 16 180 512 = 0xddddddcddddddddd) "literal left margin/rule"
  require (Surface.backgroundCanvasWord 496 180 511 = 0xdfdddddddddddddd) "literal odd padding/rule"
  require (Surface.backgroundCanvasWord 496 148 511 = 0x0f00000000000000) "separator precedes margins"
  for (width,height,words) in #[(512,640,true),(527,321,true),(513,320,false)] do
    checkBackground width height words
  for (w,h,x,y,words) in #[(512,640,32,32,true),(527,321,480,288,true),
                          (513,320,32,32,false),(512,640,496,624,false),
                          (1650,2200,1632,2176,false)] do
    checkTile w h x y words
  IO.println "SURFACE_WORDS:PASS scalar pixels, aligned transfers, odd/partial edges, and unchanged neighbors"
end SurfaceWords
open Lean Elab Command
run_cmd liftIO SurfaceWords.check
