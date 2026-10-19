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

/-- Additive selected-publication command/record. Ordinary v1 frames retain
their old decoder; only the explicitly selected installer root admits v2/op9.
The durable record lives apart from immutable package objects and notebooks. -/
def selectedCommandVersion : UInt64 := 2
def selectedNodeCommandVersion : UInt64 := 4
def ackCommandVersion : UInt64 := 3
def ackObject : UInt64 := 0x5350000000000002
def ackMagic : UInt64 := 0x314b4341534d454c
def selectedMagic : UInt64 := 0x3154534c534d454c
def selectedVersion : UInt64 := 1
def selectedNamespace : UInt64 := 2
def selectedObject : UInt64 := 0x7fffffffffffff01
def selectedBytes : UInt64 := 64
def selectedPackageNamespace : UInt64 := 1

def selectionShape (tag recordVersion ns identity edition crc ordinal reserved : UInt64) : UInt64 :=
  if tag = selectedMagic then if recordVersion = selectedVersion then
  if ns = selectedPackageNamespace then
  if identity = 0 then 0 else if maximumIdentity < identity then 0 else
  if edition = 0 then 0 else if maximumEdition < edition then 0 else
  if crc ≤ 0xffffffff then if ordinal < maximumEntries then if reserved = 0 then 1 else 0
  else 0 else 0 else 0 else 0 else 0

def selectionCommandShape (actualMagic actualVersion operation identity edition ordinal transaction crc : UInt64) : UInt8 :=
  if actualMagic = magic then
  if (if actualVersion = selectedCommandVersion then (1 : UInt64) else
      if actualVersion = selectedNodeCommandVersion then 1 else 0) = 1 then
  if operation = 9 then
  if selectionShape selectedMagic selectedVersion selectedPackageNamespace identity edition crc ordinal 0 = 1 then
  if (if actualVersion = selectedCommandVersion then if ordinal = 0 then (1 : UInt64) else 0 else 1) = 1 then
  if transaction = 0 then malformed else if transaction ≤ 0x7fffffffffffffff then 0 else malformed
  else malformed else malformed else unsupported else unsupported else malformed

def ackCommandShape (actualMagic actualVersion operation queue schoolCommit bytes localCommit crc : UInt64) : UInt8 :=
  if actualMagic = magic then if actualVersion = ackCommandVersion then if operation = 10 then
  if queue >>> 48 = 0x5351 then if 0 < (queue &&& 0x0000ffffffffffff) then
  if 0 < schoolCommit then if schoolCommit ≤ 0x7fffffffffffffff then
  if bytes = 0 then if 0 < localCommit then if localCommit ≤ 0x7fffffffffffffff then
  if crc ≤ 0xffffffff then 0 else malformed else malformed else malformed else malformed
  else malformed else malformed else malformed else malformed else unsupported else unsupported else malformed

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
