import Lemma.Platform.RiscV.ExecutionPrimitives

/-! Host finite structured-startup checks. This does not execute a target or
prove hardware PMP behavior; the raw object/ELF audit and guest are separate. -/
open Lemma.Platform.RiscV.ExecutionPrimitives
private def require (ok : Bool) (message : String) : IO Unit :=
  unless ok do throw <| IO.userError message
private def commonConfig : Configuration := {
  stage := .supervisor, lemmasim := true, commonOFDM := true,
  kernelMain := "kernel", firmwareDispatcher := "firmware", supervisorDispatcher := "dispatcher" }
private def rejected (config : Configuration) : Bool :=
  match config.validate with | .error _ => true | .ok _ => false

def check : IO Unit := do
  require (commonPmpAddress == 0x04004c7f && commonPmpConfiguration == 27 && commonPmpReadbacks == 0x804e01f0) "independent Common PMP constants"
  for config in [{commonConfig with productBoot := true},
                 {commonConfig with stage := .bootstrapM},
                 {commonConfig with lemmasim := false},
                 {commonConfig with startupCase := .machineOriginProbe}] do
    require (rejected config) "Common grant escaped exclusive normal LemmaSim supervisor startup"
  let actual ← IO.ofExcept <| renderStartup commonConfig
  for line in ["li t0, 67128447", "csrw pmpaddr8, t0", "csrr t1, pmpaddr8",
               "li t0, 27", "csrw pmpcfg2, t0", "li t0, 2152595952",
               "sd t1, 0(t0)", "sd t1, 8(t0)"] do
    require (actual.contains line) ("Common startup lost " ++ line)
  require (!(actual.contains "li t0, 67127423")) "Common gained BootNV address"
  for config in [{commonConfig with commonOFDM := false},
                 {commonConfig with commonOFDM := false, lemmasim := false},
                 {commonConfig with commonOFDM := false, stage := .bootstrapM}] do
    let historical ← IO.ofExcept <| renderStartup config
    require (!(historical.contains "pmpaddr8") && !(historical.contains "pmpcfg2") &&
             !(historical.contains "li t0, 2152595952")) "default-false historical startup acquired Common state"
  -- Exact already generated source-bound legacy Wire and Product outputs:
  -- genuinely re-render the current default selectors with their actual roots.
  for (directory, config) in [
    ("build/kernel/task006-usb-wire-bulk-notebook-a2", ({
      stage := Stage.supervisor, lemmasim := true,
      kernelMain := "lemma_kernel_core0_action_535", firmwareDispatcher := "lemma_firmware_core0_action_9",
      supervisorDispatcher := "lemma_kernel_core0_action_698" } : Configuration)),
    ("build/kernel/task006-product-executed-bulk-notebook-a2", ({
      stage := Stage.supervisor, lemmasim := true, productBoot := true,
      kernelMain := "lemma_kernel_core0_action_578", firmwareDispatcher := "lemma_firmware_core0_action_9",
      supervisorDispatcher := "lemma_kernel_core0_action_741" } : Configuration))] do
    let historical ← IO.FS.readFile (System.FilePath.mk directory / "startup.S")
    let rendered ← IO.ofExcept <| renderStartup config
    require (historical == rendered) ("changed historical default startup bytes: " ++ directory)
  IO.println "WIFI_PMP_HOST:PASS finite scope/negative selectors; retained Wire/Product startup bytes identical"

#eval check
