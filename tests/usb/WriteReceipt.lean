import Lemma.USB.Block
import Lean.Elab.Term
import Std.Data.HashMap

-- Host-only literal memory fixture evaluates the actual target Action. No
-- fixture enters RV64; the bitwise polynomial oracle is independent of the codec.
open Lean Elab Term
elab "usbValidateReply%" : term => do
  let name := mkPrivateNameCore `Lemma.USB.Block `Lemma.USB.Block.validateReply
  discard <| getConstInfo name
  pure (mkConst name)
private def validate : UInt64 → UInt64 → UInt64 → UInt64 → UInt64 → UInt64 → Lemma.Core0.Memory.Action := usbValidateReply%
namespace USBReceiptFixture
open Lemma.Core0.Memory
structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  writes : Array UInt64 := #[]
def get (s : State) (a : UInt64) : UInt64 := s.words.getD a 0
def put (s : State) (a v : UInt64) : State := {s with words := s.words.insert a v}
def require (ok : Bool) (message : String) : IO Unit := if ok then pure () else throw <| IO.userError message
partial def run (memory : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done s v => pure (s,v)
  | .bind first next => let (s,v) ← run memory first; run memory (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "unbounded receipt fixture"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status = 0 then
        let result ← run memory (step i.toUInt32 count value a b c d)
        status := result.1; value := result.2
    run memory (next status value)
  | .platform op a b _ _ _ _ next =>
    require (a % 8 = 0) "unaligned receipt access"
    require (op == .physicalRead64 || op == .physicalWrite64) "unexpected receipt primitive"
    if op == .physicalRead64 then run memory (next 0 (get (← memory.get) a)) else
      memory.modify fun s => {(put s a b) with writes := s.writes.push a}
      run memory (next 0 0)
  | _ => throw <| IO.userError "unexpected receipt Action"
def crc (words : Array UInt64) : UInt64 := Id.run do
  let mut acc : UInt64 := 0
  for word in words do
    for j in [:8] do
      let byte := (word >>> (j.toUInt64*8)) &&& 255
      acc := acc ^^^ (byte <<< 56)
      for _ in [:8] do acc := (acc <<< 1) ^^^ (if acc >>> 63 = 1 then 0x42f0e1eba9ea3693 else 0)
  return acc
def base : UInt64 := 0x82000000
def receipt (request : UInt64) (mismatch error length : UInt64) : State := Id.run do
  let mut s : State := {}
  let mut words : Array UInt64 := #[0x313030504d434d4c,1,3,73,(if request = 1 then 0 else 9),512,length,error]
  if length = 512 then
    for i in [:64] do
      let value := i.toUInt64 * 0x102030405 + 19
      s := put s (base+192+i.toUInt64*8) value
      words := words.push (if i = 31 then value ^^^ mismatch else value)
  for i in [:words.size] do s := put s (base+768+i.toUInt64*8) words[i]!
  s := put s (base+768+words.size.toUInt64*8) (crc words)
  s := put s (Lemma.USB.Block.state+40) request
  s := put s (Lemma.USB.Block.state+64) 9
  s := put s (Lemma.USB.Block.state+80) 2
  return s
def check (request mismatch error length amount : UInt64) (expected : UInt8) : IO Unit := do
  let initial := receipt request mismatch error length
  let memory ← IO.mkRef initial
  let result ← run memory (validate base amount request 73 9 1)
  require (result.1 = expected) s!"receipt request={request}/mismatch={mismatch}/error={error}/length={length}: {result}"
  let final ← memory.get
  if expected = 0 then
    require (result.2 = request) "completed wrong operation"
    require (get final (Lemma.USB.Block.state+40) = 0) "request retained after receipt"
    require (get final (Lemma.USB.Block.state+80) = 0) "receive phase retained"
    require (get final (Lemma.USB.Block.state+64) = (if request = 1 then 9 else 10)) "receipt sequence advanced incorrectly"
    if request = 1 then for i in [:64] do require (get final (base+1536+i.toUInt64*8) = get initial (base+832+i.toUInt64*8)) "read bytes differ"
    else require (final.writes.all fun a => a < base || base+4096 ≤ a) "write/barrier mutated owned payload"
  else
    require (get final (Lemma.USB.Block.state+56) = 1) "bad receipt not quarantined"
    require (get final (Lemma.USB.Block.state+64) = 9) "bad receipt advanced sequence"
    require (final.writes = #[Lemma.USB.Block.state+56]) "bad receipt published completion/payload"
end USBReceiptFixture

def main : IO Unit := do
  USBReceiptFixture.check 2 0 0 512 584 0
  USBReceiptFixture.check 1 0 0 512 584 0
  USBReceiptFixture.check 5 0 0 0 72 0
  USBReceiptFixture.check 2 1 0 512 584 Lemma.USB.Block.corruptCompletion
  USBReceiptFixture.check 2 0 5 512 584 Lemma.USB.Block.corruptCompletion
  USBReceiptFixture.check 2 0 0 0 72 Lemma.USB.Block.corruptCompletion
  USBReceiptFixture.check 5 0 0 512 584 Lemma.USB.Block.corruptCompletion
  IO.println "PASS actual USB receipt Actions: exact persisted write prefix, read bytes, barrier, mismatch/error/short/unexpected payload rejection"
