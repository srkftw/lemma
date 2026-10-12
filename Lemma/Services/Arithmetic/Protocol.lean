import Lemma.Mathematics.Exact
import Lemma.User.Memory

/-! Copied-message exact arithmetic protocol v1. The packet contains the
original typed goal and document/revision identity; it carries no proof term,
memory pointer, capability grant or trusted recognition proposal. -/
namespace Lemma.Services.Arithmetic.Protocol
open Lemma.Core0.Memory Lemma.User

def magic : UInt64 := 0x3150434854414d4c
def version : UInt64 := 1
def requestBytes : UInt64 := 112
def replyBytes : UInt64 := 80
def deadlineTicks : UInt64 := 10000000
def field (buffer offset : UInt64) : Action := Memory.read64 (buffer + offset)
def put (buffer offset value : UInt64) : Action := Memory.write64 (buffer + offset) value

def validIdentity (ns page revision goal budget request : UInt64) : Bool :=
  if ns = 0 then false else if 2 < ns then false else
  if page = 0 then false else if 64 < page then false else
  if revision = 0 then false else if 0x7ffffffffffffffe < revision then false else
  if goal = 0 then false else if 3 < goal then false else
  if (if budget = 0 then true else if budget = 8 then true else false) = false then false else
  if request = 0 then false else if 0x7ffffffffffffffe < request then false else true

def request (buffer ns page revision goal n d p0 p1 p2 budget request : UInt64) : Action :=
  if validIdentity ns page revision goal budget request = true then
  .bind (put buffer 0 magic) fun s _ => if s = 0 then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  .bind (put buffer 16 Lemma.Mathematics.Exact.checkerIdentity) fun s _ => if s = 0 then
  .bind (put buffer 24 ns) fun s _ => if s = 0 then
  .bind (put buffer 32 page) fun s _ => if s = 0 then
  .bind (put buffer 40 revision) fun s _ => if s = 0 then
  .bind (put buffer 48 goal) fun s _ => if s = 0 then
  .bind (put buffer 56 n) fun s _ => if s = 0 then
  .bind (put buffer 64 d) fun s _ => if s = 0 then
  .bind (put buffer 72 p0) fun s _ => if s = 0 then
  .bind (put buffer 80 p1) fun s _ => if s = 0 then
  .bind (put buffer 88 p2) fun s _ => if s = 0 then
  .bind (put buffer 96 budget) fun s _ => if s = 0 then
  put buffer 104 request else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done 234 0

def reply (buffer ns page revision goal outcome budget request : UInt64) : Action :=
  .bind (put buffer 0 magic) fun s _ => if s = 0 then
  .bind (put buffer 8 version) fun s _ => if s = 0 then
  .bind (put buffer 16 Lemma.Mathematics.Exact.checkerIdentity) fun s _ => if s = 0 then
  .bind (put buffer 24 ns) fun s _ => if s = 0 then
  .bind (put buffer 32 page) fun s _ => if s = 0 then
  .bind (put buffer 40 revision) fun s _ => if s = 0 then
  .bind (put buffer 48 goal) fun s _ => if s = 0 then
  .bind (put buffer 56 outcome) fun s _ => if s = 0 then
  .bind (put buffer 64 budget) fun s _ => if s = 0 then
  put buffer 72 request else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0

end Lemma.Services.Arithmetic.Protocol
