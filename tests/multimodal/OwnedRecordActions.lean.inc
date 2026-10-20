
namespace Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture
open Std Lemma.Core0.Memory Lemma.Kernel.Memory
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  reads : Array UInt64 := #[]
  writes : Nat := 0
  callbacks : Nat := 0
  operations : Nat := 0
  failRead : Option UInt64 := none
  failWrite : Option (UInt64 × UInt64) := none
  faultUsed : Bool := false
  flushes : Nat := 0
  pcm : Array UInt64 := #[]
  expireAfter : Nat := 0
  capHandle : UInt64 := 0

def word (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  { s with words := if v = 0 then s.words.erase a else s.words.insert a v }
def byte (s : State) (a : UInt64) : UInt64 :=
  (word s (a - a % 8) >>> (a % 8 * 8)) &&& 255
def putByte (s : State) (a v : UInt64) : State :=
  let shift := a % 8 * 8
  put s (a - a % 8) ((word s (a - a % 8) &&& ~~~((255 : UInt64) <<< shift)) |||
    ((v &&& 255) <<< shift))

def require (b : Bool) (message : String) : IO Unit :=
  if b then pure () else throw <| IO.userError message

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next =>
    if count.toNat > budget then execute state (next 9 initial) else
    let mut status : UInt8 := 0
    let mut acc := initial
    for i in [:count.toNat] do
      if status = 0 then
        state.modify fun s => { s with callbacks := s.callbacks + 1 }
        let result ← execute state (step i.toUInt32 count acc c0 c1 c2 c3)
        status := result.1
        acc := result.2
    execute state (next status acc)
  | .platform op a b _ _ _ _ next =>
    let s ← state.get
    if s.operations ≥ 10000000 then throw <| IO.userError "fixture budget exhausted"
    state.set { s with operations := s.operations + 1 }
    if op == .installSatp then
      state.modify fun s => {s with flushes := s.flushes+1}
      execute state (next 0 0)
    else if op == .deviceRead64 then execute state (next 0 (word s a))
    else if op == .deviceWrite64 then
      state.modify fun s => put s a b
      if a == Lemma.Drivers.Multimodal.base + 256 + 176 then
        state.modify fun s => put s (Lemma.Drivers.Multimodal.base + 256 + 184) 1
      if a == Lemma.Drivers.Multimodal.base + 256 + 8*256 + 112 then
        state.modify fun s =>
          let s := { s with pcm := s.pcm.push b }
          let s := put s (Lemma.Drivers.Multimodal.base + 256 + 8*256 + 240) (s.pcm.size.toUInt64)
          if s.expireAfter > 0 && s.pcm.size == s.expireAfter then put s (Lemma.Drivers.Multimodal.base+24) 1000000 else s
      execute state (next 0 0)
    else
      require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000))
        s!"access outside finite physical RAM {a}"
      match op with
      | .physicalRead64 =>
        require (a % 8 == 0) "unaligned read64"
        state.modify fun s => { s with reads := s.reads.push a }
        if (← state.get).failRead == some a then execute state (next 95 0)
        else execute state (next 0 (word (← state.get) a))
      | .physicalWrite64 =>
        require (a % 8 == 0) "unaligned write64"
        if s.failWrite == some (a,b) && !s.faultUsed then
          state.modify fun s => { s with faultUsed := true }
          execute state (next 96 0)
        else
          state.modify fun s => { (put s a b) with writes := s.writes + 1 }
          execute state (next 0 0)
      | .physicalRead8 =>
        if (← state.get).failRead == some a then execute state (next 95 0)
        else execute state (next 0 (byte (← state.get) a))
      | .physicalWrite8 =>
        state.modify fun s => { (putByte s a b) with writes := s.writes + 1 }
        execute state (next 0 0)
      | _ => throw <| IO.userError "unexpected primitive"
  | _ => throw <| IO.userError "unexpected Action"

def success (state : IO.Ref State) (action : Action) : IO UInt64 := do
  let (s,v) ← execute state action
  require (s == 0) s!"unexpected status{s}"
  pure v


