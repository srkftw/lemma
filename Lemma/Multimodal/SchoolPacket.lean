import Lemma.Multimodal.TutorPackage

/-! Explicit owner-local school JOIN and assistance/3. The first192 action
bytes retain every v2 field meaning (including three reserved-zero words).
The appended64 bytes bind a full authority digest, durable binding record,
generation, guest deadline and policy. The hosted authority resolves that
record to principal/enrollment; no remote authentication is inferred here. -/
namespace Lemma.Multimodal.SchoolPacket
open Lemma.Core0.Memory Lemma.User Lemma.Courses.PackageFormat
private def different (a b : UInt64) : Bool := if a = b then false else true
def magic : UInt64 := 0x314e494f4a484353
def invitationBytes : UInt64 := 104
def actionBytes : UInt64 := 256
private def word (address offset : UInt64) : Action := Memory.read64 (address+offset)
private def markerByte (kind index : UInt64) : UInt64 :=
  let packed := if kind = 1 then
    if index/8 = 0 then 0x63732d616d6d656c else if index/8 = 1 then 0x7365732d6c6f6f68 else 0x312f6e6f6973
  else if index/8 = 0 then 0x63732d616d6d656c else if index/8 = 1 then 0x7373612d6c6f6f68 else
    if index/8 = 2 then 0x2f65636e61747369 else 0x33
  (packed >>> (index%8*8)) &&& 255
private def markerStep (i _ : UInt32) (acc address kind _ _ : UInt64) : Action :=
  .bind (Memory.read8 (address+i.toUInt64)) fun s byte => if s = 0 then
  .done 0 (acc ||| (byte ^^^ markerByte kind i.toUInt64)) else .done s 0
private def nibble (byte : UInt64) : UInt64 :=
  if 48 ≤ byte then if byte ≤ 57 then byte-48 else
  if 97 ≤ byte then if byte ≤ 102 then byte-87 else 256 else 256 else 256
private def decodeStep (i _ : UInt32) (acc address output _ _ : UInt64) : Action :=
  .bind (Memory.read8 (address+i.toUInt64*2)) fun s high => if s = 0 then
  .bind (Memory.read8 (address+i.toUInt64*2+1)) fun s low => if s = 0 then
  let a := nibble high
  let b := nibble low
  if a < 16 then if b < 16 then
  .bind (Memory.write8 (output+i.toUInt64) ((a <<< 4) ||| b)) fun s _ => .done s acc
  else .done malformed 0 else .done malformed 0 else .done s 0 else .done s 0
private def separate (a aBytes b bBytes : UInt64) : Bool :=
  if a ≤ 0xffffffffffffffff-aBytes then if b ≤ 0xffffffffffffffff-bBytes then
  if a ≤ b then aBytes ≤ b-a else bBytes ≤ a-b else false else false
private def actionShape (package packet : UInt64) : Action :=
  .bind (word package 32) fun s edition => if s = 0 then
  .bind (word packet 40) fun s sequence => if s = 0 then
  .bind (word package 248) fun s body => if s = 0 then
  .bind (word packet 104) fun s textBytes => if s = 0 then
  if edition = sequence then if spanLength body = textBytes then .done 0 1 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

/-- kind1 is a104-byte JOIN packet; kind2 is a256-byte school action. The
marker is a distinct package format application; old reserved words stay zero.
0 is ordinary/nonmatching,1 is decoded, access/format errors retain status. -/
def decode (address bytes output kind : UInt64) : Action :=
  let count : UInt64 := if kind = 1 then invitationBytes else actionBytes
  let markerBytes : UInt64 := if kind = 1 then 22 else 25
  if (if kind = 1 then (1 : UInt64) else if kind = 2 then 1 else 0) = 0 then .done malformed 0 else
  if bytes < 128 then .done malformed 0 else if maximumBytes < bytes then .done malformed 0 else
  if address%8 = 0 then if output%8 = 0 then if separate address bytes output count = true then
  .bind (word address 104) fun s source => if s = 0 then
  if spanOffset source < 128 then .done malformed 0 else if bytes < spanOffset source then .done malformed 0 else
  if bytes-spanOffset source < spanLength source then .done malformed 0 else
  if spanLength source = markerBytes then
  .boundedFoldU64 25 markerStep markerBytes.toUInt32 0 (address+spanOffset source) kind 0 0 fun s delta => if s = 0 then
  if delta = 0 then
  .bind (Lemma.Courses.PackageTarget.validate address bytes) fun s _ => if s = 0 then
  .bind (word address 112) fun s packet => if s = 0 then
  if spanLength packet = count*2 then
  .boundedFoldU64 256 decodeStep count.toUInt32 0 (address+spanOffset packet) output 0 0 fun s _ => if s = 0 then
  .bind (word address 24) fun s identity => if s = 0 then
  .bind (word address 40) fun s entries => if s = 0 then
  .bind (word address 136) fun s nodeKind => if s = 0 then
  if identity = (if kind = 1 then 60000 else 60001) then if entries = 1 then if nodeKind = 1 then
  if kind = 1 then .done 0 1 else actionShape address output
  else .done malformed 0 else .done malformed 0 else .done malformed 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done 0 0 else .done s 0 else .done 0 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

private def copyStep (i _ : UInt32) (acc source output _ _ : UInt64) : Action :=
  let offset := (i.toUInt64+1)*8
  .bind (word source offset) fun s value => if s = 0 then
  .bind (Memory.write64 (output+offset) value) fun s _ => .done s acc else .done s 0
