import Lemma.Platform.LemmaSim.NotebookKernel
import Lean.Elab.Command
import Std.Data.HashMap

/-! Host-only finite observer of genuine maintained Actions. The comparison
retains the historical syscall-eight body and invokes the actual old private
device callback through an ordinary elaborated alias. It is not target code.
Only independently recorded, successful immutable metadata read blocks may
be removed; every remaining primitive, value, failure and write stays ordered.
The fault fixtures do not assert equivalence for a transient fault that first
appears only at a removed duplicate read. -/
open Lean Elab Command
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p =>
    p.1.toString.endsWith "NotebookKernel.deviceCallBulk"
  unless candidates.length = 1 do throwError "expected exact genuine old deviceCallBulk"
  let n := mkIdent candidates.head!.1
  let alias := mkIdent <| Name.mkSimple "originalBulkDeviceCall"
  elabCommand (← `(def $alias (a b c d : UInt64) : Lemma.Core0.Memory.Action := $n a b c d))
  let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith "Paper.uploadWord"
  unless candidates.length = 1 do throwError "expected exact genuine old Paper word callback"
  let n := mkIdent candidates.head!.1
  let alias := mkIdent <| Name.mkSimple "originalPaperWord"
  elabCommand (← `(def $alias (i count : UInt32) (a b c d e : UInt64) : Lemma.Core0.Memory.Action := $n i count a b c d e))

namespace SurfaceBulkBorrowFixture
open Lemma.Core0.Memory Lemma.Core0.Execution Lemma.Kernel.Memory
open Lemma.Kernel Lemma.User Lemma.Platform.LemmaSim

-- Offset proofs for the exact36-word capture destination. These prove only
-- descriptor layout disjointness; Action/LLVM audits establish the used spans.
theorem savedHeaderDisjoint (offset : Nat) (h : 2048 ≤ offset) : ¬offset < 1552 := by omega
theorem savedLoaderDisjoint (offset : Nat) (h : offset < 2336) : ¬2400 ≤ offset := by omega
theorem savedCapabilityDisjoint (offset : Nat) (h : offset < 2336) : ¬2560 ≤ offset := by omega

/-- Exact ordinary Lean metadata-only predecessor, using the unchanged genuine
private single-word callback. Quarantined host comparison only. -/
def beforeUploadAt (buffer offset x y width height : UInt64) : Action :=
  if Frames.pool ≤ buffer then if buffer ≤ Frames.expandedPoolLimit - 4096 then
  if buffer % 4096 = 0 then
  if width = 0 then .done Lemma.Drivers.Paper.invalid 0 else if 32 < width then .done Lemma.Drivers.Paper.invalid 0 else
  if height = 0 then .done Lemma.Drivers.Paper.invalid 0 else if 32 < height then .done Lemma.Drivers.Paper.invalid 0 else
  let length := ((width + 1) / 2) * height
  let copied := ((length + 7) / 8) * 8
  if offset % 8 = 0 then if offset ≤ 4096 - copied then
  .bind (IO.write64 (DeviceABI.paperBase+64) x) fun s _ => if s = 0 then
  .bind (IO.write64 (DeviceABI.paperBase+72) y) fun s _ => if s = 0 then
  .bind (IO.write64 (DeviceABI.paperBase+80) width) fun s _ => if s = 0 then
  .bind (IO.write64 (DeviceABI.paperBase+88) height) fun s _ => if s = 0 then
  .bind (IO.write64 (DeviceABI.paperBase+96) length) fun s _ => if s = 0 then
  .boundedFoldU64 64 originalPaperWord ((length + 7) / 8).toUInt32 0 (buffer + offset) 0 0 0 fun s _ =>
  if s = 0 then
  .bind (IO.write64 (DeviceABI.paperBase+104) 1) fun s _ => if s = 0 then
  .bind (IO.read64 (DeviceABI.paperBase+24)) fun s error => if s = 0 then
    if error = 0 then .done 0 length else .done Lemma.Drivers.Paper.deviceError error else .done s 0
  else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done Lemma.Drivers.Paper.invalid 0 else .done Lemma.Drivers.Paper.invalid 0
  else .done Lemma.Drivers.Paper.invalid 0 else .done Lemma.Drivers.Paper.invalid 0 else .done Lemma.Drivers.Paper.invalid 0

