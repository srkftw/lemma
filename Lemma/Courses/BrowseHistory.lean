import Lemma.Courses.PackageWorkspace

/-! `lemma-course-browse-history/1`: recover a display location from an already
validated workspace. A location is provenance for browsing, never authority for
the current goal, a new submission or evidence. No workspace byte is written.
An explicit current selection wins; otherwise the latest installed source in
completed attempt history supplies the location. No known source returns zero.
The package reader still validates the actual installed package/edition/CRC. -/
namespace Lemma.Courses.BrowseHistory
open Lemma.Core0.Memory
open Lemma.Documents

def version : UInt64 := 1

private def latestStep (i _ : UInt32) (selected buffer count mask _ : UInt64) : Action :=
  let index := i.toUInt64
  if index < count then if (mask >>> index) &&& 1 = 1 then
    .done 0 (buffer + PackageWorkspace.attempts + index * PackageBinding.bytes)
  else .done 0 selected else .done 0 selected

/-- Return an owned binding address for the reader, with zero meaning no known
location. Full validation precedes selection, including Unknown rows, actual
attempt count, request/budget bindings and all reserved fields. This function
neither changes current applicability nor creates a checker result. -/
def location (buffer ns page : UInt64) : Action :=
  .bind (PackageWorkspace.validate buffer ns page) fun s _ =>
  if s = 0 then
    .bind (Lemma.User.Memory.read64 (buffer + 48)) fun s mask => if s = 0 then
    if (mask >>> 8) &&& 1 = 1 then .done 0 (buffer + PackageWorkspace.selection) else
    .bind (Mathematics.field (buffer + PackageWorkspace.inner) 144) fun s count => if s = 0 then
    .boundedFoldU64 8 latestStep 8 0 buffer count mask 0 fun s selected => .done s selected
    else .done s 0 else .done s 0
  else .done s 0
end Lemma.Courses.BrowseHistory
