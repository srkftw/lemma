import Lemma.Applications.Notebook
import Std.Data.HashMap
import Lean.Elab.Command

/-! Literal Action observations only, not a kernel/controller replacement or
RV64 acceptance. Expected indices, bytes and queue prefixes are independent of
the guest's packing and submission helpers. -/
namespace DirtySurfaceFixture
open Lemma.Core0.Memory Lemma.Ink

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  width : UInt64 := 64
  height : UInt64 := 96
  indices : Array UInt64 := #[3,0,1,2,4,5]
  accepted : Nat := 0
  packets : Nat := 0
  refreshes : Nat := 0
  touches : Nat := 0
  failure : UInt64 := 0
  status : UInt8 := 0
  completedPrefix : UInt64 := 0

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message
def pixel (x y : UInt64) : UInt64 := (x * 3 + y * 5) % 16
def sourceByte (s : State) (offset : UInt64) : UInt64 :=
  let stride := (s.width + 1) / 2
  let x := offset % stride * 2
  let y := offset / stride
  (pixel x y <<< 4) ||| (if s.width ≤ x + 1 then 15 else pixel (x + 1) y)
def read (s : State) (address : UInt64) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:8] do
    let a := address + i.toUInt64
    let byte := if Surface.framebuffer ≤ a && a < Surface.framebuffer + ((s.width + 1) / 2) * s.height
      then sourceByte s (a - Surface.framebuffer)
      else (s.words.getD address 0 >>> (i * 8).toUInt64) &&& 255
    value := value ||| (byte <<< (i * 8).toUInt64)
  return value
def write (s : State) (address value : UInt64) : State :=
  {s with words := s.words.insert address value}
def byte (s : State) (address : UInt64) : UInt64 :=
  (read s (address - address % 8) >>> (address % 8 * 8)) &&& 255

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => return (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "dirty batch exceeded declared fold"
    let mut result := ((0 : UInt8),initial)
    for i in [:count.toNat] do
      if result.1 = 0 then result ← execute state (step i.toUInt32 count result.2 a b c d)
    execute state (next result.1 result.2)
  | .platform op a b c d e f next =>
    let s ← state.get
    if op = .syscall then
      require (a=64 && b=73 && f=0) "dirty batch acquired an undeclared syscall"
      if c=4 then execute state (next 0 0)
      else if c=3 then execute state (next 0 7)
      else if c=2 then
        require (d=Surface.metadata && read s (d+40)=8) "refresh sequence/metadata differs"
        require (read s d=0 && read s (d+8)=0 && read s (d+16)=s.width && read s (d+24)=s.height)
          "refresh lost original rectangle"
        state.modify fun s => {s with refreshes:=s.refreshes+1}
        execute state (next 0 8)
      else if c=5 then
        require (d=Surface.bulkPacket && 1≤e && e≤4) "dirty upload ABI/count differs"
        require (read s d=2 && read s (d+8)=e && read s (d+16)=0 && read s (d+24)=0)
          "dirty packet header differs"
        let columns := (s.width+31)/32
        for i in [:e.toNat] do
          require (s.accepted+i<s.indices.size) "unexpected extra dirty tile"
          let index := s.indices[s.accepted+i]!
          let x := index%columns*32; let y := index/columns*32
          let w := min 32 (s.width-x); let h := min 32 (s.height-y)
          let entry := d+32+i.toUInt64*32
          require (read s entry=x && read s (entry+8)=y && read s (entry+16)=w && read s (entry+24)=h)
            "noncontiguous dirty tile order/geometry differs"
          let stride := (w+1)/2
          for j in [:(stride*h).toNat] do
            let px := x+j.toUInt64%stride*2; let py := y+j.toUInt64/stride
            let low := if s.width≤px+1 then 15 else pixel (px+1) py
            require (byte s (d+256+i.toUInt64*512+j.toUInt64)=pixel px py*16+low)
              "dirty payload differs from literal pixels"
        let completed := if s.status=0 then e else s.completedPrefix
        state.modify fun s => {s with accepted:=s.accepted+completed.toNat,packets:=s.packets+1}
        execute state (next s.status completed)
      else throw <| IO.userError "unsupported dirty fixture operation"
    else
      require (0x10000≤a && a<0x350000) "dirty access escaped owned test spans"
      let width := if op=.virtualRead64 || op=.virtualWrite64 then 8 else 1
      if width=8 then require (a%8=0) "unaligned dirty word"
      state.modify fun s => {s with touches:=s.touches+1}
      if a=s.failure then execute state (next 95 0) else
      match op with
      | .virtualRead64 => execute state (next 0 (read s a))
      | .virtualRead8 => execute state (next 0 (byte s a))
      | .virtualWrite64 | .virtualWrite8 =>
        require (!(Surface.framebuffer≤a && a<Surface.framebuffer+2000000)) "upload altered source pixels"
        state.modify fun st =>
          if width=8 then write st a b else
          let shift := a%8*8
          write st (a-a%8) ((read st (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift))
        execute state (next 0 0)
      | _ => throw <| IO.userError "unsupported dirty fixture primitive"
  | _ => throw <| IO.userError "unsupported dirty fixture Action"

def initial : State := Id.run do
  let mut s : State := {}
  for (offset,value) in #[(0,73),(32,64),(40,96),(336,0),(344,0),(352,64),(360,96),
      (456,6),(464,16382),(472,4),(584,1)] do
    s := write s (Lemma.Applications.Notebook.state+offset) value
  s := write s Lemma.Applications.Notebook.dirtyBitmap 63
  for i in [:s.indices.size] do
    let slot := (16382+i.toUInt64)%16384
    let a := Lemma.Applications.Notebook.dirtyQueue+slot/4*8
    s := write s a (read s a ||| (s.indices[i]! <<< (slot%4*16)))
  return s

def pack (indices : Array UInt64) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:indices.size] do value := value ||| (indices[i]! <<< (i*16).toUInt64)
  return value

