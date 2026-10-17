import Lemma.Applications.Notebook
import Lean.Elab.Command
import Std.Data.HashMap

/-! Literal Action observations of course-preserving Save. The fixture rejects
any framebuffer write outside the footer and changes to course/package state.
It supplies IPC admission only: no reply or Saved result is fabricated. Actual
RV64 execution, barrier responses and completed scans are separate checks. -/
namespace CourseSaveFixture
open Lean Elab Command
open Lemma.Core0.Memory
open Lemma.Applications.Notebook

structure State where
  words : Std.HashMap UInt64 UInt64 := {}
  requests : Nat := 0
  logs : Array String := #[]
  admissionStatus : UInt8 := 0
  readFault : UInt64 := 0
  writeFault : UInt64 := 0

def require (ok : Bool) (message : String) : IO Unit :=
  unless ok do throw <| IO.userError message
def read (s : State) (address : UInt64) : UInt64 := s.words.getD address 0
def write (s : State) (address value : UInt64) : State :=
  {s with words := s.words.insert address value}
def byte (s : State) (address : UInt64) : UInt64 :=
  (read s (address-address%8) >>> (address%8*8)) &&& 255

partial def execute (stateRef : IO.Ref State) (action : Action) : IO (UInt8 × UInt64) := do
  match action with
  | .done status value => return (status,value)
  | .bind first next =>
    let (s,v) ← execute stateRef first
    execute stateRef (next s v)
  | .boundedFoldU64 budget step count initial a b c d next =>
    require (count.toNat ≤ budget) "Save exceeded its declared fold bound"
    let mut result := ((0 : UInt8),initial)
    for i in [:count.toNat] do
      if result.1 = 0 then result ← execute stateRef (step i.toUInt32 count result.2 a b c d)
    execute stateRef (next result.1 result.2)
  | .platform op a b c d e f next =>
    let s ← stateRef.get
    match op with
    | .virtualRead64 => execute stateRef (next (if a=s.readFault then 83 else 0) (read s a))
    | .virtualRead8 => execute stateRef (next (if a=s.readFault then 83 else 0) (byte s a))
    | .virtualWrite64 | .virtualWrite8 =>
      require (a ≠ state+512) "Save closed the course"
      if 0x332000 ≤ a && a < 0x33e000 then
        require (b=(if op=.virtualWrite64 then read s a else byte s a))
          "Save changed the selected course/package context"
      if Lemma.Ink.Surface.framebuffer ≤ a && a < Lemma.Ink.Surface.framebuffer+1815000 then
        let row := (a-Lemma.Ink.Surface.framebuffer)/825
        require (132 ≤ row && row < 148) "Save rebuilt pixels outside the footer"
      if a=s.writeFault then execute stateRef (next 84 0) else
        stateRef.modify fun s => if op=.virtualWrite64 then write s a b else
          let shift := a%8*8
          write s (a-a%8) ((read s (a-a%8) &&& ~~~((255 : UInt64) <<< shift)) ||| ((b &&& 255) <<< shift))
        execute stateRef (next 0 0)
    | .syscall =>
      if a=15 then
        require (b=7 && c=0 && d=0x20200 && e=88 && f=0) "unexpected console authority/shape"
        let text := String.ofList ((List.range 88).map fun i => Char.ofNat (byte s (d+i.toUInt64)).toNat)
        require (!text.startsWith "K1 0000000000000421") "request admission fabricated Saved"
        stateRef.modify fun s => {s with logs := s.logs.push text}
        execute stateRef (next 0 88)
      else if a=22 then
        require (b=9 && c=outgoing && d=64 && e=42 && f=300000000) "Save escaped the single ordinary Store IPC slot"
        for (offset,value) in #[(0,0x31525453414d454c),(8,1),(16,8),(24,1),(32,0),(40,0),(48,0),(56,0)] do
          require (read s (outgoing+offset)=value) "actual Store status request differs"
        stateRef.modify fun s => {s with requests := s.requests+1}
        execute stateRef (next s.admissionStatus 77)
      else throw <| IO.userError "Save acquired another syscall/device"
    | _ => throw <| IO.userError "undeclared Save primitive"
  | _ => throw <| IO.userError "undeclared Save Action"

def initial : State := Id.run do
  let mut s : State := {}
  for (offset,value) in #[(0,73),(16,9),(24,7),(32,1650),(40,2200),(72,1),(80,1),
      (128,8),(136,0),(176,41),(272,512),(336,65535),(344,65535),(512,1),(752,12)] do
    s := write s (state+offset) value
  -- A genuinely allocated, completed course view. Existing cancellation may
  -- write idle bookkeeping back unchanged; selected content must stay intact.
  for (offset,value) in #[(8,0),(16,1),(32,2),(48,1),(56,1),(72,1),(120,1),
      (128,1),(136,1),(144,1)] do
    s := write s (0x33c800+offset) value
  return s

def check : IO Unit := do
  for action in #[packageRequestSave,packageRecoverableToolbar 7] do
    let ref ← IO.mkRef initial
    require ((← execute ref action)=(0,0)) "course Save request failed"
    let s ← ref.get
    require (s.requests=1 && read s (state+512)=1 && read s (state+160)=6 &&
      read s (state+136)=1 && read s (state+496)=8 && read s (state+168)=77 &&
      read s (state+232)=8) "Save failed to retain course/Pending/validated completion state"
    require (s.logs.any (·.startsWith "K1 0000000000000423")) "missing Pending publication"
  for (offset,value) in #[(536,1),(160,3),(112,1),(144,0x308000),(136,2)] do
    let before := write initial (state+offset) value
    let ref ← IO.mkRef before
    require ((← execute ref packageRequestSave)=(0,0)) "busy Save changed error precedence"
    let after ← ref.get
    require (after.requests=0 && after.logs.isEmpty && after.words.toArray=before.words.toArray)
      "busy/read-only Save overwrote work or submitted IPC"
  let failed ← IO.mkRef {initial with admissionStatus:=83}
  require ((← execute failed packageRequestSave)=(0,0)) "failed admission killed notebook"
  let s ← failed.get
  require (s.requests=1 && read s (state+136)=2 && read s (state+424)=83 &&
    read s (state+160)=0 && read s (state+512)=1 && s.logs.any (·.startsWith "K1 0000000000000424"))
    "failed admission did not preserve course and report Failed"
  let readFailed ← IO.mkRef {initial with readFault:=state+160}
  require ((← execute readFailed packageRequestSave)=(83,0) && (← readFailed.get).requests=0)
    "guard read failure submitted a request"
  let prepareFailed ← IO.mkRef {initial with writeFault:=outgoing+16}
  require ((← execute prepareFailed packageRequestSave)=(0,0) && (← prepareFailed.get).requests=0 &&
    read (← prepareFailed.get) (state+136)=2) "failed preparation reached IPC or Saved"

run_cmd do
  liftIO check
  logInfo "COURSE_SAVE:PASS course retained/footer-only/Pending-only/single-slot/busy/admission-and-preparation-failure; literal Action component only"
end CourseSaveFixture
