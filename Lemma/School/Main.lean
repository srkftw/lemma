import Lemma.School.Authority
import Lemma.School.Catalogue

open Lean Lemma.School

private def response (value : Json) : Json := object [("ok",toJson true),("result",value)]
private def errorResponse (message : String) : Json := object [("ok",toJson false),("error",toJson message)]

private def command (root : System.FilePath) (request : Json) : IO Json := do
  let op ← Store.lift (str request "op")
  if op == "init" then
    let state ← Store.initSchool root request
    return object [("school",toJson state.school),("generation",toJson state.generation)]
  if op == "restore" then return ← Authority.restore root request
  if op == "init-package" then return ← Authority.installDefinition root request
  let state ← Store.load root
  let (next,result) ← Authority.execute root state request
  if next.records.size != state.records.size || next.generation != state.generation || next.clock != state.clock then
    Store.commit root next
  return result

private def request (root : System.FilePath) (line : String) : IO Json := do
  if line.utf8ByteSize > 1048576 then Store.fail "request byte limit exceeded"
  command root (← Store.lift (Json.parse line))

private def serve (root : System.FilePath) : IO UInt32 := do
  let state ← Store.load root
  let next := {state with generation:=state.generation+1}
  Store.commit root next
  let input ← IO.getStdin
  let output ← IO.getStdout
  repeat
    let line ← input.getLine
    if line.isEmpty then break
    try
      let result ← request root line
      output.putStrLn (response result).compress
      output.flush
      if flag result "stopping" then break
    catch e =>
      output.putStrLn (errorResponse e.toString).compress
      output.flush
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
