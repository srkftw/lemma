import Lemma.Courses.PackageBinding
import Lemma.Documents.MathematicsClosure

/-! `lemma-course-workspace/1` keeps the original Doc8 byte-for-byte inside a
separate3712-byte owned record. Package selection metadata supplements original
checker/execution authority; it never replaces a real admitted reply.
An all-zero history row is explicitly Unknown, never inherited current origin.
Only the integrating guest may copy an actual completed attempt binding. -/
namespace Lemma.Courses.PackageWorkspace
open Lemma.Core0.Memory
open Lemma.Courses.PackageFormat
open Lemma.Documents

def magic : UInt64 := 0x3153574b504d454c
def version : UInt64 := 1
def bytes : UInt64 := 3712
def inner : UInt64 := 64
def selection : UInt64 := 2560
def attempts : UInt64 := 2688
def object (page : UInt64) : UInt64 := 0x504b000000000000 ||| page

private def field (buffer offset : UInt64) : Action := Lemma.User.Memory.read64 (buffer + offset)
private def put (buffer offset value : UInt64) : Action := Lemma.User.Memory.write64 (buffer + offset) value
private def zeroStep (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (put buffer (i.toUInt64 * 8) 0) fun s _ => .done s acc
private def zeroCheck (i _ : UInt32) (acc buffer _ _ _ : UInt64) : Action :=
  .bind (field buffer (i.toUInt64 * 8)) fun s value => if s = 0 then
  if value = 0 then .done 0 acc else .done malformed 0 else .done s 0
private def copyBindingStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (field source (i.toUInt64 * 8)) fun s value => if s = 0 then
  .bind (put target (i.toUInt64 * 8) value) fun s _ => .done s acc else .done s 0

private def shape (buffer ns page : UInt64) : UInt64 :=
  if buffer % 8 = 0 then if buffer ≤ 0xffffffffffffffff - bytes then
  if ns = 0 then 0 else if 2 < ns then 0 else
  if page = 0 then 0 else if 64 < page then 0 else 1 else 0 else 0

/-- Import an already validated Doc8 as explicit Unknown package history.
Only owned disjoint staging is written; the caller publishes on success. -/
def create (buffer source ns page : UInt64) : Action :=
  if shape buffer ns page = 1 then
  if source % 8 = 0 then if source ≤ 0xffffffffffffffff - Mathematics.currentBytes then
  if (if buffer + bytes ≤ source then (1 : UInt64) else if source + Mathematics.currentBytes ≤ buffer then 1 else 0) = 1 then
  .bind (Mathematics.field source 8) fun s v => if s = 0 then if v = 8 then
  .bind (MathematicsClosure.validate source ns page) fun s _ => if s = 0 then
  .boundedFoldU64 464 zeroStep 464 0 buffer 0 0 0 fun s _ => if s = 0 then
  .bind (Mathematics.copyCurrent source (buffer + inner)) fun s copied => if s = 0 then
  if copied = Mathematics.currentBytes then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  .bind (put buffer 16 bytes) fun s _ => if s = 0 then
  .bind (put buffer 24 ns) fun s _ => if s = 0 then
  .bind (put buffer 32 page) fun s _ => if s = 0 then
  .bind (put buffer 40 Mathematics.currentBytes) fun s _ => if s = 0 then
  put buffer 0 magic
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0

private def validateAttempt (i _ : UInt32) (acc buffer count mask _ : UInt64) : Action :=
  let index := i.toUInt64
  let binding := buffer + attempts + index * PackageBinding.bytes
  if (mask >>> index) &&& 1 = 0 then
    .boundedFoldU64 16 zeroCheck 16 acc binding 0 0 0 fun s _ => .done s acc
  else if index < count then
    let entry := buffer + inner + 256 + index * 72
    .bind (Mathematics.field entry 0) fun s revision => if s = 0 then
    .bind (Mathematics.field entry 8) fun s goal => if s = 0 then
    .bind (PackageBinding.applicable binding revision goal goal 0) fun s applicable => if s = 0 then
    if applicable = 1 then
    .bind (field binding 96) fun s declaredBudget => if s = 0 then
    .bind (Mathematics.field entry 64) fun s actualBudget => if s = 0 then
    if declaredBudget = actualBudget then .done 0 acc else .done malformed 0
    else .done s 0 else .done s 0
    else .done malformed 0
    else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0

private def validateSelection (buffer mask : UInt64) : Action :=
  if (mask >>> 8) &&& 1 = 0 then
    .boundedFoldU64 16 zeroCheck 16 0 (buffer + selection) 0 0 0 fun s _ => .done s 0
  else
    .bind (PackageBinding.validate (buffer + selection)) fun s _ => if s = 0 then
    .bind (field (buffer + selection) 120) fun s boundRevision => if s = 0 then
    .bind (Mathematics.field (buffer + inner) 40) fun s revision => if s = 0 then
    if boundRevision ≤ revision then .done 0 0 else .done malformed 0
    else .done s 0 else .done s 0 else .done s 0

/-- Validate original checker/execution/learner records before package rows.
Known attempt metadata must retain its exact declared request budget.
Known current package metadata can be stale for the edited revision; validation
retains that history while applicability stays a separate exact check. -/
def validate (buffer ns page : UInt64) : Action :=
  if shape buffer ns page = 1 then
  .bind (field buffer 0) fun s tag => if s = 0 then if tag = magic then
  .bind (field buffer 8) fun s v => if s = 0 then if v = version then
  .bind (field buffer 16) fun s total => if s = 0 then if total = bytes then
  .bind (field buffer 24) fun s actualNS => if s = 0 then if actualNS = ns then
  .bind (field buffer 32) fun s actualPage => if s = 0 then if actualPage = page then
  .bind (field buffer 40) fun s size => if s = 0 then if size = Mathematics.currentBytes then
  .bind (field buffer 48) fun s mask => if s = 0 then if mask < 512 then
  .bind (field buffer 56) fun s reserved => if s = 0 then if reserved = 0 then
  .bind (Mathematics.field (buffer + inner) 8) fun s docVersion => if s = 0 then if docVersion = 8 then
  .bind (MathematicsClosure.validate (buffer + inner) ns page) fun s _ => if s = 0 then
  .bind (Mathematics.field (buffer + inner) 144) fun s count => if s = 0 then if count ≤ 8 then
  .boundedFoldU64 8 validateAttempt 8 0 buffer count mask 0 fun s _ => if s = 0 then
  validateSelection buffer mask else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done unsupported 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done malformed 0

private def separate (a n b m : UInt64) : UInt64 :=
  if a ≤ 0xffffffffffffffff - n then if b ≤ 0xffffffffffffffff - m then
  if a+n ≤ b then 1 else if b+m ≤ a then 1 else 0 else 0 else 0

private def copyBinding (source target : UInt64) : Action :=
  .bind (put target 0 0) fun s _ => if s = 0 then
  .boundedFoldU64 15 copyBindingStep 15 0 (source+8) (target+8) 0 0 fun s _ => if s = 0 then
  put target 0 PackageBinding.magic else .done s 0 else .done s 0

private def validateOwned (buffer : UInt64) : Action :=
  .bind (field buffer 24) fun s ns => if s = 0 then
  .bind (field buffer 32) fun s page => if s = 0 then validate buffer ns page else .done s 0 else .done s 0

/-- Copy the immutable current selection when a real request begins. Stale
selection cannot be used for a newer/different original mathematical object.
The exact selected request budget must also equal the package declaration.
Caller retains this owned snapshot until completion or explicit cancellation. -/
def snapshotSelection (buffer target : UInt64) : Action :=
  if target % 8 = 0 then if separate buffer bytes target PackageBinding.bytes = 1 then
  .bind (validateOwned buffer) fun s _ => if s = 0 then
  .bind (field buffer 48) fun s mask => if s = 0 then if (mask >>> 8) &&& 1 = 1 then
  .bind (Mathematics.field (buffer+inner) 40) fun s revision => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 48) fun s goal => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 120) fun s domain => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 128) fun s assumptions => if s = 0 then
  .bind (PackageBinding.applicable (buffer+selection) revision goal domain assumptions) fun s applies => if s = 0 then
  if applies = 1 then
  .bind (field (buffer+selection) 96) fun s declaredBudget => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 136) fun s actualBudget => if s = 0 then
  if declaredBudget = actualBudget then copyBinding (buffer+selection) target else .done selectionAbsent 0
  else .done s 0 else .done s 0
  else .done selectionAbsent 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done selectionAbsent 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0

