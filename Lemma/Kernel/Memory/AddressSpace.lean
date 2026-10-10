import Lemma.Kernel.Memory.Batch

/-! Single-hart Sv39 ownership. Every address space has independent 4 KiB
tables, ASID zero and conservative full invalidation. Algorithms and metadata
movement are compiled Lean Actions. The S-only pool map is a trusted RW/NX
management alias: the contract is user-PTE W^X, not strict global W^X.

Descriptors are generation-tagged owner-1 frames. Table frames belong to the
address-space owner, and U leaves retain exact generation handles. Publication
is last; destruction is forbidden while the root is tracked as installed.
The active-root word is trusted bookkeeping for the typed enter/return boundary,
not an instruction to activate a root before the caller SATP is saved.
-/
namespace Lemma.Kernel.Memory.AddressSpace
open Lemma.Core0.Memory
open Lemma.Kernel.Memory

def activeRoot : UInt64 := 0x80400600
def magic : UInt64 := 0x31534150414d454c
def tableList : UInt64 := 128
def leafList : UInt64 := 384
def capacity : UInt64 := 32
def registryCount : UInt64 := 1408
def registryList : UInt64 := 1424
def expandedCapacity : UInt64 := 1024
def userContextOffset : UInt64 := 2048
def invalidDescriptor : UInt8 := 70
def invalidAddress : UInt8 := 71
def invalidPermission : UInt8 := 72
def duplicateMapping : UInt8 := 73
def missingMapping : UInt8 := 74
def invalidPte : UInt8 := 75
def resourceLimit : UInt8 := 76
def activeAddressSpace : UInt8 := 77
def invariantFailure : UInt8 := 78

def satpWord (rootPA : UInt64) : UInt64 :=
  if rootPA = 0 then 0 else (0x8000000000000000 : UInt64) ||| (rootPA >>> 12)
def vpn0 (va : UInt64) : UInt64 := (va >>> 12) &&& 511
def vpn1 (va : UInt64) : UInt64 := (va >>> 21) &&& 511
def vpn2 (va : UInt64) : UInt64 := (va >>> 30) &&& 511
def page (va : UInt64) : UInt64 := va - va % 4096
def tableEntry (pa : UInt64) : UInt64 := (pa >>> 12) <<< 10 ||| 1
def leafEntry (pa permissions : UInt64) : UInt64 :=
  (pa >>> 12) <<< 10 ||| (0x51 : UInt64) ||| (permissions <<< 1) |||
    (if permissions &&& 2 = 2 then (0x80 : UInt64) else 0)
def ptePhysical (pte : UInt64) : UInt64 := (pte >>> 10) <<< 12
def tableSlot (table va : UInt64) : UInt64 := table + vpn0 va * 8
def failed (status : UInt8) : Bool := if status = 0 then false else true

def addressValid (va : UInt64) : Bool :=
  if 0x10000 ≤ va then
    if va < 0x40000000 then
      if page va = 0x10000000 then false else
      if page va = 0x00100000 then false else true
    else false
  else false
def alignedAddress (va : UInt64) : Bool :=
  if addressValid va = true then if va % 4096 = 0 then true else false else false
/-- Expanded User stacks have true unmapped neighboring leaves. Legacy
profiles retain their prior address checks and Loader-established guards. -/
def bindingAddressValid (va maximum : UInt64) : Bool :=
  if maximum = expandedCapacity then
    if page va = 0x3fff9000 then false else
    if page va = 0x3fffe000 then false else true
  else true
def permissionsValid (permissions : UInt64) : Bool :=
  if permissions = 1 then true else if permissions = 3 then true else if permissions = 5 then true else false
def requestValid (permission : UInt64) : Bool :=
  if permission = 1 then true else if permission = 2 then true else if permission = 4 then true else false
def purposePermits (purpose permissions : UInt64) : Bool :=
  if purpose = 3 then if permissions = 5 then true else false else
  if purpose = 4 then if permissions = 1 then true else if permissions = 3 then true else false else
  if purpose = 5 then if permissions = 3 then true else false else false
def tableShape (pte : UInt64) : Bool :=
  if pte >>> 54 = 0 then
    if pte &&& 0x3ff = 1 then Frames.frameAddressValid (ptePhysical pte) else false
  else false

/-- Caller updates this only immediately around the trusted typed transition.
Zero means the initial Bare supervisor environment. -/
def noteActive (rootPA : UInt64) : Action :=
  if rootPA = 0 then Access.write64 activeRoot 0 else
  if Frames.frameAddressValid rootPA = true then Access.write64 activeRoot rootPA
  else .done invalidAddress 0

