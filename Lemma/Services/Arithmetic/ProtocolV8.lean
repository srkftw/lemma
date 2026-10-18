import Lemma.Multimodal.Parameterized
import Lemma.Services.Arithmetic.Protocol

/-! Additive parameterized arithmetic copied protocol. The192byte task envelope
is defined by Parameterized; reply echoes its first22words exactly and replaces
reserved words22/23 with outcome/checker identity. All old protocols unchanged.
The tutor never receives the isolated endpoint capability. -/
namespace Lemma.Services.Arithmetic.ProtocolV8
open Lemma.Core0.Memory Lemma.User

def version : UInt64 := 2
def requestBytes : UInt64 := 192
def replyBytes : UInt64 := 192
def checkerIdentity : UInt64 := Lemma.Multimodal.Parameterized.checkerIdentity
private def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer+offset) value

def request (buffer source edition object task revision kind assumptions a b c d n den p0 p1 p2 budget submission assisted session consent : UInt64) : Action :=
  if submission = 0 then .done 234 0 else if 0x7ffffffffffffffe < submission then .done 234 0 else
  if Lemma.Multimodal.Parameterized.validIdentity source edition object task revision session = false then .done 234 0 else
  .bind (put buffer 0 version) fun s _ => if s = 0 then
  .bind (put buffer 8 source) fun s _ => if s = 0 then
  .bind (put buffer 16 edition) fun s _ => if s = 0 then
  .bind (put buffer 24 object) fun s _ => if s = 0 then
  .bind (put buffer 32 task) fun s _ => if s = 0 then
  .bind (put buffer 40 revision) fun s _ => if s = 0 then
  .bind (put buffer 48 kind) fun s _ => if s = 0 then
  .bind (put buffer 56 assumptions) fun s _ => if s = 0 then
  .bind (put buffer 64 a) fun s _ => if s = 0 then
  .bind (put buffer 72 b) fun s _ => if s = 0 then
  .bind (put buffer 80 c) fun s _ => if s = 0 then
  .bind (put buffer 88 d) fun s _ => if s = 0 then
  .bind (put buffer 96 n) fun s _ => if s = 0 then
  .bind (put buffer 104 den) fun s _ => if s = 0 then
  .bind (put buffer 112 p0) fun s _ => if s = 0 then
  .bind (put buffer 120 p1) fun s _ => if s = 0 then
  .bind (put buffer 128 p2) fun s _ => if s = 0 then
  .bind (put buffer 136 budget) fun s _ => if s = 0 then
  .bind (put buffer 144 submission) fun s _ => if s = 0 then
  .bind (put buffer 152 assisted) fun s _ => if s = 0 then
  .bind (put buffer 160 session) fun s _ => if s = 0 then
  .bind (put buffer 168 consent) fun s _ => if s = 0 then
  .bind (put buffer 176 0) fun s _ => if s = 0 then
  put buffer 184 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0
private def copyStep (i _ : UInt32) (acc source target _ _ : UInt64) : Action :=
  .bind (Memory.read64 (source+i.toUInt64*8)) fun s value => if s = 0 then
  .bind (Memory.write64 (target+i.toUInt64*8) value) fun s _ => .done s acc else .done s 0

def reply (request output outcome : UInt64) : Action :=
  .boundedFoldU64 22 copyStep 22 0 request output 0 0 fun s _ => if s = 0 then
  .bind (put output 176 outcome) fun s _ => if s = 0 then put output 184 checkerIdentity else .done s 0
  else .done s 0
end Lemma.Services.Arithmetic.ProtocolV8
