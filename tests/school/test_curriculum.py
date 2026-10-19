"""Independent host orchestration of the maintained Lean curriculum implementation."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "Lemma/School/CurriculumMain.lean"


class CurriculumTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        build = subprocess.run(
            ["lake", "build", "Lemma.School.CurriculumMain"], cwd=ROOT,
            text=True, capture_output=True, timeout=120)
        if build.returncode:
            raise AssertionError(build.stdout + build.stderr)

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="lemma-curriculum-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def run_lean(self, *arguments, ok=True):
        result = subprocess.run(
            ["lake", "env", "lean", "--run", str(MAIN), *map(str, arguments)],
            cwd=ROOT, text=True, capture_output=True, timeout=90)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout + result.stderr

    def unit(self):
        return self.run_lean("fixture")

    def write_unit(self, unit, name="unit.json"):
        path = self.work / name
        path.write_text(json.dumps(unit), encoding="utf-8")
        return path

    def test_sha256_independent_vectors_padding_and_chunk_boundaries(self):
        for size in [0, 3, 55, 56, 63, 64, 65, 65537]:
            data = b"abc" if size == 3 else bytes(i % 251 for i in range(size))
            path = self.work / f"bytes-{size}"
            path.write_bytes(data)
            with self.subTest(size=size):
                self.assertEqual(self.run_lean("sha256", path), hashlib.sha256(data).hexdigest())

    def test_import_exact_originals_order_duplicates_revision_and_page(self):
        values = ["1. Preserve  TWO spaces", "2. escaped \"quote\" \\ line\nnext", "32. Unicode α — ∑", "1. Preserve  TWO spaces"]
        # A token crosses the 64KiB source-read boundary, without a large corpus.
        values += [f"7. padding {i:04d} " + "x" * 80 for i in range(750)]
        path = self.work / "catalogue.json"
        raw = (" \n" + json.dumps(values, ensure_ascii=False, indent=2) + "\n").encode()
        path.write_bytes(raw)
        receipt = self.run_lean("catalogue", "import", self.work, "owner", path)
        manifest = receipt["manifest"]
        revision = hashlib.sha256(raw).hexdigest()
        self.assertEqual(manifest["sourceDigest"], revision)
        self.assertEqual(manifest["records"], len(values))
        directory = Path(receipt["directory"])
        self.assertEqual((directory / "source.json").read_bytes(), raw)
        rows = [json.loads(row) for row in (directory / "records.jsonl").read_text().splitlines()]
        self.assertEqual([row["original"] for row in rows], values)
        self.assertEqual([row["position"] for row in rows], list(range(len(values))))
        self.assertEqual(rows[2]["numberLabel"], "32")
        self.assertEqual(rows[2]["originalUtf8Sha256"], hashlib.sha256(values[2].encode()).hexdigest())
        self.assertTrue(self.run_lean("catalogue", "import", self.work, "owner", path)["reused"])
        page = self.run_lean("catalogue", "search", self.work, "owner", revision, "PRESERVE", 1, 1)
        self.assertEqual(page["matchCount"], 2)
        self.assertEqual(page["records"][0]["record"]["position"], 3)
        row = self.run_lean("catalogue", "lookup", self.work, "owner", revision, 2)
        self.assertEqual(row["record"]["original"], values[2])
        self.assertEqual(row["recordId"], f"sha256:{revision}#2")
        path.write_text(json.dumps(["1. A changed revision"]), encoding="utf-8")
        changed = self.run_lean("catalogue", "import", self.work, "owner", path)
        self.assertNotEqual(changed["manifest"]["sourceDigest"], revision)
        self.assertEqual((directory / "source.json").read_bytes(), raw)
        self.assertEqual(len([p for p in (self.work / "catalogues/owner").iterdir() if not p.name.startswith(".")]), 2)

    def test_malformed_and_oversized_sources_never_publish(self):
        for raw in [b"[]", b'["a",]', b'["a"', b'["a", 2]', b'["a"]x', b'["\\q"]', b'["\xff"]', b'["' + b'x' * 65536 + b'"]']:
            with self.subTest(raw=raw[:30]):
                path = self.work / "bad.json"
                path.write_bytes(raw)
                self.run_lean("catalogue", "import", self.work, "bad", path, ok=False)
                self.assertFalse(any((self.work / "catalogues/bad").iterdir()))
        self.run_lean("catalogue", "import", self.work, "../escape", path, ok=False)

    def test_tamper_and_page_budget_reject(self):
        receipt = self.run_lean("catalogue", "import", self.work, "owner", ROOT / "fixtures/school/catalogue.json")
        digest = receipt["manifest"]["sourceDigest"]
        self.run_lean("catalogue", "search", self.work, "owner", digest, "", 0, 101, ok=False)
        self.run_lean("catalogue", "lookup", self.work, "owner", digest, 99, ok=False)
        (Path(receipt["directory"]) / "records.jsonl").write_text('{"forged": true}\n')
        error = self.run_lean("catalogue", "lookup", self.work, "owner", digest, 0, ok=False)
        self.assertIn("digest mismatch", error)

    def test_unit_roundtrip_exact_package_and_independent_context(self):
        unit = self.unit()
        path = self.write_unit(unit)
        preview = self.run_lean("preview", path)
        self.assertEqual(preview["definition"], unit)
        output = self.work / "unit.lcp"
        compiled = self.run_lean("compile", path, output)
        self.assertEqual(compiled["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertEqual(compiled["sha256"], preview["packageSha256"])
        self.assertEqual([int(value) for value in self.run_lean("fixture-checks")], [1, 2, 2])
        context = self.run_lean("tutor-context", path, "coefficients")
        self.assertIn("hint", context)
        self.assertNotIn("assessment", context)
        self.assertNotIn("referenceTheorem", context)
        self.run_lean("tutor-context", path, "reason", ok=False)
        self.run_lean("tutor-context", path, "later-review", ok=False)
        self.assertEqual(self.run_lean("resolve-sources", path), ["fixtures/school/Distributivity.txt"])

    def test_unit_file_admission_before_decode(self):
        path = self.work / "too-large.json"
        path.write_bytes(b" " * 1048577)
        self.assertIn("1MiB", self.run_lean("preview", path, ok=False))
        self.assertIn("regular file", self.run_lean("preview", self.work, ok=False))

    def test_authoring_invalid_references_cycles_and_independent_assistance(self):
        unit = self.unit()
        related = {"fromActivity": "reason", "toActivity": "prepare", "kind": "prerequisite", "origin": "test", "reviewed": True, "reviewHistory": [], "confidencePermille": None}
        # Derived JSON encoding of single-constructor sum tags is read from the real fixture.
        related["kind"] = unit["relations"][0]["kind"]
        unit["relations"].append(related)
        self.assertIn("cycle", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["relations"] = unit["relations"][1:]
        self.assertIn("reviewed authoring provenance", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["activities"] = unit["activities"][:-1]
        unit["relations"] = [r for r in unit["relations"] if r["toActivity"] != "later-review" and r["fromActivity"] != "later-review"]
        self.assertIn("every guest node", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["course"]["nodes"][3]["sourceAnchor"] = "unknown:anchor"
        self.assertIn("missing source anchor", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["activities"][5]["assistance"] = unit["activities"][0]["assistance"]
        self.assertIn("independent assessment", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["course"]["nodes"][0]["unimplementedEffect"] = "network"
        self.assertIn("unsupported authoring construct", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["anchors"][0]["edition"] = "different"
        self.assertIn("edition/file identity", self.run_lean("preview", self.write_unit(unit), ok=False))
        unit = self.unit()
        unit["sources"]["sources"][0]["ownerLocation"] = str(self.work / "missing.txt")
        self.assertIn("MissingSource", self.run_lean("resolve-sources", self.write_unit(unit), ok=False))


if __name__ == "__main__":
    unittest.main()
