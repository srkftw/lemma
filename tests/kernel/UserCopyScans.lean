import Lemma.Kernel.Memory.UserCopy
import Lemma.Drivers.VirtIOBlock
import Lean.Elab.Command
import Std.Data.HashMap

/-! Independent finite byte RAM interpreting the production Actions. Literal
registry mutations probe duplicate/error ordering at eight-row and page cuts.
The bounded work observations count actual callbacks/accesses, not RV64 cycles. -/
namespace UserCopyScanFixture
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.User

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  reads : Array UInt64 := #[]
  writes : Nat := 0
  callbacks : Nat := 0
  operations : Nat := 0
  failRead : Option UInt64 := none

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
    if op == .installSatp then execute state (next 0 0)
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

def rowAddress (s : State) (address : UInt64) (expanded : Bool) (index : Nat) : UInt64 :=
  if expanded then word s (address + 1432 + (index / 128).toUInt64 * 16) + (index % 128).toUInt64 * 32
  else address + 384 + index.toUInt64 * 32

def reset (s : State) : State :=
  { s with reads := #[], callbacks := 0, writes := 0, operations := 0, failRead := none }

def expectNoWrite (state : IO.Ref State) (expected : UInt8) (action : Action) : IO Unit := do
  let before ← state.get
  let (status,_) ← execute state action
  require (status == expected) s!"expected{expected}, got{status}"
  require ((← state.get).words == before.words && (← state.get).writes == before.writes)
    "failed preflight changed RAM"

/-- Additional rows intentionally contain only independently constructed VA
words: lookup must read every live VA to find duplicates before inspecting the
selected exact grant/PTE. This isolates the scan without using 1024 target
allocations to manufacture a work-count oracle. -/
def populated (saved : State) (address : UInt64) (expanded : Bool) (amount : Nat) : State := Id.run do
  let mut s := put saved (address + 48) amount.toUInt64
  for i in [2:amount] do
    s := put s (rowAddress saved address expanded i) (0x800000 + i.toUInt64 * 4096)
  return reset s

def checkDirectory (amount : UInt64) : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure amount (if amount = 1024 then 128 else 8192) 4)
  discard <| success state Frames.init
  -- A real purpose1 owner2 grant at index0 exercises zero as a valid packed
  -- index. Its placement before descriptor construction keeps that descriptor
  -- in a separate owner1 frame. All eight selected grants remain real/live.
  let spare ← success state (Frames.allocate 2 1)
  let sparePA ← success state (Frames.resolvePurpose 2 spare 1)
  require (sparePA == 0x82000000) "literal index-zero fixture"
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  state.modify fun s => put (put s (address + 1424) spare) (address + 1432) sparePA
  let saved := reset (← state.get)
  state.set saved
  require ((← success state (AddressSpace.base descriptor)) == address) "zero-index directory validation"
  let valid ← state.get
  require (valid.callbacks == 8) "directory validation must have eight current-entry callbacks"
  for i in [:8] do
    require (valid.reads.toList.count (address + 1432 + i.toUInt64 * 16) == 1)
      "previous validated directory physical address was reread"
    for j in [i+1:8] do
      let changed := put (put saved (address + 1424 + j.toUInt64 * 16)
        (word saved (address + 1424 + i.toUInt64 * 16)))
        (address + 1432 + j.toUInt64 * 16) (word saved (address + 1432 + i.toUInt64 * 16))
      state.set changed
      expectNoWrite state AddressSpace.invalidDescriptor (AddressSpace.base descriptor)
      -- Distinctness rejects the second alias before rereading its pins.
      -- A failure at this physical pin address would occur at the earlier
      -- entry instead, and must retain that earlier necessary-read priority.
      -- The current recordedPA read still precedes distinctness.
      let pa := word changed (address + 1432 + j.toUInt64 * 16)
      let record := 0x80401000 + (pa - 0x82000000) / 4096 * 32
      require ((← state.get).reads.toList.count (record + 16) == 1)
        "duplicate alias reread pins after distinctness rejection"
      state.set { changed with failRead := some (record + 16) }
      expectNoWrite state 95 (AddressSpace.base descriptor)
      state.set { changed with failRead := some (address + 1432 + j.toUInt64 * 16) }
      expectNoWrite state 95 (AddressSpace.base descriptor)
  -- Literal highest admitted index exercises every bit in a 13-bit field.
  -- The finite RAM ownership tuple is independently populated, then the real
  -- resolver checks its exact generation/owner/purpose and recorded address.
  let highIndex := amount - 1
  let highRecord : UInt64 := 0x80401000 + highIndex * 32
  let high := put (put (put (put saved highRecord 2) (highRecord + 8) 1)
    (highRecord + 16) 0) (highRecord + 24) 1
  state.set (put (put high (address + 1472) (amount + highIndex))
    (address + 1480) (0x82000000 + highIndex * 4096))
  require ((← success state (AddressSpace.base descriptor)) == address) "highest13-bit directory index"
  for i in [:8] do
    let handleSlot := address + 1424 + i.toUInt64 * 16
    let physicalSlot := handleSlot + 8
    let handle := word saved handleSlot
    let physical := word saved physicalSlot
    let record := 0x80401000 + (physical - 0x82000000) / 4096 * 32
    for (location,value,expected) in #[(handleSlot,0,Frames.invalidFrame),
        (handleSlot,handle + amount,Frames.notOwned),
        (record,0,Frames.notOwned),(record,3,Frames.notOwned),
        (record + 24,0,Frames.notOwned),(record + 24,2,Frames.notOwned),
        (record + 8,0,Frames.purposeDenied),(record + 8,2,Frames.purposeDenied),
        (record + 16,1,AddressSpace.invalidDescriptor),
        (physicalSlot,physical + 1,AddressSpace.invalidDescriptor),
        (physicalSlot,physical + 4096,AddressSpace.invalidDescriptor),
        (physicalSlot,0x84000000,AddressSpace.invalidDescriptor),
        (physicalSlot,0,AddressSpace.invalidDescriptor)] do
      state.set (put saved location value)
      expectNoWrite state expected (AddressSpace.base descriptor)
    for location in #[handleSlot,record,record + 24,record + 8,physicalSlot,record + 16] do
      state.set { saved with failRead := some location }
      expectNoWrite state 95 (AddressSpace.base descriptor)
  IO.println s!"DIRECTORY_PACK_WORK frames{amount} entries8 callbacks{valid.callbacks} reads64{valid.reads.size} physical-reads8"
  IO.println "DIRECTORY_PACK:PASS all28duplicatepairs index0 ownership generation purpose exact-PA alignment bounds pins necessary-read-failure priority no-writes"

