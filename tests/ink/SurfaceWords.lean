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
  byteReads : Nat := 0
  byteWrites : Nat := 0
  framebufferEnd : UInt64 := 0
  failedRead : UInt64 := 0

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
    let state ← memory.get
    if Surface.framebuffer ≤ address && state.framebufferEnd != 0 then
      require (address + length ≤ state.framebufferEnd) "transfer exceeds allocated framebuffer pages"
    if length = 8 then require (address % 8 = 0) "unaligned word transfer"
    let index := (address - origin).toNat
    match op with
    | .virtualRead8 | .virtualRead64 =>
      let state ← memory.get
      if state.failedRead = address then execute memory (next 95 0) else do
        let mut result : UInt64 := 0
        for i in [:length.toNat] do
          result := result ||| (state.bytes[index+i]!.toUInt64 <<< (i*8).toUInt64)
        memory.modify fun s =>
          let reads := s.wordReads+(if length = 8 then 1 else 0)
          let bytes := s.byteReads+(if length = 1 then 1 else 0)
          {s with wordReads := reads, byteReads := bytes}
        execute memory (next 0 result)
    | .virtualWrite8 | .virtualWrite64 =>
      memory.modify fun s => Id.run do
        let mut bytes := s.bytes
        for i in [:length.toNat] do
          bytes := bytes.set! (index+i) ((value >>> (i*8).toUInt64) &&& 255).toUInt8
        let words := s.wordWrites + (if length = 8 then 1 else 0)
        let byteWrites := s.byteWrites + (if length = 1 then 1 else 0)
        return {s with bytes, wordWrites := words, byteWrites}
      execute memory (next 0 0)
    | _ => throw <| IO.userError "unexpected operation in surface fixture"
  | _ => throw <| IO.userError "unexpected Action in surface fixture"

def newMemory (mappedEnd : UInt64 := 0) : IO (IO.Ref State) :=
  IO.mkRef {bytes := Array.replicate (endAddress-origin).toNat 0xa5, framebufferEnd := mappedEnd}

def checkBackground (width height : UInt64) (words : Bool) : IO Unit := do
  let memory ← newMemory
  let result ← execute memory (Surface.background width height)
  let stride := (width+1)/2
  require (result = (0,stride*height)) "background status/length differs"
  let state ← memory.get
  require ((state.wordWrites > 0) = words) "packed/scalar path differs"
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
  let stride := (width+1)/2
  let bytes := stride*height
  let mappedEnd := Surface.framebuffer + ((bytes+4095)/4096)*4096
  let memory ← newMemory mappedEnd
  memory.modify fun s => {s with bytes := s.bytes.mapIdx fun index _ => (index*37+11).toUInt8}
  let initial ← memory.get
  require ((← execute memory (Surface.loadTile x y width height)) = (0,0)) "loadTile status differs"
  let loaded ← memory.get
  let mut unaligned := 0
  for row in [:32] do
    if (y+row.toUInt64)*stride % 8 != 0 then unaligned := unaligned+2
  let loadReads := if words then 64+unaligned else 0
  require (loaded.wordReads = loadReads && loaded.wordWrites = (if words then 64 else 0))
    "loadTile aligned gather count differs"
  if words then require (loaded.byteReads = 0 && loaded.byteWrites = 0) "full tile used byte transfers"
  for i in [:512] do
    let px := x + (i%16).toUInt64*2
    let py := y + (i/16).toUInt64
    let expected := if height ≤ py || width ≤ px then 255 else
      initial.bytes[(Surface.framebuffer-origin+py*stride+px/2).toNat]!
    require (loaded.bytes[(Surface.tile-origin).toNat+i]! = expected) "tile row/edge padding differs"
  -- Store distinct bytes, so a no-op or incomplete scatter cannot pass a round trip.
  let replacement := Array.range 512 |>.map fun i => (i*53+23).toUInt8
  memory.modify fun s => {s with bytes := s.bytes.mapIdx fun i byte =>
    if (Surface.tile-origin).toNat ≤ i && i < (Surface.tile-origin).toNat+512 then
      replacement[i-(Surface.tile-origin).toNat]! else byte}
  require ((← execute memory (Surface.storeTile x y width height)) = (0,0)) "storeTile status differs"
  let stored ← memory.get
  require (stored.wordReads = (if words then loadReads+64+unaligned*2 else 0) &&
    stored.wordWrites = (if words then 128+unaligned else 0)) "storeTile aligned scatter count differs"
  if words then require (stored.byteReads = 0 && stored.byteWrites = 0) "full tile store used byte transfers"
  let mut difference : Option Nat := none
  for i in [:stored.bytes.size] do
    let expected := if (Surface.tile-origin).toNat ≤ i && i < (Surface.tile-origin).toNat+512 then
      replacement[i-(Surface.tile-origin).toNat]!
    else if (Surface.framebuffer-origin).toNat ≤ i &&
      i < (Surface.framebuffer-origin+bytes).toNat then
      let offset := i.toUInt64-(Surface.framebuffer-origin)
      let row := offset/stride
      let column := offset%stride
      if y ≤ row && row < y+32 && x/2 ≤ column && column < x/2+16 &&
        x+(column-x/2)*2 < width then replacement[((row-y)*16+column-x/2).toNat]!
      else initial.bytes[i]!
    else initial.bytes[i]!
    if stored.bytes[i]! != expected && difference.isNone then difference := some i
  require difference.isNone s!"tile scatter or neighbor differs at {width}/{height}/{x}/{y}/{difference}"
  IO.println s!"SURFACE_TILE:{width}/{height}/{x}/{y} word-load={loaded.wordReads}/{loaded.wordWrites} byte-load={loaded.byteReads}/{loaded.byteWrites} word-total={stored.wordReads}/{stored.wordWrites}"

