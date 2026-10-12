import Lemma.Documents.Mathematics
import Lemma.Ink.Surface

/-! Original offline arithmetic sequence, package `lemma-course-arithmetic/1`.
Source/edition anchor is this maintained module; all prose and exercises are
original. Logical prerequisites (fraction equivalence, distributivity) differ
from the pedagogical order (fractions first, products second). It exposes typed
answer editing, exact guest checking and explicit local hints. It is not the
finished immutable package installer, tutor transport or proof-kernel port. -/
namespace Lemma.Courses.Arithmetic
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Documents

private def bad (s : UInt8) : Bool := if s = 0 then false else true

/-- Authored ASCII text packed eight bytes per scalar constant. These are
presentation assets only; no target code is embedded in text. -/
def character (message index : UInt64) : UInt64 :=
  let word :=
    if message = 0 then -- EXACT COURSE EDIT TYPED ANSWER
      if index / 8 = 0 then 0x4f43205443415845 else if index / 8 = 1 then 0x4944452045535255 else if index / 8 = 2 then 0x2044455059542054 else 0x2020524557534e41
    else if message = 1 then -- 1/2 + 1/3 = N/D
      if index / 8 = 0 then 0x2f31202b20322f31 else if index / 8 = 1 then 0x20442f4e203d2033 else if index / 8 = 2 then 0x2020202020202020 else 0x2020202020202020
    else if message = 2 then -- (X+1)*(X+1)=C0+C1*X+C2*X*X
      if index / 8 = 0 then 0x58282a29312b5828 else if index / 8 = 1 then 0x432b30433d29312b else if index / 8 = 2 then 0x582a32432b582a31 else 0x202020202020582a
    else if message = 3 then -- UNSUPPORTED GOAL
      if index / 8 = 0 then 0x524f505055534e55 else if index / 8 = 1 then 0x4c414f4720444554 else if index / 8 = 2 then 0x2020202020202020 else 0x2020202020202020
    else if message = 4 then -- N 00 D 00 C0 00 C1 00 C2 00
      if index / 8 = 0 then 0x302044203030204e else if index / 8 = 1 then 0x2030302030432030 else if index / 8 = 2 then 0x3243203030203143 else 0x2020202020303020
    else if message = 5 then -- FIELD N D C0 C1 C2  MINUS PLUS
      if index / 8 = 0 then 0x204e20444c454946 else if index / 8 = 1 then 0x2031432030432044 else if index / 8 = 2 then 0x554e494d20203243 else 0x202053554c502053
    else if message = 6 then -- CHECK NEXT HINT LIMIT CLOSE
      if index / 8 = 0 then 0x454e204b43454843 else if index / 8 = 1 then 0x20544e4948205458 else if index / 8 = 2 then 0x4c432054494d494c else 0x202020202045534f
    else if message = 7 then -- UNCHECKED
      if index / 8 = 0 then 0x454b434548434e55 else if index / 8 = 1 then 0x2020202020202044 else if index / 8 = 2 then 0x2020202020202020 else 0x2020202020202020
    else if message = 8 then -- VERIFIED Q EXACT
      if index / 8 = 0 then 0x4445494649524556 else if index / 8 = 1 then 0x5443415845205120 else if index / 8 = 2 then 0x2020202020202020 else 0x2020202020202020
    else if message = 9 then -- INVALID
      if index / 8 = 0 then 0x2044494c41564e49 else if index / 8 = 1 then 0x2020202020202020 else if index / 8 = 2 then 0x2020202020202020 else 0x2020202020202020
    else if message = 10 then -- NEEDS CLARIFICATION
      if index / 8 = 0 then 0x4c4320534445454e else if index / 8 = 1 then 0x5441434946495241 else if index / 8 = 2 then 0x20202020204e4f49 else 0x2020202020202020
    else if message = 11 then -- UNSUPPORTED
      if index / 8 = 0 then 0x524f505055534e55 else if index / 8 = 1 then 0x2020202020444554 else if index / 8 = 2 then 0x2020202020202020 else 0x2020202020202020
    else if message = 12 then -- INDETERMINATE RESOURCE LIMIT
      if index / 8 = 0 then 0x4d52455445444e49 else if index / 8 = 1 then 0x4552204554414e49 else if index / 8 = 2 then 0x4c20454352554f53 else 0x2020202054494d49
    else if message = 13 then -- READ ADD FRACTIONS THEN EXPAND
      if index / 8 = 0 then 0x4444412044414552 else if index / 8 = 1 then 0x4f49544341524620 else if index / 8 = 2 then 0x204e45485420534e else 0x2020444e41505845
    else if message = 14 then -- HINT USE COMMON DENOMINATOR
      if index / 8 = 0 then 0x45535520544e4948 else if index / 8 = 1 then 0x204e4f4d4d4f4320 else if index / 8 = 2 then 0x414e494d4f4e4544 else 0x2020202020524f54
    else if message = 15 then -- HINT MULTIPLY EACH TERM
      if index / 8 = 0 then 0x4c554d20544e4948 else if index / 8 = 1 then 0x414520594c504954 else if index / 8 = 2 then 0x204d524554204843 else 0x2020202020202020
    else if message = 16 then -- REV 00 ATTEMPTS 0 PRACTICE
      if index / 8 = 0 then 0x4120303020564552 else if index / 8 = 1 then 0x205354504d455454 else if index / 8 = 2 then 0x4954434152502030 else 0x2020202020204543
    else if message = 17 then -- REV 00 ATTEMPTS 0 REVIEW LATER
      if index / 8 = 0 then 0x4120303020564552 else if index / 8 = 1 then 0x205354504d455454 else if index / 8 = 2 then 0x5745495645522030 else 0x2020524554414c20
    else if message = 18 then -- REV 00 ATTEMPTS 0 NEEDS SUPPORT
      if index / 8 = 0 then 0x4120303020564552 else if index / 8 = 1 then 0x205354504d455454 else if index / 8 = 2 then 0x20534445454e2030 else 0x2054524f50505553
    else 0x2020202020202020
  (word >>> (index % 8 * 8)) &&& 255

