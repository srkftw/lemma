import Lemma.Radio.WiFi.Codec
import Lemma.Compiler.CFGLower

/-! Component source/lowering and numerical host fixtures. No RV64 execution or
HE/complete radio conformance is inferred from these host evaluations. -/
open Lean Elab Command Lemma.Core0 Lemma.Compiler
run_cmd do
 let env ← getEnv
 let roots := #[``Lemma.Radio.WiFi.Codec.packetCRC,``Lemma.Radio.WiFi.Codec.scrambleBits,
   ``Lemma.Radio.WiFi.Codec.encodeSymbol,``Lemma.Radio.WiFi.Codec.interleaveSymbol,
   ``Lemma.Radio.WiFi.Codec.dataSymbol]
 let suite ← match checkAndLowerActionSuiteForProfile env .user_v0_1 roots with
  | .ok v => pure v | .error e => throwError e.render
 unless suite.usedExecutionOps.isEmpty && suite.usedDeviceOps.isEmpty && suite.usedLoops.isEmpty do
  throwError "pure Wi-Fi coding source gained device/runtime authority"
 let lowered ← match lowerActionSuiteExecution .user_v0_1 suite {
   preserveCalls := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name),symbolPrefix := "wifi_"} with
  | .ok v => pure v | .error e => throwError e
 let module : LLVM.Module := {sourceName := "genuinely elaborated Wi-Fi common coding",functions := lowered.functions}
 match LLVM.validateModule module with
 | .ok _ => pure () | .error e => throwError e
 let some output ← liftIO <| IO.getEnv "LEMMA_WIFI_CODEC_OUTPUT" | throwError "new codec output directory required"
 let path := System.FilePath.mk output
 if ← liftIO path.pathExists then throwError "refusing retained codec output"
 liftIO <| IO.FS.createDirAll path
 liftIO <| IO.FS.writeFile (path/"codec.ll") module.render
 liftIO <| IO.FS.writeFile (path/"codec.symbols") lowered.renderSymbolManifest
 logInfo "WIFI_CODEC_LOWERING:PASS genuine bounded source; no execution/device/runtime operations"

namespace WiFiCodecFixture
open Lemma.Core0.Memory Lemma.Radio.WiFi
partial def execute : Action → IO (UInt8 × UInt64)
 | .done s v => pure (s,v)
 | .bind first next => do let (s,v) ← execute first;execute (next s v)
 | .boundedFoldU64 budget step count initial c0 c1 c2 c3 next => do
   if count.toNat > budget then execute (next 9 initial) else
   let mut value := initial;let mut status : UInt8 := 0
   for i in [:count.toNat] do
    if status = 0 then let (s,v) ← execute (step i.toUInt32 count value c0 c1 c2 c3);status := s;value := v
   execute (next status value)
 | _ => throw <| IO.userError "pure coding fixture attempted hardware/runtime effect"
def require (b : Bool) (m : String) : IO Unit := unless b do throw <| IO.userError m

def check : IO Unit := do
 require ((← execute (Codec.packetCRC 9 0x3837363534333231 0x39))=(0,0xcbf43926)) "CRC32 independent ASCII numerical vector"
 let (s,v) ← execute (Codec.scrambleBits 93 16 0)
 require (s=0 && v &&& 0xffff=0x9836) "IEEE99/107 Table15 first16 scrambler bits"
 require ((← execute (Codec.encodeSymbol 0 0xd064))=(0,0x0e45889f13b0)) "IEEE99/107 Tables7/8 complete BCC vector"
 require ((← execute (Codec.interleaveSymbol 0x0e45889f13b0))=(0,0x401d2970b596)) "published BCC vector under explicit16x3 permutation"
 for i in [:48] do
  let input : UInt64 := 1 <<< i.toUInt64
  let (s,v) ← execute (Codec.interleaveSymbol input)
  require (s=0 && v = (1 <<< (3*(i.toUInt64%16)+i.toUInt64/16))) "all48 independent single-bit permutation cases"
 for (length,word0,word1) in [(0,0,0),(17,0,0),(0xffffffffffffffff,0,0)] do
  require ((← execute (Codec.packetCRC length word0 word1))=(208,0)) "wrapped/invalid resource length produced CRC"
 for (seed,count,input) in [(0,1,0),(128,1,0),(1,33,0),(1,0xffffffffffffffff,0)] do
  require ((← execute (Codec.scrambleBits seed count input))=(208,0)) "invalid scrambler resource admitted"
 for (symbol,length,seed) in [(0,0,1),(0,17,1),(8,16,1),(0,1,0),(0,1,128),(0xffffffffffffffff,16,1)] do
  require ((← execute (Codec.dataSymbol symbol length 0 0 seed))=(208,0)) "invalid DATA descriptor admitted"
 for length in [1,2,15,16] do
  for seed in [1,93,127] do
   for symbol in [:((Codec.symbols length).toNat)] do
    let (s,v) ← execute (Codec.dataSymbol symbol.toUInt64 length 0x7766554433221100 0xffeeddccbbaa9988 seed)
    require (s=0 && v < (1 <<< (61 : UInt64))) "bounded DATA carry escapes layout"
 IO.println "WIFI_CODEC_HOST:PASS primary coding numerical vectors and finite descriptor guards; not target execution"
end WiFiCodecFixture
#eval WiFiCodecFixture.check
