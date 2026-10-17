import Lemma.Platform.RiscV.ExecutionPrimitives

/- Actual structured startup output, with an independent NAPOT decoder.
This is a host Lean boundary test; RV64 CSR readback and S-mode execution
require the separately audited Product guest and native observations. -/
open Lemma.Machine.Primitives Lemma.Platform.RiscV.ExecutionPrimitives

private def require (value : Bool) (reason : String) : IO Unit :=
  if value then pure () else throw <| IO.userError reason

private def trailingOnes : Nat → Nat → Nat
  | 0, _ => 0
  | fuel+1, value => if value % 2 = 1 then 1 + trailingOnes fuel (value/2) else 0

private def configuration : Configuration := {
  stage := .supervisor, lemmasim := true, kernelMain := "compiled_kernel",
  firmwareDispatcher := "compiled_firmware", supervisorDispatcher := "compiled_supervisor" }

#eval show IO Unit from do
  let legacy := startup configuration
  let product := startup { configuration with productBoot := true }
  let extra : Array Line := #[
    .instruction (.csrWrite .pmpcfg2 .zero),
    .instruction (.loadImmediate .t0 0x0400487f),
    .instruction (.csrWrite .pmpaddr8 .t0),
    .instruction (.csrRead .t1 .pmpaddr8),
    .instruction (.branchNe .t0 .t1 "lemma_machine_fatal"),
    .instruction (.loadImmediate .t0 0x1b),
    .instruction (.csrWrite .pmpcfg2 .t0),
    .instruction (.csrRead .t1 .pmpcfg2),
    .instruction (.branchNe .t0 .t1 "lemma_machine_fatal") ]
  require (product.size == legacy.size + 9) "Product startup changed more than nine narrow instructions"
  require (product.filter (fun line => !extra.contains line) == legacy)
    "Product extension changed a historical startup instruction"
  for line in extra do
    let expected := if line == .instruction (.branchNe .t0 .t1 "lemma_machine_fatal") then 2 else 1
    require ((product.filter (fun other => other == line)).size == expected)
      "Product write/readback/error branch missing or duplicated"
  require (!legacy.any (fun line => extra.contains line)) "Legacy startup acquired Product PMP authority"
  let bits := trailingOnes 63 productPmpAddress
  let bytes := 2^(bits+3)
  let base := (productPmpAddress / 2^bits) * 2^bits * 4
  require (bits == 7 && base == 0x10012000 && bytes == 0x400)
    "Independent NAPOT decode differs from the exact NV aperture"
  let contains := fun address width => base ≤ address && address < base+bytes && width ≤ base+bytes-address
  require (contains 0x10012000 8 && contains 0x100123f8 8 && contains 0x100123ff 1 &&
    !contains 0x10011fff 1 && !contains 0x10012400 1 && !contains 0x100123f9 8)
    "Product PMP boundary or access width differs"
  require (productPmpConfiguration % 8 == 3 && productPmpConfiguration / 8 % 4 == 3 &&
    productPmpConfiguration / 128 == 0) "Product PMP must be unlocked NAPOT RW/NX"
  for invalid in #[ { configuration with lemmasim := false, productBoot := true },
      { configuration with stage := .bootstrapM, productBoot := true },
      { configuration with startupCase := .machineOriginProbe, productBoot := true } ] do
    require (match invalid.validate with | .error _ => true | .ok _ => false)
      "Product authority entered an unselected startup profile"
  require (CSR.render .pmpaddr8 == "pmpaddr8" && CSR.render .pmpcfg2 == "pmpcfg2")
    "Structured CSR names differ"
  IO.println "PRODUCT_PMP:PASS exact aperture/RW-NX/readback/default-legacy/startup-denials"