def check : IO Unit := do
  let successful ← IO.mkRef initial
  require ((← execute successful Lemma.Applications.Notebook.pumpRefreshBatched)=(0,0)) "first four-tile batch failed"
  let s ← successful.get
  require (s.packets=1 && s.accepted=4 && s.refreshes=0 && read s (Lemma.Applications.Notebook.state+456)=2 &&
    read s (Lemma.Applications.Notebook.state+464)=2 && byte s Lemma.Applications.Notebook.dirtyBitmap=48) "four-tile budget/wrapped queue differs"
  require ((← execute successful Lemma.Applications.Notebook.pumpRefreshBatched)=(0,8)) "tail batch/refresh failed"
  let s ← successful.get
  require (s.packets=2 && s.accepted=6 && s.refreshes=1 && read s (Lemma.Applications.Notebook.state+456)=0 &&
    read s (Lemma.Applications.Notebook.state+464)=4 && byte s Lemma.Applications.Notebook.dirtyBitmap=0 && read s (Lemma.Applications.Notebook.state+336)=65535)
    "tail publication/queue differs"
  let partialCase ← IO.mkRef {initial with status:=171,completedPrefix:=2}
  require ((← execute partialCase Lemma.Applications.Notebook.pumpRefreshBatched)=(171,0)) "controller partial error changed"
  let s ← partialCase.get
  require (s.accepted=2 && s.packets=1 && s.refreshes=0 && read s (Lemma.Applications.Notebook.state+456)=4 &&
    read s (Lemma.Applications.Notebook.state+464)=0 && byte s Lemma.Applications.Notebook.dirtyBitmap=54) "failed batch lost/duplicated an uncompleted tile"
  partialCase.modify fun s => {s with status:=0}
  require ((← execute partialCase Lemma.Applications.Notebook.pumpRefreshBatched)=(0,8)) "ordinary remaining-prefix retry failed"
  require ((← partialCase.get).accepted=6 && (← partialCase.get).packets=2) "retry duplicated effects"
  for (width,height,indices) in #[
      ((35 : UInt64),(33 : UInt64),#[(3 : UInt64),1,0,2]),
      (1650,2200,#[(87 : UInt64),0,3587,52])] do
    let edge ← IO.mkRef {width,height,indices : State}
    require ((← execute edge (Surface.uploadIndexedBulk 73 width height (pack indices) 4))=(0,4))
      "odd/canonical stride and clipped final tile differ"
    require ((← edge.get).packets=1 && (← edge.get).accepted=4) "edge batch submission differs"
  for packed in #[((1 : UInt64) ||| ((1 : UInt64) <<< 16)),7,65536] do
    let s ← IO.mkRef ({} : State)
    let count := if packed=65537 then 2 else 1
    require ((← execute s (Surface.uploadIndexedBulk 73 64 96 packed count))=(234,0)) "invalid indices accepted"
    require ((← s.get).touches=0 && (← s.get).packets=0) "invalid index touched memory/device"
  let broken ← IO.mkRef {initial with failure:=Surface.framebuffer}
  require ((← execute broken Lemma.Applications.Notebook.pumpRefreshBatched)=(95,0)) "late packet preparation fault changed"
  let s ← broken.get
  require (s.packets=0 && read s (Lemma.Applications.Notebook.state+456)=6 && read s (Lemma.Applications.Notebook.state+464)=16382 &&
    byte s Lemma.Applications.Notebook.dirtyBitmap=63) "preparation fault published/consumed a partial packet"
  IO.println "DIRTY_SURFACE:PASS noncontiguous literal bytes, queue wrap, four-tile budget, partial controller prefix/retry, malformed indices and late preparation fault"
end DirtySurfaceFixture
open Lean Elab Command
run_cmd liftIO DirtySurfaceFixture.check
