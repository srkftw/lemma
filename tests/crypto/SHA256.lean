import Lemma.Crypto.HMAC256

namespace SHA256Tests
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
private def seed (bytes : ByteArray) : Model := Id.run do
  let mut m : Model := {}
  for i in [:bytes.size] do m := {m with memory := m.memory.set! (4096+i) bytes[i]!}
  return m
def digest (m : Model) : String :=
  let alphabet := "0123456789abcdef".toList.toArray
  String.join <| (List.range 32).map fun i =>
    let byte := m.memory[12288+i]!.toNat
    String.ofList [alphabet[byte/16]!,alphabet[byte%16]!]
def hash (bytes : ByteArray) (expected : String) : IO Unit := do
  let state ← IO.mkRef (seed bytes)
  let result ← run state (Lemma.Crypto.SHA256.hash context source bytes.size.toUInt64 output)
  unless result.1 == 0 && digest (← state.get) == expected do
    throw <| IO.userError s!"independent SHA vector failed: {bytes.size}/{result}/{digest (← state.get)}"
def hmac (key bytes : ByteArray) (expected : String) : IO Unit := do
  let mut before := seed bytes
  for i in [:key.size] do before := {before with memory := before.memory.set! (9000+i) key[i]!}
  let state ← IO.mkRef before
  let result ← run state (Lemma.Crypto.HMAC256.authenticate context (base+9000) key.size.toUInt64 source bytes.size.toUInt64 output)
  unless result.1 == 0 && digest (← state.get) == expected do
    throw <| IO.userError s!"independent HMAC vector failed: {key.size}/{bytes.size}/{result}/{digest (← state.get)}"
def check : IO Unit := do
  -- NIST examples and boundary vectors generated independently by Python
  -- hashlib in the host-only runner. No host digest enters the guest Action.
  hash ByteArray.empty "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
  hash "abc".toUTF8 "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
  hash "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq".toUTF8
    "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"
  let vectorFile ← IO.getEnv "LEMMA_SHA_VECTORS"
  let boundary ← IO.FS.lines (vectorFile.getD "build/boot/task006-auth-draft-a1/sha-vectors.txt")
  unless boundary.size == 12 do throw <| IO.userError "missing independent SHA boundary corpus"
  for line in boundary do
    let fields := line.splitOn " "
    if fields.length != 2 then throw <| IO.userError "malformed independent vector"
    let some n := fields[0]!.toNat? | throw <| IO.userError "malformed vector size"
    let bytes := ByteArray.mk <| (Array.range n).map (fun i => ((i*37+11)%256).toUInt8)
    hash bytes fields[1]!
  -- Every split around the block and padding boundary must produce the same
  -- 129-byte digest; the source remains immutable and may be unaligned.
  let bytes := ByteArray.mk <| (Array.range 129).map (fun i => ((i*37+11)%256).toUInt8)
  for split in [:130] do
    let state ← IO.mkRef (seed bytes)
    let (s,_) ← run state <| .bind (Lemma.Crypto.SHA256.«begin» context) fun s _ => if s = 0 then
      .bind (Lemma.Crypto.SHA256.update context source split.toUInt64) fun s _ => if s = 0 then
      .bind (Lemma.Crypto.SHA256.update context (source+split.toUInt64) (129-split).toUInt64) fun s _ =>
        if s = 0 then Lemma.Crypto.SHA256.finish context output else .done s 0
      else .done s 0 else .done s 0
    unless s == 0 && digest (← state.get) == "4f1757ae4bffbae86d775b831765b75af154d52f7deaa46dd378051a2d3ad57f" do
      throw <| IO.userError s!"SHA split mismatch {split}/{s}/{digest (← state.get)}"
  for action in #[Lemma.Crypto.SHA256.hash (context+1) source 3 output,
      Lemma.Crypto.SHA256.hash context context 3 output,
      Lemma.Crypto.SHA256.hash context source 3 context,
      Lemma.Crypto.SHA256.hash context source 4097 output,
      Lemma.Crypto.SHA256.finish context output] do
    let state ← IO.mkRef (seed "abc".toUTF8)
    let (s,_) ← run state action
    unless s != 0 && (← state.get).writes == 0 do throw <| IO.userError "bad SHA admission touched memory"
  let state ← IO.mkRef (seed "abc".toUTF8)
  let (s,_) ← run state (Lemma.Crypto.SHA256.hash context source 3 output)
  unless s == 0 do throw <| IO.userError "SHA positive control"
  let before ← state.get
  let (s,_) ← run state (Lemma.Crypto.SHA256.finish context output)
  unless s == Lemma.Crypto.SHA256.wrongState && (← state.get).writes == before.writes do
    throw <| IO.userError "SHA repeated finish was admitted"
  let state ← IO.mkRef (seed "abc".toUTF8)
  let (s,_) ← run state (Lemma.Crypto.SHA256.«begin» context)
  unless s == 0 do throw <| IO.userError "SHA failure positive control"
  let before ← state.get
  state.set {before with failAt := before.operations+8}
  let (s,_) ← run state (Lemma.Crypto.SHA256.update context source 3)
  unless s == 71 do throw <| IO.userError "injected partial pending-block failure did not occur"
  let before ← state.get
  unless before.memory[1024+656]! == 0x61 do throw <| IO.userError "failed update did not retain actual earlier byte"
  let (s,_) ← run state (Lemma.Crypto.SHA256.finish context output)
  unless s == Lemma.Crypto.SHA256.wrongState && (← state.get).writes == before.writes && before.memory[12288]! == 0xa5 do
    throw <| IO.userError "partial update failure permitted a digest"
  -- RFC4231 cases1,2,6,7 independently cross-check short and hashed long keys.
  hmac (ByteArray.mk <| Array.replicate 20 0x0b) "Hi There".toUTF8
    "b0344c61d8db38535ca8afceaf0bf12b881dc200c9833da726e9376c2e32cff7"
  hmac "Jefe".toUTF8 "what do ya want for nothing?".toUTF8
    "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"
  hmac (ByteArray.mk <| Array.replicate 131 0xaa) "Test Using Larger Than Block-Size Key - Hash Key First".toUTF8
    "60e431591ee0b67f0d8a26aacbf5b77f8e0bc6213728c5140546040f0ee37f54"
  hmac (ByteArray.mk <| Array.replicate 131 0xaa)
    "This is a test using a larger than block-size key and a larger than block-size data. The key needs to be hashed before being used by the HMAC algorithm.".toUTF8
    "9b09ffa71b942fcb27635fbcd5b0e944bfdc63644f0713938a7f51535c3a35e2"
  IO.println "SHA256_ACTIONS:PASS vectors/split-boundaries/admission/repeated-finalization"
end SHA256Tests
#eval SHA256Tests.check
