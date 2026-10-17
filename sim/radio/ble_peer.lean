import Lemma.Radio.BLE.Link

/-! Hosted Lean development peer for an explicit unauthenticated manual ACL
context. Its adapter supplies only actual CRC-validated controller head bytes
and sends output through that peer's real sampled-bit controller. No notebook,
journal, persistent receipt, connection establishment or authentication policy.
All SN/NESN transitions reuse the maintained target scalar implementation. -/
namespace Lemma.Sim.BLEPeer
open Lemma.Radio.BLE

private def digit (value : UInt8) : Char :=
 if value < 10 then Char.ofNat (value.toNat+48) else Char.ofNat (value.toNat+87)
private def hexadecimal (bytes : ByteArray) : String :=
 String.ofList <| bytes.data.toList.flatMap fun byte => [digit (byte/16),digit (byte%16)]
private def nibble (c : Char) : Option UInt8 :=
 if '0' ≤ c && c ≤ '9' then some (c.toNat-48).toUInt8
 else if 'a' ≤ c && c ≤ 'f' then some (c.toNat-87).toUInt8 else none
private def parseBytes (text : String) : Option ByteArray := do
 let chars := text.toList.toArray
 if chars.size > 54 || chars.size%2 != 0 then none else
 let mut result := ByteArray.empty
 for i in [:chars.size/2] do
   let high ← nibble chars[i*2]!
   let low ← nibble chars[i*2+1]!
   result := result.push (high*16+low)
 pure result
private def number (text : String) : Option UInt64 := do
 let value ← text.toNat?
 if value ≤ 0xffffffffffffffff then some value.toUInt64 else none

private def counterLimit : UInt64 := 0x7fffffffffffffff
private def response (output : IO.FS.Stream) (text : String)
    (state accepted duplicates : UInt64) (pending : ByteArray) : IO Unit := do
 let data := if pending.isEmpty then "-" else hexadecimal pending
 output.putStrLn s!"{text} | STATE {state} ACCEPTED {accepted} DUPLICATES {duplicates} PENDING {pending.size} {data}"
 output.flush

/-- Bound raw command capture before allocation of an unbounded line. EOF with
an incomplete command is rejected. Host runtime stays outside the target image. -/
private def line (input : IO.FS.Stream) : IO (Option String) := do
 let mut bytes := ByteArray.empty
 for _ in [:256] do
   let next ← input.read 1
   if next.isEmpty then
     if bytes.isEmpty then return none
     else throw <| IO.userError "incomplete BLE peer command"
   if next[0]! = 10 then return some (String.fromUTF8! bytes)
   bytes := bytes.push next[0]!
 throw <| IO.userError "BLE peer command limit256 exceeded"

def main (arguments : List String) : IO UInt32 := do
 let input ← IO.getStdin
 let output ← IO.getStdout
 let errors ← IO.getStderr
 let mut state : UInt64 := Link.initial
 let mut pending := ByteArray.empty
 let mut accepted : UInt64 := 0
 let mut duplicates : UInt64 := 0
 if arguments != [] && arguments != ["--private-restore"] then
   throw <| IO.userError "only --private-restore is admitted"
 response output "BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT" state accepted duplicates pending
 -- A fresh privately bound process may restore one complete validated record.
 -- No live process accepts RESTORE, and no snapshot query advances the peer.
 if arguments = ["--private-restore"] then
   let some raw ← line input | return 2
   match raw.splitOn " " with
   | ["RESTORE",stateText,acceptedText,duplicatesText,data] =>
     match number stateText,number acceptedText,number duplicatesText,
       parseBytes (if data="-" then "" else data) with
     | some restored,some restoredAccepted,some restoredDuplicates,some restoredPending =>
       if Link.validState restored && restoredAccepted ≤ counterLimit &&
           restoredDuplicates ≤ counterLimit &&
           (restoredPending.isEmpty || restoredAccepted > 0) then
         state := restored;accepted := restoredAccepted;duplicates := restoredDuplicates;pending := restoredPending
         response output "RESTORED PRIVATE_CONTEXT" state accepted duplicates pending
       else
         response output "ERROR 197 RESTORE" state accepted duplicates pending
         return 2
     | _,_,_,_ =>
       response output "ERROR 197 RESTORE" state accepted duplicates pending
       return 2
   | _ =>
     response output "ERROR 197 RESTORE" state accepted duplicates pending
     return 2
 repeat
   let some raw ← line input | return 0
   let words := raw.splitOn " "
   match words with
   | ["QUIT"] => return 0
   | ["CREDIT"] => pending := ByteArray.empty;response output "CREDIT 1" state accepted duplicates pending
   | ["STATUS"] =>
     response output "STATUS" state accepted duplicates pending
   | ["CANCEL"] =>
     let result := Link.cancelResult state
     state := result &&& Link.stateMask
     response output s!"ERROR {result >>> 32} FROZEN" state accepted duplicates pending
   | ["RX",headerText,lengthText,hex] =>
     match number headerText,number lengthText,parseBytes (if hex="-" then "" else hex) with
     | some header,some length,some bytes =>
       if bytes.size.toUInt64 != length then response output "ERROR 197 SIZE" state accepted duplicates pending else
       let space : UInt64 := if length=0 then 1 else if pending.isEmpty then 1 else 0
       let result := Link.receiveResult state header length space
       if result >>> 32 != 0 then response output s!"ERROR {result >>> 32} CONTEXT" state accepted duplicates pending else
       if (result &&& Link.newReceive != 0 && length != 0 && accepted = counterLimit) ||
           (result &&& Link.duplicate != 0 && duplicates = counterLimit) then
         response output "ERROR 201 COUNTER" state accepted duplicates pending
       else
       state := result &&& Link.stateMask
       if result &&& Link.newReceive != 0 && length != 0 then
         pending := bytes;accepted := accepted+1
         errors.putStrLn s!"OPAQUE_RX {accepted} {hexadecimal bytes}"
       if result &&& Link.duplicate != 0 then duplicates := duplicates+1
       if length=0 then response output "EMPTY_RX" state accepted duplicates pending else
       let sending := if state &&& (4 : UInt64) = 4 then Link.retryResult state else Link.beginResult state
       state := sending &&& Link.stateMask
       if sending >>> 32 != 0 then response output s!"ERROR {sending >>> 32} FROZEN" state accepted duplicates pending else
       let header := Link.headerResult state 1 0
       if header >>> 32 != 0 then response output s!"ERROR {header >>> 32} HEADER" state accepted duplicates pending
       else response output s!"TX {header} 0 -" state accepted duplicates pending
     | _,_,_ => response output "ERROR 197 FORMAT" state accepted duplicates pending
   | _ => response output "ERROR 197 COMMAND" state accepted duplicates pending
 return 0
end Lemma.Sim.BLEPeer

def main (arguments : List String) : IO UInt32 := Lemma.Sim.BLEPeer.main arguments
