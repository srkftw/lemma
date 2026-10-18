import Lemma.Mathematics.Exact
import Lemma.User.Memory

/-! Additive parameterized task binding, lemma-task/2. This retains the original
exact checker, changes neither legacy goal nor document bytes, and admits fresh
operands after boot. Task authority fixes source/edition/object/task/assumption
identities; a tutor's answer is never a student submission. -/
namespace Lemma.Multimodal.Parameterized
private def different (a b : UInt64) : Bool := if a = b then false else true
open Lemma.Core0.Memory Lemma.User

def version : UInt64 := 2
def checkerIdentity : UInt64 := 0x0002000000000001
def requestBytes : UInt64 := 192
/-- Offsets: version, source, edition, object, task, revision, kind, assumptions,
    a,b,c,d,n,den,p0,p1,p2,budget,submission,assisted,session,consent,reserved[2]. -/
def validIdentity (source edition object task revision session : UInt64) : Bool :=
  if source = 0 then false else if edition = 0 then false else
  if object = 0 then false else if task = 0 then false else
  if revision = 0 then false else if session = 0 then false else
  if 0x7ffffffffffffffe < revision then false else true

/-- Kind1 is a/b+c/d=n/den in Q. Kind2 is (a*x+b)*(c*x+d)
    =p0+p1*x+p2*x*x in Q[x]. All signed values retain Exact's sign/magnitude
    encoding and explicit resource/ambiguity outcomes. No general proof kernel. -/
def check (kind assumptions a b c d n den p0 p1 p2 budget : UInt64) : UInt64 :=
  if different (assumptions) (0) = true then Lemma.Mathematics.Exact.unsupported else
  if kind = 1 then Lemma.Mathematics.Exact.rational a b c d n den budget else
  if kind = 2 then Lemma.Mathematics.Exact.polynomial a b c d p0 p1 p2 budget else
  Lemma.Mathematics.Exact.unsupported

def evaluate (request : UInt64) : Action :=
  .bind (Memory.read64 request) fun s actual => if s = 0 then
  if different (actual) (version) = true then .done 234 0 else
  .bind (Memory.read64 (request+8)) fun s source => if s = 0 then
  .bind (Memory.read64 (request+16)) fun s edition => if s = 0 then
  .bind (Memory.read64 (request+24)) fun s object => if s = 0 then
  .bind (Memory.read64 (request+32)) fun s task => if s = 0 then
  .bind (Memory.read64 (request+40)) fun s revision => if s = 0 then
  .bind (Memory.read64 (request+160)) fun s session => if s = 0 then
  if validIdentity source edition object task revision session = false then .done 234 0 else
  .bind (Memory.read64 (request+48)) fun s kind => if s = 0 then
  .bind (Memory.read64 (request+56)) fun s assumptions => if s = 0 then
  .bind (Memory.read64 (request+64)) fun s a => if s = 0 then
  .bind (Memory.read64 (request+72)) fun s b => if s = 0 then
  .bind (Memory.read64 (request+80)) fun s c => if s = 0 then
  .bind (Memory.read64 (request+88)) fun s d => if s = 0 then
  .bind (Memory.read64 (request+96)) fun s n => if s = 0 then
  .bind (Memory.read64 (request+104)) fun s den => if s = 0 then
  .bind (Memory.read64 (request+112)) fun s p0 => if s = 0 then
  .bind (Memory.read64 (request+120)) fun s p1 => if s = 0 then
  .bind (Memory.read64 (request+128)) fun s p2 => if s = 0 then
  .bind (Memory.read64 (request+136)) fun s budget => if s = 0 then
  .bind (Memory.read64 (request+176)) fun s reserved => if s = 0 then
  .bind (Memory.read64 (request+184)) fun s reserved2 => if s = 0 then
  if different (reserved) (0) = true then .done 234 0 else if different (reserved2) (0) = true then .done 234 0 else
  .done 0 (check kind assumptions a b c d n den p0 p1 p2 budget)
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

end Lemma.Multimodal.Parameterized
