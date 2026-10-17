import Lemma.Services.Arithmetic.Protocol
import Lemma.Mathematics.ExecutionIdentityV6

namespace Lemma.Services.Arithmetic.ProtocolV7
open Lemma.Core0.Memory Lemma.User

def version : UInt64 := 7
def requestBytes : UInt64 := 160
def replyBytes : UInt64 := 128
def implementation : UInt64 := Lemma.Mathematics.ExecutionIdentityV6.implementation
def lowering : UInt64 := Lemma.Mathematics.ExecutionIdentityV6.lowering
def runtime : UInt64 := Lemma.Mathematics.ExecutionIdentityV6.runtime
def resources : UInt64 := Lemma.Mathematics.ExecutionIdentityV6.resources

def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value
private def identities (buffer offset : UInt64) : Action :=
  .bind (put buffer offset implementation) fun s _ => if s = 0 then
  .bind (put buffer (offset + 8) lowering) fun s _ => if s = 0 then
  .bind (put buffer (offset + 16) runtime) fun s _ => if s = 0 then
  put buffer (offset + 24) resources else .done s 0 else .done s 0 else .done s 0

private def semantics (buffer offset domain assumptions : UInt64) : Action :=
  .bind (put buffer offset domain) fun s _ => if s = 0 then
  put buffer (offset + 8) assumptions else .done s 0

/-- Only Protocol7 appends the original domain and assumptions to the immutable
copied request. Domain=original goal and no assumptions are the admitted exact/1
context. Protocols1..6 retain their original routines and packet sizes. -/
def request (buffer ns page revision goal n d p0 p1 p2 budget request domain assumptions : UInt64) : Action :=
  if domain = goal then if assumptions = 0 then
  .bind (Lemma.Services.Arithmetic.Protocol.request buffer ns page revision goal n d p0 p1 p2 budget request) fun s _ => if s = 0 then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  .bind (identities buffer 112) fun s _ => if s = 0 then
  semantics buffer 144 domain assumptions else .done s 0 else .done s 0 else .done s 0
  else .done 234 0 else .done 234 0

def reply (buffer ns page revision goal outcome budget request domain assumptions : UInt64) : Action :=
  .bind (Lemma.Services.Arithmetic.Protocol.reply buffer ns page revision goal outcome budget request) fun s _ => if s = 0 then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  .bind (identities buffer 80) fun s _ => if s = 0 then
  semantics buffer 112 domain assumptions else .done s 0 else .done s 0 else .done s 0

/-- An untrusted client cannot request another execution registry, domain or
assumption set and obtain the admitted mathematical implementation authority. -/
def validateRequest (buffer : UInt64) : Action :=
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 112) fun s actual => if s = 0 then if actual = implementation then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 120) fun s actual => if s = 0 then if actual = lowering then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 128) fun s actual => if s = 0 then if actual = runtime then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 136) fun s actual => if s = 0 then if actual = resources then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 48) fun s goal => if s = 0 then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 144) fun s domain => if s = 0 then if domain = goal then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 152) fun s assumptions => if s = 0 then
  if assumptions = 0 then .done 0 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0 else .done s 0
  else .done 234 0 else .done s 0 else .done 234 0 else .done s 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0

end Lemma.Services.Arithmetic.ProtocolV7