/-- Caller first makes an explicit, revision-producing goal selection and
cancels any outstanding check. Authored prose cannot perform that change here.
Scratch and destination are unpublished owned buffers, separate from package. -/
def captureSelection (buffer package length ordinal scratch : UInt64) : Action :=
  if scratch % 8 = 0 then if separate scratch PackageBinding.bytes buffer bytes = 1 then
  if separate package length buffer bytes = 1 then
  .bind (validateOwned buffer) fun s _ => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 40) fun s revision => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 48) fun s goal => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 120) fun s domain => if s = 0 then
  .bind (Mathematics.field (buffer+inner) 128) fun s assumptions => if s = 0 then
  .bind (PackageBinding.capture scratch package length ordinal revision) fun s _ => if s = 0 then
  .bind (PackageBinding.applicable scratch revision goal domain assumptions) fun s applies => if s = 0 then
  if applies = 1 then
  .bind (field buffer 48) fun s mask => if s = 0 then
  .bind (copyBinding scratch (buffer+selection)) fun s _ => if s = 0 then put buffer 48 (mask ||| 256) else .done s 0
  else .done s 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0


private def equalWordsStep (i _ : UInt32) (acc first second _ _ : UInt64) : Action :=
  .bind (field first (i.toUInt64*8)) fun s actual => if s = 0 then
  .bind (field second (i.toUInt64*8)) fun s expected => if s = 0 then
  if actual = expected then .done 0 acc else .done malformed 0
  else .done s 0 else .done s 0