def checkReadFailure : IO Unit := do
  -- First row starts at an odd address. Its second aligned read fails.
  let address := Surface.framebuffer+257+16
  let memory ← newMemory (Surface.framebuffer+81920)
  memory.modify fun s => {s with failedRead := address-address%8+8}
  let initial ← memory.get
  require ((← execute memory (Surface.loadTile 32 1 513 320)) = (95,0)) "gather lost failed read status"
  require ((← memory.get).bytes = initial.bytes) "failed gather wrote a tile byte"
  require ((← execute memory (Surface.storeTile 32 1 513 320)) = (95,0)) "scatter lost failed read status"
  require ((← memory.get).bytes = initial.bytes) "scatter wrote before reading both neighbor words"

def check : IO Unit := do
  -- Literal margins, horizontal rules, and odd-width final padding.
  require (Surface.backgroundCanvasWord 16 180 512 = 0xddddddcddddddddd) "literal left margin/rule"
  require (Surface.backgroundCanvasWord 496 180 511 = 0xdfdddddddddddddd) "literal odd padding/rule"
  require (Surface.backgroundCanvasWord 496 148 511 = 0x0f00000000000000) "separator precedes margins"
  for (width,height,words) in #[(512,640,true),(527,321,true),(513,320,true),
                              (1650,193,true),(17,191,true),(7,191,false),(25,129,true)] do
    checkBackground width height words
  for (w,h,x,y,words) in #[(512,640,32,32,true),(527,321,480,288,true),
                          (513,320,32,32,true),(1650,2200,32,32,true),
                          (34,241,0,209,true),(34,256,0,224,true),
                          (1650,2200,1600,2168,true),(512,640,2,32,false),
                          (512,640,496,624,false),(1650,2200,1632,2176,false)] do
    checkTile w h x y words
  checkReadFailure
  IO.println "SURFACE_WORDS:PASS scalar pixels, aligned gather/scatter, odd/partial edges, read failures, and unchanged neighbors"
end SurfaceWords
open Lean Elab Command
run_cmd liftIO SurfaceWords.check
