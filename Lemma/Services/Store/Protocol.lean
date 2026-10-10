import Lemma.Services.Store.Format

/-! Document endpoint application framing, v1. The kernel-stamped sender and
reply capability are deliberately outside this caller-written header. -/
namespace Lemma.Services.Store.Protocol
open Lemma.Core0.Memory

def magic : UInt64 := 0x31525453414d454c
def version : UInt64 := 1
def headerBytes : UInt64 := 64
def maximumChunk : UInt64 := 128
def busy : UInt8 := 231
def wrongOwner : UInt8 := 232
def incomplete : UInt8 := 233

def namespaceValid (ns : UInt64) : UInt64 := if ns = 1 then 1 else if ns = 2 then 1 else 0
def field (packet offset : UInt64) : Action :=
  if offset % 8 = 0 then if offset < 64 then Lemma.User.Memory.read64 (packet + offset)
  else .done Format.malformed 0 else .done Format.malformed 0

def header (packet operation ns object transaction offset count : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 packet magic) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 8) version) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 16) operation) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 24) ns) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 32) object) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 40) transaction) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 48) offset) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (packet + 56) count) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0

def shape (operation ns object transaction offset count bytes : UInt64) : UInt64 :=
  if operation = 11 then
    if ns = 0 then if object = 0 then if transaction = 0 then
    if offset = 0 then if count = 0 then if bytes = 64 then 1 else 0 else 0 else 0
    else 0 else 0 else 0
  else if namespaceValid ns = 1 then
    if operation = 2 then
      if 0 < object then if 0 < transaction then if offset = 0 then
      if count ≤ Format.maximumPayload then if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 3 then
      if 0 < object then if 0 < transaction then if count ≤ maximumChunk then
      if bytes = 64 + count then 1 else 0 else 0 else 0 else 0
    else if operation = 5 then
      if 0 < object then if transaction = 0 then if count ≤ maximumChunk then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0
    else if operation = 4 then
      if 0 < object then if 0 < transaction then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 6 then
      if 0 < object then if 0 < transaction then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 9 then
      if 0 < object then if 0 < transaction then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 1 then
      if object = 0 then if transaction = 0 then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 7 then
      if object = 0 then if transaction = 0 then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 8 then
      if object = 0 then if transaction = 0 then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else if operation = 10 then
      if object = 0 then if transaction = 0 then if offset = 0 then if count = 0 then
      if bytes = 64 then 1 else 0 else 0 else 0 else 0 else 0
    else 0
  else 0

end Lemma.Services.Store.Protocol
