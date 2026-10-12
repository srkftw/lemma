import Lemma.Kernel.Memory.AddressSpace
import Lemma.User.ABI

/-! Bounded copies through owned physical aliases. The syscall dispatcher is
single-hart and nonpreemptible: every user page is checked before a destination
byte changes, and no borrowed alias survives this Action. Zero length touches
neither user memory nor kernel storage. -/
namespace Lemma.Kernel.Memory.UserCopy
open Lemma.Core0.Memory

def maximumLength : UInt64 := 4096
def userBase : UInt64 := 0x10000
def userLimit : UInt64 := 0x40000000

private def failure (status : UInt8) : UInt8 :=
  if status = 71 then Lemma.User.ABI.invalidRange else
  if status = 72 then Lemma.User.ABI.permissionDenied else
  if status = 74 then Lemma.User.ABI.missingMapping else
  Lemma.User.ABI.kernelFatal

/-- Subtraction guards run before forming an end address. This low Sv39
envelope rejects noncanonical values and excludes every high kernel address. -/
private def validRange (pointer length : UInt64) : Bool :=
  if maximumLength < length then false else
  if pointer < userBase then false else
  if userLimit ≤ pointer then false else
  if userLimit - pointer < length then false else true

/-- A nonempty range of length at most 4096 spans at most two 4096-byte
pages, even when unaligned: floor((offset + length - 1)/4096) ≤ 1.
Both leaves are preflighted before any byte is written. Increasing this bound
past one page requires a new full-page enumeration rather than this split. -/
private def firstLength (pointer length : UInt64) : UInt64 :=
  let available := 4096 - pointer % 4096
  if length ≤ available then length else available

/-- The low-address/request rejection retains priority over descriptor reads.
The validated base is borrowed only within this nonpreemptible Action. -/
private def checkedBase (descriptor pointer permission : UInt64) : Action :=
  if AddressSpace.addressValid pointer = false then .done Lemma.User.ABI.invalidRange 0 else
  if AddressSpace.requestValid permission = false then .done Lemma.User.ABI.permissionDenied 0 else
  .bind (AddressSpace.base descriptor) fun s address =>
  if s = 0 then .done 0 address else .done (failure s) 0

private def checkedLookupAt (address pointer permission : UInt64) : Action :=
  .bind (AddressSpace.lookupAt address pointer permission) fun s physical =>
  if s = 0 then .done 0 physical else .done (failure s) 0

private def validate (descriptor pointer length permission : UInt64) : Action :=
  if length = 0 then .done 0 0 else
  if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
  if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
  .bind (checkedBase descriptor pointer permission) fun s address =>
  if s = 0 then
  .bind (checkedLookupAt address pointer permission) fun s _ =>
  if s = 0 then
    let split := firstLength pointer length
    if length ≤ split then .done 0 length else
    .bind (checkedLookupAt address (pointer + split) permission) fun s _ =>
    if s = 0 then .done 0 length else .done s 0
  else .done s 0
  else .done s 0

def validateRead (descriptor pointer length : UInt64) : Action :=
  validate descriptor pointer length 1
def validateWrite (descriptor pointer length : UInt64) : Action :=
  validate descriptor pointer length 2

private def scratch (handle offset length : UInt64) : Action :=
  if 4096 < offset then .done Lemma.User.ABI.kernelFatal 0 else
  if 4096 - offset < length then .done Lemma.User.ABI.kernelFatal 0 else
  .bind (Frames.resolvePurpose 1 handle 1) fun s base =>
  if s = 0 then .done 0 (base + offset) else .done Lemma.User.ABI.kernelFatal 0

private def fromStep (i _ : UInt32) (acc first second destination split : UInt64) : Action :=
  let index := i.toUInt64
  let source := if index < split then first + index else second + (index - split)
  .bind (Access.read8 source) fun s byte =>
  if s = 0 then
    .bind (Access.write8 (destination + index) byte) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else .done Lemma.User.ABI.kernelFatal 0
  else .done Lemma.User.ABI.kernelFatal 0

private def toStep (i _ : UInt32) (acc first second source split : UInt64) : Action :=
  let index := i.toUInt64
  let destination := if index < split then first + index else second + (index - split)
  .bind (Access.read8 (source + index)) fun s byte =>
  if s = 0 then
    .bind (Access.write8 destination byte) fun s _ =>
    if s = 0 then .done 0 (acc + 1) else .done Lemma.User.ABI.kernelFatal 0
  else .done Lemma.User.ABI.kernelFatal 0

private def fromWordStep (i _ : UInt32) (acc first second destination split : UInt64) : Action :=
  let index := i.toUInt64 * 8
  let source := if index < split then first + index else second + (index - split)
  .bind (Access.read64 source) fun s word =>
  if s = 0 then
    .bind (Access.write64 (destination + index) word) fun s _ =>
    if s = 0 then .done 0 (acc + 8) else .done Lemma.User.ABI.kernelFatal 0
  else .done Lemma.User.ABI.kernelFatal 0

