import Lemma.Courses.PackageFormat

/-! Owner-local raw-console package transport, `lemma-course-command/1`.
Every command is eight little-endian UInt64 words: magic,version,operation,
identity,edition,payloadBytes,transaction-or-nodeOrdinal,expectedPackageCRC32.
Install1 is followed by exactly payloadBytes opaque package bytes. Load2 and
DeleteProbe3 have no body. This is an integrity-only local developer/author
transport, not authenticated remote tutoring or a new storage authority. -/
namespace Lemma.Courses.PackageCommand
open PackageFormat

def magic : UInt64 := 0x31504b43414d454c
def version : UInt64 := 1
def headerBytes : UInt64 := 64

def shape (actualMagic actualVersion operation identity edition bytes transaction crc : UInt64) : UInt8 :=
  if actualMagic = magic then if actualVersion = version then
  if identity = 0 then malformed else if maximumIdentity < identity then malformed else
  if edition = 0 then malformed else if maximumEdition < edition then malformed else
  if crc ≤ 0xffffffff then
  if operation = 1 then
    if bytes < 128 then malformed else if maximumBytes < bytes then resourceLimit else
    if transaction = 0 then malformed else if transaction ≤ 0x7fffffffffffffff then 0 else malformed
  else if operation = 2 then
    if bytes = 0 then if transaction < 16 then 0 else selectionAbsent else malformed
  else if operation = 3 then
    if bytes = 0 then if transaction = 0 then malformed else if transaction ≤ 0x7fffffffffffffff then 0 else malformed else malformed
  else unsupported
  else malformed else unsupported else malformed

end Lemma.Courses.PackageCommand
