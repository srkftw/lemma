import Lemma.Courses.Review
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
    else if message = 6 then -- CHECK NEXT HINT LIMIT REVIEW
      if index / 8 = 0 then 0x454e204b43454843 else if index / 8 = 1 then 0x20544e4948205458 else if index / 8 = 2 then 0x45522054494d494c else 0x2020202057454956
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
    else if message = 19 then -- AUTO PRACTICE UNCERTAIN
      if index / 8 = 0 then 0x415250204f545541 else if index / 8 = 1 then 0x4e55204543495443 else if index / 8 = 2 then 0x204e494154524543 else 0x2020202020202020
    else if message = 20 then -- AUTO REVIEW LATER UNCERTAIN
      if index / 8 = 0 then 0x564552204f545541 else if index / 8 = 1 then 0x4554414c20574549 else if index / 8 = 2 then 0x545245434e552052 else 0x20202020204e4941
    else if message = 21 then -- AUTO SUPPORT UNCERTAIN
      if index / 8 = 0 then 0x505553204f545541 else if index / 8 = 1 then 0x434e552054524f50 else if index / 8 = 2 then 0x20204e4941545245 else 0x2020202020202020
    else if message = 22 then -- MANUAL PRACTICE UNCERTAIN
      if index / 8 = 0 then 0x50204c41554e414d else if index / 8 = 1 then 0x2045434954434152 else if index / 8 = 2 then 0x4941545245434e55 else 0x202020202020204e
    else if message = 23 then -- MANUAL LATER UNCERTAIN
      if index / 8 = 0 then 0x4c204c41554e414d else if index / 8 = 1 then 0x434e552052455441 else if index / 8 = 2 then 0x20204e4941545245 else 0x2020202020202020
    else if message = 24 then -- MANUAL SUPPORT UNCERTAIN
      if index / 8 = 0 then 0x53204c41554e414d else if index / 8 = 1 then 0x552054524f505055 else if index / 8 = 2 then 0x4e4941545245434e else 0x2020202020202020
    else if message = 25 then -- REVIEW DISABLED UNCERTAIN
      if index / 8 = 0 then 0x4420574549564552 else if index / 8 = 1 then 0x2044454c42415349 else if index / 8 = 2 then 0x4941545245434e55 else 0x202020202020204e
    else if message = 26 then -- NO ATTEMPT UNDERSTANDING UNKNOWN
      if index / 8 = 0 then 0x4d45545441204f4e else if index / 8 = 1 then 0x5245444e55205450 else if index / 8 = 2 then 0x474e49444e415453 else 0x4e574f4e4b4e5520
    else if message = 27 then -- ASSISTED ATTEMPT PRACTICE
      if index / 8 = 0 then 0x4445545349535341 else if index / 8 = 1 then 0x54504d4554544120 else if index / 8 = 2 then 0x4349544341525020 else 0x2020202020202045
    else if message = 28 then -- EXACT ATTEMPT REVIEW LATER
      if index / 8 = 0 then 0x5441205443415845 else if index / 8 = 1 then 0x45522054504d4554 else if index / 8 = 2 then 0x54414c2057454956 else 0x2020202020205245
    else if message = 29 then -- INVALID ATTEMPT PRACTICE
      if index / 8 = 0 then 0x2044494c41564e49 else if index / 8 = 1 then 0x2054504d45545441 else if index / 8 = 2 then 0x4543495443415250 else 0x2020202020202020
    else if message = 30 then -- LIMIT OR UNSUPPORTED SUPPORT
      if index / 8 = 0 then 0x524f2054494d494c else if index / 8 = 1 then 0x4f505055534e5520 else if index / 8 = 2 then 0x5055532044455452 else 0x2020202054524f50
    else if message = 31 then -- YOUR MANUAL OVERRIDE
      if index / 8 = 0 then 0x4e414d2052554f59 else if index / 8 = 1 then 0x5245564f204c4155 else if index / 8 = 2 then 0x2020202045444952 else 0x2020202020202020
    else if message = 32 then -- POLICY DISABLED YOUR CHOICE
      if index / 8 = 0 then 0x44205943494c4f50 else if index / 8 = 1 then 0x2044454c42415349 else if index / 8 = 2 then 0x4f48432052554f59 else 0x2020202020454349
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
  let review := displayState >>> 24
  let mode := (review >>> 6) &&& 7
  let recommendation := review &&& 7
  let reason := (review >>> 3) &&& 7
  let showReason := review >>> 9
  if row = 0 then character 0 column else
  if row = 1 then character (if goal = 1 then 1 else if goal = 2 then 2 else 3) column else
  if row = 2 then answerCharacter column values
  else if row = 3 then character 5 column else
  if row = 4 then character 6 column else
  if row = 5 then character (7 + outcome) column else
  if row = 6 then if showReason = 1 then character (25 + reason) column else
    if hints = 0 then character 13 column else
    character (if goal = 1 then 14 else 15) column else
  if row = 7 then
    character (if mode = 4 then 25 else if mode = 0 then 18 + recommendation else 21 + mode) column
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