private def equalHistoryStep (i _ : UInt32) (acc oldDoc newDoc count _ : UInt64) : Action :=
  let index := i.toUInt64 / 17
  let word := i.toUInt64 % 17
  if count ≤ index then .done 0 acc else
  let offset := if word < 9 then 256 + index*72 + word*8 else 1984 + index*64 + (word-9)*8
  .bind (field oldDoc offset) fun s actual => if s = 0 then
  .bind (field newDoc offset) fun s expected => if s = 0 then
  if actual = expected then .done 0 acc else .done malformed 0
  else .done s 0 else .done s 0

private def equalEventsStep (i _ : UInt32) (acc oldDoc newDoc count _ : UInt64) : Action :=
  if count*2 ≤ i.toUInt64 then .done 0 acc else
  let offset := Mathematics.legacyBytes + i.toUInt64*8
  .bind (field oldDoc offset) fun s actual => if s = 0 then
  .bind (field newDoc offset) fun s expected => if s = 0 then
  if actual = expected then .done 0 acc else .done malformed 0
  else .done s 0 else .done s 0

private def equalSubmissionStep (i _ : UInt32) (acc oldDoc newDoc _ _ : UInt64) : Action :=
  let index := i.toUInt64
  let offset := if index < 7 then 40 + index*8 else 120 + (index-7)*8
  .bind (field oldDoc offset) fun s actual => if s = 0 then
  .bind (field newDoc offset) fun s expected => if s = 0 then
  if actual = expected then .done 0 acc else .done malformed 0
  else .done s 0 else .done s 0

