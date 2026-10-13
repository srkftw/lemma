import Lemma.Platform.LemmaSim.PowerControl
import Std.Data.HashMap

/- Host-only literal peripheral oracle evaluates the actual boot Actions. It
checks the Power-v1/v2 boundary and prevents false successful boot records. -/
namespace PowerConfigureSafetyFixture
open Lemma.Core0.Memory Lemma.Platform.LemmaSim
structure State where
  version : UInt64 := 2
  magic : UInt64 := 0x4c505752
  cause : UInt64 := 1
  words : Std.HashMap UInt64 UInt64 := {}
  reads : Array UInt64 := #[]
  uart : Array UInt8 := #[]
def require (ok : Bool) (message : String) : IO Unit := if ok then pure () else throw <| IO.userError message
partial def execute (r : IO.Ref State) (a : Action) : IO (UInt8 × UInt64) := do
  match a with
  | .done s v => pure (s,v)
  | .bind first next => let (s,v) ← execute r first; execute r (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "bounded initializer fixture"
    let mut status : UInt8 := 0
    let mut value := initial
    for i in [:count.toNat] do
      if status != 0 then break
      let (s,v) ← execute r (step i.toUInt32 count value a b c d)
      status := s; value := v
    execute r (next status value)
  | .uartReadStatus next => execute r (next 0 0x60)
  | .uartWriteByte byte next =>
    r.modify fun s => {s with uart := s.uart.push byte}
    execute r (next 0)
  | .platform op address value _ _ _ _ next =>
    if op == .physicalWrite64 then
      require (address == 0x80400b80 || address == 0x80400b88) "unexpected boot RAM write"
      r.modify fun s => {s with words := s.words.insert address value}
      execute r (next 0 0)
    else if op == .deviceRead64 then
      let s ← r.get
      let result ← if address == 0x10010500 then pure s.magic
        else if address == 0x10010508 then pure s.version
        else if address == 0x10010520 then pure s.cause
        else if address == 0x10010538 then pure 13
        else if address == 0x10010528 then pure 1
        else throw <| IO.userError "initializer performed watchdog/unknown I/O"
      r.modify fun s => {s with reads := s.reads.push address}
      execute r (next 0 result)
    else throw <| IO.userError "initializer performed device write/unknown primitive"
  | _ => throw <| IO.userError "unexpected initializer Action"
def check : IO Unit := do
  for cause in [1:7] do
    let r ← IO.mkRef ({cause := cause.toUInt64} : State)
    require ((← execute r (PowerControl.configureSafety 1 23)) == (0,0)) "Power-v2 reset cause rejected"
    let actual ← r.get
    require (actual.words.getD 0x80400b80 0 == 1 && actual.words.getD 0x80400b88 0 == 23) "boot endpoint configuration differs"
    require (actual.reads == #[0x10010500,0x10010508,0x10010520,0x10010538,0x10010528]) "boot identity/status read ordering differs"
    let digit := (48+cause).toUInt8
    let expected := "K1 0000000000000442 000000000000000".toUTF8.data ++ #[digit] ++
      " 000000000000000d 0000000000000001 0000000000000000\n".toUTF8.data
    require (actual.uart == expected) "Power-v2 record differs from independent literal oracle"
  for input in #[({version := 1} : State),{cause := 0},{cause := 7},{magic := 0}] do
    let r ← IO.mkRef input
    require ((← execute r (PowerControl.configureSafety 1 23)) == (197,0)) "invalid Power-v2 identity/cause admitted"
    require ((← r.get).uart.isEmpty) "invalid identity published a successful boot record"
  let legacy ← IO.mkRef ({} : State)
  require ((← execute legacy (PowerControl.configure 1 23)) == (197,0)) "legacy Power-v1 silently accepted v2"
  require ((← legacy.get).uart.isEmpty) "legacy rejection produced boot success"
  let disabled ← IO.mkRef ({version := 0,magic := 0,cause := 0} : State)
  require ((← execute disabled (PowerControl.configureSafety 0 0)) == (0,0)) "disabled policy rejected"
  require ((← disabled.get).reads.isEmpty && (← disabled.get).uart.isEmpty) "disabled policy touched hardware"
  IO.println "PASS actual Power-v2 boot configuration: all six causes, version/magic/cause negatives, no implicit watchdog writes, exact UART publication; historical Power-v1 rejects v2"
end PowerConfigureSafetyFixture
def main := PowerConfigureSafetyFixture.check
