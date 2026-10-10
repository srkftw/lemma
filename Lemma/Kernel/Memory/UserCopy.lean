import Lemma.Kernel.Memory.AddressSpace
import Lemma.User.ABI

/-! Bounded copies through owned physical aliases. The syscall dispatcher is
single-hart and nonpreemptible: every user page is checked before a destination
byte changes, and no borrowed alias survives this Action. Zero length touches
neither user memory nor kernel storage. -/
namespace Lemma.Kernel.Memory.UserCopy
open Lemma.Core0.Memory

def maximumLength : UInt64 := 256
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

private def firstLength (pointer length : UInt64) : UInt64 :=
  let available := 4096 - pointer % 4096
  if length ≤ available then length else available

private def checkedLookup (descriptor pointer permission : UInt64) : Action :=
  .bind (AddressSpace.lookup descriptor pointer permission) fun s physical =>
  if s = 0 then .done 0 physical else .done (failure s) 0

private def validate (descriptor pointer length permission : UInt64) : Action :=
  if length = 0 then .done 0 0 else
  if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
  if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
  .bind (checkedLookup descriptor pointer permission) fun s _ =>
  if s = 0 then
    let split := firstLength pointer length
    if length ≤ split then .done 0 length else
    .bind (checkedLookup descriptor (pointer + split) permission) fun s _ =>
    if s = 0 then .done 0 length else .done s 0
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

/-- A kernel scratch handle must name a live owner-1 purpose-1 frame. All
spanned user leaves are checked before the bounded copy changes scratch. -/
def copyFromUser (descriptor pointer kernelHandle offset length : UInt64) : Action :=
  if length = 0 then .done 0 0 else
  if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
  .bind (scratch kernelHandle offset length) fun s destination =>
  if s = 0 then
    if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
    .bind (checkedLookup descriptor pointer 1) fun s first =>
    if s = 0 then
      let split := firstLength pointer length
      .bind (if length ≤ split then .done 0 0 else checkedLookup descriptor (pointer + split) 1) fun s second =>
      if s = 0 then
        .boundedFoldU64 256 fromStep length.toUInt32 0 first second destination split fun s copied =>
        if s = 0 then .done 0 copied else .done Lemma.User.ABI.kernelFatal 0
      else .done s 0
    else .done s 0
  else .done s 0

/-- Preflight includes write permission on both leaves before copying the
scratch bytes. A read-only first/second page cannot produce a partial write. -/
def copyToUser (descriptor pointer kernelHandle offset length : UInt64) : Action :=
  if length = 0 then .done 0 0 else
  if maximumLength < length then .done Lemma.User.ABI.invalidArgument 0 else
  .bind (scratch kernelHandle offset length) fun s source =>
  if s = 0 then
    if validRange pointer length = false then .done Lemma.User.ABI.invalidRange 0 else
    .bind (checkedLookup descriptor pointer 2) fun s first =>
    if s = 0 then
      let split := firstLength pointer length
      .bind (if length ≤ split then .done 0 0 else checkedLookup descriptor (pointer + split) 2) fun s second =>
      if s = 0 then
        .boundedFoldU64 256 toStep length.toUInt32 0 first second source split fun s copied =>
        if s = 0 then .done 0 copied else .done Lemma.User.ABI.kernelFatal 0
      else .done s 0
    else .done s 0
  else .done s 0

end Lemma.Kernel.Memory.UserCopy
