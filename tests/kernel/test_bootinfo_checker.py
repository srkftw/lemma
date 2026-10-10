"""Host cleanup compatibility fixtures; these are not guest execution evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import create_autospec, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from check_kernel_bootinfo import observe
from core0_common import Core0Error
from run_kernel import Session


class BootInfoCleanupTests(unittest.TestCase):
    def observe_fixture(self, result):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            case = directory / "ordinary"
            case.mkdir()
            (case / "result.json").write_text(json.dumps(result))
            session = create_autospec(Session, instance=True)
            session.__enter__.return_value = session
            session.__exit__.return_value = False
            session.record.return_value = (0xa, 0x87e00000, 0, 512, 0x82000000)
            report = {"cases": []}
            with patch("check_kernel_bootinfo.Session", return_value=session):
                observe(root=ROOT, image=directory / "image.elf", output_dir=directory,
                        kind="ordinary", fixture=None, timeout=30, report=report)
            session.finish.assert_called_once()
            return report

    def result(self):
        return {"status": "PASS", "guest_live_before_cleanup": True, "returncode": -9,
                "cleanup": {"explicit_host_stop": True, "process_group_killed": True,
                            "target_exited_before_cleanup": False, "process_reaped": True}}

    def test_current_four_field_live_cleanup_is_accepted(self):
        self.assertEqual(self.observe_fixture(self.result())["cases"][0]["status"], "PASS")

    def test_missing_early_exit_and_incomplete_cleanup_evidence_is_rejected(self):
        for field in self.result()["cleanup"]:
            with self.subTest(field=field, change="missing"):
                result = self.result()
                del result["cleanup"][field]
                with self.assertRaises(Core0Error):
                    self.observe_fixture(result)
            for value in (not self.result()["cleanup"][field], int(self.result()["cleanup"][field])):
                with self.subTest(field=field, change=value):
                    result = self.result()
                    result["cleanup"][field] = value
                    with self.assertRaises(Core0Error):
                        self.observe_fixture(result)
        for field, value in (("guest_live_before_cleanup", False), ("returncode", 0), ("status", "FAIL")):
            with self.subTest(field=field):
                result = self.result()
                result[field] = value
                with self.assertRaises(Core0Error):
                    self.observe_fixture(result)


if __name__ == "__main__":
    unittest.main(verbosity=2)
