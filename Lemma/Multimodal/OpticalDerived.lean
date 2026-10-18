import Lemma.Kernel.Memory.Access

/-! OpticalDerived/1: bounded image-derived synthetic fixed-plane coarse gaze.
Raw LMNIRF01 images remain the acquisition record. This transformer preserves
frame/time/config/calibration references and makes no sensor or human accuracy
claim. A single synthetic eye feature and face fiducial are not per-eye,
binocular, pupil-size, vergence, head-pose, affect or understanding outputs.
Caller owns immutable frame/parameters/output spans; a later service must enforce
owned mappings and current local-processing grants before invoking this code. -/
namespace Lemma.Multimodal.OpticalDerived
open Lemma.Core0.Memory Lemma.Kernel.Memory

def version : UInt64 := 1
def unavailableCoordinate : UInt64 := 0xffffffffffffffff
/-- Status0 coarse region;1 unavailable;2 malformed;3 occluded;4 uncalibrated;
5 head-out-of-volume;6 dropped;7 off-screen;8 synchronization invalid;
9 stale display history;10 partial/uncertain displayed region;11 permission;
12 image saturation;13 uncertainty crosses region;14 closed eyelid pattern;
15 counter exhaustion;16 ambiguous image feature. These are observations, not
psychological labels. -/
def different (a b : UInt64) : Bool := if a = b then false else true
private def rd (base index : UInt64) : Action := Access.read64 (base+index*8)
private def wr (base index value : UInt64) : Action := Access.write64 (base+index*8) value
private def failed (s : UInt8) : Bool := if s = 0 then false else true

def count (stats : UInt64) : UInt64 := stats &&& 511
def sx (stats : UInt64) : UInt64 := (stats >>> 9) &&& 4095
def sy (stats : UInt64) : UInt64 := (stats >>> 21) &&& 4095
def minX (stats : UInt64) : UInt64 := (stats >>> 33) &&& 15
def maxX (stats : UInt64) : UInt64 := (stats >>> 37) &&& 15
def minY (stats : UInt64) : UInt64 := (stats >>> 41) &&& 15
def maxY (stats : UInt64) : UInt64 := (stats >>> 45) &&& 15
private def small (a b : UInt64) : UInt64 := if a < b then a else b
private def large (a b : UInt64) : UInt64 := if a < b then b else a
private def distance (a b : UInt64) : UInt64 := if a < b then b-a else a-b

def addPixel (stats x y : UInt64) : UInt64 :=
  (count stats + (1 : UInt64)) ||| ((sx stats+x) <<< 9) ||| ((sy stats+y) <<< 21) |||
  ((small (minX stats) x) <<< 33) ||| ((large (maxX stats) x) <<< 37) |||
  ((small (minY stats) y) <<< 41) ||| ((large (maxY stats) y) <<< 45)

def featureX (stats : UInt64) : UInt64 := if count stats = 0 then unavailableCoordinate else sx stats*256/count stats
def featureY (stats : UInt64) : UInt64 := if count stats = 0 then unavailableCoordinate else sy stats*256/count stats

def featureState (stats : UInt64) : UInt64 :=
  if count stats = 0 then 3 else
  if 32 < count stats then 16 else
  if maxX stats < minX stats then 2 else if maxY stats < minY stats then 2 else
  if maxY stats = minY stats then
    if 5 ≤ maxX stats-minX stats then if maxX stats-minX stats ≤ 10 then 14 else 16 else 16
  else if count stats < 4 then 16 else
  if 4 < maxX stats-minX stats then 16 else if 4 < maxY stats-minY stats then 16 else 0

private def statsStep (i _ : UInt32) (acc frame width roi threshold : UInt64) : Action :=
  let p := i.toUInt64
  let x := p % width
  let y := p / width
  if x < (roi &&& 255) then .done 0 acc else
  if y < ((roi >>> 8) &&& 255) then .done 0 acc else
  if ((roi >>> 16) &&& 255) ≤ x then .done 0 acc else
  if ((roi >>> 24) &&& 255) ≤ y then .done 0 acc else
  .bind (Access.read64 (frame+256+(p/4)*8)) fun s word => if failed s = true then .done s 0 else
  let pixel := (word >>> ((p % 4)*16)) &&& 65535
  if pixel < threshold then .done 0 (addPixel acc x y) else .done 0 acc

