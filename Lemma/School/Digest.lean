import Lean

/-! Hosted Lean SHA-256 byte identity, FIPS 180-4. No shell, external hashing
service, authentication or target runtime claim. File hashing reads 64KiB chunks.
The existing physical-memory target SHA256 remains a separate binding. -/
namespace Lemma.School.Digest

private def constants : Array UInt32 := #[
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2]

private def rotate (x n : UInt32) : UInt32 := (x >>> n) ||| (x <<< (32-n))
private def small0 (x : UInt32) := rotate x 7 ^^^ rotate x 18 ^^^ (x >>> 3)
private def small1 (x : UInt32) := rotate x 17 ^^^ rotate x 19 ^^^ (x >>> 10)
private def big0 (x : UInt32) := rotate x 2 ^^^ rotate x 13 ^^^ rotate x 22
private def big1 (x : UInt32) := rotate x 6 ^^^ rotate x 11 ^^^ rotate x 25

structure State where
  words : Array UInt32 := #[0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19]
  pending : ByteArray := ByteArray.empty
  bytes : Nat := 0
  deriving Inhabited

private def compress (words : Array UInt32) (block : ByteArray) : Array UInt32 := Id.run do
  let mut w : Array UInt32 := #[]
  for i in [:16] do
    let j := i*4
    w := w.push ((block[j]!.toUInt32 <<< 24) ||| (block[j+1]!.toUInt32 <<< 16) |||
      (block[j+2]!.toUInt32 <<< 8) ||| block[j+3]!.toUInt32)
  for i in [16:64] do
    w := w.push (small1 w[i-2]! + w[i-7]! + small0 w[i-15]! + w[i-16]!)
  let mut a := words[0]!
  let mut b := words[1]!
  let mut c := words[2]!
  let mut d := words[3]!
  let mut e := words[4]!
  let mut f := words[5]!
  let mut g := words[6]!
  let mut h := words[7]!
  for i in [:64] do
    let t1 := h + big1 e + ((e &&& f) ^^^ ((~~~e) &&& g)) + constants[i]! + w[i]!
    let t2 := big0 a + ((a &&& b) ^^^ (a &&& c) ^^^ (b &&& c))
    h := g; g := f; f := e; e := d+t1; d := c; c := b; b := a; a := t1+t2
  return (words.zip #[a,b,c,d,e,f,g,h]).map fun (x,y) => x+y

def update (state : State) (bytes : ByteArray) : State := Id.run do
  let mut state := { state with bytes := state.bytes + bytes.size }
  for byte in bytes.data do
    state := { state with pending := state.pending.push byte }
    if state.pending.size == 64 then
      state := { state with words := compress state.words state.pending, pending := ByteArray.empty }
  return state

private def hexByte (b : UInt8) : String :=
  let digits := "0123456789abcdef".toList.toArray
  String.ofList [digits[b.toNat / 16]!,digits[b.toNat % 16]!]

def finish (state : State) : String := Id.run do
  let paddingSize := if state.pending.size < 56 then 56-state.pending.size else 120-state.pending.size
  let mut pad := (ByteArray.empty.push 128)
  for _ in [:paddingSize-1] do pad := pad.push 0
  let bits := state.bytes.toUInt64 * 8
  for i in [:8] do pad := pad.push ((bits >>> ((7-i)*8).toUInt64).toUInt8)
  let result := update state pad
  let mut text := ""
  for word in result.words do
    for i in [:4] do text := text ++ hexByte ((word >>> ((3-i)*8).toUInt32).toUInt8)
  return text

def sha256Bytes (bytes : ByteArray) : String := finish (update {} bytes)
def sha256String (text : String) : String := sha256Bytes text.toUTF8

def sha256File (path : System.FilePath) : IO String := do
  IO.FS.withFile path .read fun handle => do
    let mut state : State := {}
    repeat
      let chunk ← handle.read 65536
      if chunk.isEmpty then break
      state := update state chunk
    return finish state

def valid (text : String) : Bool :=
  text.length == 64 && text.toList.all (fun c => c.isDigit || ('a' ≤ c && c ≤ 'f'))

end Lemma.School.Digest
