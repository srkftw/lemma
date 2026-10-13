import Lemma.Kernel.Memory.AddressSpace
import Lemma.Compiler.CFGLower

/-! Independent historical full-registry callback and exact fault traces.
The observation alias refers to the actual imported private declaration.
No fixture or host interpreter enters the target image. -/
open Lean Elab Command
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p =>
    p.1.toString.endsWith "AddressSpace.validateRegistryStep"
  unless candidates.length = 1 do throwError "expected exactly one maintained validateRegistryStep"
  let n := mkIdent candidates.head!.1
  elabCommand (← `(def $(mkIdent `observedRegistryStep) (i count : UInt32)
      (packed address owner first group : UInt64) : Lemma.Core0.Memory.Action :=
      $n i count packed address owner first group))

namespace RegistryLocalReference
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Kernel.Memory.AddressSpace
def readSlot (address offset : UInt64) : Action := Access.read64 (address+offset)
def packedMember (packed amount index : UInt64) : Bool :=
  if 0 < amount then
    if packed &&& 8191 = index then true else
    if 1 < amount then
      if (packed >>> 13) &&& 8191 = index then true else
      if 2 < amount then
        if (packed >>> 26) &&& 8191 = index then true else
        if 3 < amount then
          if (packed >>> 39) &&& 8191 = index then true else false
        else false
      else false
    else false
  else false

def before (i _ : UInt32) (packed address owner first group : UInt64) : Action :=
  let ordinal := group + i.toUInt64
  .bind (readSlot address (registryList + ordinal * 16)) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose owner handle 1) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (readSlot address (registryList + ordinal * 16 + 8)) fun s recorded =>
  if failed s = true then .done s 0 else
  if (if physical = recorded then false else true) = true then .done invalidDescriptor 0 else
  let index := (physical - Frames.pool) / Frames.bytes
  if 8192 ≤ index then .done invalidDescriptor 0 else
  if (if group = 4 then packedMember first 4 index else false) = true then .done invalidDescriptor 0 else
  if packedMember packed i.toUInt64 index = true then .done invalidDescriptor 0 else
  -- The exact owner/generation/purpose and recorded physical address have just
  -- been checked. Prior entries are immutable in this S critical section;
  -- inspect pins here and carry only the bounded index in the local pack.
  .bind (Access.read64 (Frames.record index + 16)) fun s pins =>
  if failed s = true then .done s 0 else
  if pins = 0 then .done 0 (packed ||| (index <<< (i.toUInt64 * 13)))
  else .done invalidDescriptor 0

end RegistryLocalReference
namespace RegistryLocalFaults
open Lemma.Core0.Memory
structure Request where
  address : UInt64
  status : UInt8
  value : UInt64
  deriving BEq
structure State where
  amount : UInt64 := 8192
  cursor : UInt64 := 0
  handle : UInt64 := 0
  actualOwner : UInt64 := 2
  generation : UInt64 := 1
  purpose : UInt64 := 1
  recorded : UInt64 := 0
  record : UInt64 := 0
  pins : UInt64 := 0
  requests : Array Request := #[]
  failAt : Nat := 7
  failure : UInt8 := 7

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message

def boundary (address : UInt64) : UInt8 :=
  if address % 8 = 0 then
    if 0x80200000 ≤ address && address ≤ 0x802ffff8 then 0 else
    if 0x80400000 ≤ address && address ≤ 0x804ffff8 then 0 else
    if 0x80500000 ≤ address && address ≤ 0x8050fff8 then 0 else
    if 0x80600000 ≤ address && address ≤ 0x806ffff8 then 0 else
    if 0x82000000 ≤ address && address ≤ 0x83fffff8 then 0 else
    if 0x87e00000 ≤ address && address ≤ 0x87fffff8 then 0 else 7
  else 8

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .platform op address _ _ _ _ _ next =>
    require (op = .physicalRead64) "unexpected registry primitive"
    let old ← state.get
    let value := if address = 0x804006a0 then old.amount
      else if address = old.cursor then old.handle
      else if address = old.cursor+8 then old.recorded
      else if address = old.record then old.actualOwner
      else if address = old.record+24 then old.generation
      else if address = old.record+8 then old.purpose
      else if address = old.record+16 then old.pins else 0
    let mut status := boundary address
    if status = 0 && old.requests.size = old.failAt then status := old.failure
    state.set {old with requests := old.requests.push ⟨address,status,(if status=0 then value else 0)⟩}
    execute state (next status (if status = 0 then value else 0))
  | _ => throw <| IO.userError "unexpected registry Action"