def flushCurrent : Action :=
  .bind (Access.read64 activeRoot) fun s current =>
  if failed s = true then .done s 0 else
  if current = 0 then
    .platform .installSatp 0 0 0 0 0 0 fun s v => .done s v
  else if Frames.frameAddressValid current = true then
    .platform .installSatp (satpWord current) 0 0 0 0 0 fun s v => .done s v
  else .done invariantFailure 0

private def get (base slot : UInt64) : Action := Access.read64 (base + slot)
private def put (base slot value : UInt64) : Action := Access.write64 (base + slot) value

/-- The expanded registry has eight owned metadata pages, each with 128 rows.
Its directory is validated by `base`; it is never mapped with U permissions. -/
private def row (address index : UInt64) : Action :=
  .bind (get address 80) fun s amount => if failed s = true then .done s 0 else
  if amount = 32 then
    if index < 32 then .done 0 (address + leafList + index * 32)
    else .done resourceLimit 0
  else if amount = expandedCapacity then
    if index < expandedCapacity then
      .bind (get address (registryList + index / 128 * 16 + 8)) fun s physical =>
      if failed s = true then .done s 0 else
      if Frames.frameAddressValid physical = true then
        .done 0 (physical + index % 128 * 32)
      else .done invalidDescriptor 0
    else .done resourceLimit 0
  else .done invalidDescriptor 0

private def registryUniqueStep (i _ : UInt32) (acc address physical _ _ : UInt64) : Action :=
  .bind (get address (registryList + i.toUInt64 * 16 + 8)) fun s previous =>
  if failed s = true then .done s 0 else
  if previous = physical then .done invalidDescriptor 0 else .done 0 (acc + 1)

private def validateRegistryStep (i _ : UInt32) (acc address owner _ _ : UInt64) : Action :=
  .bind (get address (registryList + i.toUInt64 * 16)) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose owner handle 1) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (get address (registryList + i.toUInt64 * 16 + 8)) fun s recorded =>
  if failed s = true then .done s 0 else
  if (if physical = recorded then false else true) = true then .done invalidDescriptor 0 else
  .boundedFoldU64 8 registryUniqueStep i 0 address physical 0 0 fun s _ =>
  if failed s = true then .done s 0 else
  .bind (Frames.mappingCount owner handle) fun s pins =>
  if failed s = true then .done s 0 else
  if pins = 0 then .done 0 (acc + 1) else .done invalidDescriptor 0

private def validateRegistry (address owner version leafCapacity : UInt64) : Action :=
  .bind (get address registryCount) fun s amount => if failed s = true then .done s 0 else
  if version = 1 then
    if leafCapacity = 32 then
      if amount = 0 then
        .bind Frames.runtimeCount fun s frames => if failed s = true then .done s 0 else
        if frames = 512 then .done 0 0 else .done invalidDescriptor 0
      else .done invalidDescriptor 0
    else .done invalidDescriptor 0
  else if version = 2 then
    if leafCapacity = expandedCapacity then
      if amount = 8 then
        .bind Frames.runtimeCount fun s frames => if failed s = true then .done s 0 else
        if frames = 8192 then
          .boundedFoldU64 8 validateRegistryStep 8 0 address owner 0 0 fun s checked =>
          if failed s = true then .done s 0 else
          if checked = 8 then .done 0 0 else .done invalidDescriptor 0
        else .done invalidDescriptor 0
      else .done invalidDescriptor 0
    else .done invalidDescriptor 0
  else .done invalidDescriptor 0

