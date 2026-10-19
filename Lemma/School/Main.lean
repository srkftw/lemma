import Lemma.School.Authority
import Lemma.School.Catalogue

open Lean Lemma.School

private def response (value : Json) : Json := object [("ok",toJson true),("result",value)]
private def errorResponse (message : String) : Json := object [("ok",toJson false),("error",toJson message)]

/-- Reading elapsed time does not mutate acknowledged domain history. Clock
epochs and execution generations do; they are durable before admission. -/
private def changed (before after : State) : Bool :=
  before.schema != after.schema || before.records.size != after.records.size || before.generation != after.generation ||
  before.clockEpoch != after.clockEpoch || before.clockEpochSequence != after.clockEpochSequence

private def openState (root : System.FilePath) : IO State := do
  let before ← Store.load root
  let state ← Store.bindClock before
  if changed before state then Store.commit root state
  return state

private def command (root : System.FilePath) (request : Json) : IO Json := do
  let op ← Store.lift (str request "op")
  if op == "init" then
    let state ← Store.initSchool root request
    return object [("school",toJson state.school),("generation",toJson state.generation)]
  if op == "restore" then return ← Authority.restore root request
  if op == "init-package" then return ← Authority.installDefinition root request
  let state ← openState root
  let (next,result) ← Authority.execute root state request
  if changed state next then Store.commit root next state.references
  return result

private def request (root : System.FilePath) (line : String) : IO Json := do
  if line.utf8ByteSize > 1048576 then Store.fail "request byte limit exceeded"
  command root (← Store.lift (Json.parse line))

private def serve (root : System.FilePath) : IO UInt32 := do
  -- Recovery verifies each artifact once. The mutex excludes a second writer;
  -- queries use this validated state and never reread or rewrite the snapshot.
  let state ← Store.bindClock (← Store.load root) true
  Store.commit root state
  let current ← IO.mkRef state
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    let before ← current.get
    let executed ← try
      if line.utf8ByteSize > 1048576 then Store.fail "request byte limit exceeded"
      let request ← Store.lift (Json.parse line)
      pure (.ok (← Authority.execute root before request) : Except String (State × Json))
    catch e => pure (.error e.toString)
    match executed with
    | .error message =>
      output.putStrLn (errorResponse message).compress
      output.flush
    | .ok (next,result) =>
      try
        if changed before next then Store.commit root next before.references
        current.set next
      catch e =>
        -- A failed storage barrier can leave an uncertain commit. Never accept
        -- another mutation against stale cached state; restart must recover it.
        output.putStrLn (errorResponse s!"commit failed; authority stopped: {e}").compress
        output.flush
        return 1
      output.putStrLn (response result).compress
      output.flush
      if flag result "stopping" then break
  return 0

def main (args : List String) : IO UInt32 := do
  try
    match args with
    | [root,"serve"] => serve root
    | "catalogue" :: rest => Lemma.School.Catalogue.cli rest
    | [root,line] =>
      IO.println (response (← request root line)).compress
      return 0
    | _ =>
      IO.eprintln "usage: lemma-school ROOT REQUEST_JSON | lemma-school ROOT serve | lemma-school catalogue ..."
      return 2
  catch e =>
    IO.println (errorResponse e.toString).compress
    return 1
