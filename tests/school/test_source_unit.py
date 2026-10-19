"""Source-derived declaration validation requires metadata, not private PDF bytes."""
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SourceDerivedUnitTests(unittest.TestCase):
    def test_teacher_definitions_compile_with_source_context_and_distinct_publications(self):
        build = subprocess.run(["lake", "build", "Lemma.School.CurriculumMain"], cwd=ROOT, capture_output=True, text=True, timeout=120)
        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
        for filename, identity, edition in [("source-derived-unit.json", 802, 1), ("source-derived-client-unit.json", 1, 2)]:
            with self.subTest(filename=filename), tempfile.TemporaryDirectory(prefix="lemma-source-unit-") as directory:
                definition = ROOT / "examples/school" / filename
                unit = json.loads(definition.read_text())
                self.assertEqual(unit["activities"][3]["goal"], "binomialSquare")
                self.assertTrue(unit["activities"][5]["assessment"]["independent"])
                self.assertEqual(unit["activities"][5]["assistance"], "none")
                self.assertEqual(unit["sources"]["sources"][0]["fileDigest"], "0a58ddf126b86d9d93c63977722c299093ea7a64bfe39bb0f3a5ba123037d7cd")
                anchor = next(a for a in unit["anchors"] if a["id"] == "aops07:identity-p307")
                self.assertEqual((anchor["pdfPageIndex"], anchor["printedPageLabel"]), (323, "307"))
                self.assertEqual(anchor["verification"], "verified")
                output = Path(directory) / "unit.lcp"
                run = subprocess.run(["lake", "env", "lean", "--run", "Lemma/School/CurriculumMain.lean", "compile", str(definition), str(output)], cwd=ROOT, capture_output=True, text=True, timeout=60)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                receipt = json.loads(run.stdout)
                bytes_ = output.read_bytes()
                self.assertEqual(struct.unpack_from("<QQ", bytes_, 24), (identity, edition))
                self.assertEqual(receipt["sha256"], hashlib.sha256(bytes_).hexdigest())
                self.assertEqual(struct.unpack_from("<Q", bytes_, 40)[0], 8)
                self.assertNotIn(b"First Printing 2007.\n", bytes_)
