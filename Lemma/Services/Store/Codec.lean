import Lemma.Services.Store.Format

namespace Lemma.Services.Store.Codec
open Lemma.Core0.Memory
open Format

def root (buffer capacity generation segment count tail sequence : UInt64) : Action :=
  if rootShape capacity generation segment count tail sequence = 1 then
  let hash := rootHash capacity generation segment count tail sequence
  .bind (clearSector buffer) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 buffer rootMagic) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 8) version) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 16) generation) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 24) capacity) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 32) segment) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 40) (segmentStart capacity segment)) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 48) (segmentLength capacity)) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 56) count) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 64) tail) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 72) sequence) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 80) hash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 88) (~~~hash)) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0

/-- A validated root is copied to a private 64-byte candidate row. Empty/torn
slots return value0 without authorizing format. Unsupported version rejects. -/
def readRoot (buffer capacity candidate : UInt64) : Action :=
  .bind (Lemma.User.Memory.write64 candidate 0) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.read64 buffer) fun s magic => if s = 0 then
  if magic = rootMagic then
  .bind (Lemma.User.Memory.read64 (buffer + 8)) fun s ver => if s = 0 then
  if ver = version then
  .bind (Lemma.User.Memory.read64 (buffer + 16)) fun s generation => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 24)) fun s cap => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 32)) fun s segment => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 40)) fun s start => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 48)) fun s length => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 56)) fun s count => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 64)) fun s tail => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 72)) fun s sequence => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 80)) fun s hash => if s = 0 then
  .bind (Lemma.User.Memory.read64 (buffer + 88)) fun s inverse => if s = 0 then
  .bind (reservedZero buffer 96) fun reserved _ =>
  if reserved = 0 then if cap = capacity then
  if rootShape cap generation segment count tail sequence = 1 then
  if start = segmentStart cap segment then if length = segmentLength cap then
  if hash = rootHash cap generation segment count tail sequence then if inverse = ~~~hash then
  .bind (Lemma.User.Memory.write64 (candidate + 8) segment) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (candidate + 16) count) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (candidate + 24) tail) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (candidate + 32) sequence) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (candidate + 40) hash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 candidate generation) fun s _ => .done s generation
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done 0 0 else .done 0 0 else .done 0 0 else .done 0 0
  else .done 0 0 else .done 0 0 else .done 0 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0
  else .done unsupported 0 else .done s 0
  else .done 0 0 else .done s 0 else .done s 0

def record (buffer generation ns object transaction sequence length kind payloadHash : UInt64) : Action :=
  if recordShape ns object transaction sequence length kind = 1 then
  let hash := recordHash generation ns object transaction sequence length kind payloadHash
  .bind (clearSector buffer) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 buffer recordMagic) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 8) version) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 16) generation) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 24) ns) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 32) object) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 40) transaction) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 48) sequence) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 56) length) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 64) kind) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 72) (payloadSectors length)) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 80) payloadHash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 88) hash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 96) (~~~hash)) fun s _ => .done s hash
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0

def publication (buffer generation ns object transaction sequence length kind payloadHash : UInt64) : Action :=
  if recordShape ns object transaction sequence length kind = 1 then
  let headerHash := recordHash generation ns object transaction sequence length kind payloadHash
  let hash := publicationHash generation ns object transaction sequence length kind payloadHash headerHash
  .bind (record buffer generation ns object transaction sequence length kind payloadHash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 buffer commitMagic) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 72) payloadHash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 80) headerHash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 88) hash) fun s _ => if s = 0 then
  .bind (Lemma.User.Memory.write64 (buffer + 96) (~~~hash)) fun s _ => .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0
  else .done malformed 0

end Lemma.Services.Store.Codec