def beforeDispatch (frame : UInt64) : Action :=
  .bind (Access.read64 Process.control) fun s descriptor => if s = 0 then
  .bind (Task.capture descriptor frame) fun s context => if s = 0 then
  .bind (Access.read64 (context + 256)) fun s pc => if s = 0 then
  if pc % 4 = 0 then
  .bind (AddressSpace.lookup descriptor pc 4) fun s _ => if s = 0 then
  .bind (Access.read64 (context + 136)) fun s number => if s = 0 then
  if number = 64 then originalBulkDeviceCall descriptor context pc number
  else .done 50 0
  else .done 50 0 else .done 50 0 else .done 50 0
  else .done 50 0 else .done 50 0 else .done 50 0

structure Request where
  op : Op
  address : UInt64
  value : UInt64
  status : UInt8
  deriving BEq
instance : Inhabited Request := ⟨⟨.physicalRead64,0,0,0⟩⟩
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  requests : Array Request := #[]
  operations : Nat := 0
  callbacks : Nat := 0
  commands : Nat := 0
  errorAt : Nat := 0
  failRead : Option UInt64 := none
  failWrite : Option UInt64 := none
  failPIO : Option (Op × UInt64 × Nat) := none
  failure : UInt8 := 7
  globalFault : Bool := false

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message
def word (s : State) (a : UInt64) := s.words.getD a 0
def put (s : State) (a v : UInt64) : State :=
  {s with words := if v = 0 then s.words.erase a else s.words.insert a v}
def byte (s : State) (a : UInt64) := (word s (a-a%8) >>> (a%8*8)) &&& 255
def putByte (s : State) (a v : UInt64) :=
  let shift := a%8*8
  put s (a-a%8) ((word s (a-a%8) &&& ~~~((255:UInt64) <<< shift)) ||| ((v &&& 255) <<< shift))
def reset (s : State) := {s with
  requests := #[]
  operations := 0
  callbacks := 0
  commands := 0
  errorAt := 0
  failRead := none
  failWrite := none
  failPIO := none
  failure := 7
  globalFault := false}