private def cachedPixel (position row first second : UInt64) : UInt64 :=
  if row < 15 then if position % 12 < 9 then
    let glyph := if position < 12 then first else second
    if (glyph >>> (14 - (row / 3 * 3 + position % 12 / 3))) &&& 1 = 1 then 0 else 15
  else 15 else 15

private def cachedPair (position row first second : UInt64) : UInt64 :=
  (cachedPixel position row first second <<< 4) ||| cachedPixel (position + 1) row first second

/-- One little-endian word covers sixteen declared course pixels. The word
starts at a multiple of sixteen, so it meets at most two twelve-pixel character
cells. Glyph lookup happens once per cell rather than once per pixel. -/
def panelWord (x y goal values displayState : UInt64) : UInt64 :=
  if x ≤ 368 then if x % 16 = 0 then if y < 160 then
    let first := Lemma.Ink.Surface.letter (panelCharacter (y / 20) (x / 12) goal values displayState)
    let second := Lemma.Ink.Surface.letter (panelCharacter (y / 20) (x / 12 + 1) goal values displayState)
    let start := x % 12
    let row := y % 20
    cachedPair start row first second |||
    (cachedPair (start + 2) row first second <<< 8) |||
    (cachedPair (start + 4) row first second <<< 16) |||
    (cachedPair (start + 6) row first second <<< 24) |||
    (cachedPair (start + 8) row first second <<< 32) |||
    (cachedPair (start + 10) row first second <<< 40) |||
    (cachedPair (start + 12) row first second <<< 48) |||
    (cachedPair (start + 14) row first second <<< 56)
  else 0xffffffffffffffff else 0xffffffffffffffff else 0xffffffffffffffff

private def renderByteStep (i _ : UInt32) (acc address word _ _ : UInt64) : Action :=
  .bind (Memory.write8 (address + i.toUInt64) ((word >>> (i.toUInt64 * 8)) &&& 255)) fun s _ => .done s acc

private def renderStep (i _ : UInt32) (acc width goal values displayState : UInt64) : Action :=
  let x := (i.toUInt64 % 24) * 16
  let y := i.toUInt64 / 24
  let word := panelWord x y goal values displayState
  let address := Lemma.Ink.Surface.framebuffer + (160 + y) * ((width + 1) / 2) + 12 + x / 2
  if address &&& 7 = 0 then
    .bind (Memory.write64 address word) fun s _ => .done s acc
  else
    .boundedFoldU64 8 renderByteStep 8 acc address word 0 0 fun s value => .done s value

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
  .bind (Review.summary buffer) fun s review => if bad s = true then .done s 0 else
  .boundedFoldU64 3840 renderStep 3840 0 width goal
    (n ||| (d <<< 7) ||| (p0 <<< 14) ||| (p1 <<< 21) ||| (p2 <<< 28))
    (outcome ||| (hints <<< 3) ||| ((revision % 100) <<< 9) ||| (attempts <<< 16) ||| (review <<< 24)) fun s _ => .done s 0

/-- First two real goals retain their own immutable identity. Goal3 is an
explicit unsupported example, never converted into a successful answer. -/
def next (buffer : UInt64) : Action :=
  .bind (Mathematics.eventCapacity buffer) fun s _ => if bad s = true then .done s 0 else
  .bind (Mathematics.field buffer 48) fun s goal => if bad s = true then .done s 0 else
  .bind (Mathematics.revise buffer) fun s _ => if bad s = true then .done s 0 else
  let nextGoal := if goal < 3 then goal + 1 else 1
  .bind (Mathematics.put buffer 48 nextGoal) fun s _ => if bad s = true then .done s 0 else
  .bind (Mathematics.put buffer 120 nextGoal) fun s _ => if bad s = true then .done s 0 else
  Mathematics.appendEvent buffer 4 1 0

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
    else if column < 27 then Mathematics.reviewMode buffer else .done 0 0
  else .done 0 0

end Lemma.Courses.Arithmetic