def fixture : IO (IO.Ref State × UInt64 × UInt64 × UInt64 × UInt64) := do
  let r ← IO.mkRef ({} : State)
  discard <| success r (Frames.configure 512 32 4)
  discard <| success r Frames.init
  discard <| success r Lemma.Kernel.Objects.init
  let descriptor ← success r (AddressSpace.create 2)
  discard <| success r (Lemma.Kernel.Capability.attach descriptor)
  let key ← success r (Lemma.Kernel.Objects.createEndpoint descriptor)
  let cap ← success r (Lemma.Kernel.Capability.grantBoot descriptor key Lemma.User.CapabilityABI.endpointCall)
  discard <| success r (Lemma.Kernel.Capability.activate descriptor)
  r.modify fun s => { (put s state key) with capHandle := cap }
  let page ← success r (Frames.allocate 2 4)
  let user ← success r (Frames.resolve 2 page)
  discard <| success r (AddressSpace.mapUser descriptor 0x40000 page 3)
  let scratch ← success r (Frames.allocate 1 1)
  let dma ← success r (Frames.allocate 1 1)
  let dmaPA ← success r (Frames.resolvePurpose 1 dma 1)
  let scratchPA ← success r (Frames.resolvePurpose 1 scratch 1)
  for (a,v) in [(state+8,scratch),(state+16,dma),(state+64,11),(state+80,3),
      (state+88,1000000),(state+96,128),(state+104,100),
      (Lemma.Drivers.Multimodal.base+24,100),
      (Lemma.Drivers.Multimodal.base+256+144,1),
      (Lemma.Drivers.Multimodal.base+256+224,123),
      (Lemma.Drivers.Multimodal.base+256+32,2)] do
    r.modify fun s => put s a v
  require (dmaPA != user && dmaPA != scratchPA) "DMA shares user or metadata memory"
  pure (r,descriptor,user,dmaPA,scratchPA)

def complete (r : IO.Ref State) (dmaPA : UInt64) : IO Unit := do
  for (i,v) in #[0xffffffffffff1234,100,104,33,123,2,17,255].toList.zipIdx do
    r.modify fun s => put s (dmaPA+v.toUInt64*8) i
  r.modify fun s => put s (Lemma.Drivers.Multimodal.base+256+184) 2

