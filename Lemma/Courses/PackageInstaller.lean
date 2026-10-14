import Lemma.Courses.PackageCommand
import Lemma.Courses.PackageStore
import Lemma.Courses.PackageAwaitClient
import Lemma.User.CapabilityConsole

/-! Separately linked owner-local course installer. Raw console input is copied
into its own pages. Guest validation, Store staging/publication, loading and
selection execute here. It receives Console Read/Write and Store Call grants,
never raw block or notebook memory authority. Installed receipts require the
real Store Commit reply; Present/selected data are distinct observations. -/
namespace Lemma.Courses.PackageInstaller
open Lemma.Core0.Memory
open Lemma.User
open Lemma.Services.Store
open Lemma.Courses.PackageFormat

def header : UInt64 := 0x20300
def state : UInt64 := 0x20800
def outgoing : UInt64 := 0x20b00
def incoming : UInt64 := 0x20c00
def context : UInt64 := 0x20e00
def package : UInt64 := 0x40000
def loaded : UInt64 := 0x48000

private def get (offset : UInt64) : Action := Memory.read64 (state + offset)
private def put (offset value : UInt64) : Action := Memory.write64 (state + offset) value
private def command (offset : UInt64) : Action := Memory.read64 (header + offset)
private def minimum (a b : UInt64) : UInt64 := if a < b then a else b
private def failed : Action := .done 95 0

private def allocateStep (i _ : UInt32) (count _ _ _ _ : UInt64) : Action :=
  let address := package + i.toUInt64 * 4096
  .bind (Syscall.allocatePage address) fun s actual =>
  if s = 0 then if actual = address then .done 0 (count + 1) else failed else .done s 0

private def reset : Action :=
  .bind (put 16 0) fun s _ => if s = 0 then
  .bind (put 24 0) fun s _ => if s = 0 then put 32 0 else failed else failed

private def report (operation identity edition crc sequence : UInt64) (status : UInt8) : Action :=
  .bind (get 0) fun s console => if s = 0 then
  CapabilityConsole.record console 0x4b1 (operation ||| (status.toUInt64 <<< 8)) sequence
    (identity ||| (edition <<< 16)) crc else failed

private def prepare (identity edition target request : UInt64) : Action :=
  .bind (get 8) fun s endpoint => if s = 0 then
  .bind (Memory.write64 context endpoint) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 8) outgoing) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 16) incoming) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 24) 1) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 32) identity) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 40) edition) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 48) target) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 56) 32768) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 64) request) fun s _ => if s = 0 then
  .bind (Memory.write64 (context + 72) 0) fun s _ => .done s 0
  else failed else failed else failed else failed else failed else failed else failed else failed else failed else failed

private def loadPackage (identity edition ordinal expected : UInt64) : Action :=
  .bind (PackageStore.load context) fun s bytes => if s = 0 then
  .bind (Memory.read64 (loaded + 80)) fun s crc => if s = 0 then
  if crc = expected then
  .bind (get 0) fun s console => if s = 0 then
  .bind (CapabilityConsole.record console 0x4b2 bytes crc identity edition) fun s _ => if s = 0 then
  .bind (PackageTarget.goal loaded bytes ordinal) fun s goal =>
  if s = 0 then
  .bind (CapabilityConsole.record console 0x4b3 ordinal goal crc edition) fun s _ => if s = 0 then
  report 2 identity edition crc 0 0 else failed
  else report 2 identity edition crc 0 s
  else failed else failed
  else report 2 identity edition crc 0 integrityFailure
  else failed else report 2 identity edition expected 0 s

private def execute : Action :=
  .bind (command 16) fun s operation => if s = 0 then
  .bind (command 24) fun s identity => if s = 0 then
  .bind (command 32) fun s edition => if s = 0 then
  .bind (command 40) fun s bytes => if s = 0 then
  .bind (command 48) fun s transaction => if s = 0 then
  .bind (command 56) fun s expected => if s = 0 then
  .bind (get 40) fun s request => if s = 0 then
  if request ≤ Format.maximumSequence - 6288 then
  .bind (put 40 (request + 6288)) fun s _ => if s = 0 then
  .bind (prepare identity edition (if operation = 2 then loaded else package) request) fun s _ => if s = 0 then
  .bind (if operation = 1 then
    .bind (Memory.read64 (package + 80)) fun s crc => if s = 0 then
    if crc = expected then
      .bind (PackageStore.install context bytes transaction) fun s sequence => report operation identity edition crc sequence s
    else report operation identity edition crc 0 integrityFailure else failed
  else if operation = 2 then
    .bind (PackageStore.awaitReady context) fun s _ => if s = 0 then
    .bind (Memory.write64 (context + 64) (request + 6000)) fun s _ => if s = 0 then
    loadPackage identity edition transaction expected else failed
    else report operation identity edition expected 0 s
  else if operation = 3 then
    .bind (get 8) fun s endpoint => if s = 0 then
    .bind (Client.call endpoint outgoing incoming 6 1 (object identity edition) transaction 0 0 0 request)
      fun s sequence => report operation identity edition expected sequence s
    else failed
  else report operation identity edition expected 0 unsupported) fun s _ =>
  if s = 0 then reset else failed
  else failed else failed
  else report operation identity edition expected 0 resourceLimit
  else failed else failed else failed else failed else failed else failed else failed