def compare (address : UInt64) (i : UInt32) (packed owner first group : UInt64)
    (initial : State) : IO Unit := do
  let initial := {initial with cursor := address+1424+(group+i.toUInt64)*16, record := 0x80401000+(initial.handle%initial.amount)*32}
  let a ← IO.mkRef initial
  let b ← IO.mkRef initial
  let ra ← execute a (RegistryLocalReference.before i 4 packed address owner first group)
  let rb ← execute b (observedRegistryStep i 4 packed address owner first group)
  require (ra = rb && (← a.get).requests == (← b.get).requests)
    "registry changed owner/generation/purpose/pins/duplicate priority or exact read prefix"

run_cmd do
  liftIO do
    for amount in #[512,1024,8192] do
      for index in [:amount.toNat] do
        let initial : State := {amount,handle:=amount+index.toUInt64,recorded:=0x82000000+index.toUInt64*4096}
        for position in [:8] do
          compare 0x82300000 0 0 2 0 0 {initial with failAt:=position}
    for address in #[0,0x801ffff8,0x80200000,0x802ff000,0x80400000,0x804ff000,
        0x80500000,0x8050f000,0x80600000,0x806ff000,0x81ffffff,0x82000000,
        0x82000001,0x82000008,0x83fff000,0x83fff008,0x83fffff8,0x84000000,
        0x87e00000,0x87fff000,0xfffffffffffff000,0xfffffffffffffff8,0xffffffffffffffff] do
      for i in #[0,1,3,4,7,8,0xffffffff] do
        for group in #[0,4,8,0xfffffffffffffffc,0xffffffffffffffff] do
          for position in [:8] do
            compare address i 0 2 0 group {handle:=8234,recorded:=0x8202a000,failAt:=position}
    for index in (#[0,1,42,8191] : Array UInt64) do
      for i in (#[0,1,2,3,4,0xffffffff] : Array UInt32) do
        for group in #[0,4] do
          for p in [:4] do
            let duplicate := index <<< (p.toUInt64*13)
            for packed in #[0,duplicate] do
              for first in #[0,duplicate] do
                for position in [:8] do
                  compare 0x82300000 i packed 2 first group
                    {handle:=8192+index,recorded:=0x82000000+index*4096,failAt:=position}
    for owner in #[0,1,2,64,0xfffffffffffffffe,0xffffffffffffffff] do
      for actualOwner in #[0,1,2,0xffffffffffffffff] do
        for generation in #[0,1,2,0xffffffffffffffff] do
          for purpose in #[0,1,2,5,0xffffffffffffffff] do
            for pins in #[0,1,0xffffffffffffffff] do
              for recorded in #[0,0x8202a000,0x8202a008,0xffffffffffffffff] do
                compare 0x82300000 0 0 owner 0 0
                  {handle:=8234,actualOwner,generation,purpose,pins,recorded}
    for amount in #[0,1,511,513,8191,8193,0xffffffffffffffff] do
      compare 0x82300000 0 0 2 0 0 {amount,handle:=8234,recorded:=0x8202a000}
    for status in [:256] do
      for position in [:8] do
        compare 0x82300000 3 0 2 0 4
          {handle:=8234,recorded:=0x8202a000,failAt:=position,failure:=status.toUInt8}
    IO.println "REGISTRY_LOCAL_FAULTS:PASS every9728 index, descriptor/ordinal/wrap, owner/generation/purpose/pin/dedup and allstatus/error read prefixes"
end RegistryLocalFaults

open Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_4
      #[`observedRegistryStep, `RegistryLocalReference.before] with
    | .ok s => pure s | .error e => throwError e.render
  let lowered ← match lowerActionSuiteExecution .kernel_v0_4 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineLiteralConstants := true, inlinePrimitiveWrappers := true, symbolPrefix := "registry_local_" } with
    | .ok s => pure s | .error e => throwError e
  let module : LLVM.Module := { sourceName := "maintained complete locally bounded registry validation", functions := lowered.functions }
  match LLVM.validateModule module with
    | .ok () => pure () | .error e => throwError e
  let some directory ← liftIO <| IO.getEnv "LEMMA_REGISTRY_LOCAL_OUT" | throwError "fresh output required"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite registry fixture"
  liftIO <| IO.FS.createDirAll path
  liftIO <| IO.FS.writeFile (path / "program.ll") module.render
  liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  logInfo "REGISTRY_LOCAL_COMPILE:PASS maintained genuine checked LLVM"
