import Lemma.Courses.PackageWorkspace
import Lemma.Services.Arithmetic.ClientV9

/-! Shared owned local-tool client semantics. The containing Notebook owns
all storage barriers, UI scheduling and capabilities; no host participates. -/
namespace Lemma.Courses.LocalReduction
open Lemma.Core0.Memory Lemma.User
private def read (p o : UInt64) : Action := Memory.read64 (p+o)
private def write (p o v : UInt64) : Action := Memory.write64 (p+o) v

/-- Read the validated existing task origin, including a stale checking
selection after numeric edits. That provenance does not make checking current.
Unknown work stays explicitly unbound. It never borrows the help overlay. -/
def request (workspace document outgoing event crcAddress ns page requestID : UInt64) : Action :=
  .bind (PackageWorkspace.validate workspace ns page) fun s _ => if s = 0 then
  .bind (read document 40) fun s revision => if s = 0 then
  .bind (read document 48) fun s goal => if s = 0 then
  .bind (read document 56) fun s n => if s = 0 then
  .bind (read document 64) fun s d => if s = 0 then
  .bind (read document 192) fun s count => if s = 0 then
  if goal = 1 then if count ≤ 48 then if d = 0 then .done 234 0 else
  .bind (Lemma.Documents.LocalToolEvents.freshRequestID document requestID (outgoing+128)) fun s freshID => if s = 0 then
  .bind (read workspace 48) fun s mask => if s = 0 then
  .bind (if (mask >>> 8) &&& 1 = 1 then
    .bind (read (workspace+PackageWorkspace.selection) 16) fun s source => if s = 0 then
    .bind (read (workspace+PackageWorkspace.selection) 24) fun s edition => if s = 0 then
    .bind (read (workspace+PackageWorkspace.selection) 32) fun s crc => if s = 0 then
    .bind (read (workspace+PackageWorkspace.selection) 40) fun s node => if s = 0 then
    .bind (read (workspace+PackageWorkspace.selection) 64) fun s selectedGoal => if s = 0 then
    if selectedGoal = 1 then
    .bind (write crcAddress 0 crc) fun s _ => if s = 0 then
    Lemma.Services.Arithmetic.ProtocolV9.request outgoing source edition (PackageWorkspace.object page) node revision ns page n d freshID 0 0
    else .done s 0 else .done 240 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else
      .bind (write crcAddress 0 0) fun s _ => if s = 0 then
      Lemma.Services.Arithmetic.ProtocolV9.request outgoing 0 0 (PackageWorkspace.object page) 0 revision ns page n d freshID 0 0 else .done s 0)
    fun s _ => if s = 0 then
  .bind (read crcAddress 0) fun s crc => if s = 0 then
  .bind (Lemma.Documents.LocalToolEvents.prepare event outgoing crc) fun s _ => .done s freshID
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 235 0 else .done 234 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def same (a ao b bo : UInt64) : Action :=
  .bind (read a ao) fun s x => if s = 0 then
  .bind (read b bo) fun s y => if s = 0 then
  if x = y then .done 0 0 else .done 234 0 else .done s 0 else .done s 0

def current (workspace document request event ns page : UInt64) : Action :=
  .bind (PackageWorkspace.validate workspace ns page) fun s _ => if s = 0 then check else .done s 0
where
  origin : Action :=
    .bind (read workspace 48) fun s mask => if s = 0 then
    .bind (read request 24) fun s source => if s = 0 then
    if source = 0 then if (mask >>> 8) &&& 1 = 0 then .done 0 0 else .done 234 0 else
    .bind (if (mask >>> 8) &&& 1 = 1 then .done 0 0 else .done 234 0) fun s _ => if s = 0 then
    .bind (same (workspace+PackageWorkspace.selection) 16 request 24) fun s _ => if s = 0 then
    .bind (same (workspace+PackageWorkspace.selection) 24 request 32) fun s _ => if s = 0 then
    .bind (same (workspace+PackageWorkspace.selection) 40 request 48) fun s _ => if s = 0 then
    same (workspace+PackageWorkspace.selection) 32 event 64
    else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else .done s 0 else .done s 0
  check : Action :=
    .bind (same document 24 request 64) fun s _ => if s = 0 then
    .bind (same document 32 request 72) fun s _ => if s = 0 then
    .bind (same document 40 request 56) fun s _ => if s = 0 then
    .bind (same document 56 request 80) fun s _ => if s = 0 then
    .bind (same document 64 request 88) fun s _ => if s = 0 then
    .bind (read request 40) fun s object => if s = 0 then
    .bind (if object = PackageWorkspace.object page then .done 0 0 else .done 234 0) fun s _ => if s = 0 then
    .bind (read document 48) fun s goal => if s = 0 then
    .bind (if goal = 1 then .done 0 0 else .done 234 0) fun s _ => if s = 0 then origin
    else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
    else .done s 0 else .done s 0 else .done s 0 else .done s 0

def stagePrepared (workspace document stagedDocument stagedWorkspace event : UInt64) : Action :=
  .bind (Lemma.Documents.Mathematics.copyCurrent document stagedDocument) fun s _ => if s = 0 then
  .bind (Lemma.Documents.LocalToolEvents.append stagedDocument event) fun s _ => if s = 0 then
  PackageWorkspace.stageRefresh workspace stagedDocument stagedWorkspace else .done s 0 else .done s 0

/-- Admitted reply bytes only. Recheck every current-work field and captured
source CRC before the staged edit; a later CHECK is separate evidence. -/
def stageApplied (workspace document stagedDocument stagedWorkspace request event reply ns page : UInt64) : Action :=
  .bind (current workspace document request event ns page) fun s _ => if s = 0 then
  .bind (read reply (IPCABI.headerBytes+144)) fun s n => if s = 0 then
  .bind (read reply (IPCABI.headerBytes+152)) fun s d => if s = 0 then
  .bind (read reply (IPCABI.headerBytes+160)) fun s outcome => if s = 0 then
  .bind (read event 0) fun s revision => if s = 0 then
  .bind (write event 8 (Lemma.Documents.LocalToolEvents.descriptor 2 outcome)) fun s _ => if s = 0 then
  .bind (write event 16 (revision+1)) fun s _ => if s = 0 then
  .bind (write event 96 n) fun s _ => if s = 0 then
  .bind (write event 104 d) fun s _ => if s = 0 then
  .bind (Lemma.Documents.Mathematics.copyCurrent document stagedDocument) fun s _ => if s = 0 then
  .bind (Lemma.Documents.Mathematics.applyLocalTool stagedDocument event) fun s _ => if s = 0 then
  PackageWorkspace.stageRefresh workspace stagedDocument stagedWorkspace
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

def stageTerminal (workspace document stagedDocument stagedWorkspace event outcome ns page : UInt64) : Action :=
  .bind (PackageWorkspace.validate workspace ns page) fun s _ => if s = 0 then
  .bind (write event 8 (Lemma.Documents.LocalToolEvents.descriptor 3 outcome)) fun s _ => if s = 0 then
  .bind (write event 16 0) fun s _ => if s = 0 then
  .bind (write event 96 0) fun s _ => if s = 0 then
  .bind (write event 104 0) fun s _ => if s = 0 then
  stagePrepared workspace document stagedDocument stagedWorkspace event
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
end Lemma.Courses.LocalReduction