def imageStats (frame width height roi threshold : UInt64) : Action :=
  .boundedFoldU64 256 statsStep (width*height).toUInt32 (((15 : UInt64) <<< 33) ||| ((15 : UInt64) <<< 41)) frame width roi threshold fun s value => .done s value

private def frameCheck (i _ : UInt32) (acc frame _ _ _ : UInt64) : Action :=
  .bind (rd frame i.toUInt64) fun s v => if failed s = true then .done s 0 else
  let n := i.toUInt64
  let code : UInt64 :=
    if n = 0 then if different v 0x31304652494e4d4c = true then 2 else 0 else
    if n = 1 then if different v 1 = true then 2 else 0 else
    if n = 2 then if different v 1 = true then 2 else 0 else
    if n = 3 then if v = 0 then 1 else if v = unavailableCoordinate then 15 else 0 else
    if n = 4 then if v = 0 then 1 else if v = unavailableCoordinate then 15 else 0 else
    if n = 5 then if v = 0 then 4 else 0 else
    if n = 10 then if different v 0 = true then 2 else 0 else
    if n = 11 then if different v 0 = true then 2 else 0 else
    if n = 12 then if different v 16 = true then 2 else 0 else
    if n = 13 then if different v 16 = true then 2 else 0 else
    if n = 14 then if v = 0 then 2 else if 64 < v then 2 else 0 else
    if n = 15 then if v = 0 then 2 else if 65535 < v then 2 else 0 else
    if n = 16 then if v = 0 then 2 else if 65535 < v then 2 else 0 else
    if n = 17 then if v = 0 then 11 else 0 else
    if n = 18 then if v &&& 1 = 1 then 12 else if v &&& 8 = 8 then 6 else if different v 0 = true then 1 else 0 else
    if n = 19 then if different v 512 = true then 2 else 0 else
    if n = 20 then if different v 32 = true then 2 else 0 else
    if n = 21 then if different v 100000000 = true then 8 else 0 else
    if n = 22 then if different v 850 = true then 2 else 0 else
    if n = 25 then if different v 1 = true then 4 else 0 else
    if n = 26 then if different v 1 = true then 1 else 0 else
    if n = 27 then if different v 1 = true then 1 else 0 else
    if n = 28 then if different v 1 = true then 2 else 0 else
    if n = 29 then if different v 1 = true then 2 else 0 else
    if n = 30 then if different v 0 = true then 2 else 0 else
    if n = 31 then if different v 0 = true then 2 else 0 else 0
  if acc = 0 then .done 0 code else .done 0 acc

def validateFrame (frame : UInt64) : Action :=
  .boundedFoldU64 32 frameCheck 32 0 frame 0 0 0 fun s value => .done s value

/-- This v1 synthetic geometric calibration deliberately accepts only a full
16x16 source frame. The two subregions are software analysis windows into that
same immutable exposure; they are never additional sensor instances. -/
private def parameterCheck (i _ : UInt32) (acc params _ _ _ : UInt64) : Action :=
  .bind (rd params i.toUInt64) fun s v => if failed s = true then .done s 0 else
  let n := i.toUInt64
  let code : UInt64 :=
    if n = 0 then if different v 0x3150444c = true then 2 else 0 else
    if n = 1 then if different v 1 = true then 2 else 0 else
    if n = 2 then if v = 0 then 4 else 0 else
    if n = 3 then if v = 0 then 4 else 0 else
    if n = 4 then if v = 0 then 4 else if 65535 < v then 4 else 0 else
    if n = 5 then if different v 0x08100000 = true then 2 else 0 else
    if n = 6 then if different v 0x10100800 = true then 2 else 0 else
    if 7 ≤ n then if n ≤ 10 then if 3840 < v then 4 else 0 else other n v else other n v
  if acc = 0 then .done 0 code else .done 0 acc
