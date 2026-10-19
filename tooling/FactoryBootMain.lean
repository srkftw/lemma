import Lemma.Boot.ProductExecuted
import Lemma.Boot.DevelopmentAuthentication

/-! Hosted factory artifact authoring for the public-development-key ROM.
This creates a NEW, offline raw backing; it cannot publish to a running machine.
The actual ROM must still load and authenticate every byte before execution.
No installation, update, antirollback or power-loss evidence is implied. -/
namespace Lemma.Tooling.FactoryBoot
open Lemma.Boot

private def word (bytes : ByteArray) (index : Nat) : UInt64 := Id.run do
  let mut value : UInt64 := 0
  for i in [:8] do value := value ||| (bytes[index*8+i]!.toUInt64 <<< (i.toUInt64*8))
  return value

private def appendWord (bytes : ByteArray) (value : UInt64) : ByteArray := Id.run do
  let mut bytes := bytes
  for i in [:8] do bytes := bytes.push ((value >>> (i.toUInt64*8)).toUInt8)
  return bytes

private def checksum (bytes : ByteArray) : UInt64 :=
  ProductExecuted.crcFinish (bytes.foldl (fun crc byte => ProductExecuted.crcByte crc byte.toUInt64) ProductExecuted.crcInitial)

def confirmedMetadata (slot identity : UInt64) : Except String ByteArray := do
  unless ProductExecuted.metadataFieldsValid ProductExecuted.metadataMagic ProductExecuted.formatVersion
      1 slot identity ProductExecuted.noTrial 0 0 ProductExecuted.maximumAttempts do
    throw "factory metadata fields rejected by the maintained Product10 policy"
  let fields := #[ProductExecuted.metadataMagic, ProductExecuted.formatVersion, 1,
    slot, identity, ProductExecuted.noTrial, 0, 0, ProductExecuted.maximumAttempts]
  let mut bytes := ByteArray.emptyWithCapacity 512
  for i in [:63] do bytes := appendWord bytes (fields[i]?.getD 0)
  return appendWord bytes (checksum bytes)

private def checkInputs (image tag : ByteArray) : Except String UInt64 := do
  unless 4096 ≤ image.size && image.size ≤ 16777216 && image.size % 512 == 0 && tag.size == 512 do
    throw "bounded complete image and one tag sector required"
  let identity := word image 2
  unless ProductExecuted.headerFieldsValid (word image 0) (word image 1) identity
      (word image 3) (word image 4) (word image 5) &&
      word image 63 == checksum (image.extract 0 504) do
    throw "image header fields or checksum differ from Product10"
  unless word tag 0 == DevelopmentAuthentication.tagMagic &&
      word tag 1 == DevelopmentAuthentication.tagVersion && word tag 2 == 0 &&
      word tag 3 == identity && word tag 4 == ProductExecuted.compatibility &&
      word tag 5 == DevelopmentAuthentication.keyId && word tag 63 == checksum (tag.extract 0 504) do
    throw "slot0 development tag structure or checksum differs"
  return identity

private def boundedRead (path : System.FilePath) (limit : Nat) : IO ByteArray := do
  let metadata ← path.metadata
  unless metadata.type == .file && metadata.byteSize ≤ limit.toUInt64 do
    throw (IO.userError "factory input is not a bounded regular file")
  let bytes ← IO.FS.withFile path .read (fun handle => handle.read (USize.ofNat (limit+1)))
  if limit < bytes.size then throw (IO.userError "factory input grew beyond its bound")
  return bytes

private def unwrap {α : Type} (value : Except String α) : IO α :=
  match value with
  | .ok result => pure result
  | .error error => throw (IO.userError error)

def provision (imagePath tagPath output : System.FilePath) : IO UInt64 := do
  if ← output.pathExists then throw (IO.userError "refusing existing factory output")
  let image ← boundedRead imagePath 16777216
  let tag ← boundedRead tagPath 512
  let identity ← unwrap (checkInputs image tag)
  let metadata ← unwrap (confirmedMetadata 0 identity)
  -- Equal byte-identical generation1 peers select metadata0. There is no
  -- pending trial/confirmation lease, and the unused slot remains all zero.
  let zero := (List.replicate 512 (0 : UInt8)).toByteArray
  IO.FS.withFile output .write fun handle => do
    handle.write metadata
    handle.write metadata
    handle.write tag
    for _ in [:5] do handle.write zero
    handle.write image
    for _ in [:ProductExecuted.mediumSectors.toNat-8-image.size/512] do handle.write zero
  return identity
end Lemma.Tooling.FactoryBoot

def main (arguments : List String) : IO UInt32 := do
  match arguments with
  | ["--public-development-key", image, tag, output] =>
    let identity ← Lemma.Tooling.FactoryBoot.provision image tag output
    IO.println s!"Factory slot0 identity {identity}; actual ROM authentication and cold execution remain required"
    return 0
  | _ => throw (IO.userError "factory authoring: --public-development-key IMAGE SLOT0_TAG NEW_BOOT_RAW")
