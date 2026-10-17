import Lean
import Lemma.Compiler.CFGLower
import Lemma.Platform.RiscV.ExecutionPrimitives
import tests.qemu.SoftTlbExecProbe

/-! Dedicated test exporter. It invokes the existing genuine declaration checker
and unchanged kernel-v0.4 lowering; it supplies no manually built Action AST.
The typed machine lines only establish privilege, PMP, stack and trap disposition. -/
open Lean Elab Command Lemma.Compiler
open Lemma.Machine.Primitives

private def ins (i : Instruction) : Line := .instruction i
private def lines (a : Array Line) : String := String.intercalate "\n" (a.toList.map Line.render)

elab "#lemma_qemu_softtlb_exec_probe" : command => do
  let env ← getEnv
  let suite ← liftIO <| IO.ofExcept <| (Lemma.Core0.checkAndLowerActionSuiteForProfile env
    .kernel_v0_4 #[``Lemma.Qemu.SoftTlbExecProbe.run]).mapError (·.render)
  let preserved := suite.scalarFunctions.map (·.name) ++ suite.actionFunctions.map (·.name)
  let lowered ← liftIO <| IO.ofExcept <| lowerActionSuiteExecution .kernel_v0_4 suite
    { preserveCalls := preserved, symbolPrefix := "lemma_probe_" }
  let mut declarations : Array LLVM.Declaration := #[]
  for spec in suite.usedExecutionOps do
    if let some name := spec.primitiveSymbol? then
      declarations := declarations.push {
        name := name
        returnType := if spec.resultKind == .checked then .checkedResult else .i64
        parameters := spec.machineArguments.map llvmTy }
  declarations := declarations.push { name := "core0_io_fence", returnType := .void, parameters := #[] }
  let module : LLVM.Module := {
    sourceName := "genuine Lean QEMU executable SoftTLB probe"
    declarations := declarations
    functions := lowered.functions }
  liftIO <| IO.ofExcept <| LLVM.validateModule module
  let some root := lowered.roots[0]? | throwError "Missing genuinely lowered probe root"
  let startup := ".option norvc\n.option norelax\n.section .text.start,\"ax\",@progbits\n.global _start\n.global core0_io_fence\n.global lemma_exec_install_satp\n.global lemma_exec_fence_instruction\n" ++ lines #[
    .label "_start", ins (.csrWrite .mie .zero), ins .maskMachineInterruptEnable,
    ins (.csrWrite .satp .zero), ins .translationFenceAll,
    ins (.loadImmediate .sp 0x80510000), ins (.move .gp .zero), ins (.move .tp .zero),
    ins (.loadAddress .t0 "probe_fatal"), ins (.csrWrite .mtvec .t0), ins (.csrWrite .stvec .t0),
    ins (.loadImmediate .t0 0x3fffffffffffff), ins (.csrWrite .pmpaddr0 .t0),
    ins (.loadImmediate .t0 0x1f), ins (.csrWrite .pmpcfg0 .t0),
    ins (.loadImmediate .t0 0x800), ins (.csrWrite .mstatus .t0),
    ins (.loadAddress .t0 "probe_supervisor"), ins (.csrWrite .mepc .t0), ins .machineReturn,
    .label "probe_supervisor", ins (.call root.llvm), ins (.branchNeZero .a0 "probe_fatal"),
    .label "probe_park", ins .waitForInterrupt, ins (.jump "probe_park"),
    .label "probe_fatal", ins (.loadImmediate .t0 0x100000),
    ins (.loadImmediate .t1 0x3333), ins (.storeWord .t1 .t0 0), ins (.jump "probe_fatal"),
    .label "core0_io_fence", ins .fenceIO, ins .return] ++ "\n" ++
    lines Lemma.Platform.RiscV.ExecutionPrimitives.installSatp ++ "\n" ++
    lines Lemma.Platform.RiscV.ExecutionPrimitives.fenceInstruction ++ "\n"
  let some a := lowered.symbols.find? (fun row => row.source == ``Lemma.Qemu.SoftTlbExecProbe.valueA)
    | throwError "Missing genuinely lowered valueA"
  let some b := lowered.symbols.find? (fun row => row.source == ``Lemma.Qemu.SoftTlbExecProbe.valueB)
    | throwError "Missing genuinely lowered valueB"
  let linker := "OUTPUT_ARCH(riscv)\nENTRY(_start)\n" ++
    "PHDRS { start PT_LOAD FLAGS(5); main PT_LOAD FLAGS(7); code_a PT_LOAD FLAGS(5); code_b PT_LOAD FLAGS(5); }\n" ++
    "SECTIONS { .text.start 0x80000000 : { *(.text.start) } :start\n" ++
    ".alias_a 0x82050000 : AT(0x82103000) { *(.text." ++ a.llvm ++ ") } :code_a\n" ++
    ".alias_b 0x82104000 : AT(0x82104000) { *(.text." ++ b.llvm ++ ") } :code_b\n" ++
    ".text 0x80200000 : AT(0x80200000) { *(.text*) *(.rodata*) } :main\n" ++
    ".data : { *(.data*) } :main .bss : { *(.bss*) } :main\n" ++
    "ASSERT(SIZEOF(.alias_a) > 0 && SIZEOF(.alias_a) <= 4096, \"Compiled pageA extent\")\n" ++
    "ASSERT(SIZEOF(.alias_b) > 0 && SIZEOF(.alias_b) <= 4096, \"Compiled pageB extent\")\n" ++
    "/DISCARD/ : { *(.comment) *(.eh_frame*) } }\n"
  let some out ← liftIO (IO.getEnv "LEMMA_SOFTTLB_EXEC_OUT") | throwError "Missing probe output"
  liftIO <| IO.FS.createDirAll out
  for (name, contents) in #[ ("program.ll", module.render), ("startup.S", startup),
    ("link.ld", linker), ("symbols.txt", lowered.renderSymbolManifest),
    ("normalized.txt", String.intercalate "\n" (suite.actionFunctions.toList.map fun f => f.name.toString ++ ":" ++ f.body.renderNormalized)) ] do
    liftIO <| IO.FS.writeFile (System.FilePath.mk out / name) contents
  logInfo "Genuine checked kernel-v0.4 SoftTLB probe exported"

#lemma_qemu_softtlb_exec_probe