where
  other (n v : UInt64) : UInt64 :=
    if n = 11 then if 256 < v then 4 else 0 else
    if n = 12 then if v = 0 then 4 else if 4096 < v then 4 else 0 else
    if n = 13 then if v = 0 then 4 else if 4096 < v then 4 else 0 else
    if n = 14 then if 4096 < v then 4 else 0 else
    if n = 15 then if 4096 < v then 4 else 0 else
    if n = 16 then if v = 0 then 4 else if 512 < v then 4 else 0 else
    if n = 17 then if v = 0 then 4 else if 512 < v then 4 else 0 else
    if n = 18 then if 512 < v then 4 else 0 else
    if n = 19 then if 0x7ffffffffffffffe < v then 4 else 0 else
    if n = 20 then if 0x7ffffffffffffffe < v then 8 else 0 else
    if n = 21 then if v = 0 then 11 else 0 else
    if n = 22 then if v = 0 then 11 else 0 else
    if n = 23 then if v = 0 then 11 else 0 else
    if n = 24 then if v = 0 then 8 else 0 else
    if n = 25 then if v = 0 then 8 else 0 else
    if n = 26 then if different v 1 = true then 8 else 0 else
    if n = 27 then if different v 1 = true then 8 else 0 else
    if n = 28 then if different v 0 = true then 8 else 0 else
    if n = 29 then if 100 < v then 8 else 0 else
    if n = 30 then if 0x7ffffffffffffffe < v then 8 else 0 else
    if n = 31 then if 0x7ffffffffffffffe < v then 8 else 0 else
    if 32 ≤ n then if n ≤ 38 then if v = 0 then 9 else if 0x7ffffffffffffffe < v then 9 else 0 else last n v else last n v
  last (n v : UInt64) : UInt64 :=
    if n = 39 then if 0x7ffffffffffffffe < v then 9 else 0 else
    if n = 40 then if 0x7ffffffffffffffe < v then 9 else 0 else
    if 41 ≤ n then if n ≤ 44 then if 4096 < v then 2 else 0 else rest n v else rest n v
  rest (n v : UInt64) : UInt64 :=
    if n = 45 then if different v 1 = true then 10 else 0 else
    if 46 ≤ n then if n ≤ 49 then if 4096 < v then 2 else 0 else ending n v else ending n v
  ending (n v : UInt64) : UInt64 :=
    if n = 50 then if 1 < v then 2 else 0 else
    if n = 51 then if different v 1 = true then 4 else 0 else
    if n = 52 then if different v 1 = true then 2 else 0 else
    if n = 53 then if different v 1 = true then 2 else 0 else
    if n = 54 then if v = 0 then 8 else if 100000000 < v then 8 else 0 else
    if n = 55 then if different v 0 = true then 2 else 0 else
    if n = 56 then if different v 1 = true then 11 else 0 else
    if n = 57 then if different v 1 = true then 2 else 0 else 0

def validateParameters (params : UInt64) : Action :=
  .boundedFoldU64 58 parameterCheck 58 0 params 0 0 0 fun s value => .done s value

/-- Fixed-plane affine image geometry, expressed as integer pixels per source
pixel. Head translation is removed by a separately observed fiducial. Rotation,
depth, out-of-plane motion and human anatomy are not modeled or qualified. -/
def mappedCoordinate (eye face refEye refFace center gain extent : UInt64) : UInt64 :=
  if eye+refFace < face+refEye then
    let magnitude := (face+refEye-eye-refFace)*gain/256
    if center < magnitude then unavailableCoordinate else
    if extent ≤ center-magnitude then unavailableCoordinate else center-magnitude
  else
    let magnitude := (eye+refFace-face-refEye)*gain/256
    if extent ≤ center+magnitude then unavailableCoordinate else center+magnitude

def regionStatus (x y radius x0 y0 x1 y1 : UInt64) : UInt64 :=
  if x1 ≤ x0 then 2 else if y1 ≤ y0 then 2 else
  if x < radius then 13 else if y < radius then 13 else
  if x-radius < x0 then 13 else if y-radius < y0 then 13 else
  if x1 ≤ x+radius then 13 else if y1 ≤ y+radius then 13 else 0

def pendingStatus (x y radius pending x0 y0 x1 y1 : UInt64) : UInt64 :=
  if pending = 0 then 0 else if x1 ≤ x0 then 2 else if y1 ≤ y0 then 2 else
  if x+radius < x0 then 0 else if y+radius < y0 then 0 else
  if x1 ≤ x-radius then 0 else if y1 ≤ y-radius then 0 else 10

private def clearStep (i _ : UInt32) (acc output _ _ _ : UInt64) : Action :=
  .bind (wr output i.toUInt64 (if i = 6 then unavailableCoordinate else if i = 7 then unavailableCoordinate else 0)) fun s _ => .done s acc
