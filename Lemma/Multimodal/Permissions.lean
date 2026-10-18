/-! Explicit per-stream grants. Discovery grants no collection. Bits distinguish
acquisition, local processing, transmission, retention, research and training;
output is separate. Epochs retire instead of wrapping. No host/tutor authority. -/
namespace Lemma.Multimodal.Permissions

private def mmDifferent (a b : UInt64) : Bool := if a = b then false else true
private def mmFailed (s : UInt8) : Bool := if s = 0 then false else true

def epochLimit : UInt64 := 0x7ffffffffffffffe

def request (stream bits rate extent expiry now session : UInt64) : UInt64 :=
  if 8 < stream then 2 else if bits = 0 then 2 else if 127 < bits then 2 else
  if stream = 8 then if mmDifferent bits 64 = true then 7 else limits rate extent expiry now session else
  if mmDifferent (bits &&& 64) (0) = true then 7 else
  if bits &&& 1 = 0 then 7 else limits rate extent expiry now session
where
  limits (rate extent expiry now session : UInt64) : UInt64 :=
    if session = 0 then 7 else if rate = 0 then 3 else if 1000000 < rate then 3 else
    if extent = 0 then 3 else if 1048576 < extent then 3 else
    if expiry ≤ now then 8 else if 10000000000 < expiry - now then 3 else 0

/-- Snapshot-era grant checks must be evaluated against the current interaction
session. Transmit/retain/training never follow from acquisition by implication. -/
def permits (held needed grantEpoch currentEpoch grantSession currentSession expiry now : UInt64) : UInt64 :=
  if grantEpoch = 0 then 7 else if mmDifferent grantEpoch currentEpoch = true then 4 else
  if grantSession = 0 then 7 else if mmDifferent grantSession currentSession = true then 4 else
  if expiry ≤ now then 8 else if mmDifferent (held &&& needed) (needed) = true then 7 else 0

def nextEpoch (epoch : UInt64) : UInt64 :=
  if epoch < epochLimit then epoch + 1 else 0

end Lemma.Multimodal.Permissions