private def headerComplete : Action :=
  .bind (command 0) fun s magic => if s = 0 then
  .bind (command 8) fun s version => if s = 0 then
  .bind (command 16) fun s operation => if s = 0 then
  .bind (command 24) fun s identity => if s = 0 then
  .bind (command 32) fun s edition => if s = 0 then
  .bind (command 40) fun s bytes => if s = 0 then
  .bind (command 48) fun s transaction => if s = 0 then
  .bind (command 56) fun s crc => if s = 0 then
  let status := PackageCommand.shape magic version operation identity edition bytes transaction crc
  if status = 0 then
    if operation = 1 then
      .bind Syscall.time fun s now => if s = 0 then
      if now ≤ 0xffffffffffffffff - 100000000 then
      .bind (put 16 0) fun s _ => if s = 0 then
      .bind (put 24 bytes) fun s _ => if s = 0 then
      .bind (put 32 1) fun s _ => if s = 0 then put 48 (now + 100000000) else failed else failed else failed
      else failed else failed
    else execute
  else
    -- Unknown framing cannot safely resynchronize an arbitrary byte stream.
    -- Report the actual error, then terminate this unprivileged task only.
    .bind (report operation identity edition crc 0 status) fun s _ =>
    if s = 0 then Syscall.exit status.toUInt64 else failed
  else failed else failed else failed else failed else failed else failed else failed else failed

private def receive (phase filled desired : UInt64) : Action :=
  .bind (get 0) fun s console => if s = 0 then
  let address := if phase = 0 then header else package
  let count := minimum 256 (desired - filled)
  .bind (Capability.consoleRead console (address + filled) count) fun status bytes =>
  if status = ABI.noByte then if bytes = 0 then
    .bind (Syscall.sleep 10000) fun s _ => if s = 0 then .done 0 0 else failed
  else failed else
  if status = 0 then if 0 < bytes then if bytes ≤ count then
    .bind (put 16 (filled + bytes)) fun s _ => if s = 0 then
    if filled + bytes = desired then if phase = 0 then headerComplete else execute else .done 0 0
    else failed
  else failed else failed else failed
  else failed

def step : Action :=
  .bind (get 32) fun s phase => if s = 0 then
  .bind (get 16) fun s filled => if s = 0 then
  .bind (get 24) fun s body => if s = 0 then
  let desired := if phase = 0 then (64 : UInt64) else body
  if phase ≤ 1 then if filled < desired then
    if phase = 0 then receive phase filled desired else
    .bind (get 48) fun s deadline => if s = 0 then
    .bind Syscall.time fun s now => if s = 0 then
    if now < deadline then receive phase filled desired else Syscall.exit 93
    else failed else failed
  else failed else failed
  else failed else failed else failed

def main (initialization : UInt64) : Action :=
  if initialization ≤ 1 then
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s identity => if s = 0 then
  .boundedFoldU64 16 allocateStep 16 0 0 0 0 0 fun s pages => if s = 0 then
  if pages = 16 then
  .bind (put 0 console) fun s _ => if s = 0 then
  .bind (put 8 endpoint) fun s _ => if s = 0 then
  .bind (put 40 6001) fun s _ => if s = 0 then
  .bind reset fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x4b5 identity initialization console endpoint) fun s _ => if s = 0 then
  .bind (prepare 1 1 loaded 1) fun s _ => if s = 0 then
  .bind (PackageStore.awaitPublished context initialization) fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x4b0 identity initialization console endpoint) fun s _ =>
  if s = 0 then .loop step else failed else failed else failed else failed
  else failed else failed else failed else failed
  else failed else failed else failed else failed else failed

  else failed

/-! The completion-driven successor preserves historical main and every
command/Load/Install path. Only startup uses the explicitly selected op16
Store root. Admission is pending; only its genuine mounted reply reaches4b0.
The same private pages, capability grants and initialization flag remain. -/
def mainAwait (initialization : UInt64) : Action :=
  if initialization ≤ 1 then
  .bind (Capability.bootGrant 0) fun s console => if s = 0 then
  .bind (Capability.bootGrant 1) fun s endpoint => if s = 0 then
  .bind Syscall.identity fun s identity => if s = 0 then
  .boundedFoldU64 16 allocateStep 16 0 0 0 0 0 fun s pages => if s = 0 then
  if pages = 16 then
  .bind (put 0 console) fun s _ => if s = 0 then
  .bind (put 8 endpoint) fun s _ => if s = 0 then
  .bind (put 40 6001) fun s _ => if s = 0 then
  .bind reset fun s _ => if s = 0 then
  .bind (CapabilityConsole.record console 0x4b5 identity initialization console endpoint) fun s _ => if s = 0 then
  .bind (prepare 1 1 loaded 1) fun s _ => if s = 0 then
  .bind (PackageAwaitClient.call endpoint outgoing incoming 1 initialization 1) fun s generation => if s = 0 then
  if 0 < generation then
  .bind (CapabilityConsole.record console 0x4b0 identity initialization console endpoint) fun s _ =>
  if s = 0 then .loop step else failed else failed
  else failed else failed else failed
  else failed else failed else failed else failed
  else failed else failed else failed else failed else failed
  else failed

end Lemma.Courses.PackageInstaller
