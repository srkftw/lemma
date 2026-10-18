import Lemma.Crypto.AEAD
import Lemma.Crypto.HKDF256
import Lemma.Multimodal.TutorAction
import Lemma.Multimodal.Parameterized
namespace MultimodalCryptoTests
open Lemma.Core0.Memory
def base : UInt64 := 0x80000000
def context : UInt64 := base+1024
def source : UInt64 := base+4096
def output : UInt64 := base+12288
structure Model where
  memory : ByteArray := ByteArray.mk (Array.replicate 16384 0xa5)
  operations : Nat := 0
  failAt : Nat := 0
  writes : Nat := 0
private def offset (address bytes : UInt64) : Except String Nat := do
  if address < base || 16384 < bytes || 16384-bytes < address-base then
    throw "independent crypto memory bounds"
  return (address-base).toNat
partial def run (state : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
      let (s,v) ← run state first
      run state (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
      if budget < count.toNat then throw <| IO.userError "crypto exceeded declared loop"
      let mut s : UInt8 := 0
      let mut v := initial
      for i in [:count.toNat] do
        if s == 0 then
          let result ← run state (step i.toUInt32 count v a b c d)
          s := result.1
          v := result.2
      run state (next s v)
  | .platform op address value _ _ _ _ next => do
      let m ← state.get
      let bytes := if op == .physicalRead64 || op == .physicalWrite64 then 8 else 1
      unless op == .physicalRead8 || op == .physicalRead64 || op == .physicalWrite8 || op == .physicalWrite64 do
        throw <| IO.userError "crypto acquired undeclared effect"
      if bytes == 8 && address%8 != 0 then throw <| IO.userError "unaligned crypto word"
      let position ← IO.ofExcept <| offset address bytes
      let operation := m.operations+1
      state.set {m with operations := operation}
      if m.failAt == operation then run state (next 71 0) else
      if op == .physicalRead8 || op == .physicalRead64 then
        let mut word : UInt64 := 0
        for i in [:bytes.toNat] do
          word := word ||| (m.memory[position+i]!.toUInt64 <<< (i.toUInt64*8))
        run state (next 0 word)
      else
        let mut data := m.memory
        for i in [:bytes.toNat] do data := data.set! (position+i) ((value >>> (i.toUInt64*8)).toUInt8)
        state.set {m with memory := data, operations := operation, writes := m.writes+1}
        run state (next 0 0)
  | _ => throw <| IO.userError "crypto acquired an undeclared Action"

private def unhex (s : String) : ByteArray := Id.run do
  let chars := s.toList.toArray
  let mut out := ByteArray.empty
  for i in [:chars.size/2] do
    let digit (c : Char) := if c <= '9' then c.toNat-48 else c.toNat-87
    out := out.push ((digit chars[2*i]!*16+digit chars[2*i+1]!).toUInt8)
  return out
private def seedAt (m : Model) (offset : Nat) (b : ByteArray) : Model := Id.run do
  let mut memory := m.memory
  for i in [:b.size] do memory := memory.set! (offset+i) b[i]!
  return {m with memory}
private def bytesAt (m : Model) (offset count : Nat) : ByteArray := m.memory.extract offset (offset+count)
def check : IO Unit := do
  let key := base+8000
  let nonce := base+8032
  let aad := base+8064
  let plaintext := base+8192
  let ciphertext := base+12288
  let tag := base+12544
  let restored := base+12800
  -- Independently published RFC8439 sections2.3.2,2.5.2,2.8.2:
  -- https://www.rfc-editor.org/rfc/rfc8439.html#section-2.8.2
  let mut m : Model := {}
  m := seedAt m 8000 (unhex "000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f")
  m := seedAt m 8032 (unhex "000000090000004a00000000")
  let state ← IO.mkRef m
  let result ← run state (Lemma.Crypto.ChaCha20.block context key nonce 1 ciphertext)
  unless result.1 == 0 && bytesAt (← state.get) 12288 64 == unhex "10f1e7e4d13b5915500fdd1fa32071c4c7d1f4c733c068030422aa9ac3d46c4ed2826446079faa0914c2d705d98b02a2b5129cd1de164eb9cbd083e8a2503c4e" do
    throw <| IO.userError "RFC8439 ChaCha20 block mismatch"
  m := seedAt m 8000 (unhex "85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b")
  m := seedAt m 8192 "Cryptographic Forum Research Group".toUTF8
  state.set m
  let result ← run state (Lemma.Crypto.Poly1305.authenticate context key plaintext 34 tag)
  unless result.1 == 0 && bytesAt (← state.get) 12544 16 == unhex "a8061dc1305136c6c22b8baf0c0127a9" do
    throw <| IO.userError s!"RFC8439 Poly1305 mismatch {bytesAt (← state.get) 12544 16}"
  let message := "Ladies and Gentlemen of the class of '99: If I could offer you only one tip for the future, sunscreen would be it.".toUTF8
  m := seedAt m 8000 (unhex "808182838485868788898a8b8c8d8e8f909192939495969798999a9b9c9d9e9f")
  m := seedAt m 8032 (unhex "070000004041424344454647")
  m := seedAt m 8064 (unhex "50515253c0c1c2c3c4c5c6c7")
  m := seedAt m 8192 message
  state.set m
  let result ← run state (Lemma.Crypto.AEAD.«seal» context key nonce aad 12 plaintext message.size.toUInt64 ciphertext tag)
  let expected := unhex "d31a8d34648e60db7b86afbc53ef7ec2a4aded51296e08fea9e2b5a736ee62d63dbea45e8ca9671282fafb69da92728b1a71de0a9e060b2905d6a5b67ecd3b3692ddbd7f2d778b8c9803aee328091b58fab324e4fad675945585808b4831d7bc3ff4def08e4b7a9de576d26586cec64b6116"
  unless result.1 == 0 && bytesAt (← state.get) 12288 114 == expected && bytesAt (← state.get) 12544 16 == unhex "1ae10b594f09e26a7e902ecbd0600691" do
    throw <| IO.userError s!"RFC8439 AEAD mismatch {result} / {bytesAt (← state.get) 12544 16}"
  let sealed ← state.get
  let result ← run state (Lemma.Crypto.AEAD.open context key nonce aad 12 ciphertext 114 restored tag)
  unless result.1 == 0 && bytesAt (← state.get) 12800 114 == message do
    throw <| IO.userError "AEAD authenticated roundtrip mismatch"
  -- Every one-bit tag mutation must reject before changing a plaintext byte.
  for i in [:128] do
    let bad := seedAt sealed (12544+i/8) (ByteArray.mk #[sealed.memory[12544+i/8]! ^^^ (1 <<< (i%8).toUInt8)])
    state.set bad
    let result ← run state (Lemma.Crypto.AEAD.open context key nonce aad 12 ciphertext 114 restored tag)
    unless result.1 == Lemma.Crypto.AEAD.badTag && bytesAt (← state.get) 12800 114 == bytesAt sealed 12800 114 do
      throw <| IO.userError "forged tag changed unauthenticated plaintext"
  let original ← state.get
  for action in #[Lemma.Crypto.AEAD.«seal» (context+1) key nonce aad 12 plaintext 114 ciphertext tag,
      Lemma.Crypto.AEAD.«seal» context key nonce aad 257 plaintext 114 ciphertext tag,
      Lemma.Crypto.AEAD.«seal» context key nonce aad 12 plaintext 4097 ciphertext tag,
      Lemma.Crypto.AEAD.«seal» context key nonce aad 12 plaintext 114 (plaintext+1) tag] do
    state.set original
    let result ← run state action
    unless result.1 != 0 && (← state.get).writes == original.writes do
      throw <| IO.userError "AEAD bad admission mutated memory"
  -- RFC5869 AppendixA.1, the first32bytes of its42byte OKM.
  -- https://www.rfc-editor.org/rfc/rfc5869.html#appendix-A.1
  m := seedAt m 8000 (ByteArray.mk <| Array.replicate 22 0x0b)
  m := seedAt m 8032 (unhex "000102030405060708090a0b0c")
  m := seedAt m 8064 (unhex "f0f1f2f3f4f5f6f7f8f9")
  state.set m
  let result ← run state (Lemma.Crypto.HKDF256.derive context nonce 13 key 22 aad 10 tag)
  unless result.1 == 0 && bytesAt (← state.get) 12544 32 == unhex "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf" do
    throw <| IO.userError "RFC5869 HKDF32 mismatch"
  IO.println "MULTIMODAL_CRYPTO_ACTIONS:PASS RFC8439/block/poly/aead/128-forgeries/admission/RFC5869-HKDF"
end MultimodalCryptoTests
#eval MultimodalCryptoTests.check