/-- Reject stale descriptors, altered ABI fields, and a root which no longer
matches the live owned table frame. Loader state at +2400..+2559 is reserved. -/
def base (descriptor : UInt64) : Action :=
  .bind (Frames.resolvePurpose 1 descriptor 1) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get address 0) fun s tag =>
  if failed s = true then .done s 0 else
  if (if tag = magic then false else true) = true then .done invalidDescriptor 0 else
  .bind (get address 8) fun s version =>
  if failed s = true then .done s 0 else
  if (if version = 1 then false else if version = 2 then false else true) = true then .done invalidDescriptor 0 else
  .bind (get address 16) fun s self =>
  if failed s = true then .done s 0 else
  if (if self = descriptor then false else true) = true then .done invalidDescriptor 0 else
  .bind (get address 24) fun s owner =>
  if failed s = true then .done s 0 else
  if Frames.ownerValid owner = false then .done invalidDescriptor 0 else
  .bind (get address 32) fun s state =>
  if failed s = true then .done s 0 else
  if (if state = 1 then false else true) = true then .done invalidDescriptor 0 else
  .bind (get address 40) fun s tables =>
  if failed s = true then .done s 0 else
  if tables < 11 then .done invalidDescriptor 0 else
  if 32 < tables then .done invalidDescriptor 0 else
  .bind (get address 48) fun s leaves =>
  if failed s = true then .done s 0 else
  .bind (get address 80) fun s leafCapacity =>
  if failed s = true then .done s 0 else
  if leafCapacity < leaves then .done invalidDescriptor 0 else
  .bind (validateRegistry address owner version leafCapacity) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (get address 88) fun s tableCapacity =>
  if failed s = true then .done s 0 else
  if (if tableCapacity = 32 then false else true) = true then .done invalidDescriptor 0 else
  .bind (get address 56) fun s rootHandle =>
  if failed s = true then .done s 0 else
  .bind (get address tableList) fun s firstHandle =>
  if failed s = true then .done s 0 else
  if (if rootHandle = firstHandle then false else true) = true then .done invalidDescriptor 0 else
  .bind (Frames.resolvePurpose owner rootHandle 2) fun s rootPA =>
  if failed s = true then .done s 0 else
  .bind (get address 64) fun s recordedPA =>
  if failed s = true then .done s 0 else
  if (if recordedPA = rootPA then false else true) = true then .done invalidDescriptor 0 else
  .bind (get address 72) fun s translation =>
  if failed s = true then .done s 0 else
  if translation = satpWord rootPA then .done 0 address else .done invalidDescriptor 0

def owner (descriptor : UInt64) : Action :=
  .bind (base descriptor) fun s address =>
  if failed s = true then .done s 0 else get address 24
def root (descriptor : UInt64) : Action :=
  .bind (base descriptor) fun s address =>
  if failed s = true then .done s 0 else get address 64
def satp (descriptor : UInt64) : Action :=
  .bind (root descriptor) fun s address => .done s (satpWord address)
def context (descriptor : UInt64) : Action :=
  .bind (base descriptor) fun s address => .done s (address + userContextOffset)

private def tableAt (address index : UInt64) : Action :=
  if index < 32 then
    .bind (get address 24) fun s owner =>
    if failed s = true then .done s 0 else
    .bind (get address (tableList + index * 8)) fun s handle =>
    if failed s = true then .done s 0 else Frames.resolvePurpose owner handle 2
  else .done resourceLimit 0

private def memberStep (i _ : UInt32) (acc address wanted _ _ : UInt64) : Action :=
  if i < 8 then .done 0 acc else
    .bind (tableAt address i.toUInt64) fun s table =>
    if failed s = true then .done s 0 else
    .done 0 (if table = wanted then 1 else acc)
private def ownedTable (address table : UInt64) : Action :=
  .bind (get address 40) fun s amount =>
  if failed s = true then .done s 0 else
  if amount ≤ 32 then
    .boundedFoldU64 32 memberStep amount.toUInt32 0 address table 0 0 fun s found =>
    if failed s = true then .done s 0 else
    if found = 1 then .done 0 table else .done invalidPte 0
  else .done invalidDescriptor 0
private def child (address pte : UInt64) : Action :=
  if tableShape pte = true then ownedTable address (ptePhysical pte) else .done invalidPte 0

/-- Three levels only; intermediate leaves and arbitrary PFNs fail closed. -/
private def walkSlot (address va : UInt64) : Action :=
  .bind (tableAt address 0) fun s top =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (top + vpn2 va * 8)) fun s first =>
  if failed s = true then .done s 0 else
  .bind (tableAt address 7) fun s middle =>
  if failed s = true then .done s 0 else
  if (if first = tableEntry middle then false else true) = true then .done invalidPte 0 else
  .bind (Access.read64 (middle + vpn1 va * 8)) fun s second =>
  if failed s = true then .done s 0 else
  .bind (child address second) fun s bottom =>
  if failed s = true then .done s 0 else .done 0 (tableSlot bottom va)

private def link (address parentIndex entryIndex childIndex : UInt64) : Action :=
  if entryIndex < 512 then
    .bind (tableAt address parentIndex) fun s parent =>
    if failed s = true then .done s 0 else
    .bind (tableAt address childIndex) fun s target =>
    if failed s = true then .done s 0 else
    Access.write64 (parent + entryIndex * 8) (tableEntry target)
  else .done invalidAddress 0

private def fillStep (i _ : UInt32) (acc table physical flags _ : UInt64) : Action :=
  let address := physical + i.toUInt64 * 4096
  .bind (Access.write64 (tableSlot table address) ((address >>> 12) <<< 10 ||| flags)) fun s _ =>
  .done s acc
