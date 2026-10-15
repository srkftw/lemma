import Lemma.Courses.PackageInstaller
import Lean.Elab.Command
import Std.Data.HashMap

/-! Literal observations only. Real UART FIFO/backpressure, installation and
notebook cold timing require separate compiled guest execution. No reply,
package, journal or readiness result is manufactured here. -/
namespace CourseIngressIdleTests
open Lean Elab Command Lemma.Core0.Memory Lemma.User
open Lemma.Courses.PackageInstaller

structure Model where
  words : Std.HashMap UInt64 UInt64 := {}
  sleeps : Array UInt64 := #[]
  reads : Array (UInt64 × UInt64) := #[]
  exits : Array UInt64 := #[]
  readStatus : UInt8 := ABI.noByte
  readBytes : UInt64 := 0
  sleepStatus : UInt8 := 0
  faultAddress : UInt64 := 0
  now : UInt64 := 1000

def require (condition : Bool) (message : String) : IO Unit :=
  unless condition do throw <| IO.userError message
def word (m : Model) (address : UInt64) : UInt64 := m.words.getD address 0
def set (m : Model) (offset value : UInt64) : Model :=
  {m with words := m.words.insert (state + offset) value}

partial def run (ref : IO.Ref Model) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => return (status, value)
  | .bind first next =>
    let (s,v) ← run ref first
    run ref (next s v)
  | .platform operation a b c d e f next =>
    let m ← ref.get
    match operation with
    | .virtualRead64 =>
      require (state ≤ a && a < state + 64 && a % 8 = 0) "read escaped installer state"
      run ref (next (if a = m.faultAddress then 83 else 0) (word m a))
    | .virtualWrite64 =>
      require (a = state + 16 || a = state + 56) "idle receive changed command/deadline/Store state"
      ref.set {m with words := m.words.insert a b}
      run ref (next 0 0)
    | .syscall =>
      if a = CapabilityABI.console then
        require (b = 7 && c = 1 && 0 < e && e ≤ 256 && f = 0 &&
          ((header ≤ d && d + e ≤ header + 64) ||
           (package ≤ d && d + e ≤ package + 32768))) "changed console grant/read authority"
        ref.set {m with reads := m.reads.push (d,e)}
        run ref (next m.readStatus m.readBytes)
      else if a = ABI.sleep then
        require (c ||| d ||| e ||| f = 0) "changed sleep ABI"
        ref.set {m with sleeps := m.sleeps.push b}
        run ref (next m.sleepStatus 0)
      else if a = ABI.time then
        require (b ||| c ||| d ||| e ||| f = 0) "changed time ABI"
        run ref (next 0 m.now)
      else if a = ABI.exit then
        require (b = 93 && c ||| d ||| e ||| f = 0) "changed body timeout"
        ref.set {m with exits := m.exits.push b}
        run ref (next 0 0)
      else throw <| IO.userError "idle polling acquired IPC/device/publication authority"
    | _ => throw <| IO.userError "unexpected idle polling primitive"
  | _ => throw <| IO.userError "unexpected idle polling control form"

def initial : Model := set {} 0 7

def check : IO Unit := do
  let ref ← IO.mkRef initial
  for delay in #[10000,20000,40000,80000,160000,320000,640000,1000000,1000000] do
    require ((← run ref stepIdle) = (0,0)) "empty ingress failed"
    let m ← ref.get
    require (m.sleeps.back! = delay && m.reads.back! = (header,64) &&
      word m (state+16) = 0 && word m (state+32) = 0) "backoff consumed/reframed missing bytes"
  require (word (← ref.get) (state+56) = 7) "backoff did not saturate"
  ref.modify fun m => {m with readStatus := 0, readBytes := 1}
  require ((← run ref stepIdle) = (0,0)) "actual first byte failed"
  require (word (← ref.get) (state+16) = 1 && word (← ref.get) (state+56) = 0 &&
    (← ref.get).sleeps.size = 9) "first byte did not reset delay immediately"
  for phase in #[0,1] do
    let partialState := set (set (set (set (set initial 16 7) 24 128) 32 phase) 48 2000) 56 7
    let partialRef ← IO.mkRef partialState
    require ((← run partialRef stepIdle) = (0,0)) "partial frame failed"
    let m ← partialRef.get
    require (m.sleeps = #[10000] && m.reads = #[(if phase=0 then header+7 else package+7,
      if phase=0 then 57 else 121)] && word m (state+56) = 7) "backoff reached partial frame"
  let timed ← IO.mkRef {set (set (set initial 32 1) 24 128) 48 1000 with now := 1000}
  require ((← run timed stepIdle) = (0,0) && (← timed.get).exits = #[93] &&
    (← timed.get).reads.isEmpty && (← timed.get).sleeps.isEmpty) "partial deadline was extended"
  for (status,bytes) in #[(ABI.noByte,1),(0,0),(0,65),(83,0)] do
    let bad ← IO.mkRef {initial with readStatus := status, readBytes := bytes}
    require ((← run bad stepIdle) = (95,0) && (← bad.get).sleeps.isEmpty &&
      (← bad.get).words.toArray = initial.words.toArray) "bad read was accepted or mutated progress"
  let malformed ← IO.mkRef (set initial 56 8)
  require ((← run malformed stepIdle) = (95,0) && (← malformed.get).sleeps.isEmpty)
    "invalid backoff state slept"
  let failedRead ← IO.mkRef {initial with faultAddress := state+56}
  require ((← run failedRead stepIdle) = (95,0) && (← failedRead.get).sleeps.isEmpty)
    "failed progress read slept"
  let failedSleep ← IO.mkRef {initial with sleepStatus := 83}
  require ((← run failedSleep stepIdle) = (95,0) &&
    word (← failedSleep.get) (state+56) = 1) "sleep failure lost its actual progress prefix"

run_cmd do
  liftIO check
  logInfo "COURSE_INGRESS_IDLE:PASS empty backoff/first-byte reset/partial1ms/original timeout/errors; literal Action only"
end CourseIngressIdleTests
