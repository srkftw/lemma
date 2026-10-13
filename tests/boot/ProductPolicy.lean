import Lemma.Boot.Product

open Lemma.Boot.Product

private def bytesOf (words : Array UInt64) : Array UInt8 := Id.run do
  let mut bytes := #[]
  for word in words do
    for index in [:8] do bytes := bytes.push ((word >>> (index * 8).toUInt64).toUInt8)
  return bytes
private def wordsOf (bytes : Array UInt8) : Array UInt64 := Id.run do
  let mut words := #[]
  for index in [:64] do
    let mut word : UInt64 := 0
    for byte in [:8] do word := word ||| (bytes[index * 8 + byte]!.toUInt64 <<< (byte * 8).toUInt64)
    words := words.push word
  return words
private def checksum (words : Array UInt64) : UInt64 :=
  crcFinish <| (words.extract 0 63).foldl crcWord crcInitial
private def makeMetadata (generation confirmed id trial trialId attempts : UInt64) : Array UInt64 := Id.run do
  let mut words := #[metadataMagic,formatVersion,generation,confirmed,id,trial,trialId,attempts,maximumAttempts]
  for _ in [:54] do words := words.push 0
  words := words.push (checksum words)
  return words
private def metadataValid (words : Array UInt64) : Bool :=
  words.size == 64 &&
  metadataFieldsValid words[0]! words[1]! words[2]! words[3]! words[4]!
    words[5]! words[6]! words[7]! words[8]! &&
  (words.extract 9 63).all (· == 0) && words[63]! == checksum words
private def selected (a b : Array UInt64) : UInt64 :=
  chooseMetadata (if metadataValid a then 1 else 0) (if metadataValid b then 1 else 0)
    a[2]! b[2]! (if a == b then 1 else 0)
private def demand (condition : Bool) (label : String) : IO Unit :=
  unless condition do throw <| IO.userError label

def bootPolicyTests : IO Unit := do
  let text := "123456789".toUTF8
  demand (crcFinish (text.foldl (fun c b => crcByte c b.toUInt64) crcInitial) == 0xcbf43926) "CRC32 standard vector"
  for (word, expected) in #[(0,0x6522df69),(0x0807060504030201,0x3fca88c5),
      (0x1122334455667788,0x1d34f12e),(0xffffffffffffffff,0x2144df1c)] do
    demand (crcFinish (crcWord crcInitial word) == expected) "independent little-endian CRC vector"
  demand (validSegment 4096 700 4096 0x80200000) "valid segment rejected"
  demand (validSegment 4096 0 8 0x80200000) "pure BSS segment rejected"
  for (o,f,m,d) in #[(0,8,8,ramFirst),(512,8,8,ramFirst),(4096,0,0,ramFirst),(4096,8,7,ramFirst),
      (4097,8,8,ramFirst),(4096,8,8,ramFirst+1),(4096,8,8,ramLimit),
      (0xfffffffffffffe00,1024,1024,ramFirst),(4096,8,0xffffffffffffffff,ramFirst)] do
    demand (!validSegment o f m d) "unsafe image span accepted"
  demand (validDiscovery 40 0 && validDiscovery 3072 0xffffffff) "valid bounded discovery rejected"
  demand (!validDiscovery 39 0 && !validDiscovery 3073 0 && !validDiscovery 40 0x100000000) "unsafe discovery length/checksum admitted"
  demand (discoveryWordValid 0x28000000edfe0dd0 40 && !discoveryWordValid 0x28000000edfe0dd0 41 && !discoveryWordValid 0x28000000edfe0dd1 40) "actual FDT magic/big-endian length validation"
  let good := makeMetadata 7 0 11 noTrial 0 0
  let old := makeMetadata 6 0 11 noTrial 0 0
  let trial := makeMetadata 8 0 11 1 22 0
  demand (metadataValid good && metadataValid trial) "valid metadata rejected"
  demand (selected good old == 0 && selected old good == 1) "generation selection"
  demand (selected good good == 0) "exact equal metadata"
  let conflicting := makeMetadata 7 1 22 noTrial 0 0
  demand (selected good conflicting == 3) "same generation conflict accepted"
  -- Every single-bit corruption is rejected; the old peer remains usable.
  let raw := bytesOf trial
  for bit in [:4096] do
    let changed := raw.set! (bit / 8) (raw[bit/8]! ^^^ (1 <<< (bit % 8)).toUInt8)
    let damaged := wordsOf changed
    demand (!metadataValid damaged && selected good damaged == 0) "CRC corruption/peer recovery"
  -- A failed write may persist any prefix. Neither success nor rollback is
  -- inferred. The confirmed peer is never modified by metadata publication.
  let previous := bytesOf old
  for cut in [:513] do
    let torn := wordsOf (raw.extract 0 cut ++ previous.extract cut 512)
    demand (metadataValid good) "known-good modified by publication"
    let which := selected good torn
    demand (which == 0 || which == 1) "torn publication destroyed selection"
    if which == 1 then demand (metadataValid torn && torn[2]! == 8) "selected incomplete publication"
  demand (chooseImage 0 1 0 == 1 && chooseImage 0 1 2 == 1 && chooseImage 0 1 3 == 0) "bounded attempt fallback"
  demand (needsAttempt 1 2 && !needsAttempt 1 3 && !needsAttempt noTrial 0) "trial barrier requirement"
  demand (canConfirm 1 22 1 22 && !canConfirm 1 23 1 22 && !canConfirm 0 11 1 22) "confirmation binding"
  for g in #[0,0xffffffffffffffff] do
    demand (!metadataFieldsValid metadataMagic 1 g 0 11 noTrial 0 0 3) "generation wrap admitted"
  IO.println "BOOT_POLICY_HOST:PASS CRC known answers, bounded load spans, 4096 bit corruptions, 513 torn prefixes, attempt/fallback/confirmation policy"

#eval bootPolicyTests