private def copyProvenance (frame params output : UInt64) : Action :=
  .bind (wr output 0 0x31444552444d4c) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 1 1) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 3) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 9 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 4) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 10 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 5) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 11 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 2) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 12 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 6) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 13 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 7) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 14 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 8) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 15 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 20) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 16 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 32) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 17 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 33) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 18 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 34) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 19 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 35) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 20 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 36) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 21 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 37) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 22 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 52) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 23 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 53) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 24 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 24) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 31 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 21) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 32 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 22) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 33 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd params 23) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 34 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 18) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 35 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 23) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 36 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 14) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 37 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 15) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 38 v) fun s _ => if failed s = true then .done s 0 else
  .bind (rd frame 16) fun s v => if failed s = true then .done s 0 else
  .bind (wr output 39 v) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 25 1) fun s _ => .done s 0

private def finish (output status eye face x y radius eyeStats faceStats : UInt64) : Action :=
  .bind (wr output 2 status) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 3 eye) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 4 face) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 5 (if eye = 14 then 1 else 0)) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 6 (if status = 0 then x else unavailableCoordinate)) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 7 (if status = 0 then y else unavailableCoordinate)) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 8 radius) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 26 (if status = 0 then 1 else 0)) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 27 eyeStats) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 28 faceStats) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 29 (if face = 0 then featureX faceStats else unavailableCoordinate)) fun s _ => if failed s = true then .done s 0 else
  .bind (wr output 30 (if face = 0 then featureY faceStats else unavailableCoordinate)) fun s _ => .done s status

private def compute (frame params output eyeStats faceStats : UInt64) : Action :=
  let eyeState := featureState eyeStats
  let faceState := featureState faceStats
  .bind (rd params 2) fun s calibration => if failed s = true then .done s 0 else
  .bind (rd params 3) fun s expectedConfig => if failed s = true then .done s 0 else
  .bind (rd params 7) fun s refEyeX => if failed s = true then .done s 0 else
  .bind (rd params 8) fun s refEyeY => if failed s = true then .done s 0 else
  .bind (rd params 9) fun s refFaceX => if failed s = true then .done s 0 else
  .bind (rd params 10) fun s refFaceY => if failed s = true then .done s 0 else
  .bind (rd params 11) fun s headRadius => if failed s = true then .done s 0 else
  .bind (rd params 12) fun s displayWidth => if failed s = true then .done s 0 else
  .bind (rd params 13) fun s displayHeight => if failed s = true then .done s 0 else
  .bind (rd params 14) fun s centerX => if failed s = true then .done s 0 else
  .bind (rd params 15) fun s centerY => if failed s = true then .done s 0 else
  .bind (rd params 16) fun s gainX => if failed s = true then .done s 0 else
  .bind (rd params 17) fun s gainY => if failed s = true then .done s 0 else
  .bind (rd params 18) fun s residual => if failed s = true then .done s 0 else
  .bind (rd params 19) fun s expires => if failed s = true then .done s 0 else
  .bind (rd params 20) fun s now => if failed s = true then .done s 0 else
  .bind (rd params 22) fun s consent => if failed s = true then .done s 0 else
  .bind (rd params 25) fun s mapEpoch => if failed s = true then .done s 0 else
  .bind (rd params 29) fun s timeUncertainty => if failed s = true then .done s 0 else
  .bind (rd params 30) fun s mapStart => if failed s = true then .done s 0 else
  .bind (rd params 31) fun s mapEnd => if failed s = true then .done s 0 else
  .bind (rd params 37) fun s sequence => if failed s = true then .done s 0 else
  .bind (rd params 38) fun s actualSequence => if failed s = true then .done s 0 else
  .bind (rd params 39) fun s knownStart => if failed s = true then .done s 0 else
  .bind (rd params 40) fun s knownEnd => if failed s = true then .done s 0 else
  .bind (rd params 41) fun s x0 => if failed s = true then .done s 0 else
  .bind (rd params 42) fun s y0 => if failed s = true then .done s 0 else
  .bind (rd params 43) fun s x1 => if failed s = true then .done s 0 else
  .bind (rd params 44) fun s y1 => if failed s = true then .done s 0 else
  .bind (rd params 46) fun s pendingX0 => if failed s = true then .done s 0 else
  .bind (rd params 47) fun s pendingY0 => if failed s = true then .done s 0 else
  .bind (rd params 48) fun s pendingX1 => if failed s = true then .done s 0 else
  .bind (rd params 49) fun s pendingY1 => if failed s = true then .done s 0 else
  .bind (rd params 50) fun s pending => if failed s = true then .done s 0 else
  .bind (rd params 54) fun s maxAge => if failed s = true then .done s 0 else
  .bind (rd frame 4) fun s epoch => if failed s = true then .done s 0 else
  .bind (rd frame 5) fun s config => if failed s = true then .done s 0 else
  .bind (rd frame 6) fun s captureStart => if failed s = true then .done s 0 else
  .bind (rd frame 7) fun s captureEnd => if failed s = true then .done s 0 else
  .bind (rd frame 8) fun s available => if failed s = true then .done s 0 else
  .bind (rd frame 9) fun s period => if failed s = true then .done s 0 else
  .bind (rd frame 15) fun s exposure => if failed s = true then .done s 0 else
  .bind (rd frame 16) fun s rowTicks => if failed s = true then .done s 0 else
  .bind (rd frame 17) fun s captureConsent => if failed s = true then .done s 0 else
  let radius := (large gainX gainY+1)/2+residual
  let rawStatus : UInt64 :=
    if calibration = 0 then 4 else
    if different expectedConfig config = true then 4 else
    if different consent captureConsent = true then 11 else
    if expires ≤ now then 4 else
    if different epoch mapEpoch = true then 8 else
    if 0x7ffffffffffe0000 < captureStart then 8 else
    if different captureEnd (captureStart+exposure) = true then 8 else
    if different available (captureEnd+16*rowTicks) = true then 8 else
    if period < exposure+16*rowTicks then 8 else
    if now < available then 8 else if maxAge < now-captureEnd then 1 else
    if captureStart < mapStart then 8 else if mapEnd < captureEnd then 8 else
    if captureStart < timeUncertainty then 8 else
    if actualSequence < sequence then 9 else
    if captureStart-timeUncertainty < knownStart then 9 else
    if knownEnd < captureEnd+timeUncertainty then 9 else
    if displayWidth ≤ centerX then 4 else if displayHeight ≤ centerY then 4 else
    if displayWidth < x1 then 2 else if displayHeight < y1 then 2 else 0
  let faceX := featureX faceStats
  let faceY := featureY faceStats
  let headState : UInt64 := if different faceState 0 = true then faceState else
    if headRadius < distance faceX refFaceX then 5 else
    if headRadius < distance faceY refFaceY then 5 else 0
  let gx := mappedCoordinate (featureX eyeStats) faceX refEyeX refFaceX centerX gainX displayWidth
  let gy := mappedCoordinate (featureY eyeStats) faceY refEyeY refFaceY centerY gainY displayHeight
  let status : UInt64 :=
    if different rawStatus 0 = true then rawStatus else
    if different headState 0 = true then headState else
    if different eyeState 0 = true then eyeState else
    if gx = unavailableCoordinate then 7 else if gy = unavailableCoordinate then 7 else
    let region := regionStatus gx gy radius x0 y0 x1 y1
    if different region 0 = true then region else
    pendingStatus gx gy radius pending pendingX0 pendingY0 pendingX1 pendingY1
  finish output status eyeState headState gx gy radius eyeStats faceStats

