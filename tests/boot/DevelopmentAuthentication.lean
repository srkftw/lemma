import Lemma.Boot.DevelopmentAuthentication
open Lemma.Boot.DevelopmentAuthentication Lemma.Boot.ProductExecuted
-- Admission and disjointness of the actual compiled ROM's fixed workspaces.
-- This catches both the sector-helper16KiB bound and checked physical-region
-- bounds. The actual negative/positive MAC remains an RV64 integration test.
#eval show IO Unit from do
  let spans : Array (UInt64 × UInt64) := #[(scratch,64),(scratch+0x400,512),(scratch+0x800,80),
    (tagBuffer,512),(headerBuffer,512),(domain,32),(keyBuffer,32),(digest,32),
    (workspace,2048),(metadata0Buffer,512),(metadata1Buffer,512)]
  for (base,bytes) in spans do
    unless base%8 == 0 && scratch ≤ base && base+bytes ≤ scratch+0x4000 do
      throw <| IO.userError "authenticated ROM escaped admitted scratch"
  for i in [:spans.size] do
    for j in [:i] do
      let (a,an) := spans[i]!
      let (b,bn) := spans[j]!
      unless a+an ≤ b || b+bn ≤ a do
        throw <| IO.userError "authenticated ROM workspaces overlap"
  IO.println "DEVELOPMENT_AUTH_LAYOUT:PASS"