def check (expanded : Bool) : IO Unit := do
  let state ← IO.mkRef ({} : State)
  discard <| success state (Frames.configure (if expanded then 8192 else 512)
    (if expanded then 8192 else 32) 4)
  discard <| success state Frames.init
  let descriptor ← success state (AddressSpace.create 2)
  let address ← success state (AddressSpace.base descriptor)
  let scratch ← success state (Frames.allocate 1 1)
  let scratchPA ← success state (Frames.resolvePurpose 1 scratch 1)
  let first ← success state (Frames.allocate 2 4)
  discard <| success state (Frames.allocate 3 4)
  let second ← success state (Frames.allocate 2 4)
  let firstPA ← success state (Frames.resolve 2 first)
  let secondPA ← success state (Frames.resolve 2 second)
  discard <| success state (AddressSpace.mapUser descriptor 0x40000 first 3)
  discard <| success state (AddressSpace.mapUser descriptor 0x41000 second 3)
  for i in [:4096] do
    state.modify fun s => putByte s (scratchPA + i.toUInt64) ((i.toUInt64 * 13 + 19) % 256)
  let saved ← state.get
  -- The ordinary block path uses this exact owner-1 purpose-1 frame, then
  -- passes only its checked payload span to the device. A user grant or an
  -- unrelated physical address must never replace that DMA frame.
  let blockState := put (put saved 0x80400a00 scratch) 0x80400a08 scratchPA
  state.set (reset blockState)
  require ((← success state Lemma.Drivers.VirtIOBlock.bounce) == scratchPA + 0x600)
    "owned block bounce address"
  require ((← success state (UserCopy.copyFromUser descriptor 0x40080 scratch 0x600 512)) == 512)
    "ordinary authorized block payload copy"
  let payload ← state.get
  for i in [:4096] do
    require (byte payload (scratchPA + i.toUInt64) ==
      (if 0x600 ≤ i && i < 0x800 then byte saved (firstPA + 0x80 + i.toUInt64 - 0x600)
        else byte saved (scratchPA + i.toUInt64))) "copy escaped 512-byte block payload"
  for (slot,value,expected) in #[(0x80400a00,first,Frames.notOwned),
      (0x80400a00,scratch + (if expanded then 8192 else 512),Frames.notOwned),
      (0x80400a08,firstPA,Lemma.Drivers.VirtIOBlock.corruptCompletion),
      (0x80400a28,1,Lemma.Drivers.VirtIOBlock.busy),
      (0x80400a38,1,Lemma.Drivers.VirtIOBlock.poisoned)] do
    state.set (reset (put blockState slot value))
    expectNoWrite state expected Lemma.Drivers.VirtIOBlock.bounce
  state.set (reset saved)
  expectNoWrite state ABI.kernelFatal (UserCopy.copyFromUser descriptor 0x40000 first 0x600 512)
  IO.println s!"BLOCK_BOUNCE_BOUNDARY:PASS expanded={expanded} exact-owner-generation payload512 pending poison no-user-DMA-handle no-writes-on-rejection"
  let amounts := if expanded then #[2,7,8,9,127,128,129,257,1024] else #[2,7,8,9,31,32]
  for amount in amounts do
    state.set (populated saved address expanded amount)
    require ((← success state (AddressSpace.lookup descriptor 0x40011 1)) == firstPA + 17)
      "literal selected alias"
    let after ← state.get
    let expectedRows := (List.range amount).map fun i => rowAddress saved address expanded i
    let actualRows := after.reads.toList.filter fun a => expectedRows.contains a
    require (actualRows == expectedRows) s!"scan skipped, repeated or reordered live VA rows amount{amount}"
    -- Every full eight-row callback replaces eight one-row callbacks; directory
    -- uniqueness/table membership folds add a fixed bounded overhead ≤64.
    require (after.callbacks ≤ amount / 8 + amount % 8 + (amount + 127) / 128 + 64)
      s!"one callback per VA remains amount{amount} callbacks{after.callbacks}"
    for index in #[1,7,8,127,128,amount - 1] do
      if index < amount then
        let base := populated saved address expanded amount
        state.set (put base (rowAddress saved address expanded index) 0x40000)
        expectNoWrite state AddressSpace.invalidDescriptor (AddressSpace.lookup descriptor 0x40000 1)
        -- A duplicate earlier in scan retains priority over a later failed read.
        if index + 1 < amount then
          state.modify fun s => { s with failRead := some (rowAddress saved address expanded (index + 1)) }
          expectNoWrite state AddressSpace.invalidDescriptor (AddressSpace.lookup descriptor 0x40000 1)
        state.set { base with failRead := some (rowAddress saved address expanded index) }
        expectNoWrite state 95 (AddressSpace.lookup descriptor 0x40000 1)
    -- Missing mappings still read the entire live list, including exact tails.
    state.set (populated saved address expanded amount)
    expectNoWrite state AddressSpace.missingMapping (AddressSpace.lookup descriptor 0x600000 1)
  let amount := if expanded then 1024 else 32
  let base := populated saved address expanded amount
  state.set base
  require ((← success state (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)) == 4096)
    "preflighted two-page result"
  let copied ← state.get
  for i in [:4096] do
    let pa := if i < 2048 then firstPA + 2048 + i.toUInt64 else secondPA + i.toUInt64 - 2048
    require (byte copied pa == (i.toUInt64 * 13 + 19) % 256) "independent two-page payload bytes"
  require (copied.reads.toList.count (address + 0) == 1) "descriptor/directory revalidated for second leaf"
  require (copied.writes == 512) "copy write count or hidden metadata writes"
  IO.println s!"USER_COPY_SCAN_WORK expanded={expanded} rows={amount} callbacks={copied.callbacks} reads64={copied.reads.size} writes={copied.writes}"
  -- Fresh calls must revalidate directory/owner/generation/purpose and actual
  -- PTE, even after a previous successful copy: no alias cache across calls.
  let firstRecord := 0x80401000 + (first % (if expanded then 8192 else 512)) * 32
  let firstRow := rowAddress saved address expanded 0
  let secondRow := rowAddress saved address expanded 1
  for (location,value,expected) in #[(firstRecord,3,ABI.kernelFatal),
      (firstRecord + 24,2,ABI.kernelFatal),(firstRecord + 8,1,ABI.kernelFatal),
      (firstRow + 24,1,ABI.kernelFatal),(firstRow + 16,0,ABI.kernelFatal),
      (secondRow + 24,1,ABI.kernelFatal)] do
    state.set (put base location value)
    expectNoWrite state expected (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
  for location in #[address, firstRecord + 8, firstRow + 16, secondRow + 16] do
    state.set { base with failRead := some location }
    expectNoWrite state ABI.kernelFatal (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
  state.set (reset saved)
  discard <| success state (AddressSpace.unmap descriptor 0x41000)
  discard <| success state (AddressSpace.mapUser descriptor 0x41000 second 1)
  let readOnly ← state.get
  state.set (populated readOnly address expanded amount)
  expectNoWrite state ABI.permissionDenied (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
  -- Missing/read-only second leaf fails after first-page validation, but before
  -- any destination write; an invalid first address keeps priority over a bad
  -- descriptor and zero/oversize lengths need no descriptor reads.
  state.set (put base secondRow 0x42000)
  expectNoWrite state ABI.missingMapping (UserCopy.copyToUser descriptor 0x40800 scratch 0 4096)
  state.set (put base address 0)
  expectNoWrite state ABI.invalidRange (UserCopy.validateRead descriptor 0x100000 1)
  expectNoWrite state ABI.invalidArgument (UserCopy.validateRead descriptor 0x40000 4097)
  require ((← success state (UserCopy.copyFromUser 0 0 0 0 0)) == 0) "zero copy touched invalid handles"
  state.set base
  require ((← success state (UserCopy.validateWrite descriptor 0x40800 4096)) == 4096)
    "two-page validation"
  require ((← state.get).reads.toList.count address == 1) "validateWrite repeats descriptor validation"
  IO.println s!"USER_COPY_SCANS:PASS expanded={expanded} exactorderedrows block-page-tail duplicate readfault ownership generation purpose PTE permissions no-partial-write"
end UserCopyScanFixture

open Lean Elab Command
run_cmd do
  liftIO <| UserCopyScanFixture.checkDirectory 1024
  liftIO <| UserCopyScanFixture.checkDirectory 8192
  liftIO <| UserCopyScanFixture.check false
  liftIO <| UserCopyScanFixture.check true