/-- The only accepted primitive is a protected immutable768-byte source frame.
No source/viewport grant is created here. The staged service must validate its
actual owned frame, processing grant and guest-owned display-history record. -/
def evaluate (frame params output : UInt64) : Action :=
  .boundedFoldU64 40 clearStep 40 0 output 0 0 0 fun s _ => if failed s = true then .done s 0 else
  .bind (copyProvenance frame params output) fun s _ => if failed s = true then .done s 0 else
  .bind (validateFrame frame) fun s frameStatus => if failed s = true then .done s 0 else
  if different frameStatus 0 = true then finish output frameStatus frameStatus frameStatus unavailableCoordinate unavailableCoordinate 0 0 0 else
  .bind (validateParameters params) fun s parameterStatus => if failed s = true then .done s 0 else
  if different parameterStatus 0 = true then finish output parameterStatus parameterStatus parameterStatus unavailableCoordinate unavailableCoordinate 0 0 0 else
  .bind (rd params 4) fun s threshold => if failed s = true then .done s 0 else
  .bind (rd params 5) fun s eyeROI => if failed s = true then .done s 0 else
  .bind (rd params 6) fun s faceROI => if failed s = true then .done s 0 else
  .bind (imageStats frame 16 16 eyeROI threshold) fun s eyeStats => if failed s = true then .done s 0 else
  .bind (imageStats frame 16 16 faceROI threshold) fun s faceStats => if failed s = true then .done s 0 else
  compute frame params output eyeStats faceStats

end Lemma.Multimodal.OpticalDerived
