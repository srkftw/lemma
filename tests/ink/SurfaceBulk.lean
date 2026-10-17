import Lemma.Ink.Surface
import Lean.Elab.Command

namespace BulkSurfaceFixture
open Lemma.Core0.Memory Lemma.Ink
structure State where
  bytes : Array UInt8
  packets : Nat := 0
  tiles : Nat := 0
  failure : UInt64 := 0
  width : UInt64
  height : UInt64
def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message
def origin : UInt64 := 0x10000
def ending : UInt64 := 0x310000
def readWord (bytes : Array UInt8) (address : UInt64) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:8] do value := value ||| (bytes[(address-origin).toNat+i]!.toUInt64 <<< (i*8).toUInt64)
  return value
def literalPixel (x y : UInt64) : UInt64 := (x * 3 + y * 5) % 16
partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => return (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "declared bound exceeded"
    let mut s : UInt8 := 0
    let mut v := initial
    for i in [:count.toNat] do
      if s = 0 then
        let result ← execute state (step i.toUInt32 count v a b c d)
        s := result.1; v := result.2
    execute state (next s v)
  | .platform op a b c d e f next =>
    let st ← state.get
    if op = .syscall then
      require (a=64 && b=73 && c=5 && d=Surface.bulkPacket && 1≤e && e≤7 && f=0) "wrong batch ABI"
      let word := readWord st.bytes
      require (word d=2 && word (d+8)=e && word (d+16)=0 && word (d+24)=0) "wrong header"
      for i in [:e.toNat] do
        let entry := d+32+i.toUInt64*32
        let x := word entry; let y := word (entry+8)
        let w := word (entry+16); let h := word (entry+24)
        let index := st.tiles+i
        let columns := (st.width+31)/32
        require (x=index.toUInt64%columns*32 && y=index.toUInt64/columns*32) "tile order changed"
        require (w=min 32 (st.width-x) && h=min 32 (st.height-y)) "edge geometry differs"
        let stride := (w+1)/2
        for offset in [:(stride*h).toNat] do
          let px := x+(offset.toUInt64%stride)*2
          let py := y+offset.toUInt64/stride
          let high := literalPixel px py
          let low := if st.width≤px+1 then 15 else literalPixel (px+1) py
          let address := d+256+i.toUInt64*512+offset.toUInt64
          require (st.bytes[(address-origin).toNat]!.toUInt64 = high*16+low) "literal payload differs"
      state.modify fun s => {s with packets:=s.packets+1,tiles:=s.tiles+e.toNat}
      execute state (next 0 e)
    else
      let width := if op=.virtualRead64 || op=.virtualWrite64 then 8 else 1
      require (origin≤a && a≤ending-width) "outside owned fixture memory"
      if width=8 then require (a%8=0) "unaligned word"
      if a=st.failure then execute state (next 95 0) else
      match op with
      | .virtualRead8 => execute state (next 0 st.bytes[(a-origin).toNat]!.toUInt64)
      | .virtualRead64 => execute state (next 0 (readWord st.bytes a))
      | .virtualWrite8 | .virtualWrite64 =>
        state.modify fun s => Id.run do
          let mut bytes := s.bytes
          for i in [:width.toNat] do bytes := bytes.set! ((a-origin).toNat+i) ((b >>> (i*8).toUInt64).toUInt8)
          return {s with bytes}
        execute state (next 0 0)
      | _ => throw <| IO.userError "unsupported operation"
  | _ => throw <| IO.userError "unsupported Action"
def checkCase (w h : UInt64) (failure : UInt64 := 0) : IO Unit := do
  let mut bytes := Array.replicate (ending-origin).toNat (0xa5:UInt8)
  let stride := (w+1)/2
  for offset in [:(stride*h).toNat] do
    let x := offset.toUInt64%stride*2; let y := offset.toUInt64/stride
    let low := if w≤x+1 then 15 else literalPixel (x+1) y
    bytes := bytes.set! ((Surface.framebuffer-origin).toNat+offset) (literalPixel x y*16+low).toUInt8
  let state ← IO.mkRef {bytes,width:=w,height:=h,failure : State}
  let result ← execute state (Surface.uploadAllBulk 73 w h)
  let final ← state.get
  let count := ((w+31)/32)*((h+31)/32)
  if failure=0 then
    require (result=(0,count) && final.tiles=count.toNat && final.packets=((count+6)/7).toNat) "wrong completion/count"
  else require (result.1=95 && final.packets=0) "fault submitted a partial guest packet"
  require (final.bytes[(Surface.bulkPacket-origin).toNat-1]! = (0xa5:UInt8) && final.bytes[(Surface.bulkPacket-origin).toNat+3840]! = (0xa5:UInt8)) "fixture page boundary corrupt"
  IO.println s!"BULK_SURFACE:{w}/{h} packets={final.packets} tiles={final.tiles} status={result.1}"
def check : IO Unit := do
  checkCase 35 33
  checkCase 224 32
  checkCase 225 32
  checkCase 512 64
  checkCase 35 33 (Surface.tile+8)
  IO.println "BULK_SURFACE:PASS independent tile order/compact byte oracle, seven-entry/tail batches, checked-read failure"
end BulkSurfaceFixture
open Lean Elab Command
run_cmd liftIO BulkSurfaceFixture.check