/-- Preflight checks may read input buffers only. Target is a distinct owned
unpublished staging page. Every old semantic/execution history row is retained.
A no-attempt transition cannot silently attach a package to an existing row. -/
private def transitionBase (buffer document target addAttempt : UInt64) : Action :=
  if target % 8 = 0 then if document % 8 = 0 then
  if separate buffer bytes target bytes = 1 then
  if separate document Mathematics.currentBytes target bytes = 1 then
  .bind (validateOwned buffer) fun s _ => if s = 0 then
  .bind (field buffer 24) fun s ns => if s = 0 then
  .bind (field buffer 32) fun s page => if s = 0 then
  .bind (field document 8) fun s v => if s = 0 then if v = 8 then
  .bind (MathematicsClosure.validate document ns page) fun s _ => if s = 0 then
  .bind (field (buffer+inner) 144) fun s oldCount => if s = 0 then
  .bind (field document 144) fun s newCount => if s = 0 then
  if oldCount + addAttempt = newCount then
  .bind (field (buffer+inner) 40) fun s oldRevision => if s = 0 then
  .bind (field document 40) fun s newRevision => if s = 0 then
  if oldRevision ≤ newRevision then
  .boundedFoldU64 136 equalHistoryStep 136 0 (buffer+inner) document oldCount 0 fun s _ => if s = 0 then
  .bind (field (buffer+inner) 192) fun s oldEvents => if s = 0 then
  .bind (field document 192) fun s newEvents => if s = 0 then
  if oldEvents ≤ newEvents then
  .boundedFoldU64 128 equalEventsStep 128 0 (buffer+inner) document oldEvents 0 fun s _ =>
  if s = 0 then .done 0 oldCount else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0
  else .done s 0 else .done unsupported 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0 else .done malformed 0

/-- Inputs stay immutable throughout this non-yielding checked-memory Action.
Only target is written; its magic stays zero until the root finishes staging. -/
private def cloneContents (buffer document target : UInt64) : Action :=
  .bind (put target 0 0) fun s _ => if s = 0 then
  .boundedFoldU64 463 copyBindingStep 463 0 (buffer+8) (target+8) 0 0 fun s _ => if s = 0 then
  Mathematics.copyCurrent document (target+inner) else .done s 0 else .done s 0

/-- Stage an edit, hint or unchanged-attempt update. Existing package bindings
stay exact, while an edited current binding becomes inapplicable independently.
The integrating Notebook publishes/saves target only after this succeeds. -/
def stageRefresh (buffer document target : UInt64) : Action :=
  .bind (transitionBase buffer document target 0) fun s _ => if s = 0 then
  .bind (cloneContents buffer document target) fun s copied => if s = 0 then
  if copied = Mathematics.currentBytes then
  .bind (put target 0 magic) fun s _ => if s = 0 then .done 0 target else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0

