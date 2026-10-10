import Lemma.Applications.Notebook
import Lean.Elab.Command

/-! Host-only literal typography/layout checks. The expected glyphs are written
as independent visible rows, not generated from production bit constants. This
does not claim a visible manual test or replace an actual guest screenshot. -/
namespace NotebookGlyphs
open Lemma.Ink Lemma.Applications

def require (value : Bool) (message : String) : IO Unit :=
  if value then pure () else throw <| IO.userError message

def rows (code : Char) : Array String :=
  if code == 'A' then #["010","101","111","101","101"] else
  if code == 'D' then #["110","101","101","101","110"] else
  if code == 'E' then #["111","100","110","100","111"] else
  if code == 'F' then #["111","100","110","100","100"] else
  if code == 'G' then #["111","100","101","101","111"] else
  if code == 'H' then #["101","101","111","101","101"] else
  if code == 'I' then #["111","010","010","010","111"] else
  if code == 'L' then #["100","100","100","100","111"] else
  if code == 'N' then #["101","111","111","111","101"] else
  if code == 'O' then #["111","101","101","101","111"] else
  if code == 'P' then #["111","101","111","100","100"] else
  if code == 'R' then #["110","101","110","101","101"] else
  if code == 'S' then #["111","100","111","001","111"] else
  if code == 'U' then #["101","101","101","101","111"] else
  if code == 'V' then #["101","101","101","101","010"] else
  if code == 'W' then #["101","101","101","111","111"] else
  if code == 'Y' then #["101","101","010","010","010"] else
  if code == '0' then #["111","101","101","101","111"] else
  if code == '1' then #["010","110","010","010","111"] else
  if code == '2' then #["111","001","111","100","111"] else
  if code == '3' then #["111","001","111","001","111"] else
  if code == '4' then #["101","101","111","001","001"] else
  if code == '5' then #["111","100","111","001","111"] else
  if code == '6' then #["111","100","111","101","111"] else
  if code == '7' then #["111","001","010","010","010"] else
  if code == '8' then #["111","101","111","101","111"] else
  if code == '9' then #["111","101","111","001","111"] else
  #["000","000","000","000","000"]

def packed (rows : Array String) : UInt64 :=
  rows.foldl (fun value row => row.toList.foldl
    (fun value bit => value * 2 + (if bit == '1' then 1 else 0)) value) 0

def check : IO Unit := do
  for char in "ADEFGHILNOPRSUVWY0123456789 ".toList do
    require (Surface.letter char.toNat.toUInt64 == packed (rows char)) s!"incorrect literal glyph {char}"
  let left := #["010","100","111","100","010"]
  let right := #["010","001","111","001","010"]
  require (Surface.glyph 1 == packed left && Surface.glyph 2 == packed right) "previous/next arrows"
  require (Surface.glyph 5 == packed (rows 'E') && Surface.glyph 7 == packed (rows 'S')) "erase/save labels swapped"
  require (Surface.letter 83 != Surface.letter 50) "Saved begins with a digit2"
  for (state, text) in #[(0,"SAVED     N2 P64 W8 "),(1,"PENDING   N2 P64 W8 "),
                         (2,"FAILED    N2 P64 W8 "),(3,"READ ONLY N2 P64 W8 ")] do
    let chars := text.toList.toArray
    require (chars.size == 20) "literal status width"
    for index in [:20] do
      require (Notebook.statusCharacter state index.toUInt64 2 64 2048 == chars[index]!.toNat.toUInt64)
        s!"incorrect status text {state} cell{index}"
    for y in [:16] do
      for x in [:240] do
        let char := chars[x / 12]!
        let black := if y < 15 && x % 12 < 9 then
          ((rows char)[y / 3]!.toList.toArray)[x % 12 / 3]! == '1' else false
        let expected := if black then (0 : UInt64) else 15
        require (Notebook.statusPixel x.toUInt64 y.toUInt64 2 64 state 2048 == expected)
          s!"status pixel mismatch at{x}/{y} state{state}"
    require (Notebook.statusPixel 240 0 2 64 state 2048 == 15 &&
      Notebook.statusPixel 0 16 2 64 state 2048 == 15) "status overflow clipping"
  for (width,height) in #[(1650,2200),(1404,1872),(512,320)] do
    for (button, expected) in #[(1,left),(2,right),(5,rows 'E'),(7,rows 'S')] do
      for row in [:5] do
        for col in [:3] do
          let black := (expected[row]!.toList.toArray)[col]! == '1'
          let x := button * (width / 8) + 24 + col.toUInt64 * 12 + 1
          let y := 36 + row.toUInt64 * 12 + 1
          require (Surface.backgroundPixel x y width height == if black then 0 else 15)
            "runtime geometry toolbar glyph placement"
  IO.println "NOTEBOOK_GLYPHS:PASS literal arrows/E/S and full4-state words;20cells/3840pixels;both geometries"

end NotebookGlyphs
open Lean Elab Command
run_cmd liftIO NotebookGlyphs.check