private def toWordStep (i _ : UInt32) (acc first second source split : UInt64) : Action :=
  let index := i.toUInt64 * 8
  let destination := if index < split then first + index else second + (index - split)
  .bind (Access.read64 (source + index)) fun s word =>
  if s = 0 then
    .bind (Access.write64 destination word) fun s _ =>
    if s = 0 then .done 0 (acc + 8) else .done Lemma.User.ABI.kernelFatal 0
  else .done Lemma.User.ABI.kernelFatal 0

/-- Every transferred word is wholly inside a preflighted page and scratch
span. Unaligned and partial-word copies keep their exact byte semantics. -/
private def wordsAligned (first second scratch split length : UInt64) : Bool :=
  if first % 8 = 0 then if second % 8 = 0 then if scratch % 8 = 0 then
  if split % 8 = 0 then if length % 8 = 0 then true else false else false
  else false else false else false

/-- A kernel scratch handle must name a live owner-1 purpose-1 frame. All
spanned user leaves are checked before the bounded copy changes scratch. -/
private def copyFromUserResult (aliasResult descriptor pointer kernelHandle offset length : UInt64) : Action :=
  if length = 0 then .done 0 0 else
  if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
  .bind (scratch kernelHandle offset length) fun s destination =>
  if s = 0 then
    if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
    .bind (checkedBase descriptor pointer 1) fun s address =>
    if s = 0 then
    .bind (checkedLookupAt address pointer 1) fun s first =>
    if s = 0 then
      let split := firstLength pointer length
      .bind (if length ≤ split then .done 0 0 else checkedLookupAt address (pointer + split) 1) fun s second =>
      if s = 0 then
        if wordsAligned first second destination split length = true then
          .boundedFoldU64 512 fromWordStep (length / 8).toUInt32 0 first second destination split fun s copied =>
          if s = 0 then .done 0 (if aliasResult = 1 then first else copied) else .done Lemma.User.ABI.kernelFatal 0
        else
          .boundedFoldU64 4096 fromStep length.toUInt32 0 first second destination split fun s copied =>
          if s = 0 then .done 0 (if aliasResult = 1 then first else copied) else .done Lemma.User.ABI.kernelFatal 0
      else .done s 0
    else .done s 0
    else .done s 0
  else .done s 0

def copyFromUser (descriptor pointer kernelHandle offset length : UInt64) : Action :=
  copyFromUserResult 0 descriptor pointer kernelHandle offset length

/-- Kernel-only result variant. The sole admitted caller copies surface metadata
into a scratch frame distinct from the descriptor, then borrows this checked read
alias for another span of the same user page within that nonpreemptible Action.
The returned alias is not a handle, does not cross a syscall, and is never cached. -/
def copyFromUserReadPage (descriptor pointer kernelHandle offset length : UInt64) : Action :=
  copyFromUserResult 1 descriptor pointer kernelHandle offset length

/-- The compiled caller guard binds reference/first to the successful metadata
copy above. Both scratch ownership and the new span are checked afresh; a range
outside the already checked page follows the ordinary complete validation path. -/
def copyFromUserReusingReadPage (descriptor reference first pointer kernelHandle offset length : UInt64) : Action :=
  if reference / 4096 = pointer / 4096 then
  if length ≤ 4096 - pointer % 4096 then
    if length = 0 then .done 0 0 else
    if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
    .bind (scratch kernelHandle offset length) fun s destination =>
    if s = 0 then
      if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
      let source := first - reference % 4096 + pointer % 4096
      if wordsAligned source 0 destination length length = true then
        .boundedFoldU64 512 fromWordStep (length / 8).toUInt32 0 source 0 destination length fun s copied =>
        if s = 0 then .done 0 copied else .done Lemma.User.ABI.kernelFatal 0
      else
        .boundedFoldU64 4096 fromStep length.toUInt32 0 source 0 destination length fun s copied =>
        if s = 0 then .done 0 copied else .done Lemma.User.ABI.kernelFatal 0
    else .done s 0
  else copyFromUser descriptor pointer kernelHandle offset length
  else copyFromUser descriptor pointer kernelHandle offset length

/-- Preflight includes write permission on both leaves before copying the
scratch bytes. A read-only first/second page cannot produce a partial write. -/
def copyToUser (descriptor pointer kernelHandle offset length : UInt64) : Action :=
  if length = 0 then .done 0 0 else
  if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
  .bind (scratch kernelHandle offset length) fun s source =>
  if s = 0 then
    if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
    .bind (checkedBase descriptor pointer 2) fun s address =>
    if s = 0 then
    .bind (checkedLookupAt address pointer 2) fun s first =>
    if s = 0 then
      let split := firstLength pointer length
      .bind (if length ≤ split then .done 0 0 else checkedLookupAt address (pointer + split) 2) fun s second =>
      if s = 0 then
        if wordsAligned first second source split length = true then
          .boundedFoldU64 512 toWordStep (length / 8).toUInt32 0 first second source split fun s copied =>
          if s = 0 then .done 0 copied else .done Lemma.User.ABI.kernelFatal 0
        else
          .boundedFoldU64 4096 toStep length.toUInt32 0 first second source split fun s copied =>
          if s = 0 then .done 0 copied else .done Lemma.User.ABI.kernelFatal 0
      else .done s 0
    else .done s 0
    else .done s 0
  else .done s 0

end Lemma.Kernel.Memory.UserCopy