private def digestStep (i _ : UInt32) (acc packet _ _ _ : UInt64) : Action :=
  .bind (word packet (16+i.toUInt64*8)) fun s value => if s = 0 then .done 0 (acc ||| value) else .done s 0

/-- Requires a decoded104-byte packet and the still-current original ASK.
Success commits its tag last. A failed staging write invalidates transient
school context; it never creates a joined receipt. -/
def acceptInvitation (package packet context tutor now : UInt64) : Action :=
  if context%8 = 0 then if separate packet invitationBytes context invitationBytes = true then
  if separate context invitationBytes tutor 88 = true then
  .bind (word package 16) fun s length => if s = 0 then
  if separate package length context invitationBytes = true then
  .bind (word packet 0) fun s tag => if s = 0 then
  .bind (word packet 8) fun s version => if s = 0 then
  .bind (word packet 48) fun s binding => if s = 0 then
  .bind (word packet 56) fun s generation => if s = 0 then
  .bind (word packet 64) fun s deadline => if s = 0 then
  .bind (word packet 72) fun s policy => if s = 0 then
  .bind (word packet 80) fun s session => if s = 0 then
  .bind (word packet 88) fun s course => if s = 0 then
  .bind (word packet 96) fun s edition => if s = 0 then
  .bind (word tutor 0) fun s actualSession => if s = 0 then
  .bind (word tutor 32) fun s completed => if s = 0 then
  .bind (word tutor 48) fun s actualCourse => if s = 0 then
  .bind (word tutor 56) fun s actualEdition => if s = 0 then
  .bind (word package 32) fun s sequence => if s = 0 then
  if different tag magic = true then .done 0 20 else if different version 1 = true then .done 0 20 else
  if binding = 0 then .done 0 22 else if 0x7ffffffffffffffe < binding then .done 0 22 else
  if generation = 0 then .done 0 23 else if 0x7ffffffffffffffe < generation then .done 0 23 else
  if policy = 0 then .done 0 25 else if 0x7ffffffffffffffe < policy then .done 0 25 else
  if 0x7ffffffffffffffe < deadline then .done 0 24 else
  if deadline < now then .done 0 24 else if different session actualSession = true then .done 0 26 else
  if different course actualCourse = true then .done 0 27 else if different edition actualEdition = true then .done 0 27 else
  if 0xfffffffe < completed then .done 0 5 else if different sequence (completed+1) = true then .done 0 5 else
  .boundedFoldU64 4 digestStep 4 0 packet 0 0 0 fun s identity => if s = 0 then
  if identity = 0 then .done 0 21 else
  .bind (Memory.write64 context 0) fun s _ => if s = 0 then
  .boundedFoldU64 12 copyStep 12 0 packet context 0 0 fun s _ => if s = 0 then
  .bind (Memory.write64 context magic) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0 else .done s 0
  else .done malformed 0 else .done malformed 0 else .done malformed 0

private def compareStep (i _ : UInt32) (acc proposal context _ _ : UInt64) : Action :=
  if acc = 0 then
  .bind (word proposal (192+i.toUInt64*8)) fun s proposed => if s = 0 then
  .bind (word context (16+i.toUInt64*8)) fun s actual => if s = 0 then
  let reason : UInt64 := if i < 4 then 21 else if i = 4 then 22 else if i = 5 then 23 else if i = 6 then 24 else 25
  .done 0 (if proposed = actual then 0 else reason) else .done s 0 else .done s 0
  else .done 0 acc

def active (context : UInt64) : Action :=
  .bind (word context 0) fun s tag => if s = 0 then .done 0 (if tag = magic then 1 else 0) else .done s 0

/-- All v2 anchor/grant/revision/sequence/claim/annotation rules precede the
additional exact joined binding. Neither response class confers verification. -/
def actionReason (proposal tutor context now : UInt64) : Action :=
  .bind (word proposal 56) fun s start => if s = 0 then
  if now < start then .done 0 7 else
  .bind (TutorAction.validateVersion proposal tutor now 3) fun s old => if s = 0 then
  if old = 0 then
  .bind (active context) fun s joined => if s = 0 then
  if joined = 0 then .done 0 20 else
  .boundedFoldU64 8 compareStep 8 0 proposal context 0 0 fun s mismatch => if s = 0 then
  if mismatch = 0 then
  .bind (word proposal 8) fun s session => if s = 0 then
  .bind (word context 80) fun s actualSession => if s = 0 then
  .bind (word proposal 120) fun s policy => if s = 0 then
  .bind (word context 72) fun s actualPolicy => if s = 0 then
  .bind (word proposal 64) fun s deadline => if s = 0 then
  .bind (word context 64) fun s maximumDeadline => if s = 0 then
  .bind (word proposal 136) fun s course => if s = 0 then
  .bind (word context 88) fun s actualCourse => if s = 0 then
  .bind (word proposal 144) fun s edition => if s = 0 then
  .bind (word context 96) fun s actualEdition => if s = 0 then
  if different session actualSession = true then .done 0 26 else
  if different policy actualPolicy = true then .done 0 25 else
  if maximumDeadline < now then .done 0 24 else if maximumDeadline < deadline then .done 0 24 else
  if different course actualCourse = true then .done 0 27 else if different edition actualEdition = true then .done 0 27 else .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 mismatch else .done s 0 else .done s 0
  else .done 0 old else .done s 0 else .done s 0
end Lemma.Multimodal.SchoolPacket