private def fillRange (address tableIndex physical amount flags : UInt64) : Action :=
  if amount ≤ 512 then
    .bind (tableAt address tableIndex) fun s table =>
    if failed s = true then .done s 0 else
    .boundedFoldU64 512 fillStep amount.toUInt32 0 table physical flags 0 fun s v => .done s v
  else .done resourceLimit 0

/-- Expanded pools share the same trusted S-only RW/NX alias limitation.
Each additional aligned 2 MiB leaf covers allocator-owned RAM only. No U bit
is set, and the historical 512-frame instance installs no extra leaf. -/
private def expandedPoolStep (i _ : UInt32) (acc middle _ _ _ : UInt64) : Action :=
  let physical := 0x82200000 + i.toUInt64 * 0x200000
  .bind (Access.write64 (middle + (17 + i.toUInt64) * 8)
    ((physical >>> 12) <<< 10 ||| (0xc7 : UInt64))) fun s _ => .done s (acc + 1)

private def mapExpandedPool (address : UInt64) : Action :=
  .bind Frames.runtimeCount fun s amount => if failed s = true then .done s 0 else
  if amount = 512 then .done 0 0 else
  if amount = 8192 then
    .bind (link address 7 96 11) fun s _ => if failed s = true then .done s 0 else
    .bind (link address 7 97 12) fun s _ => if failed s = true then .done s 0 else
    .bind (fillRange address 11 0x0c000000 1 0xc7) fun s _ => if failed s = true then .done s 0 else
    .bind (fillRange address 11 0x0c002000 1 0xc7) fun s _ => if failed s = true then .done s 0 else
    .bind (fillRange address 12 0x0c201000 1 0xc7) fun s _ => if failed s = true then .done s 0 else
    .bind (fillRange address 9 0x10001000 1 0xc7) fun s _ => if failed s = true then .done s 0 else
    .bind (fillRange address 9 0x10010000 2 0xc7) fun s _ => if failed s = true then .done s 0 else
    .bind (tableAt address 1) fun s middle => if failed s = true then .done s 0 else
    .boundedFoldU64 15 expandedPoolStep 15 0 middle 0 0 0 fun s mapped =>
    if failed s = true then .done s 0 else
    if mapped = 15 then .done 0 mapped else .done invariantFailure 0
  else .done invariantFailure 0

private def buildKernel (address : UInt64) : Action :=
  .bind (link address 0 2 1) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 1 1 2) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 1 2 3) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 1 3 4) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 1 16 5) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 1 63 6) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 0 0 7) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 7 0 8) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 7 128 9) fun s _ => if failed s = true then .done s 0 else
  .bind (link address 7 511 10) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 2 0x80200000 256 0x4b) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 3 0x80400000 256 0xc7) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 3 0x80500000 16 0xc7) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 4 0x80600000 256 0x43) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 5 0x82000000 512 0xc7) fun s _ => if failed s = true then .done s 0 else
  .bind (mapExpandedPool address) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 6 0x87e00000 512 0x43) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 8 0x00100000 1 0xc7) fun s _ => if failed s = true then .done s 0 else
  .bind (fillRange address 9 0x10000000 1 0xc7) fun s _ => if failed s = true then .done s 0 else
  -- Stable S-only metadata alias, inside the compiler's admitted U-address
  -- envelope. An actual U load therefore reaches the hardware U-bit check.
  .bind (tableAt address 8) fun s low => if failed s = true then .done s 0 else
  Access.write64 (tableSlot low 0x30000) ((0x80400000 : UInt64) >>> 12 <<< 10 ||| 0xc7)

private def releaseTableStep (i amount : UInt32) (acc address owner _ _ : UInt64) : Action :=
  let index := amount.toUInt64 - 1 - i.toUInt64
  .bind (get address (tableList + index * 8)) fun s handle =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Frames.mappingCount owner handle) fun s pins =>
  if failed s = true then .done invariantFailure 0 else
  if 1 < pins then .done invariantFailure 0 else
  .bind (if pins = 1 then Frames.unpin owner handle else .done 0 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Frames.release owner handle) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (put address (tableList + index * 8) 0) fun s _ => .done s (acc + 1)
private def rollbackTables (address : UInt64) (original : UInt8) : Action :=
  .bind (get address 24) fun s owner => if failed s = true then .done invariantFailure 0 else
  .bind (get address 40) fun s amount => if failed s = true then .done invariantFailure 0 else
  if amount ≤ 32 then
    .boundedFoldU64 32 releaseTableStep amount.toUInt32 0 address owner 0 0 fun s released =>
    if failed s = true then .done invariantFailure 0 else
    if released = amount then .done original 0 else .done invariantFailure 0
  else .done invariantFailure 0