/-- Bind only the one actual new Protocol7 attempt. The existing guest client
must already have admitted the exact reply and completed the original Doc8.
This adds package provenance; it does not invoke or replace mathematical checking.
Death, OOM, cancellation, stale replies or history exhaustion do not call it. -/
def stageCompleted (buffer document submitted request target : UInt64) : Action :=
  if request = 0 then .done malformed 0 else if 0x7ffffffffffffffe < request then .done malformed 0 else
  if submitted % 8 = 0 then if separate submitted PackageBinding.bytes target bytes = 1 then
  .bind (transitionBase buffer document target 1) fun s oldCount => if s = 0 then
  if oldCount < 8 then
  .bind (field buffer 48) fun s mask => if s = 0 then if (mask >>> 8) &&& 1 = 1 then
  .boundedFoldU64 16 equalWordsStep 16 0 (buffer+selection) submitted 0 0 fun s _ => if s = 0 then
  .bind (field (buffer+inner) 40) fun s revision => if s = 0 then
  .bind (field (buffer+inner) 48) fun s goal => if s = 0 then
  .bind (field (buffer+inner) 120) fun s domain => if s = 0 then
  .bind (field (buffer+inner) 128) fun s assumptions => if s = 0 then
  .bind (PackageBinding.applicable submitted revision goal domain assumptions) fun s applies => if s = 0 then
  if applies = 1 then
  .bind (field submitted 96) fun s declaredBudget => if s = 0 then
  .bind (field document 136) fun s actualBudget => if s = 0 then
  if declaredBudget = actualBudget then
  .boundedFoldU64 10 equalSubmissionStep 10 0 (buffer+inner) document 0 0 fun s _ => if s = 0 then
  .bind (field document (1920+56)) fun s origin => if s = 0 then if origin = 7 then
  .bind (field document 1920) fun s actualRequest => if s = 0 then if actualRequest = request then
  .bind (cloneContents buffer document target) fun s copied => if s = 0 then
  if copied = Mathematics.currentBytes then
  .bind (copyBinding submitted (target+attempts+oldCount*PackageBinding.bytes)) fun s _ => if s = 0 then
  .bind (put target 48 (mask ||| ((1 : UInt64) <<< oldCount))) fun s _ => if s = 0 then
  .bind (put target 0 magic) fun s _ => if s = 0 then .done 0 target else .done s 0
  else .done s 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done s 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done s 0
  else .done selectionAbsent 0 else .done s 0
  else .done resourceLimit 0 else .done s 0
  else .done malformed 0 else .done malformed 0


/-- An explicit builtin/non-package selection retains every known historical
package row, clears only the current selection, and stages the actual changed
Doc8. Caller cancels any outstanding check before producing that revision. -/
def stageUnknownSelection (buffer document target : UInt64) : Action :=
  .bind (transitionBase buffer document target 0) fun s _ => if s = 0 then
  .bind (field buffer 48) fun s mask => if s = 0 then
  .bind (cloneContents buffer document target) fun s copied => if s = 0 then
  if copied = Mathematics.currentBytes then
  .boundedFoldU64 16 zeroStep 16 0 (target+selection) 0 0 0 fun s _ => if s = 0 then
  .bind (put target 48 (mask &&& 255)) fun s _ => if s = 0 then
  .bind (put target 0 magic) fun s _ => if s = 0 then .done 0 target else .done s 0
  else .done s 0 else .done s 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0

/-- A real completed builtin request has explicitly Unknown package origin.
Exactly one new Doc8 attempt is admitted while all earlier known/unknown rows
and learner-event prefixes stay exact. No current package binding is inherited.
The existing Protocol7 client/reply admission remains the execution authority. -/
def stageCompletedUnknown (buffer document request target : UInt64) : Action :=
  if request = 0 then .done malformed 0 else if 0x7ffffffffffffffe < request then .done malformed 0 else
  .bind (transitionBase buffer document target 1) fun s oldCount => if s = 0 then
  if oldCount < 8 then
  .bind (field buffer 48) fun s mask => if s = 0 then if (mask >>> 8) &&& 1 = 0 then
  .boundedFoldU64 10 equalSubmissionStep 10 0 (buffer+inner) document 0 0 fun s _ => if s = 0 then
  .bind (field document (1920+56)) fun s origin => if s = 0 then if origin = 7 then
  .bind (field document 1920) fun s actualRequest => if s = 0 then if actualRequest = request then
  .bind (cloneContents buffer document target) fun s copied => if s = 0 then
  if copied = Mathematics.currentBytes then
  .bind (put target 0 magic) fun s _ => if s = 0 then .done 0 target else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done s 0 else .done malformed 0 else .done s 0
  else .done s 0 else .done malformed 0 else .done s 0
  else .done resourceLimit 0 else .done s 0

end Lemma.Courses.PackageWorkspace
