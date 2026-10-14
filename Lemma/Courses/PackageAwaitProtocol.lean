import Lemma.Services.Store.Protocol
import Lemma.User.IPC

/-! `lemma-course-mounted-await/1` is a course-only copied endpoint operation.
It is separate from historical status8 and recovery14/15. A pending request
does not mean Ready. Only a completed guest mount can produce status0/mode1.
This grants no formatting authority and creates no durability receipt. -/
namespace Lemma.Courses.PackageAwaitProtocol
open Lemma.Core0.Memory
open Lemma.Services.Store

def version : UInt64 := 2
def operation : UInt64 := 16
def maximumWaitTicks : UInt64 := 300000000
def maximumWaiters : UInt64 := 4

/-- Request words are magic/version/op/namespace/object0/initializer/0/0.
Initializer1 only waits through unformatted media; it cannot format them. -/
def shape (magic ver op ns object initialization offset count bytes : UInt64) : UInt64 :=
  if magic = Protocol.magic then if ver = version then if op = operation then
  if Protocol.namespaceValid ns = 1 then if object = 0 then if initialization ≤ 1 then
  if offset ||| count = 0 then if bytes = 64 then 1 else 0 else 0
  else 0 else 0 else 0 else 0 else 0 else 0

def header (buffer ns initialization : UInt64) : Action :=
  if buffer % 8 = 0 then if buffer ≤ 0xffffffffffffffff - 64 then
  if Protocol.namespaceValid ns = 1 then if initialization ≤ 1 then
  .bind (Lemma.User.Memory.write64 buffer Protocol.magic) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 8) version) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 16) operation) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 24) ns) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 32) 0) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 40) initialization) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 48) 0) fun s _ => if s = 0 then
  Lemma.User.Memory.write64 (buffer + 56) 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
  else .done Format.malformed 0 else .done Format.malformed 0
  else .done Format.malformed 0 else .done Format.malformed 0

/-- The final word is the actual validated root generation, not a payload count.
Success requires published writable mount1, a positive root generation and an
ordinary bounded sequence. Unformatted2/read-only3/busy0 are explicit errors.
The root generation is on-disk mount identity, not a device/session/auth epoch. -/
def resultValid (status mode sequence generation : UInt64) : UInt64 :=
  if sequence ≤ Format.maximumSequence then
  if status = 0 then if mode = 1 then if 0 < generation then
    if generation ≤ Format.maximumSequence then 1 else 0 else 0 else 0
  else if status = Format.unformatted.toUInt64 then if mode = 2 then 1 else 0
  else if status = Format.readOnly.toUInt64 then if mode = 3 then 1 else 0
  else if status = Protocol.busy.toUInt64 then if mode = 0 then 1 else 0
  else if status = Format.malformed.toUInt64 then if mode = 0 then 1 else 0
  else if status = Format.unsupported.toUInt64 then if mode = 0 then 1 else 0
  else if status = Lemma.User.IPCABI.timeout.toUInt64 then if mode = 0 then 1 else 0
  else 0
  else 0

end Lemma.Courses.PackageAwaitProtocol