private def releaseDescriptor (descriptor : UInt64) (original : UInt8) : Action :=
  .bind (Frames.release 1 descriptor) fun s _ =>
  if s = 0 then .done original 0 else .done invariantFailure 0

private def releaseRegistryStep (i amount : UInt32) (acc address owner _ _ : UInt64) : Action :=
  let index := amount.toUInt64 - 1 - i.toUInt64
  .bind (get address (registryList + index * 16)) fun s handle =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Frames.resolvePurpose owner handle 1) fun s physical =>
  if failed s = true then .done invariantFailure 0 else
  .bind (get address (registryList + index * 16 + 8)) fun s recorded =>
  if failed s = true then .done invariantFailure 0 else
  if (if physical = recorded then false else true) = true then .done invariantFailure 0 else
  .bind (Frames.release owner handle) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (put address (registryList + index * 16) 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (put address (registryList + index * 16 + 8) 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (put address registryCount index) fun s _ => .done s (acc + 1)

private def rollbackRegistry (address : UInt64) (original : UInt8) : Action :=
  .bind (get address 24) fun s owner => if failed s = true then .done invariantFailure 0 else
  .bind (get address registryCount) fun s amount => if failed s = true then .done invariantFailure 0 else
  if amount ≤ 8 then
    .boundedFoldU64 8 releaseRegistryStep amount.toUInt32 0 address owner 0 0 fun s released =>
    if failed s = true then .done invariantFailure 0 else
    if released = amount then .done original 0 else .done invariantFailure 0
  else .done invariantFailure 0

private def abortCreate (descriptor address : UInt64) (original : UInt8) : Action :=
  .bind (rollbackRegistry address original) fun s _ =>
  if (if s = original then false else true) = true then .done invariantFailure 0 else
  .bind (rollbackTables address original) fun s _ =>
  if s = original then releaseDescriptor descriptor original else .done invariantFailure 0

private def copyTableStep (i _ : UInt32) (acc address _ _ _ : UInt64) : Action :=
  .bind (Access.read64 (Batch.handles + i.toUInt64 * 8)) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (put address (tableList + i.toUInt64 * 8) handle) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put address 40 (i.toUInt64 + 1)) fun s _ => .done s (acc + 1)
private def pinTableStep (i _ : UInt32) (acc address owner _ _ : UInt64) : Action :=
  .bind (get address (tableList + i.toUInt64 * 8)) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.pin owner handle) fun s _ => .done s (acc + 1)

private def copyRegistryStep (i _ : UInt32) (acc address owner _ _ : UInt64) : Action :=
  .bind (Access.read64 (Batch.handles + i.toUInt64 * 8)) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose owner handle 1) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (put address (registryList + i.toUInt64 * 16) handle) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put address (registryList + i.toUInt64 * 16 + 8) physical) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (put address registryCount (i.toUInt64 + 1)) fun s _ => .done s (acc + 1)

private def buildRegistry (address owner amount : UInt64) : Action :=
  if amount = 512 then put address registryCount 0 else
  if amount = 8192 then
    .bind (Batch.allocate owner 1 8) fun s _ => if failed s = true then .done s 0 else
    .boundedFoldU64 8 copyRegistryStep 8 0 address owner 0 0 fun s copied =>
    if s = 0 then
      if copied = 8 then .done 0 8 else .done invariantFailure 0
    else
      .bind (Batch.rollback owner 8 s) fun rolledBack _ =>
      if (if rolledBack = s then false else true) = true then .done invariantFailure 0 else
      .bind (put address registryCount 0) fun clearStatus _ =>
      if failed clearStatus = true then .done invariantFailure 0 else .done s 0
  else .done invariantFailure 0

def create (owner : UInt64) : Action :=
  .bind Frames.runtimeCount fun s amount => if failed s = true then .done s 0 else
  let initialTables := if amount = 8192 then 13 else 11
  if Frames.ownerValid owner = false then .done Frames.badOwner 0 else
  .bind (Frames.allocate 1 1) fun s descriptor =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose 1 descriptor 1) fun s address =>
  if failed s = true then releaseDescriptor descriptor s else
  .bind (put address 24 owner) fun s _ =>
  if failed s = true then releaseDescriptor descriptor s else
  .bind (Batch.allocate owner 2 initialTables) fun s _ =>
  if failed s = true then releaseDescriptor descriptor s else
  .boundedFoldU64 13 copyTableStep initialTables.toUInt32 0 address 0 0 0 fun s _ =>
  if failed s = true then
    .bind (Batch.rollback owner initialTables s) fun rollbackStatus _ =>
    if rollbackStatus = s then releaseDescriptor descriptor s else .done invariantFailure 0
  else
  .bind (get address tableList) fun s rootHandle =>
  if failed s = true then abortCreate descriptor address s else
  .bind (tableAt address 0) fun s rootPA =>
  if failed s = true then abortCreate descriptor address s else
  .bind (put address 8 (if amount = 8192 then 2 else 1)) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 16 descriptor) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 56 rootHandle) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 64 rootPA) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 72 (satpWord rootPA)) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 80 (if amount = 8192 then expandedCapacity else 32)) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 88 32) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (buildRegistry address owner amount) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (buildKernel address) fun s _ => if failed s = true then abortCreate descriptor address s else
  .boundedFoldU64 13 pinTableStep initialTables.toUInt32 0 address owner 0 0 fun s _ =>
  if failed s = true then abortCreate descriptor address s else
  .bind (put address 32 1) fun s _ => if failed s = true then abortCreate descriptor address s else
  .bind (put address 0 magic) fun s _ =>
  if failed s = true then abortCreate descriptor address s else .done 0 descriptor

