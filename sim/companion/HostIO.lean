import Protocol

/-! Host-process boundary only. Protocol and durability policy remain Lean. -/
namespace LemmaSim.Companion

def primitive (helper : String) (args : Array String) : IO String := do
  let result ← IO.Process.output { cmd := "python3", args := #[helper] ++ args }
  if result.exitCode != 0 then throw (IO.userError s!"raw primitive failed: {result.stderr}")
  return result.stdout.trimAscii.toString

end LemmaSim.Companion
