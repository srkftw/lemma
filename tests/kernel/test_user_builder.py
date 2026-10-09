"""Host-only ownership/selection failure tests for independent user builds."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from build_kernel import module_closure, validate_configuration_stage
from build_user import build
from core0_common import Core0Error


class UserBuilderFailures(unittest.TestCase):
    def test_peer_development_import_rejected_even_if_allow_development(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "Lemma/User/Development/Tasks/Compute.lean"
            selected.parent.mkdir(parents=True)
            selected.write_text("import Lemma.User.Development.Tasks.Busy\n")
            (selected.parent / "Busy.lean").write_text("-- another image\n")
            with self.assertRaisesRegex(Core0Error, "another development image"):
                module_closure(root, "Lemma.User.Development.Tasks.Compute", allow_development=True)

    def test_selected_image_can_share_production_user_library(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "Lemma/User/Development/Tasks/Compute.lean"
            selected.parent.mkdir(parents=True)
            selected.write_text("import Lemma.User.Console\n")
            library = root / "Lemma/User/Console.lean"
            library.write_text("-- maintained production library\n")
            closure = module_closure(root, "Lemma.User.Development.Tasks.Compute", allow_development=True)
            self.assertEqual(set(closure), {"Lemma/User/Development/Tasks/Compute.lean", "Lemma/User/Console.lean"})

    def test_tasks_configuration_cannot_build_in_machine_mode(self):
        with self.assertRaisesRegex(Core0Error, "require supervisor"):
            validate_configuration_stage("tasks-development", "bootstrap-m")

    def test_independent_unknown_or_path_key_fails_before_any_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for key in ("../compute", "unknown", "compute/"):
                with patch("build_user.require_tools") as tools:
                    with self.assertRaisesRegex(Core0Error, "unknown closed"):
                        build(root=root, output_dir=root / "build/user/probe", image_key=key, opt_level="O2")
                    tools.assert_not_called()

    def test_independent_output_cannot_replace_evidence_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch("build_user.require_tools") as tools:
                with self.assertRaisesRegex(Core0Error, "whole build/user"):
                    build(root=root, output_dir=root / "build/user", image_key="compute", opt_level="O2")
                tools.assert_not_called()


if __name__ == "__main__":
    unittest.main()
