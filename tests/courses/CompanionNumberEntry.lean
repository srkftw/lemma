import Lemma.Applications.Notebook
import Std.Data.HashMap

/-! Execute the joined imported Actions against bounded owned RAM. The model
rejects storage/checker IPC and pinned-source writes. This component establishes
input/recovery isolation; RV64, USB and peer durability need connected runs. -/
open Lean Elab Command
run_cmd do
  for (suffix, aliasName) in [("Notebook.numericRecoverableInputSample", `joinedInput),
      ("Notebook.numericInputSample", `healthyInput),
      ("Notebook.drainNumericRecoverableInput", `joinedDrain)] do
    let owners := (← getEnv).constants.toList.filter fun row => row.1.toString.endsWith suffix
    unless owners.length == 1 do throwError "actual imported Action owner is not unique: {suffix}"
    let owner := mkIdent owners.head!.1
    if suffix.endsWith "drainNumericRecoverableInput" then
      elabCommand (← `(def $(mkIdent aliasName) (input : UInt64) : Lemma.Core0.Memory.Action := $owner input))
    else
      elabCommand (← `(def $(mkIdent aliasName) : Lemma.Core0.Memory.Action := $owner))

namespace CompanionNumberEntryTests
open Lemma.Core0.Memory Lemma.Applications.Notebook Lemma.User
private def packageState : UInt64 := 0x33c800
structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  writeFault : Option UInt64 := none
  writes : Array (UInt64 × UInt64) := #[]
  inputReads : Nat := 0
  console : Array String := #[]

private def permitted (a : UInt64) : Bool :=
  (0x20200 ≤ a && a < 0x20d00) || (0x110000 ≤ a && a < 0x2cc000) ||
  (ink0 ≤ a && a < 0x33e000)
private def read (m : Model) (a : UInt64) : UInt64 :=
  m.words.getD a (if 0x110000 ≤ a && a < 0x2cc000 then 0xffffffffffffffff else 0)
private def set (m : Model) (a v : UInt64) : Model := {m with words := m.words.insert a v}
private def byte (m : Model) (a : UInt64) : UInt64 := (read m (a-a%8) >>> (a%8*8)) &&& 255
private def writable (a : UInt64) : Bool :=
  (0x20200 ≤ a && a < 0x20d00) || (0x110000 ≤ a && a < 0x2cc000) ||
  (ink1 ≤ a && a < 0x329000) || (packageState ≤ a && a < packageState+256)
partial def run (ref : IO.Ref Model) : Action → IO (UInt8 × UInt64)
  | .done s v => pure (s,v)
  | .bind first next => do
    let (s,v) ← run ref first
    run ref (next s v)
  | .boundedFoldU64 budget step count initial a b c d next => do
    if count.toNat > budget then throw <| IO.userError "input exceeded its declared bound"
    let mut result := ((0 : UInt8),initial)
    for i in [:count.toNat] do
      if result.1 == 0 then result ← run ref (step i.toUInt32 count result.2 a b c d)
    run ref (next result.1 result.2)
  | .platform op a b c d e f next => do
    if op == .virtualRead64 || op == .virtualRead8 then
      unless permitted a do throw <| IO.userError s!"unowned read {a}"
      let m ← ref.get
      run ref (next 0 (if op == .virtualRead8 then byte m a else read m a))
    else if op == .virtualWrite64 || op == .virtualWrite8 then
      unless writable a do throw <| IO.userError s!"pinned source/document or unowned write {a}"
      let m ← ref.get
      let width := if op == .virtualWrite8 then 1 else 8
      if m.writeFault.any (fun address => a ≤ address && address < a+width) then run ref (next 17 0)
      else
        let aligned := a-a%8
        let shift := a%8*8
        let updated := if width == 8 then set m a b else
          set m aligned ((read m aligned &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift))
        ref.set {updated with writes := m.writes.push (a,width)}
        run ref (next 0 0)
    else if op == .syscall && a == CapabilityABI.console then
      unless b == 4 && c == 0 && d == Console.packetAddress && e == 88 && f == 0 do
        throw <| IO.userError "console ownership/framing changed"
      let m ← ref.get
      let bytes := ByteArray.mk ((List.range 88).toArray.map fun i => (byte m (d+i.toUInt64)).toUInt8)
      let line := String.fromUTF8! bytes
      if line.startsWith "K1 0000000000000421" then throw <| IO.userError "provisional input manufactured Saved"
      ref.set {m with console := m.console.push line}
      run ref (next 0 88)
    else if op == .syscall && a == 65 && b == 2 && c == 1 && d == raw && e == 0 && f == 0 then
      ref.modify fun m => {m with inputReads := m.inputReads+1}
      run ref (next 174 0)
    else throw <| IO.userError s!"offline input acquired IPC/checker/console authority {a}"
  | _ => throw <| IO.userError "input acquired an undeclared/unbounded Action"

private def initial (status retained : UInt64) : Model := Id.run do
  let mut m : Model := {}
  for (slot,value) in #[(0,1),(8,2),(16,3),(24,4),(32,1650),(40,2200),
      (48,65535),(56,65535),(64,4095),(72,1),(80,1),(88,2),(96,14),
      (120,ink1),(128,11),(136,status),(144,ink0),(272,512),
      (336,65535),(344,65535),(424,227),(512,1),(592,1),(600,ink0),
      (608,344),(616,65548),(632,11),(648,retained),(752,12)] do
    m := set m (state+slot) value
  for i in [:43] do m := set m (ink0+i.toUInt64*8) (0xfedcba9876540000+i.toUInt64)
  for i in [:1024] do m := set m (mathematics+i.toUInt64*8) (0x12340000+i.toUInt64)
  return m
private def sample (m : Model) (sequence flags : UInt64) : Model := Id.run do
  let mut m := m
  for (offset,value) in #[(0,sequence),(8,1000+sequence),(16,20000),(24,7000),
      (32,1234),(40,flags),(48,1),(56,0),(64,1)] do m := set m (raw+offset) value
  return m
private def expect (b : Bool) (message : String) : IO Unit :=
  unless b do throw <| IO.userError message
private def observe (m : Model) (a : Action) : IO ((UInt8 × UInt64) × Model) := do
  let ref ← IO.mkRef m
  let r ← run ref a
  pure (r,← ref.get)

def check : IO Unit := do
  -- Healthy hover and a keypad contact while a publication is pending must
  -- use exactly the ordinary numeric input path, including its busy guard.
  for flags in #[(2 : UInt64),3] do
    let m := sample (set (initial 1 0) (state+160) 1) 1 flags
    let (a,joined) ← observe m joinedInput
    let (b,ordinary) ← observe m healthyInput
    expect (a == b && joined.words == ordinary.words && joined.writes == ordinary.writes)
      "healthy input differs from the actual numeric path"
    expect (read joined (packageState+200) == 0 && read joined (state+112) == 0)
      "busy numeric contact became offline ink"
  for (status,retained) in (#[(2,1),(1,1)] : Array (UInt64 × UInt64)) do
    let first := sample (initial status retained) 1 3
    let ref ← IO.mkRef first
    expect ((← run ref joinedInput).1 == 0) "retained contact failed"
    let drawn ← ref.get
    expect (read drawn (state+112) == 1 && read drawn (state+104) == 14 &&
      read drawn (state+136) == status && read drawn (state+648) == retained &&
      read drawn (packageState+200) == 1) "retained key did not become bounded provisional raw ink"
    expect (drawn.writes.any (fun (address,_) => 0x110000 ≤ address && address < 0x2cc000))
      "offline raw point did not rasterize"
    ref.modify fun m => sample m 2 2
    expect ((← run ref joinedInput).1 == 0) "retained release failed"
    let released ← ref.get
    expect (read released (state+104) == 0 && read released (state+112) == 2 &&
      read released (state+136) == status) "release fabricated acknowledgment or lost raw contact"
    for n in [:2] do
      let expected := sample first (n.toUInt64+1) (if n == 0 then 3 else 2)
      for offset in [:9] do
        expect (read released (ink1+128+n.toUInt64*72+offset.toUInt64*8) ==
          read expected (raw+offset.toUInt64*8)) "raw sample fields changed"
    for i in [:43] do expect (read released (ink0+i.toUInt64*8) == read first (ink0+i.toUInt64*8)) "retained source changed"
    for i in [:1024] do expect (read released (mathematics+i.toUInt64*8) == read first (mathematics+i.toUInt64*8)) "document/history changed before reconciliation"
  let fault := {sample (initial 2 1) 1 3 with writeFault := some (packageState+200)}
  let (failed,after) ← observe fault joinedInput
  expect (failed == (17,0) && after.words == fault.words && after.writes.isEmpty)
    "pad invalidation failure admitted an untracked input"
  let m := set (initial 1 0) (state+112) 384
  let (full,after) ← observe m (joinedDrain 2)
  expect (full == (0,0) && after.inputReads == 0) "healthy full-buffer backpressure changed"
  let m := set (initial 2 1) (state+112) 384
  let (empty,after) ← observe m (joinedDrain 2)
  expect (empty == (0,0) && after.inputReads == 1) "retained full buffer prevented reconciliation input polling"
  IO.println "COMPANION_NUMBER_ENTRY16:PASS actual joined/healthy Actions; retained raw press/release/raster/9fields; pinned source/document/history immutable; no storage/checker IPC or Saved; marker failure/backpressure; component only"
end CompanionNumberEntryTests

def main : IO Unit := CompanionNumberEntryTests.check
