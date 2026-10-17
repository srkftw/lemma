import Lemma.User.Runtime.Arena
import Lemma.Mathematics.Exact

namespace Lemma.Mathematics.OwnedSubmission
open Lemma.Core0.Memory Lemma.User.Runtime

/-- Identical admitted original domains. This pure selector is also usable by
cold record validation; heap resource errors create no mathematical evidence. -/
def result (goal n d p0 p1 p2 budget : UInt64) : UInt64 :=
  if goal = 1 then Exact.rational 1 2 1 3 n d budget else
  if goal = 2 then Exact.polynomial 1 1 1 1 p0 p1 p2 budget else Exact.unsupported

private def writeInputs (handle goal n d p0 p1 p2 budget : UInt64) : Action :=
  .bind (Arena.bytesWriteWord handle 0 goal) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 8 n) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 16 d) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 24 p0) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 32 p1) fun s _ => if s = 0 then
  .bind (Arena.bytesWriteWord handle 40 p2) fun s _ => if s = 0 then
  Arena.bytesWriteWord handle 48 budget else .done s 0 else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def checkObject (handle resultBox : UInt64) : Action :=
  .bind (Arena.bytesReadWord handle 0) fun s goal => if s = 0 then
  .bind (Arena.bytesReadWord handle 8) fun s n => if s = 0 then
  .bind (Arena.bytesReadWord handle 16) fun s d => if s = 0 then
  .bind (Arena.bytesReadWord handle 24) fun s p0 => if s = 0 then
  .bind (Arena.bytesReadWord handle 32) fun s p1 => if s = 0 then
  .bind (Arena.bytesReadWord handle 40) fun s p2 => if s = 0 then
  .bind (Arena.bytesReadWord handle 48) fun s budget => if s = 0 then
  Arena.boxSet resultBox (result goal n d p0 p1 p2 budget) else .done s 0
  else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0 else .done s 0

private def complete (input resultBox : UInt64) (status : UInt8) (value : UInt64) : Action :=
  .bind (Arena.release input) fun inputStatus _ =>
  .bind (Arena.release resultBox) fun resultStatus _ =>
  if inputStatus = 0 then if resultStatus = 0 then .done status value
    else .done resultStatus 0 else .done inputStatus 0

/-- The worker borrows a real output object. Its retained reference is released
before the caller reads the completed value; the caller keeps its own reference. -/
private def runBorrowed (input resultBox : UInt64) : Action :=
  .bind (Arena.retain resultBox) fun s _ => if s = 0 then
  .bind (checkObject input resultBox) fun resultStatus _ =>
  .bind (Arena.release resultBox) fun cleanup _ =>
  if cleanup = 0 then if resultStatus = 0 then Arena.boxGet resultBox
    else .done resultStatus 0 else .done cleanup 0
  else .done s 0

/-- Real owned allocation and release surround every submission. OOM or
cancellation returns its actual error without submitting or changing evidence.
This is not yet a separately linked verifier or managed-language constructor. -/
def check (goal n d p0 p1 p2 budget : UInt64) : Action :=
  .bind Arena.ensure fun s _ => if s = 0 then
  .bind (Arena.newBox 0) fun s resultBox => if s = 0 then
  .bind (Arena.newBytes 56) fun s input => if s = 0 then
  .bind (writeInputs input goal n d p0 p1 p2 budget) fun s _ =>
  if s = 0 then
  .bind (runBorrowed input resultBox) fun s outcome => complete input resultBox s outcome
  else complete input resultBox s 0
  else .bind (Arena.release resultBox) fun cleanup _ =>
    if cleanup = 0 then .done s 0 else .done cleanup 0
  else .done s 0 else .done s 0

end Lemma.Mathematics.OwnedSubmission
