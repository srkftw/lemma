import tests.kernel.IPCCallBaseReuse

/-! Host-only exact effect regression for descriptor direct loads. The reference
is the immediately preceding complete base declaration, with its original
noinline read wrapper. Both run through the same finite physical-access model;
this file is not reachable from a target image. No read projection is allowed. -/
open Lean Elab Command
open Lemma.Core0.Memory Lemma.Kernel.Memory Lemma.Kernel Lemma.User
open CallBorrowFaults
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p => p.1.toString.endsWith "AddressSpace.validateRegistry"
  unless candidates.length = 1 do throwError "one genuine maintained registry validator required"
  let n := mkIdent candidates.head!.1
  let alias := mkIdent <| Name.mkSimple "registryBefore"
  elabCommand (← `(def $alias (a b c d : UInt64) : Action := $n a b c d))
namespace DescriptorDirectLoadsFixture
open Lemma.Kernel.Memory.AddressSpace
private def readBefore (address offset : UInt64) : Action := Access.read64 (address + offset)
def before (descriptor : UInt64) : Action :=
  .bind (Frames.resolvePurpose 1 descriptor 1) fun s address =>
  if failed s = true then .done s 0 else
  .bind (readBefore address 0) fun s tag =>
  if failed s = true then .done s 0 else
  if (if tag = magic then false else true) = true then .done invalidDescriptor 0 else
  .bind (readBefore address 8) fun s version =>
  if failed s = true then .done s 0 else
  if (if version = 1 then false else if version = 2 then false else if version = 3 then false else true) = true then .done invalidDescriptor 0 else
  .bind (readBefore address 16) fun s self =>
  if failed s = true then .done s 0 else
  if (if self = descriptor then false else true) = true then .done invalidDescriptor 0 else
  .bind (readBefore address 24) fun s owner =>
  if failed s = true then .done s 0 else
  if Frames.ownerValid owner = false then .done invalidDescriptor 0 else
  .bind (readBefore address 32) fun s state =>
  if failed s = true then .done s 0 else
  if (if state = 1 then false else true) = true then .done invalidDescriptor 0 else
  .bind (readBefore address 40) fun s tables =>
  if failed s = true then .done s 0 else
  if tables < (if version = 3 then 14 else 11) then .done invalidDescriptor 0 else
  if 32 < tables then .done invalidDescriptor 0 else
  .bind (readBefore address 48) fun s leaves =>
  if failed s = true then .done s 0 else
  .bind (readBefore address 80) fun s leafCapacity =>
  if failed s = true then .done s 0 else
  if leafCapacity < leaves then .done invalidDescriptor 0 else
  .bind (registryBefore address owner version leafCapacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (readBefore address 88) fun s tableCapacity =>
  if failed s = true then .done s 0 else
  if (if tableCapacity = (if version = 3 then 0x3353415000000020 else 32) then false else true) = true then .done invalidDescriptor 0 else
  .bind (readBefore address 56) fun s rootHandle =>
  if failed s = true then .done s 0 else
  .bind (readBefore address tableList) fun s firstHandle =>
  if failed s = true then .done s 0 else
  if (if rootHandle = firstHandle then false else true) = true then .done invalidDescriptor 0 else
  .bind (Frames.resolvePurpose owner rootHandle 2) fun s rootPA =>
  if failed s = true then .done s 0 else
  .bind (readBefore address 64) fun s recordedPA =>
  if failed s = true then .done s 0 else
  if (if recordedPA = rootPA then false else true) = true then .done invalidDescriptor 0 else
  .bind (readBefore address 72) fun s translation =>
  if failed s = true then .done s 0 else
  if translation = satpWord rootPA then .done 0 address else .done invalidDescriptor 0

def compare (snapshot : CallBorrowFaults.State) (descriptor : UInt64) : IO (Array Request) := do
  let old ← IO.mkRef (reset snapshot)
  let fresh ← IO.mkRef (reset snapshot)
  -- Retain the declared persistent fault in both copies.
  old.modify fun s => {s with failRead := snapshot.failRead, failWrite := snapshot.failWrite}
  fresh.modify fun s => {s with failRead := snapshot.failRead, failWrite := snapshot.failWrite}
  let a ← execute old (before descriptor)
  let b ← execute fresh (AddressSpace.base descriptor)
  let x ← old.get
  let y ← fresh.get
  require (a == b && x.words == y.words && x.requests == y.requests)
    s!"complete result/RAM/ordered physical effects differ {a} vs {b}"
  return x.requests

def check (count quota : UInt64) : IO Unit := do
  let ref ← IO.mkRef ({} : CallBorrowFaults.State)
  discard <| success ref (Frames.configure count quota 4)
  discard <| success ref Frames.init
  let descriptor ← success ref (AddressSpace.create 2)
  let address ← success ref (AddressSpace.base descriptor)
  let snapshot := reset (← ref.get)
  let baseline ← compare snapshot descriptor
  let addresses := baseline.foldl (fun a r => if a.contains r.address then a else a.push r.address) (#[] : Array UInt64)
  for slot in addresses do
    discard <| compare {snapshot with failRead := some slot} descriptor
  for (offset,value) in #[(0,0),(8,0),(8,4),(16,descriptor+count),(24,0),(32,0),
      (40,0),(40,33),(48,1025),(80,0),(88,0),(56,0),(128,0),(64,0),(72,0),(1408,9)] do
    discard <| compare (put snapshot (address+offset) value) descriptor
  for bad in #[0,descriptor+count,0xffffffffffffffff] do discard <| compare snapshot bad
  IO.println s!"DESCRIPTOR_DIRECT_LOADS:PASS pool{count} exact{baseline.size} effects, stable fault addresses{addresses.size},16 corrupted fields and3 invalid handles"
end DescriptorDirectLoadsFixture
#eval DescriptorDirectLoadsFixture.check 512 32
#eval DescriptorDirectLoadsFixture.check 1024 128
#eval DescriptorDirectLoadsFixture.check 8192 8192
