import Lemma.Kernel.Scheduler
import Lemma.Platform.LemmaSim.DeviceABI
import Lean.Elab.Command
import Std.Data.HashMap
open Lean Elab Command
run_cmd do
  for (suffix,alias) in [("Scheduler.enter","originalSchedulerEntry"),("Scheduler.entryV2","successorSchedulerEntry")] do
    let rows := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith suffix
    unless rows.length = 1 do throwError "genuine exact scheduler entry missing"
    let original := mkIdent rows.head!.1
    let name := mkIdent (Name.mkSimple alias)
    elabCommand (← `(def $name (a b : UInt64) : Lemma.Core0.Memory.Action := $original a b))
namespace TaskEntryBorrowFixture
-- Integer layout proof for every runtime frame index. The complete primitive
-- validates the same bound before returning pool+index*4096; this lemma is not
-- a compiler-correctness or fault-delivery proof.
theorem poolFrameLayout (index : Nat) (h : index < 8192) :
    0x82000000 ≤ 0x82000000 + index * 4096 ∧
    0x82000000 + index * 4096 ≤ 0x84000000 - 4096 ∧
    (0x82000000 + index * 4096) % 4096 = 0 := by
  constructor
  · omega
  constructor
  · omega
  · simp [Nat.add_mod]

open Lemma.Core0.Memory Lemma.Core0.Execution Lemma.Kernel.Memory Lemma.Kernel Lemma.User Lemma.Platform.LemmaSim
structure Request where
  op : Op
  address : UInt64
  value : UInt64
  status : UInt8
  uartConstructor : UInt8
  deriving BEq
instance : Inhabited Request := ⟨⟨.physicalRead64,0,0,0,0⟩⟩
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
  enterStatus : UInt8 := 0
  enterReason : UInt64 := 1

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
    let mut i := 0
    while i < count.toNat && result.1 = 0 do
      r.modify fun s => {s with callbacks := s.callbacks+1}
      result ← execute r (step i.toUInt32 count result.2 a b c d)
      i := i+1
    execute r (next result.1 result.2)
  | .uartReadStatus next =>
    r.modify fun s => {s with requests := s.requests.push ⟨.physicalRead8,0x10000005,0x20,0,1⟩}
    execute r (next 0 0x20)
  | .uartWriteByte value next =>
    r.modify fun s => {s with requests := s.requests.push ⟨.physicalWrite8,0x10000000,value.toUInt64,0,2⟩}
    execute r (next 0)
  | .platform op a b _ _ _ _ next =>
    let s ← r.get
    require (s.operations < 4000000) "finite primitive budget exhausted"
    r.set {s with operations := s.operations+1}
    if op = .installSatp then execute r (next 0 0) else
    if op = .firmwareCall then
      r.modify fun t => {t with requests := t.requests.push ⟨op,a,b,0,0⟩}
      execute r (next 0 (if a = 2 then 123 else if a = 5 then 10123 else 0))
    else if op = .enterUser then
      r.modify fun t => {t with requests := t.requests.push ⟨op,a,s.enterReason,s.enterStatus,0⟩}
      -- Finite hardware-boundary fixture: the returned S continuation has the
      -- recorded kernel root active. This is not a guest or trap execution.
      if s.enterStatus = 0 then r.modify fun t => put t AddressSpace.activeRoot (word t (Process.control+8))
      execute r (next s.enterStatus s.enterReason)
    else
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
    r.modify fun s => {s with requests := s.requests.push ⟨op,a,(if isRead && fault then 0 else value),status,0⟩}
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
    require ((← r.get).globalFault && e.toString.endsWith "non-returning architectural access fault") s!"unexpected fixture exception: {e.toString}"
    pure none


def compare (snapshot : State) (descriptor : UInt64) : IO (Nat × Nat) := do
  let probe ← IO.mkRef snapshot
  let checked ← outcome probe (AddressSpace.base descriptor)
  let probed ← probe.get
  let block := if checked.isSome && checked.get!.1 = 0 then probed.requests else #[]
  require (block.all fun r => r.op = .physicalRead64 && r.status = 0)
    "only this snapshot's successful immutable complete descriptor validation block"
  let old ← IO.mkRef snapshot; let fresh ← IO.mkRef snapshot
  let before ← outcome old (originalSchedulerEntry descriptor 123)
  let after ← outcome fresh (successorSchedulerEntry descriptor 123)
  let a ← old.get; let b ← fresh.get
  require (before == after && a.words == b.words && a.commands == b.commands)
    s!"outcome or RAM differs {before} vs {after}"
  let mut i := 0; let mut j := 0; let mut removed := 0
  while i < a.requests.size do
    if a.requests.extract i (i+block.size) == block && b.requests.extract j (j+block.size) != block then
      i := i+block.size; removed := removed+1
    else
      require (b.requests[j]? == some a.requests[i]!) s!"ordered primitive prefix differs at old{i}/new{j}: oldaddr{a.requests[i]!.address}/value{a.requests[i]!.value}/status{a.requests[i]!.status} vs newaddr{b.requests[j]!.address}/value{b.requests[j]!.value}/status{b.requests[j]!.status}"
      i := i+1; j := j+1
  require (j = b.requests.size && removed ≤ 3) "only three exact duplicate descriptor reads may be removed"
  pure (a.requests.size,b.requests.size)

def setup (expanded : Bool) : IO (State × UInt64 × UInt64 × UInt64) := do
  let r ← IO.mkRef ({} : State)
  discard <| success r (Frames.configure (if expanded then 8192 else 512) (if expanded then 8192 else 32) 4)
  discard <| success r Frames.init
  let descriptor ← success r (AddressSpace.create 2)
  let address ← success r (AddressSpace.base descriptor)
  let stack ← success r (Frames.allocateContiguous4 2 1)
  let handles := #[word (← r.get) stack,word (← r.get) (stack+8),word (← r.get) (stack+16),word (← r.get) (stack+24)]
  let stackPA ← success r (Frames.resolvePurpose 2 handles[0]! 1)
  for (offset,value) in #[((2400 : UInt64),handles[0]!),(2480,handles[1]!),(2488,handles[2]!),(2496,handles[3]!),
      (2504,4),(2512,stackPA),(2408,stackPA+16368)] do r.modify fun t => put t (address+offset) value
  r.modify fun t => put (put t stackPA Loader.stackCanary) (stackPA+16376) Loader.stackCanary
  discard <| success r Task.init
  let record ← success r Task.table
  r.modify fun t => put (put (put t record descriptor) (record+8) Task.running) (record+80) 19
  let translation := word (← r.get) (address+72)
  r.modify fun t => put t (address+2048+272) translation
  pure (reset (← r.get),descriptor,address,record)

def check (expanded : Bool) : IO Unit := do
  let (snapshot,descriptor,address,record) ← setup expanded
  let validation ← IO.mkRef snapshot
  discard <| success validation (AddressSpace.base descriptor)
  let block := (← validation.get).requests
  let (before,after) ← compare snapshot descriptor
  require (before = after+3*block.size) "exact three complete scans removed"
  let run ← IO.mkRef snapshot
  let result ← execute run (originalSchedulerEntry descriptor 123)
  require (result.1 = 0 && result.2 = 1) "genuine entry positive did not return fixture reason1"
  let trace := (← run.get).requests
  let reads := (trace.filter fun r => r.op = .physicalRead64).map (·.address) |>.toList.eraseDups.toArray
  let writes := (trace.filter fun r => r.op = .physicalWrite64).map (·.address) |>.toList.eraseDups.toArray
  for addr in reads do
    for status in #[7,8,9,95,255] do discard <| compare {snapshot with failRead := some addr,failure := status} descriptor
    discard <| compare {snapshot with failRead := some addr,globalFault := true} descriptor
  for addr in writes do
    for status in #[7,8,9,95,255] do discard <| compare {snapshot with failWrite := some addr,failure := status} descriptor
    discard <| compare {snapshot with failWrite := some addr,globalFault := true} descriptor
  for addr in reads do
    discard <| compare (put snapshot addr (word snapshot addr ^^^ 1)) descriptor
  for state in #[0,1,2,4,5,6,7] do discard <| compare (put snapshot (record+8) state) descriptor
  for descriptor in #[0,descriptor+8192,0xffffffffffffffff] do discard <| compare snapshot descriptor
  for reason in #[0,1,2,3,4,5,6,7] do discard <| compare {snapshot with enterReason := reason} descriptor
  for status in #[7,8,9,95,255] do discard <| compare {snapshot with enterStatus := status} descriptor
  require (block.all fun req => req.address != address+2048 && req.address != address+2312 && req.address != address+2328)
    "context writes alias descriptor authority"
  IO.println s!"TASK_ENTRY_BORROW:PASS expanded{expanded} original{before}/successor{after}/scan{block.size}; reads{reads.size}/writes{writes.size}; exact immutable-fault/corruption/writeprefix/global-fault and entry-status/reason gates"
end TaskEntryBorrowFixture

def main : IO Unit := do
  TaskEntryBorrowFixture.check false
  TaskEntryBorrowFixture.check true
  IO.println "No transient-only duplicate-read fault equivalence or target/CPU performance claim"