private def findRowStep (i _ : UInt32) (acc address wanted _ _ : UInt64) : Action :=
  .bind (row address i.toUInt64) fun s entry => if failed s = true then .done s 0 else
  .bind (Access.read64 entry) fun s va =>
  if failed s = true then .done s 0 else
  if va = wanted then
    if acc = 0 then .done 0 (i.toUInt64 + 1) else .done invalidDescriptor 0
  else .done 0 acc
private def findRow (address va : UInt64) : Action :=
  .bind (get address 48) fun s amount =>
  if failed s = true then .done s 0 else
  .bind (get address 80) fun s maximum => if failed s = true then .done s 0 else
  if amount ≤ maximum then
    .boundedFoldU64 1024 findRowStep amount.toUInt32 0 address (page va) 0 0 fun s v => .done s v
  else .done invalidDescriptor 0

private def dropHandle (owner handle : UInt64) (original : UInt8) : Action :=
  .bind (Frames.mappingCount owner handle) fun s pins =>
  if failed s = true then .done invariantFailure 0 else
  if 1 < pins then .done invariantFailure 0 else
  .bind (if pins = 1 then Frames.unpin owner handle else .done 0 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Frames.release owner handle) fun s _ =>
  if failed s = true then .done invariantFailure 0 else .done original 0

private def abortNewTable (address va oldCount handle : UInt64) (original : UInt8) : Action :=
  .bind (tableAt address 7) fun s middle =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Access.write64 (middle + vpn1 va * 8) 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind flushCurrent fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (get address 24) fun s owner =>
  if failed s = true then .done invariantFailure 0 else
  .bind (dropHandle owner handle original) fun s _ =>
  if s = original then
    .bind (put address (tableList + oldCount * 8) 0) fun s _ =>
    if failed s = true then .done invariantFailure 0 else
    .bind (put address 40 oldCount) fun s _ =>
    if failed s = true then .done invariantFailure 0 else .done original 0
  else .done invariantFailure 0

/-- Missing low-address L0 tables are constructed provisionally. A failed map
removes its parent PTE, flushes, and releases the new table. -/
private def ensureBottom (address va : UInt64) : Action :=
  .bind (tableAt address 7) fun s middle =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (middle + vpn1 va * 8)) fun s entry =>
  if failed s = true then .done s 0 else
  if (if entry = 0 then false else true) = true then child address entry else
  .bind (get address 40) fun s oldCount =>
  if failed s = true then .done s 0 else
  if 32 ≤ oldCount then .done resourceLimit 0 else
  .bind (get address 24) fun s owner =>
  if failed s = true then .done s 0 else
  .bind (Frames.allocate owner 2) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Frames.resolvePurpose owner handle 2) fun s bottom =>
  if failed s = true then dropHandle owner handle s else
  .bind (Frames.pin owner handle) fun s _ =>
  if failed s = true then dropHandle owner handle s else
  .bind (put address (tableList + oldCount * 8) handle) fun s _ =>
  if failed s = true then abortNewTable address va oldCount handle s else
  .bind (put address 40 (oldCount + 1)) fun s _ =>
  if failed s = true then abortNewTable address va oldCount handle s else
  .bind (Access.write64 (middle + vpn1 va * 8) (tableEntry bottom)) fun s _ =>
  if failed s = true then abortNewTable address va oldCount handle s else
  .bind flushCurrent fun s _ =>
  if failed s = true then abortNewTable address va oldCount handle s else .done 0 bottom