private def digit (value index : UInt64) : UInt64 :=
  48 + (if index = 0 then value / 10 else value % 10)

/-- Typed-answer formatting owns its sparse digit switch separately from the
panel row switch, keeping each compiler-generated table in one pure owner. -/
def answerCharacter (column values : UInt64) : UInt64 :=
  if column = 2 then digit (values &&& 127) 0 else if column = 3 then digit (values &&& 127) 1 else
  if column = 7 then digit ((values >>> 7) &&& 127) 0 else if column = 8 then digit ((values >>> 7) &&& 127) 1 else
  if column = 13 then digit ((values >>> 14) &&& 127) 0 else if column = 14 then digit ((values >>> 14) &&& 127) 1 else
  if column = 19 then digit ((values >>> 21) &&& 127) 0 else if column = 20 then digit ((values >>> 21) &&& 127) 1 else
  if column = 25 then digit ((values >>> 28) &&& 127) 0 else if column = 26 then digit ((values >>> 28) &&& 127) 1 else
  character 4 column

def panelCharacter (row column goal values displayState : UInt64) : UInt64 :=
  let outcome := displayState &&& 7
  let hints := (displayState >>> 3) &&& 63
  let revision := (displayState >>> 9) &&& 127
  let attempts := (displayState >>> 16) &&& 15
  if row = 0 then character 0 column else
  if row = 1 then character (if goal = 1 then 1 else if goal = 2 then 2 else 3) column else
  if row = 2 then answerCharacter column values
  else if row = 3 then character 5 column else
  if row = 4 then character 6 column else
  if row = 5 then character (7 + outcome) column else
  if row = 6 then if hints = 0 then character 13 column else
    character (if goal = 1 then 14 else 15) column else
  if row = 7 then
    let recommendation := if outcome < 3 then 16 + (outcome &&& 1) else 18
    if column = 4 then digit (revision % 100) 0 else
    if column = 5 then digit (revision % 100) 1 else
    if column = 15 then 48 + attempts else character recommendation column
  else 32

