import Lemma.Kernel.Memory.AddressSpace
import Lemma.Compiler.CFGLower

/-! Independent historical request references for the maintained frame and row
lookups. The host interpreter observes exact reads/status/result/error prefixes;
it is not linked into RV64. The row alias names the actual imported private
declaration, rather than copying the optimized implementation. -/
open Lean Elab Command
run_cmd do
  let candidates := (← getEnv).constants.toList.filter fun p =>
    p.1.toString.endsWith "AddressSpace.findRowBlockStep"
  unless candidates.length = 1 do throwError "expected exactly one maintained findRowBlockStep"
  let n := mkIdent candidates.head!.1
  elabCommand (← `(def $(mkIdent `observedRowBlockStep) (i count : UInt32)
      (acc physical wanted start context : UInt64) : Lemma.Core0.Memory.Action :=
      $n i count acc physical wanted start context))

namespace ResolveLocalReference
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
open Lemma.Kernel.Memory.Frames
def before (owner handle : UInt64) : Action :=
  .bind runtimeCount fun s count =>
  if failed s = true then .done s 0 else
  if (if ownerValid owner = true then if 0 < handle / count then true else false else false) = false then .done invalidFrame 0 else
  if resolveValid owner handle = false then .done invalidFrame 0 else
  let index := handle % count
  .bind (Access.read64 (record index)) fun s liveOwner =>
  if failed s = true then .done s 0 else
  if (if liveOwner = owner then false else true) = true then .done notOwned 0 else
  .bind (Access.read64 (record index + 24)) fun s generation =>
  if failed s = true then .done s 0 else
  if (if generation = handle / count then false else true) = true then .done notOwned 0 else
  .done 0 (address index)

end ResolveLocalReference

namespace RowLocalReference
open Lemma.Core0.Memory
open Lemma.Kernel.Memory
def before (i _ : UInt32) (acc physical wanted start _ : UInt64) : Action :=
  let offset := i.toUInt64 * 8
  .bind (Access.read64 (physical + (offset + 0) * 32)) fun s va0 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va0 = wanted then if acc = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found0 := if va0 = wanted then start + offset + 0 + 1 else acc
  .bind (Access.read64 (physical + (offset + 1) * 32)) fun s va1 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va1 = wanted then if found0 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found1 := if va1 = wanted then start + offset + 1 + 1 else found0
  .bind (Access.read64 (physical + (offset + 2) * 32)) fun s va2 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va2 = wanted then if found1 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found2 := if va2 = wanted then start + offset + 2 + 1 else found1
  .bind (Access.read64 (physical + (offset + 3) * 32)) fun s va3 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va3 = wanted then if found2 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found3 := if va3 = wanted then start + offset + 3 + 1 else found2
  .bind (Access.read64 (physical + (offset + 4) * 32)) fun s va4 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va4 = wanted then if found3 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found4 := if va4 = wanted then start + offset + 4 + 1 else found3
  .bind (Access.read64 (physical + (offset + 5) * 32)) fun s va5 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va5 = wanted then if found4 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found5 := if va5 = wanted then start + offset + 5 + 1 else found4
  .bind (Access.read64 (physical + (offset + 6) * 32)) fun s va6 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va6 = wanted then if found5 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found6 := if va6 = wanted then start + offset + 6 + 1 else found5
  .bind (Access.read64 (physical + (offset + 7) * 32)) fun s va7 =>
  if Lemma.Kernel.Memory.AddressSpace.failed s = true then .done s 0 else
  if (if va7 = wanted then if found6 = 0 then false else true else false) = true then
    .done Lemma.Kernel.Memory.AddressSpace.invalidDescriptor 0 else
  let found7 := if va7 = wanted then start + offset + 7 + 1 else found6
  .done 0 found7

end RowLocalReference

namespace ResolveLocalFaults
open Lemma.Core0.Memory
structure Request where
  address : UInt64
  status : UInt8
  value : UInt64
  deriving BEq
structure State where
  amount : UInt64 := 8192
  liveOwner : UInt64 := 2
  generation : UInt64 := 1
  requests : Array Request := #[]
  failAt : Nat := 3
  failure : UInt8 := 7

def require (ok : Bool) (message : String) : IO Unit :=
  if ok then pure () else throw <| IO.userError message

