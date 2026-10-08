"""Self-contained validation for the closed Gate 1 compiler-fault corpus."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "tests" / "foundation" / "compiler_faults.json"
UINT64_HEX = re.compile(r"0x[0-9a-f]{16}\Z")

ROOT_DECL = "Lemma.Examples.Foundation.CompilerFaults.entry"
EXPECTED_CASES = {
    "ult-as-ule": {
        "name": "unsigned-lt-equal",
        "case_id": "0x0000000000000101",
        "target_source": "Lemma.Examples.Foundation.CompilerFaults.strictLt",
        "args": [
            "0x0000000000000000",
            "0x0000000000000007",
            "0x0000000000000007",
        ],
        "expected_clean": "0x0000000000000022",
        "expected_mutant": "0x0000000000000011",
    },
    "ult-as-slt": {
        "name": "unsigned-lt-high-bit",
        "case_id": "0x0000000000000102",
        "target_source": "Lemma.Examples.Foundation.CompilerFaults.unsignedLt",
        "args": [
            "0x0000000000000001",
            "0x8000000000000000",
            "0x0000000000000000",
        ],
        "expected_clean": "0x0000000000000044",
        "expected_mutant": "0x0000000000000033",
    },
    "add-as-sub": {
        "name": "add-vs-sub-asymmetric",
        "case_id": "0x0000000000000103",
        "target_source": "Lemma.Examples.Foundation.CompilerFaults.addPair",
        "args": [
            "0x0000000000000002",
            "0x0000000000000009",
            "0x0000000000000004",
        ],
        "expected_clean": "0x000000000000000d",
        "expected_mutant": "0x0000000000000005",
    },
    "zext-as-sext": {
        "name": "zext-vs-sext-top-bit",
        "case_id": "0x0000000000000104",
        "target_source": "Lemma.Examples.Foundation.CompilerFaults.widen32",
        "args": [
            "0x0000000000000003",
            "0x0000000080000001",
            "0x0000000000000000",
        ],
        "expected_clean": "0x0000000080000001",
        "expected_mutant": "0xffffffff80000001",
    },
    "trunc-high-half": {
        "name": "trunc-low-vs-high-half",
        "case_id": "0x0000000000000105",
        "target_source": "Lemma.Examples.Foundation.CompilerFaults.truncate32",
        "args": [
            "0x0000000000000004",
            "0x1122334455667788",
            "0x0000000000000000",
        ],
        "expected_clean": "0x0000000055667788",
        "expected_mutant": "0x0000000011223344",
    },
    "swap-call-args": {
        "name": "call-arguments-swapped",
        "case_id": "0x0000000000000106",
        "target_source": "Lemma.Examples.Foundation.CompilerFaults.callOrder",
        "args": [
            "0x0000000000000005",
            "0x0000000000000009",
            "0x0000000000000004",
        ],
        "expected_clean": "0x0000000000000005",
        "expected_mutant": "0xfffffffffffffffb",
    },
}


class CompilerFaultManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = json.loads(MANIFEST.read_text(encoding="utf-8"))
        cls.cases = cls.document["cases"]

    def test_closed_schema_and_six_fault_ids(self) -> None:
        self.assertEqual(set(self.document), {"schema_version", "root", "cases"})
        self.assertEqual(self.document["schema_version"], 1)
        self.assertEqual(self.document["root"], ROOT_DECL)
        self.assertIsInstance(self.cases, list)
        self.assertEqual(len(self.cases), 6)
        self.assertEqual({case["fault"] for case in self.cases}, set(EXPECTED_CASES))
        expected_fields = {
            "name",
            "case_id",
            "fault",
            "target_source",
            "args",
            "expected_clean",
            "expected_mutant",
            "covers",
        }
        for case in self.cases:
            with self.subTest(fault=case.get("fault")):
                self.assertEqual(set(case), expected_fields)

    def test_names_ids_targets_and_values_are_unique_and_well_formed(self) -> None:
        for field in ("name", "case_id", "fault", "target_source"):
            values = [case[field] for case in self.cases]
            self.assertEqual(len(values), len(set(values)), f"duplicate {field}")
        for case in self.cases:
            with self.subTest(fault=case["fault"]):
                self.assertRegex(case["case_id"], UINT64_HEX)
                self.assertEqual(len(case["args"]), 3)
                for value in (
                    *case["args"],
                    case["expected_clean"],
                    case["expected_mutant"],
                ):
                    self.assertIsInstance(value, str)
                    self.assertRegex(value, UINT64_HEX)
                self.assertNotEqual(case["expected_clean"], case["expected_mutant"])
                self.assertIsInstance(case["covers"], list)
                self.assertTrue(case["covers"])
                self.assertTrue(all(isinstance(item, str) and item for item in case["covers"]))

    def test_distinguishing_vectors_match_the_source_fixture(self) -> None:
        actual = {case["fault"]: case for case in self.cases}
        for fault, expected in EXPECTED_CASES.items():
            with self.subTest(fault=fault):
                for field, value in expected.items():
                    self.assertEqual(actual[fault][field], value)


if __name__ == "__main__":
    unittest.main()