private def rollbackLastTable (address va oldCount : UInt64) (original : UInt8) : Action :=
  .bind (get address 40) fun s currentCount =>
  if failed s = true then .done invariantFailure 0 else
  if currentCount = oldCount then .done original 0 else
  if currentCount = oldCount + 1 then
    .bind (get address (tableList + oldCount * 8)) fun s handle =>
    if failed s = true then .done invariantFailure 0 else
    abortNewTable address va oldCount handle original
  else .done invariantFailure 0

private def clearRow (address index : UInt64) : Action :=
  .bind (row address index) fun s entry => if failed s = true then .done s 0 else
  .bind (Access.write64 entry 0) fun s _ => if failed s = true then .done s 0 else
  .bind (Access.write64 (entry + 8) 0) fun s _ => if failed s = true then .done s 0 else
  .bind (Access.write64 (entry + 16) 0) fun s _ => if failed s = true then .done s 0 else
  Access.write64 (entry + 24) 0

private def abortLeaf (address va oldTables index owner handle slot : UInt64)
    (original : UInt8) : Action :=
  .bind (Access.write64 slot 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind flushCurrent fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (Frames.unpin owner handle) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (clearRow address index) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  .bind (put address 48 index) fun s _ =>
  if failed s = true then .done invariantFailure 0 else
  rollbackLastTable address va oldTables original

private def commitLeaf (address va oldTables index owner handle slot pte permissions : UInt64) : Action :=
  .bind (Access.write64 slot pte) fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind flushCurrent fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind (row address index) fun s entry =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind (Access.write64 entry va) fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind (Access.write64 (entry + 8) handle) fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind (Access.write64 (entry + 16) pte) fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind (Access.write64 (entry + 24) permissions) fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else
  .bind (put address 48 (index + 1)) fun s _ =>
  if failed s = true then abortLeaf address va oldTables index owner handle slot s else .done 0 handle

def mapUser (descriptor va handle permissions : UInt64) : Action :=
  if alignedAddress va = false then .done invalidAddress 0 else
  if permissionsValid permissions = false then .done invalidPermission 0 else
  .bind (base descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get address 80) fun s maximum => if failed s = true then .done s 0 else
  if bindingAddressValid va maximum = false then .done invalidAddress 0 else
  .bind (get address 24) fun s owner =>
  if failed s = true then .done s 0 else
  if owner = 1 then .done invalidPermission 0 else
  .bind (Frames.resolve owner handle) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (Frames.purpose owner handle) fun s purpose =>
  if failed s = true then .done s 0 else
  if purposePermits purpose permissions = false then .done invalidPermission 0 else
  .bind (findRow address va) fun s found =>
  if failed s = true then .done s 0 else
  if (if found = 0 then false else true) = true then .done duplicateMapping 0 else
  .bind (get address 48) fun s index =>
  if failed s = true then .done s 0 else
  if maximum ≤ index then .done resourceLimit 0 else
  .bind (get address 40) fun s oldTables =>
  if failed s = true then .done s 0 else
  .bind (ensureBottom address va) fun s bottom =>
  if failed s = true then .done s 0 else
  let slot := tableSlot bottom va
  .bind (Access.read64 slot) fun s entry =>
  if failed s = true then rollbackLastTable address va oldTables s else
  if (if entry = 0 then false else true) = true then rollbackLastTable address va oldTables invalidPte else
  .bind (Frames.pin owner handle) fun s _ =>
  if failed s = true then rollbackLastTable address va oldTables s else
  commitLeaf address va oldTables index owner handle slot (leafEntry physical permissions) permissions

/-- Returns a management-alias physical byte address only after the actual
walk, tracked exact PTE, live generation, owner, purpose and permissions agree. -/
def lookup (descriptor va permission : UInt64) : Action :=
  if addressValid va = false then .done invalidAddress 0 else
  if requestValid permission = false then .done invalidPermission 0 else
  .bind (base descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get address 80) fun s maximum => if failed s = true then .done s 0 else
  if bindingAddressValid va maximum = false then .done invalidAddress 0 else
  .bind (findRow address va) fun s found =>
  if failed s = true then .done s 0 else
  if found = 0 then .done missingMapping 0 else
  let index := found - 1
  .bind (get address 24) fun s owner =>
  if failed s = true then .done s 0 else
  if owner = 1 then .done invalidPermission 0 else
  .bind (row address index) fun s entry => if failed s = true then .done s 0 else
  .bind (Access.read64 (entry + 8)) fun s handle =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (entry + 16)) fun s trackedPte =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 (entry + 24)) fun s permissions =>
  if failed s = true then .done s 0 else
  if permissionsValid permissions = false then .done invalidPte 0 else
  .bind (Frames.resolve owner handle) fun s physical =>
  if failed s = true then .done s 0 else
  .bind (Frames.purpose owner handle) fun s purpose =>
  if failed s = true then .done s 0 else
  if purposePermits purpose permissions = false then .done invalidPte 0 else
  if (if trackedPte = leafEntry physical permissions then false else true) = true then .done invalidPte 0 else
  .bind (walkSlot address va) fun s slot =>
  if failed s = true then .done s 0 else
  .bind (Access.read64 slot) fun s actualPte =>
  if failed s = true then .done s 0 else
  if (if actualPte = trackedPte then false else true) = true then .done invalidPte 0 else
  if permissions &&& permission = permission then .done 0 (physical + va % 4096)
  else .done invalidPermission 0