def panelPixel (x y goal values displayState : UInt64) : UInt64 :=
  if x < 384 then if y < 160 then
    let column := x / 12
    let cellX := x % 12
    let cellY := y % 20
    if cellX < 9 then if cellY < 15 then
      let code := panelCharacter (y / 20) column goal values displayState
      if (Lemma.Ink.Surface.letter code >>> (14 - (cellY / 3 * 3 + cellX / 3))) &&& 1 = 1 then 0 else 15
    else 15 else 15 else 15 else 15

private def renderStep (i _ : UInt32) (acc width goal values displayState : UInt64) : Action :=
  let x := (i.toUInt64 % 192) * 2
  let y := i.toUInt64 / 192
  let packed := (panelPixel x y goal values displayState <<< 4) ||| panelPixel (x + 1) y goal values displayState
  .bind (Memory.write8 (Lemma.Ink.Surface.framebuffer + (160 + y) * ((width + 1) / 2) + 12 + x / 2) packed) fun s _ => .done s acc

def render (buffer width : UInt64) : Action :=
  .bind (Mathematics.field buffer 48) fun s goal => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 56) fun s n => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 64) fun s d => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 72) fun s p0 => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 80) fun s p1 => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 88) fun s p2 => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 96) fun s outcome => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 152) fun s hints => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 40) fun s revision => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 144) fun s attempts => if bad s = true then .done s 0 else
  .boundedFoldU64 30720 renderStep 30720 0 width goal
    (n ||| (d <<< 7) ||| (p0 <<< 14) ||| (p1 <<< 21) ||| (p2 <<< 28))
    (outcome ||| (hints <<< 3) ||| ((revision % 100) <<< 9) ||| (attempts <<< 16)) fun s _ => .done s 0

/-- First two real goals retain their own immutable identity. Goal3 is an
explicit unsupported example, never converted into a successful answer. -/
def next (buffer : UInt64) : Action :=
  .bind (Mathematics.field buffer 48) fun s goal => if bad s = true then .done s 0 else
  .bind (Mathematics.revise buffer) fun s _ => if bad s = true then .done s 0 else
  let nextGoal := if goal < 3 then goal + 1 else 1
  .bind (Mathematics.put buffer 48 nextGoal) fun s _ => if bad s = true then .done s 0 else
  Mathematics.put buffer 120 nextGoal

/-- UI hit testing uses rendered character cells. Contact release is handled
by the notebook pen protocol. Values outside this panel remain ordinary ink. -/
def press (buffer x y : UInt64) : Action :=
  let column := x / 12
  let row := y / 20
  if row = 3 then
    if column = 6 then Mathematics.put buffer 160 56 else
    if column = 8 then Mathematics.put buffer 160 64 else
    if column = 10 then Mathematics.put buffer 160 72 else if column = 11 then Mathematics.put buffer 160 72 else
    if column = 13 then Mathematics.put buffer 160 80 else if column = 14 then Mathematics.put buffer 160 80 else
    if column = 16 then Mathematics.put buffer 160 88 else if column = 17 then Mathematics.put buffer 160 88 else
    if 20 ≤ column then if column < 25 then
      .bind (Mathematics.field buffer 160) fun s selected => if bad s = true then .done s 0 else
      Mathematics.edit buffer (if selected = 0 then 56 else selected) 0
    else if 26 ≤ column then if column < 30 then
      .bind (Mathematics.field buffer 160) fun s selected => if bad s = true then .done s 0 else
      Mathematics.edit buffer (if selected = 0 then 56 else selected) 1
    else .done 0 0 else .done 0 0 else .done 0 0
  else if row = 4 then
    if column < 5 then .bind (Mathematics.submit buffer) fun s _ => .done s 0 else
    if column < 10 then next buffer else
    if column < 15 then Mathematics.hint buffer else
    if column < 21 then
      .bind (Mathematics.field buffer 136) fun s budget => if bad s = true then .done s 0 else
      .bind (Mathematics.revise buffer) fun s _ => if bad s = true then .done s 0 else
      Mathematics.put buffer 136 (if budget = 0 then 8 else 0)
    else if column < 27 then .done 0 1 else .done 0 0
  else .done 0 0

end Lemma.Courses.Arithmetic