partial def execute (state : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next =>
    let (s,v) ← execute state first
    execute state (next s v)
  | .platform op address _ _ _ _ _ next =>
    require (op = .physicalRead64 && address % 8 = 0) "unexpected resolution primitive/alignment"
    let old ← state.get
    require (0x80400000 ≤ address && address ≤ 0x804ffff8) "resolution outside metadata"
    let v := if address = 0x804006a0 then old.amount
      else if (address-0x80401000)%32 = 0 then old.liveOwner else
      if (address-0x80401000)%32 = 24 then old.generation else 0
    let status : UInt8 := if old.requests.size = old.failAt then old.failure else 0
    state.set {old with requests := old.requests.push ⟨address,status,(if status=0 then v else 0)⟩}
    execute state (next status (if status = 0 then v else 0))
  | _ => throw <| IO.userError "unexpected resolution Action"

def compare (amount owner handle liveOwner generation : UInt64) (position : Nat) (failure : UInt8) : IO Unit := do
  let a ← IO.mkRef ({amount,liveOwner,generation,failAt:=position,failure} : State)
  let b ← IO.mkRef ({amount,liveOwner,generation,failAt:=position,failure} : State)
  let ra ← execute a (ResolveLocalReference.before owner handle)
  let rb ← execute b (Lemma.Kernel.Memory.Frames.resolve owner handle)
  require (ra = rb && (← a.get).requests == (← b.get).requests)
    "resolution changed status/value/read address/error prefix"

run_cmd do
  liftIO do
    for amount in #[512,1024,8192] do
      -- Complete finite admitted index domain, pointer calculation and each first failure.
      for i in [:amount.toNat] do
        for position in [:4] do
          compare amount 2 (amount+i.toUInt64) 2 1 position 7
      for handle in #[0,1,amount-1,amount,amount+1,2*amount-1,2*amount,0xffffffffffffffff] do
        for owner in #[0,1,2,64,0xfffffffffffffffe,0xffffffffffffffff] do
          for liveOwner in #[0,1,2,0xffffffffffffffff] do
            for generation in #[0,1,2,0xffffffffffffffff] do
              for position in [:4] do
                compare amount owner handle liveOwner generation position 255
    for amount in #[0,1,511,513,8191,8193,0xffffffffffffffff] do
      for position in [:4] do compare amount 2 8192 2 1 position 7
    for status in [:256] do
      for position in [:4] do compare 8192 2 8192 2 1 position status.toUInt8
    IO.println "RESOLVE_LOCAL_FAULTS:PASS all9728 admitted indices, config/owner/generation/handle edges and all256 read-error statuses; exact read prefixes"
end ResolveLocalFaults

namespace RowLocalFaults
open Lemma.Core0.Memory
structure Request where
  address : UInt64
  status : UInt8
  value : UInt64
  deriving BEq
structure State where
  cursor : UInt64
  mask : UInt64 := 0
  requests : Array Request := #[]
  failAt : Nat := 8
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
    require (op = .physicalRead64) "unexpected row scan primitive"
    let old ← state.get
    let index := (address-old.cursor)/32
    require (index < 8) "row scan read outside eight source rows"
    let v : UInt64 := if old.mask &&& (1 <<< index) = 0 then 0x80000 else 0x81000
    let mut status := boundary address
    if status = 0 && old.requests.size = old.failAt then status := old.failure
    state.set {old with requests := old.requests.push ⟨address,status,(if status=0 then v else 0)⟩}
    execute state (next status (if status = 0 then v else 0))
  | _ => throw <| IO.userError "unexpected row scan Action"

def compare (physical : UInt64) (index : UInt32) (acc start mask : UInt64) (position : Nat) (failure : UInt8) : IO Unit := do
  let cursor := physical+index.toUInt64*256
  let a ← IO.mkRef ({cursor,mask,failAt:=position,failure} : State)
  let b ← IO.mkRef ({cursor,mask,failAt:=position,failure} : State)
  let ra ← execute a (RowLocalReference.before index 16 acc physical 0x81000 start 0)
  let rb ← execute b (observedRowBlockStep index 16 acc physical 0x81000 start 0)
  require (ra = rb && (← a.get).requests == (← b.get).requests)
    "row scan changed duplicate/read-error priority, value, or exact read prefix"

run_cmd do
  liftIO do
    -- Every pattern of the eight source VA equality tests, including duplicates.
    for mask in [:256] do
      for acc in #[0,1,0xffffffffffffffff] do
        for position in [:9] do compare 0x82000000 9 acc 128 mask.toUInt64 position 7
    for physical in #[0,0x801ffff8,0x80200000,0x802fff18,0x802ffff8,0x80400000,
        0x804fff18,0x804ffff8,0x80500000,0x8050ff18,0x8050fff8,0x80600000,
        0x806fff18,0x806ffff8,0x81fffff8,0x82000000,0x82000001,0x83ffff18,
        0x83ffff20,0x83fffff8,0x84000000,0x87e00000,0x87ffff18,0x87fffff8,
        0xffffffffffffff18,0xfffffffffffffff8,0xffffffffffffffff] do
      for index in #[0,1,15,16,0xffffffff] do
        for start in #[0,128,0xffffffffffffffff] do
          for mask in #[0,1,3,128,255] do
            for position in [:9] do compare physical index 0 start mask position 255
    for status in [:256] do
      for position in [:9] do compare 0x83fff000 15 0 0 0 position status.toUInt8
    IO.println "ROW_LOCAL_FAULTS:PASS all256 duplicate patterns/priority, all256 read statuses, boundaries/wrap/indices; exact read/result prefixes"
end RowLocalFaults

open Lemma.Core0 Lemma.Compiler
run_cmd do
  let suite ← match checkAndLowerActionSuiteForProfile (← getEnv) .kernel_v0_4
      #[`Lemma.Kernel.Memory.Frames.resolve, `observedRowBlockStep,
        `ResolveLocalReference.before, `RowLocalReference.before] with
    | .ok s => pure s | .error e => throwError e.render
  let lowered ← match lowerActionSuiteExecution .kernel_v0_4 suite {
      preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),
      inlineLiteralConstants := true, inlinePrimitiveWrappers := true, symbolPrefix := "local_lookup_" } with
    | .ok s => pure s | .error e => throwError e
  let module : LLVM.Module := { sourceName := "maintained source-local checked lookups", functions := lowered.functions }
  match LLVM.validateModule module with
    | .ok () => pure () | .error e => throwError e
  let some directory ← liftIO <| IO.getEnv "LEMMA_LOCAL_LOOKUP_OUT" | throwError "fresh output required"
  let path := System.FilePath.mk directory
  if ← liftIO path.pathExists then throwError "refusing to overwrite lookup fixture"
  liftIO <| IO.FS.createDirAll path
  liftIO <| IO.FS.writeFile (path / "program.ll") module.render
  liftIO <| IO.FS.writeFile (path / "symbols.txt") lowered.renderSymbolManifest
  logInfo "LOCAL_LOOKUP_COMPILE:PASS maintained genuine checked LLVM"
