import Lemma.Services.Arithmetic.Protocol
import Lemma.Mathematics.ExecutionIdentityV5

namespace Lemma.Services.Arithmetic.ProtocolV6
open Lemma.Core0.Memory Lemma.User

def version : UInt64 := 6
def requestBytes : UInt64 := 144
def replyBytes : UInt64 := 112
def implementation : UInt64 := Lemma.Mathematics.ExecutionIdentityV5.implementation
def lowering : UInt64 := Lemma.Mathematics.ExecutionIdentityV5.lowering
def runtime : UInt64 := Lemma.Mathematics.ExecutionIdentityV5.runtime
def resources : UInt64 := Lemma.Mathematics.ExecutionIdentityV5.resources

def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value
private def identities (buffer offset : UInt64) : Action :=
  .bind (put buffer offset implementation) fun s _ => if s = 0 then
  .bind (put buffer (offset + 8) lowering) fun s _ => if s = 0 then
  .bind (put buffer (offset + 16) runtime) fun s _ => if s = 0 then
  put buffer (offset + 24) resources else .done s 0 else .done s 0 else .done s 0

/-- Historical protocol1 has its original routines and wire lengths. This is a
new bounded-String request that demands a closed implementation authority before submission. -/
def request (buffer ns page revision goal n d p0 p1 p2 budget request : UInt64) : Action :=
  .bind (Lemma.Services.Arithmetic.Protocol.request buffer ns page revision goal n d p0 p1 p2 budget request) fun s _ => if s = 0 then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  identities buffer 112 else .done s 0 else .done s 0

def reply (buffer ns page revision goal outcome budget request : UInt64) : Action :=
  .bind (Lemma.Services.Arithmetic.Protocol.reply buffer ns page revision goal outcome budget request) fun s _ => if s = 0 then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  identities buffer 80 else .done s 0 else .done s 0

/-- The server does not claim an implementation requested by an untrusted
client unless every closed authority and resource contract is supported. -/
def validateRequest (buffer : UInt64) : Action :=
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 112) fun s actual => if s = 0 then if actual = implementation then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 120) fun s actual => if s = 0 then if actual = lowering then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 128) fun s actual => if s = 0 then if actual = runtime then
  .bind (Lemma.Services.Arithmetic.Protocol.field buffer 136) fun s actual => if s = 0 then
  if actual = resources then .done 0 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0 else .done 234 0
  else .done s 0 else .done 234 0 else .done s 0

end Lemma.Services.Arithmetic.ProtocolV6
