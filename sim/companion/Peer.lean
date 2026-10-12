import HostIO

/-! Independently persistent hosted-Lean opaque-byte peer.
The host helper performs only pread/fsync/truncate; all framing, validation,
receipt ordering, deduplication and append recovery below are Lean policy. -/
namespace LemmaSim.Companion

def logMagic : UInt64 := 0x3130474f4c434d4c

structure Peer where
  base : System.FilePath
  journal : System.FilePath
  helper : String
  writer : UInt64
  sequence : UInt64 := 0
  bytes : UInt64 := 8
  sectors : Std.HashMap UInt64 ByteArray := {}
  receipts : Std.HashMap UInt64 Frame := {}

def remember (p : Peer) (f : Frame) : Peer :=
  { p with
    sequence := f.sequence,
    sectors := if f.kind = 1 then p.sectors.insert (f.offset / 512) f.payload else p.sectors,
    receipts := p.receipts.insert f.sequence f }

def recover (p : Peer) : IO Peer := do
  if (← p.journal.metadata).byteSize > 64*1024*1024 then throw (IO.userError "peer journal resource bound")
  let b ← IO.FS.readBinFile p.journal
  if b.size < 8 || get64 b 0 != logMagic then throw (IO.userError "peer journal identity")
  let mut p := {p with sequence := 0,bytes := 8,sectors := {},receipts := {}}
  let mut offset := 8
  let mut records := 0
  while offset < b.size do
    if b.size-offset < 8 then break
    let n := (get64 b offset).toNat
    if n < 72 || n > maxPayload+72 then throw (IO.userError "peer journal record length")
    if n > b.size-offset-8 then break
    let f ← match decode (b.extract (offset+8) (offset+8+n)) with
      | .ok f => pure f
      | .error e => throw (IO.userError s!"peer journal corrupt: {e}")
    if f.writer != p.writer || (f.kind != 1 && f.kind != 2) || f.sequence != p.sequence+1 || records >= 100000 then throw (IO.userError "peer journal order/writer/resource")
    p := remember p f
    offset := offset+8+n
    records := records+1
  if offset < b.size then
    let _ ← primitive p.helper #["truncate",p.journal.toString,toString offset]
  return {p with bytes := offset.toUInt64}

def readBytes (p : Peer) (f : Frame) : IO ByteArray := do
  let raw ← primitive p.helper #["pread",p.base.toString,toString f.offset,toString f.length]
  let mut bytes ← match unhex raw with
    | .ok b => pure b
    | .error e => throw (IO.userError e)
  for i in [0:f.length.toNat/512] do
    if let some sector := p.sectors[(f.offset/512)+i.toUInt64]? then
      for j in [0:512] do bytes := bytes.set! (i*512+j) sector[j]!
  return bytes

def exchange (p : Peer) (f : Frame) : IO (Peer × Frame) := do
  if f.writer != p.writer || f.kind = 3 then return (p,response f 71)
  if f.kind = 0 then
    try return (p,response f 0 (← readBytes p f))
    catch _ => return (p,response f 5)
  if f.sequence <= p.sequence then
    if let some prior := p.receipts[f.sequence]? then
      if sameRequest prior f then
        try
          let _ ← primitive p.helper #["sync",p.journal.toString]
          return (p,response f 0 (if f.kind = 1 then f.payload else ByteArray.empty))
        catch _ => return (p,response f 5)
    return (p,response f 71)
  if f.sequence != p.sequence+1 || p.sequence = 0xffffffffffffffff || p.receipts.size >= 100000 then return (p,response f 71)
  let record := encode f
  let bytes := put64 ByteArray.empty record.size.toUInt64 ++ record
  if p.bytes + bytes.size.toUInt64 > 64*1024*1024 then return (p,response f 28)
  try
    IO.FS.withFile p.journal .append fun h => do h.write bytes; h.flush
  catch _ =>
    -- An OS write error may leave a prefix or even the complete record. Recover
    -- the actual observed log before accepting any subsequent transaction.
    let observed ← recover p
    return (observed,response f 5 (if observed.sequence = f.sequence && f.kind = 1 then f.payload else ByteArray.empty))
  -- Complete bytes and receipt are one checksummed append. The live peer now
  -- observes them even if the actual following fsync fails. No ACK is emitted
  -- until that barrier succeeds; retry re-syncs this exact existing receipt.
  let p := {remember p f with bytes := p.bytes+bytes.size.toUInt64}
  try
    let _ ← primitive p.helper #["sync",p.journal.toString]
    return (p,response f 0 (if f.kind = 1 then f.payload else ByteArray.empty))
  catch _ => return (p,response f 5 (if f.kind = 1 then f.payload else ByteArray.empty))

end LemmaSim.Companion
open LemmaSim.Companion

def main (args : List String) : IO UInt32 := do
  let [directory,base,writerText,helper] := args | throw (IO.userError "Peer DIR BASE WRITER OS_HELPER")
  let some writer := writerText.toNat? | throw (IO.userError "invalid writer")
  if writer = 0 || writer > 18446744073709551615 then throw (IO.userError "writer bound")
  let journal := System.FilePath.mk directory / "opaque.log"
  if (← (System.FilePath.mk base).metadata).byteSize != mediumBytes then throw (IO.userError "base capacity")
  if !(← journal.pathExists) then
    IO.FS.writeBinFile journal (put64 ByteArray.empty logMagic)
    let _ ← primitive helper #["sync",journal.toString]
    let _ ← primitive helper #["sync-directory",directory]
  let lock ← IO.FS.Handle.mk journal .readWrite
  if !(← lock.tryLock) then throw (IO.userError "peer journal already owned")
  let mut peer ← recover {base := base,journal := journal,helper := helper,writer := writer.toUInt64}
  let input ← IO.getStdin
  let output ← IO.getStdout
  while true do
    let line ← input.getLine
    if line.isEmpty then break
    let parsed := unhex line.trimAscii.toString >>= decode
    match parsed with
    | .error e => output.putStrLn s!"error {e}"; output.flush
    | .ok frame =>
      let (next,reply) ← exchange peer frame
      peer := next
      output.putStrLn (hex (encode reply))
      output.flush
  return 0
