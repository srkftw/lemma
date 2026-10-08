import Lemma.Compiler.Export
import Lemma.Compiler.Test.Mutation

/-! Test-only elaboration command for closed compiler-fault injections. -/

namespace Lemma.Compiler.Test.Export

open Lean Elab Command
open Lemma.Compiler.Test.Mutation

private def quoted (value : String) : String :=
  "\"" ++ Lemma.Compiler.Format.escapeJson value ++ "\""

private def renderReport (root : Name) (report : Report) : String :=
  String.intercalate "\n" [
    "{",
    "  \"schema_version\": 1,",
    "  \"artifact_category\": \"test-compiler-mutant\",",
    "  \"transform_stage\": \"structured-llvm-pre-optimization\",",
    "  \"production_selectable\": false,",
    "  \"source_root\": " ++ quoted root.toString ++ ",",
    "  \"fault\": " ++ quoted report.fault.stableId ++ ",",
    "  \"target_source\": " ++ quoted report.targetSource.toString ++ ",",
    "  \"target_llvm\": " ++ quoted report.targetLLVM ++ ",",
    "  \"match_count\": " ++ toString report.matchCount ++ ",",
    "  \"before\": " ++ quoted report.before ++ ",",
    "  \"after\": " ++ quoted report.after,
    "}", ""
  ]

syntax (name := core0ExportFault) "#core0_export_fault " str ident ident : command

elab_rules : command
  | `(#core0_export_fault $faultSyntax:str $rootSyntax:ident $targetSyntax:ident) => do
      let some faultText := faultSyntax.raw.isStrLit?
        | throwErrorAt faultSyntax "compiler fault must be a string literal"
      let some fault := FaultId.parse? faultText
        | throwErrorAt faultSyntax s!"unknown closed compiler fault `{faultText}`"
      let root ← resolveGlobalConstNoOverload rootSyntax
      let target ← resolveGlobalConstNoOverload targetSyntax
      let output? ← liftIO <| IO.getEnv "LEMMA_CORE0_OUT"
      let some output := output?
        | throwErrorAt rootSyntax "LEMMA_CORE0_OUT must name the generated-artifact directory"
      let env ← getEnv
      let (program, lowered) ← liftIO <| Lemma.Compiler.Export.prepareLegacyApplication env root
      let (mutated, report) ← match Mutation.apply { fault, targetSource := target } lowered with
        | .ok value => pure value
        | .error message => throwErrorAt targetSyntax message
      let outputDir := System.FilePath.mk output
      liftIO <| Lemma.Compiler.Export.writeLegacyArtifacts root outputDir program mutated
      liftIO <| IO.FS.writeFile (outputDir / "compiler-mutation.json") (renderReport root report)
      logInfoAt rootSyntax m!"Core0 test mutant `{fault.stableId}` exported `{root}` to {output}"

end Lemma.Compiler.Test.Export