def run : IO Unit := do
  let (r,descriptor,user,dma,scratch) ← fixture
  let cap := (← r.get).capHandle
  require ((← success r (call descriptor cap 18 0 0 0)) == 2) "service version negotiation failed"
  for operation in [12,13,14,15,16,17,18] do
    let before ← r.get
    require ((← execute r (call descriptor 0 operation 0 0x40000 11)).1 != 0) "new operation bypassed capability admission"
    require ((← r.get).writes == before.writes) "unauthorized new operation wrote kernel/guest state"
  require ((← success r (beginRecord descriptor 0 0x40000 11)) == 123) "wrong start sequence"
  let busy ← r.get
  require (word busy (Lemma.Drivers.Multimodal.base+256+160) == dma) "application DMA target escaped ownership"
  require (word busy (Lemma.Drivers.Multimodal.base+256+168) == 8) "record extent changed"
  require (word busy user == 0) "begin exposed incomplete record"
  require ((← execute r (finishRecord descriptor 0 0x40000 11)).1 == 6) "busy completion accepted"
  require ((← execute r (take descriptor 0 0x40000 11)).1 == 6) "CPU take bypassed pending record"
  require ((← execute r (finishRecord (descriptor+1) 0 0x40000 11)).1 == 7) "foreign descriptor accepted"
  require ((← execute r (finishRecord descriptor 0 0x40008 11)).1 == 4) "changed destination accepted"
  require ((← execute r (finishRecord descriptor 0 0x40000 12)).1 == 4) "changed epoch accepted"
  discard <| success r (UserCopy.copyFromUser descriptor 0x40000 (word busy (state+8)) 0 64)
  require (word (← r.get) (state+40) == 1 && word (← r.get) scratch == 0) "metadata touched active identity"
  complete r dma
  require ((← success r (finishRecord descriptor 0 0x40000 11)) == 123) "completion sequence differs"
  for (value,index) in #[0xffffffffffff1234,100,104,33,123,2,17,255].toList.zipIdx do
    require (word (← r.get) (user+index.toUInt64*8) == value) "incomplete record copy"
    require (word (← r.get) (dma+index.toUInt64*8) == 0) "private DMA retained raw data"
  require (word (← r.get) (state+96) == 64 && word (← r.get) (state+40) == 0) "completion charge/ownership differs"
  require ((← execute r (finishRecord descriptor 0 0x40000 11)).1 == 5) "repeated completion accepted"
  let (r,d,u,dma,_) ← fixture
  discard <| success r (beginRecord d 0 0x40000 11)
  complete r dma
  discard <| success r (AddressSpace.unmap d 0x40000)
  require ((← execute r (finishRecord d 0 0x40000 11)).1 != 0) "unmapped destination accepted"
  require (word (← r.get) (state+40) == 0 && word (← r.get) dma == 0 && word (← r.get) u == 0) "copy failure leaked private active transfer"
  let (r,d,u,dma,_) ← fixture
  discard <| success r (beginRecord d 0 0x40000 11)
  complete r dma
  r.modify fun s => put s (Lemma.Drivers.Multimodal.base+24) 1000000
  require ((← execute r (finishRecord d 0 0x40000 11)).1 == 8) "expired completion accepted"
  require (word (← r.get) u == 0 && word (← r.get) (state+40) == 0) "expired data exposed or private owner leaked"
  let (r,d,u,dma,_) ← fixture
  discard <| success r (beginRecord d 0 0x40000 11)
  complete r dma
  r.modify fun s => put s (dma+32) 124
  require ((← execute r (finishRecord d 0 0x40000 11)).1 == 4 && word (← r.get) u == 0) "changed record sequence accepted"
  let (r,d,u,dma,_) ← fixture
  discard <| success r (beginRecord d 0 0x40000 11)
  r.modify fun s => put (put s dma 99) (state+64) 12
  require ((← execute r (beginRecord d 0 0x40000 12)).1 == 6) "retired in-flight frame reused"
  require (word (← r.get) dma == 99 && word (← r.get) (state+48) == 11) "retired in-flight write ownership erased"
  complete r dma
  require ((← success r (beginRecord d 0 0x40000 12)) == 123) "new grant stranded behind retired completion"
  require (word (← r.get) u == 0 && word (← r.get) dma == 0 && word (← r.get) (state+48) == 12) "retired raw exposed or new grant lost"
  let (r,d,u,dma,_) ← fixture
  discard <| success r (beginRecord d 0 0x40000 11)
  complete r dma
  r.modify fun s => put s (Lemma.Drivers.Multimodal.base+256+16) 9
  require ((← execute r (finishRecord d 0 0x40000 11)).1 == 9) "controller overflow hidden by completed DMA"
  require (word (← r.get) u == 0 && word (← r.get) (state+40) == 0) "failed stream exposed data or retained ownership"
  let (r,d,u,_,_) ← fixture
  let block := Lemma.Drivers.Multimodal.base+256+8*256
  for (a,v) in [(state+row 8,12),(state+row 8+16,64),(state+row 8+24,1000000),
      (state+row 8+32,128),(u,0x31424350),(u+8,1),(u+16,4),(u+24,0),
      (u+32,0xffff80007fff0000)] do r.modify fun s => put s a v
  require ((← success r (pcmBatch d 8 0x40000 12)) == 4) "PCM batch count differs"
  require ((← r.get).pcm == #[0,32767,32768,65535]) "S16_LE sample order changed"
  require (word (← r.get) (state+row 8+32) == 96 && word (← r.get) (block+232) == 0) "acceptance charged wire bytes or invented playback"
  r.modify fun s => { (put s (state+row 8+32) 128) with pcm := #[], expireAfter := 2 }
  r.modify fun s => put s (block+240) 0
  let result ← execute r (pcmBatch d 8 0x40000 12)
  require (result == (8,2) && word (← r.get) (state+row 8+32) == 112) "partial expiry did not charge exact accepted prefix"
  IO.println "OWNED_RECORD_PCM_ACTIONS_PASS ownership/copy64/pending/descriptor/epoch/mapping/expiry/sequence/wipe/partial-S16-prefix"
end Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture
def main := Lemma.Platform.LemmaSim.MultimodalService.OwnedRecordFixture.run
