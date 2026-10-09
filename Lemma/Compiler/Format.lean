namespace Lemma.Compiler.Format

private def hexDigit (n : Nat) : Char :=
  if n < 10 then
    Char.ofNat ('0'.toNat + n)
  else
    Char.ofNat ('a'.toNat + (n - 10))

/-- Render exactly `width` hexadecimal digits.  Callers choose the width so
addresses and machine values never depend on host pretty-printer conventions. -/
def hexFixed (width n : Nat) : String :=
  String.ofList <| (List.range width).map fun i =>
    let shift := 4 * (width - 1 - i)
    hexDigit ((n / (2 ^ shift)) % 16)

def hex64 (n : UInt64) : String :=
  hexFixed 16 n.toNat

def hexAddr (n : Nat) : String :=
  "0x" ++ hexFixed 16 n

def escapeJson (s : String) : String :=
  String.join <| s.toList.map fun c =>
    match c with
    | '"' => "\\\""
    | '\\' => "\\\\"
    | '\n' => "\\n"
    | '\r' => "\\r"
    | '\t' => "\\t"
    | c => String.singleton c

end Lemma.Compiler.Format
