"""Host-only ownership/selection failure tests for independent user builds."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from build_kernel import (INDEPENDENT_IMAGE_KEYS, configuration_development_modules, configuration_modules, configuration_roots,
                          module_closure, user_startup_case, validate_configuration_stage)
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
        for configuration in ("tasks-development", "tasks-fault-development"):
            with self.assertRaisesRegex(Core0Error, "require supervisor"):
                validate_configuration_stage(configuration, "bootstrap-m")

    def test_fault_configuration_has_only_its_exact_kernel_roots(self):
        roots = configuration_roots("tasks-fault-development")
        self.assertEqual(roots["kernel"], (("Lemma.Kernel.Development.FaultEntry.boot", ()),
                         ("Lemma.Kernel.Development.FaultEntry.dispatch", ("u64", "u64", "u64"))))
        self.assertEqual(configuration_modules("tasks-fault-development")["kernel"],
                         "Lemma.Kernel.Development.FaultEntry")
        self.assertNotIn("user", roots)
        self.assertEqual(user_startup_case("tasks-fault-development"), "none")
        self.assertEqual(INDEPENDENT_IMAGE_KEYS["tasks-development"], {"compute", "sleeper", "busy"})
        self.assertEqual(INDEPENDENT_IMAGE_KEYS["tasks-fault-development"], {"compute", "sleeper", "busy", "fault"})

    def test_fault_key_cannot_acquire_authority_in_ordinary_or_unknown_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for configuration in ("tasks-development", "normal", "unknown"):
                with patch("build_user.require_tools") as tools:
                    with self.assertRaisesRegex(Core0Error, "unknown closed"):
                        build(root=root, output_dir=root / "build/user/probe", image_key="fault",
                              configuration=configuration, opt_level="O2")
                    tools.assert_not_called()

    def test_fault_kernel_exact_helpers_do_not_widen_f_or_user_scopes(self):
        selected = "Lemma.Kernel.Development.FaultEntry"
        helpers = ("Lemma.Kernel.Development.TasksEntry", "Lemma.Kernel.Development.Pressure")
        self.assertEqual(configuration_development_modules("tasks-fault-development", "kernel"),
                         (selected, *helpers))
        self.assertEqual(configuration_development_modules("tasks-development", "kernel"), (helpers[0],))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for module in (selected, *helpers):
                path = root / (module.replace(".", "/") + ".lean")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("-- closed development helper\n")
            entry = root / (selected.replace(".", "/") + ".lean")
            entry.write_text("\n".join("import " + module for module in helpers))
            closure = module_closure(root, selected, allow_development=True,
                                     development_modules=configuration_development_modules("tasks-fault-development", "kernel"))
            self.assertEqual(len(closure), 3)
            with self.assertRaisesRegex(Core0Error, "another development"):
                module_closure(root, selected, allow_development=True)
            outsider = root / "Lemma/Kernel/Development/Other.lean"
            outsider.write_text("-- unrelated quarantined module\n")
            entry.write_text("import Lemma.Kernel.Development.Other\n")
            with self.assertRaisesRegex(Core0Error, "another development"):
                module_closure(root, selected, allow_development=True,
                               development_modules=configuration_development_modules("tasks-fault-development", "kernel"))

    def test_managed_configuration_rejects_machine_stage_and_privileged_user_import(self):
        with self.assertRaisesRegex(Core0Error, "require supervisor"):
            validate_configuration_stage("capabilities-development", "bootstrap-m")
        for module in ["Lemma.Kernel.Capability", "Lemma.Compiler.Frontend"]:
            with tempfile.TemporaryDirectory() as directory:
                root=Path(directory);selected=root/"Lemma/User/Development/Capabilities.lean"
                selected.parent.mkdir(parents=True);selected.write_text("import "+module+"\n")
                imported=root/(module.replace(".","/")+".lean");imported.parent.mkdir(parents=True,exist_ok=True);imported.write_text("-- forbidden target dependency\n")
                with self.assertRaisesRegex(Core0Error,"privileged/compiler"):
                    module_closure(root,"Lemma.User.Development.Capabilities",allow_development=True,forbid_user_privileged_imports=True)
        self.assertEqual(INDEPENDENT_IMAGE_KEYS["capabilities-development"],{"capabilities","peer","busy","tamper"})

    def test_managed_kernel_helpers_are_exact_without_widening_prior_scopes(self):
        self.assertEqual(configuration_development_modules("capabilities-development","kernel"),
                         ("Lemma.Kernel.Development.CapsEntry","Lemma.Kernel.Development.CapAlias",
                          "Lemma.Kernel.Development.TasksEntry","Lemma.Kernel.Development.CapabilityGeneration"))
        self.assertNotIn("Lemma.Kernel.Development.CapAlias",configuration_development_modules("tasks-fault-development","kernel"))
        self.assertNotIn("Lemma.Kernel.Development.CapabilityGeneration",configuration_development_modules("tasks-development","kernel"))

    def test_ipc_selection_and_shared_client_module_are_closed(self):
        self.assertEqual(INDEPENDENT_IMAGE_KEYS['ipc-development'],{'server','clienta','clientb','busy','fault'})
        self.assertEqual(configuration_modules('ipc-development')['kernel'],'Lemma.Kernel.Development.IPCEntry')
        self.assertEqual(configuration_development_modules('ipc-development','kernel'),('Lemma.Kernel.Development.IPCEntry','Lemma.Kernel.Development.TasksEntry'))
        with self.assertRaisesRegex(Core0Error,'require supervisor'):validate_configuration_stage('ipc-development','bootstrap-m')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);selected=root/'Lemma/User/Development/IPCClients.lean';selected.parent.mkdir(parents=True)
            selected.write_text('import Lemma.User.IPC\n');library=root/'Lemma/User/IPC.lean';library.write_text('-- production library\n')
            closure=module_closure(root,'Lemma.User.Development.IPCClients',allow_development=True,forbid_user_privileged_imports=True)
            self.assertEqual(set(closure),{'Lemma/User/Development/IPCClients.lean','Lemma/User/IPC.lean'})
            other=selected.parent/'IPCServer.lean';other.write_text('-- peer image\n');selected.write_text('import Lemma.User.Development.IPCServer\n')
            with self.assertRaisesRegex(Core0Error,'another development'):module_closure(root,'Lemma.User.Development.IPCClients',allow_development=True,forbid_user_privileged_imports=True)

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