private def moveLastRow (address index last : UInt64) : Action :=
  .bind (row address last) fun s source => if failed s = true then .done s 0 else
  .bind (row address index) fun s target => if failed s = true then .done s 0 else
  .bind (Access.read64 source) fun s va => if failed s = true then .done s 0 else
  .bind (Access.read64 (source + 8)) fun s handle => if failed s = true then .done s 0 else
  .bind (Access.read64 (source + 16)) fun s pte => if failed s = true then .done s 0 else
  .bind (Access.read64 (source + 24)) fun s permissions => if failed s = true then .done s 0 else
  .bind (Access.write64 target va) fun s _ => if failed s = true then .done s 0 else
  .bind (Access.write64 (target + 8) handle) fun s _ => if failed s = true then .done s 0 else
  .bind (Access.write64 (target + 16) pte) fun s _ => if failed s = true then .done s 0 else
  Access.write64 (target + 24) permissions

def unmap (descriptor va : UInt64) : Action :=
  if alignedAddress va = false then .done invalidAddress 0 else
  .bind (lookup descriptor va 1) fun s _ =>
  if failed s = true then .done s 0 else
  .bind (base descriptor) fun s address =>
  if failed s = true then .done s 0 else
  .bind (get address 24) fun s owner => if failed s = true then .done s 0 else
  .bind (findRow address va) fun s found => if failed s = true then .done s 0 else
  if found = 0 then .done missingMapping 0 else
  let index := found - 1
  .bind (get address 48) fun s amount => if failed s = true then .done s 0 else
  if amount = 0 then .done invalidDescriptor 0 else
  .bind (row address index) fun s entry => if failed s = true then .done s 0 else
  .bind (Access.read64 (entry + 8)) fun s handle => if failed s = true then .done s 0 else
  .bind (walkSlot address va) fun s slot => if failed s = true then .done s 0 else
  .bind (Access.write64 slot 0) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind flushCurrent fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (Frames.unpin owner handle) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (moveLastRow address index (amount - 1)) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (clearRow address (amount - 1)) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (put address 48 (amount - 1)) fun s _ =>
  if failed s = true then .done invariantFailure 0 else .done 0 handle

private def destroyLeafStep (_i _ : UInt32) (acc descriptor address owner _ : UInt64) : Action :=
  .bind (row address 0) fun s entry => if failed s = true then .done s 0 else
  .bind (Access.read64 entry) fun s va => if failed s = true then .done s 0 else
  .bind (unmap descriptor va) fun s handle => if failed s = true then .done s 0 else
  .bind (Frames.mappingCount owner handle) fun s pins => if failed s = true then .done s 0 else
  if pins = 0 then
    .bind (Frames.release owner handle) fun s _ => .done s (acc + 1)
  else .done 0 (acc + 1)

/-- The caller has restored a stable supervisor root and updated activeRoot.
Every leaf is invalidated before its owner pin is removed or its frame freed. -/
def destroy (descriptor : UInt64) : Action :=
  .bind (base descriptor) fun s address => if failed s = true then .done s 0 else
  .bind (get address 64) fun s rootPA => if failed s = true then .done s 0 else
  .bind (Access.read64 activeRoot) fun s current => if failed s = true then .done s 0 else
  if rootPA = current then .done activeAddressSpace 0 else
  .bind (get address 24) fun s owner => if failed s = true then .done s 0 else
  .bind (get address 48) fun s amount => if failed s = true then .done s 0 else
  .boundedFoldU64 1024 destroyLeafStep amount.toUInt32 0 descriptor address owner 0 fun s released =>
  if failed s = true then .done invariantFailure 0 else
  if (if released = amount then false else true) = true then .done invariantFailure 0 else
  .bind flushCurrent fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (put address 32 2) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (put address 0 0) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (rollbackRegistry address 0) fun s _ => if failed s = true then .done invariantFailure 0 else
  .bind (rollbackTables address 0) fun s _ =>
  if failed s = true then .done invariantFailure 0 else releaseDescriptor descriptor 0

end Lemma.Kernel.Memory.AddressSpace