partial def execute (r : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next => let (s,v) ← execute r first; execute r (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    if budget < count.toNat then execute r (next 9 initial) else
    let mut result := (0,initial)
    for i in [:count.toNat] do
      if result.1 = 0 then
        r.modify fun s => {s with callbacks := s.callbacks+1}
        result ← execute r (step i.toUInt32 count result.2 a b c d)
    execute r (next result.1 result.2)
  | .platform op a b _ _ _ _ next =>
    let s ← r.get
    require (s.operations < 4000000) "finite primitive budget exhausted"
    r.set {s with operations := s.operations+1}
    if op = .installSatp then execute r (next 0 0) else
    let isPIO := op = .deviceRead64 || op = .deviceWrite64
    let isRead := op = .physicalRead64 || op = .physicalRead8 || op = .deviceRead64
    if isPIO then
      require (DeviceABI.paperBase ≤ a && a < DeviceABI.paperBase+4096 && a%8 = 0) "undeclared literal PIO"
    else
      require ((0x80400000 ≤ a && a < 0x80510000) || (0x82000000 ≤ a && a < 0x84000000)) "outside finite RAM"
    if op = .physicalRead64 || op = .physicalWrite64 then require (a%8 = 0) "unaligned physical64"
    let fault := if isPIO then s.failPIO == some (op,a,s.commands)
      else if isRead then s.failRead == some a else s.failWrite == some a
    let status : UInt8 := if fault then s.failure else 0
    let value := if op = .physicalRead64 then word s a else if op = .physicalRead8 then byte s a
      else if op = .deviceRead64 then
        if a = DeviceABI.paperBase+32 then 1650 else if a = DeviceABI.paperBase+40 then 2200
        else if a = DeviceABI.paperBase+24 then if s.errorAt != 0 && s.commands = s.errorAt then 9 else 0
        else 0
      else b
    r.modify fun s => {s with requests := s.requests.push ⟨op,a,(if isRead && fault then 0 else value),status⟩}
    if fault && s.globalFault then throw <| IO.userError "non-returning architectural access fault"
    match op with
    | .physicalRead64 | .physicalRead8 | .deviceRead64 => execute r (next status (if status = 0 then value else 0))
    | .physicalWrite64 =>
      if status = 0 then r.modify fun s => put s a b
      execute r (next status 0)
    | .physicalWrite8 =>
      if status = 0 then r.modify fun s => putByte s a b
      execute r (next status 0)
    | .deviceWrite64 =>
      if status = 0 && a = DeviceABI.paperBase+104 then r.modify fun s => {s with commands := s.commands+1}
      execute r (next status 0)
    | _ => throw <| IO.userError "unadmitted primitive"
  | _ => throw <| IO.userError "unadmitted Action constructor"

def success (r : IO.Ref State) (a : Action) : IO UInt64 := do
  let (s,v) ← execute r a; require (s = 0) s!"setup status{s}"; pure v
def outcome (r : IO.Ref State) (a : Action) : IO (Option (UInt8 × UInt64)) := do
  try pure <| some (← execute r a)
  catch e =>
    require ((← r.get).globalFault && e.toString.endsWith "non-returning architectural access fault") "unexpected fixture exception"
    pure none

def compare (snapshot : State) (frame : UInt64) (blocks : Array (Array Request)) : IO (Nat × Nat) := do
  require (blocks.all fun block => !block.isEmpty && block.all fun row => row.op = .physicalRead64 && row.status = 0)
    "only exact successful immutable read blocks admitted"
  let old ← IO.mkRef snapshot
  let fresh ← IO.mkRef snapshot
  let before ← outcome old (beforeDispatch frame)
  let after ← outcome fresh (NotebookKernel.dispatchBulk frame 8 0)
  let a ← old.get; let b ← fresh.get
  require (before == after && a.words == b.words && a.commands == b.commands) s!"result/RAM/controller-prefix differs {before} vs {after}"
  let mut i := 0; let mut j := 0
  while i < a.requests.size do
    let removable := blocks.find? fun block =>
      a.requests[i]! == block[0]! && a.requests.extract i (i+block.size) == block &&
      (b.requests[j]? != some block[0]! || b.requests.extract j (j+block.size) != block)
    if let some block := removable then i := i+block.size else
      require (j < b.requests.size && a.requests[i]! == b.requests[j]!) s!"ordered retained request differs {i}/{j}"
      i := i+1; j := j+1
  require (j = b.requests.size) "new request suffix"
  pure (a.requests.size,b.requests.size)

def pointer : UInt64 := 0x10a000
def pixels (i j : UInt64) := 0x0102030405060708 ^^^ (i*0x1122334455667788) ^^^ j
def batch (s : State) (pa count : UInt64) : State := Id.run do
  let mut s := put (put (put (put s pa 2) (pa+8) count) (pa+16) 0) (pa+24) 0
  for i in [:7] do
    let fields := pa+32+i.toUInt64*32
    s := put (put (put (put s fields (i.toUInt64*32)) (fields+8) 16) (fields+16) 32) (fields+24) 32
    for j in [:64] do s := put s (pa+256+i.toUInt64*512+j.toUInt64*8) (pixels i.toUInt64 j.toUInt64)
  return reset s
def expected (count : Nat) : Array (UInt64 × UInt64) := Id.run do
  let mut writes := #[]
  for i in [:count] do
    for (offset,value) in #[(64,i.toUInt64*32),(72,16),(80,32),(88,32),(96,512)] do
      writes := writes.push (DeviceABI.paperBase+offset,value)
    for j in [:64] do writes := writes.push (DeviceABI.paperBase+0x800+j.toUInt64*8,pixels i.toUInt64 j.toUInt64)
    writes := writes.push (DeviceABI.paperBase+104,1)
  return writes

def comparePaper (snapshot : State) (buffer offset width height : UInt64) : IO Unit := do
  let old ← IO.mkRef snapshot; let fresh ← IO.mkRef snapshot
  let before ← outcome old (beforeUploadAt buffer offset 13 17 width height)
  let after ← outcome fresh (Lemma.Drivers.Paper.uploadOffsetAt buffer offset 13 17 width height)
  let a ← old.get; let b ← fresh.get
  require (before == after && a.words == b.words && a.requests == b.requests && a.commands = b.commands)
    s!"paper group full ordered result/RAM/request fault prefix differs width{width}/height{height}/offset{offset}"

def checkPaper : IO Unit := do
  let buffer := Frames.pool
  let mut s : State := {}
  for i in [:512] do s := put s (buffer+i.toUInt64*8) (0x0102030405060708 ^^^ i.toUInt64)
  for w in [:34] do
    for h in [:34] do
      comparePaper s buffer 0 w.toUInt64 h.toUInt64
  for offset in #[0,8,256,3584,3585,3592,4088,4096,0xfffffffffffffff8] do
    comparePaper s buffer offset 32 32
  for physical in #[buffer-4096,buffer+1,Frames.expandedPoolLimit-4096,Frames.expandedPoolLimit] do
    comparePaper s physical 0 32 32
  for shape in #[(1,1),(3,7),(17,13),(31,31),(32,32)] do
    let width : UInt64 := shape.1; let height : UInt64 := shape.2
    let words := ((((width+1)/2)*height+7)/8).toNat
    for i in [:words] do
      for status in #[7,8,9,95,255] do
        comparePaper {s with failRead := some (buffer+i.toUInt64*8),failure := status} buffer 0 width height
        comparePaper {s with failPIO := some (.deviceWrite64,DeviceABI.paperBase+0x800+i.toUInt64*8,0),failure := status} buffer 0 width height
      comparePaper {s with failRead := some (buffer+i.toUInt64*8),globalFault := true} buffer 0 width height
      comparePaper {s with failPIO := some (.deviceWrite64,DeviceABI.paperBase+0x800+i.toUInt64*8,0),globalFault := true} buffer 0 width height
  IO.println "PAPER_WORD_GROUPS:PASS1156 shapes/9offsets/4poolbounds; exact full retained request/error/global-fault prefix at every word in five representative block/tail shapes; no physical/MMIO operation removed"

def check (expanded : Bool) : IO Unit := do
  let r ← IO.mkRef ({} : State)
  let amount : UInt64 := if expanded then 8192 else 512
  discard <| success r (Frames.configure amount (if expanded then 8192 else 32) 4)
  discard <| success r Frames.init
  discard <| success r Objects.init
  let descriptor ← success r (AddressSpace.create 2)
  let address ← success r (AddressSpace.base descriptor)
  let user ← success r (Frames.allocate 2 4)
  let pa ← success r (Frames.resolvePurpose 2 user 4)
  discard <| success r (AddressSpace.mapUser descriptor pointer user 3)
  let code ← success r (Frames.allocate 2 3)
  discard <| success r (AddressSpace.mapUser descriptor 0x10000 code 5)
  discard <| success r (Capability.attach descriptor)
  let key ← success r (Objects.createEndpoint descriptor)
  let cap ← success r (Capability.grantBoot descriptor key CapabilityABI.endpointCall)
  discard <| success r (Capability.activate descriptor)
  discard <| success r (DeviceService.configure key 0 0)
  let scratch := word (← r.get) (DeviceService.state+24)
  let scratchPA ← success r (Frames.resolvePurpose 1 scratch 1)
  let stack ← success r (Frames.allocateContiguous4 2 1)
  let handles := #[word (← r.get) stack,word (← r.get) (stack+8),word (← r.get) (stack+16),word (← r.get) (stack+24)]
  let stackPA ← success r (Frames.resolvePurpose 2 handles[0]! 1)
  for (offset,v) in #[((2400 : UInt64),handles[0]!),(2480,handles[1]!),(2488,handles[2]!),(2496,handles[3]!),
      (2504,4),(2512,stackPA),(2408,stackPA+16368)] do r.modify fun s => put s (address+offset) v
  r.modify fun s => put (put s stackPA Loader.stackCanary) (stackPA+16376) Loader.stackCanary
  discard <| success r Task.init
  let record ← success r Task.table
  r.modify fun s => put (put s record descriptor) (record+8) Task.running
  let frame := stackPA+16368-288
  let translation := word (← r.get) (address+72)
  for (offset,v) in #[((80 : UInt64),cap),(88,5),(96,pointer),(104,7),(112,0),(136,64),
      (256,0x10000),(264,0x200000020),(272,translation)] do r.modify fun s => put s (frame+offset) v
  r.modify fun s => put s Process.control descriptor
  let original := batch (← r.get) pa 7
  let baseRef ← IO.mkRef original
  discard <| success baseRef (AddressSpace.base descriptor)
  let baseTrace := (← baseRef.get).requests
  let scratchRef ← IO.mkRef original
  discard <| success scratchRef (Frames.resolvePurpose 1 scratch 1)
  let scratchTrace := (← scratchRef.get).requests
  let blocks := #[baseTrace,scratchTrace]
  let counts ← compare original frame blocks
  require (counts.1 = counts.2+3*baseTrace.size+7*scratchTrace.size) "exact three AS plus seven frame duplicate blocks"
  let fresh ← IO.mkRef original
  let actual ← execute fresh (NotebookKernel.dispatchBulk frame 8 0)
  require (actual.1 = 0) s!"actual successful dispatcher result {actual}"
  let final ← fresh.get
  let prior ← IO.mkRef original
  discard <| execute prior (beforeDispatch frame)
  let originalCallbacks := (← prior.get).callbacks
  let metadataCallbacks := 3*(← baseRef.get).callbacks+7*(← scratchRef.get).callbacks
  require (originalCallbacks = final.callbacks+392+metadataCallbacks)
    s!"seven paper64→8 groups plus exactly measured removed metadata callbacks {originalCallbacks}/{final.callbacks}/{metadataCallbacks}"
  let pio := final.requests.filterMap fun row => if row.op = .deviceWrite64 then some (row.address,row.value) else none
  require (pio == expected 7 && final.commands = 7) "independent literal controller order/payload"
  for i in [:3840] do require (byte final (scratchPA+i.toUInt64) = byte original (pa+i.toUInt64)) "complete copied prefix bytes"
  let metadata := blocks.foldl (fun acc block => block.foldl (fun acc row => if acc.contains row.address then acc else acc.push row.address) acc) (#[] : Array UInt64)
  require (final.requests.all fun row => if row.op = .physicalWrite64 || row.op = .physicalWrite8
    then !metadata.contains row.address else true) "intervening write overlaps borrowed metadata"
  for (slot,v) in #[(address,0),(address+24,0),(address+64,word original (address+64)+4096),
      (address+72,translation+1),(frame+256,0x10002),(frame+264,0x200000120),
      (frame+272,translation+1),(stackPA,0),(stackPA+16376,0),(record+8,Task.blocked),
      (address+2488,handles[1]!),(address+2408,stackPA+8192),
      (Frames.record (handles[0]!%amount)+16,1),(DeviceService.state+24,descriptor),
      (DeviceService.state+24,scratch+amount),(Frames.record (scratch%amount)+8,2),
      (pa,1),(pa+8,6),(pa+16,1),(pa+24,1),(pa+32+6*32+16,0),
      (pa+32+6*32,1640),(frame+80,cap+16),(frame+104,0),(frame+104,8),
      (frame+96,pointer+8),(frame+96,pointer+4096),(frame+112,1)] do
    discard <| compare (put original slot v) frame blocks
  for count in #[1,2,6,7] do
    discard <| compare (put (batch original pa count) (frame+104) count) frame blocks
  let addresses := final.requests.foldl (fun acc row => if row.op = .physicalRead64 || row.op = .physicalWrite64 || row.op = .physicalRead8 || row.op = .physicalWrite8
    then if acc.contains row.address then acc else acc.push row.address else acc) (#[] : Array UInt64)
  for a in addresses do
    discard <| compare {original with failRead := some a} frame blocks
    discard <| compare {original with failWrite := some a} frame blocks
  for status in #[7,9,95,255] do
    for a in #[pa+3832,scratchPA+3832,address+72,address+2048] do
      discard <| compare {original with failRead := some a,failure := status} frame blocks
      discard <| compare {original with failWrite := some a,failure := status} frame blocks
  for a in #[pa+3832,scratchPA+3832,address+72,address+2048] do
    discard <| compare {original with failRead := some a,globalFault := true} frame blocks
    discard <| compare {original with failWrite := some a,globalFault := true} frame blocks
  for command in [:7] do
    for (op,offset) in #[(Op.deviceRead64,24),(Op.deviceWrite64,64),(Op.deviceWrite64,0x800),(Op.deviceWrite64,0x9f8),(Op.deviceWrite64,104)] do
      discard <| compare {original with failPIO := some (op,DeviceABI.paperBase+offset,command)} frame blocks
    discard <| compare {original with errorAt := command+1} frame blocks
  IO.println s!"SURFACE_BULK_BORROW:PASS pool{amount} requests{counts.1}->{counts.2}; callbacks{originalCallbacks}->{final.callbacks}; ASblock{baseTrace.size}x3/frameblock{scratchTrace.size}x7 removed; full RAM/result/retained ordered PIO/copy/status/fault prefixes, stable address fault cases{addresses.size*2}, metadata disjoint"

def main : IO Unit := do
  checkPaper
  check false
  check true
end SurfaceBulkBorrowFixture
def main := SurfaceBulkBorrowFixture.main
