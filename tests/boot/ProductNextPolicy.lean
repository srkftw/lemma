import Lemma.Boot.Product
import Lemma.Boot.ProductNext

/-! Host-only independent policy regression. Product9 is a distinct compatibility
contract; this fixture grants no actual boot or physical qualification. -/
namespace ProductNextPolicyFixture
private def require (value : Bool) (name : String) : IO Unit :=
  unless value do throw <| IO.userError name

def tests : IO Unit := do
  let old : UInt64 := 0x0007000300010001
  let next : UInt64 := 0x0009000300010001
  require (Lemma.Boot.Product.compatibility == old) "historical Product7 compatibility changed"
  require (Lemma.Boot.ProductNext.compatibility == next) "Product9 compatibility differs"
  let header := Lemma.Boot.ProductNext.headerFieldsValid
  require (header 0x31474d49414d454c 1 0x9000000000001 next 1 0x80000000) "valid Product9 header"
  for binding in #[old,0,next+1,0xffffffffffffffff] do
    require (!(header 0x31474d49414d454c 1 0x9000000000001 binding 1 0x80000000)) "old/arbitrary image admitted on Product9"
  require (!(Lemma.Boot.Product.headerFieldsValid 0x31474d49414d454c 1 0x9000000000001 next 1 0x80000000)) "Product7 silently adopted Product9"
  let input : UInt64 := 0x3938373635343332
  require (Lemma.Boot.ProductNext.crcWord 0xffffffff input == Lemma.Boot.Product.crcWord 0xffffffff input) "v1 CRC word codec changed"
  require (Lemma.Boot.ProductNext.metadataFieldsValid 0x31444d42414d454c 1 2 0 10 1 11 0 3) "v1 transactional metadata changed"
  for attempt in #[0,1,2,3] do
    require (Lemma.Boot.ProductNext.chooseImage 0 1 attempt == Lemma.Boot.Product.chooseImage 0 1 attempt) "attempt/fallback semantics changed"
  IO.println "PRODUCT_NEXT_POLICY:PASS exact disjoint compatibility, historical Product7 denial, same metadata/CRC/attempt codec; no authentication or healthy boot claim"
end ProductNextPolicyFixture
#eval ProductNextPolicyFixture.tests
