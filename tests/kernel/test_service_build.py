"""Closed service deployment and independent linkage boundary fixtures."""
import copy
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_kernel import (BUFFER_POLICY, image_specs, managed_fields,
                          validate_unit, validate_user_image_catalog)
from build_kernel import (CONTRACTS, artifact_category, configuration_development_modules,
                          configuration_roots, module_closure, user_artifact_category,
                          user_module_closure, validate_configuration_stage, validate_service_user_quota)
from core0_common import Core0Error


def catalog(configuration):
    images = list(image_specs(configuration))
    return {"schema_version": 1, "contract_version": "lemma-user-image-catalog-v1",
            "configuration": configuration, "stage": "supervisor", "image_count": len(images),
            "images": copy.deepcopy(images), **managed_fields(configuration)}


def unit(configuration, key="server"):
    image = next(row for row in image_specs(configuration) if row["key"] == key)
    root = {"id": 1, "source": image["source"], "symbol": image["symbol_prefix"] + "root", "args": ["u64"]}
    return {"schema_version": 2, "artifact_category": ("production" if configuration == "service-normal" else "development") + "-user-unit",
            "configuration": configuration, "contract_version": CONTRACTS["user"], "role": "user",
            "image_key": key, "image_id": image["id"], "startup_case": "none", "roots": [root],
            "functions": [{**{field: value for field, value in root.items() if field != "id"}, "effects": []}],
            "used_execution_ops": [], "used_device_ops": [], "used_loops": [], **managed_fields(configuration, image)}


def source(root, module, imports=""):
    path = root / (module.replace(".", "/") + ".lean")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(imports + "\n")


class ServiceBuildBoundaries(unittest.TestCase):
    def test_normal_and_development_select_exact_production_roots(self):
        for configuration in ("service-normal", "service-development"):
            validate_user_image_catalog(catalog(configuration))
            self.assertEqual([row["key"] for row in image_specs(configuration)][:4], ["server", "cli", "peer", "busy"])
            validate_configuration_stage(configuration, "supervisor")
            with self.assertRaises(Core0Error):
                validate_configuration_stage(configuration, "bootstrap-m")
        self.assertEqual(configuration_roots("service-normal")["kernel"][0][0], "Lemma.Kernel.ServiceEntry.boot")
        self.assertEqual(configuration_development_modules("service-normal", "kernel"), ())
        self.assertEqual(configuration_development_modules("service-development", "kernel"), ("Lemma.Kernel.Development.ServiceEntry",))
        self.assertEqual(artifact_category("service-normal"), "production-kernel-boot-package")
        self.assertEqual(user_artifact_category("service-normal"), "production-user-image")
        self.assertEqual(user_artifact_category("service-development"), "development-user-image")

    def test_registry_rejects_role_substitution_fault_authority_and_reordering(self):
        for configuration in ("service-normal", "service-development"):
            for mutation in (lambda value: value["images"].reverse(),
                             lambda value: value["images"][0].update(boot_role="ipc-server"),
                             lambda value: value["images"][0].update(startup_case="supervisor-csr"),
                             lambda value: value.update(managed_policy="lemma-ipc-v1")):
                value = catalog(configuration); mutation(value)
                with self.assertRaises(Core0Error):
                    validate_user_image_catalog(value)
        value = catalog("service-normal"); value["images"].append(copy.deepcopy(image_specs("service-development")[-1])); value["image_count"] += 1
        with self.assertRaises(Core0Error):
            validate_user_image_catalog(value)

    def test_user_unit_rejects_sibling_sources_privilege_and_category_downgrade(self):
        for configuration in ("service-normal", "service-development"):
            validate_unit(unit(configuration), "user", configuration=configuration, image_key="server")
            for foreign in ("Lemma.Applications.BufferCLI.main", "Lemma.Kernel.Directory.discover", "Lemma.Compiler.Frontend.main"):
                value = unit(configuration)
                value["functions"].append({"source": foreign, "symbol": "lemma_user_server_foreign", "args": [], "effects": []})
                with self.assertRaises(Core0Error):
                    validate_unit(value, "user", configuration=configuration, image_key="server")
        value = unit("service-normal"); value["artifact_category"] = "development-user-unit"
        with self.assertRaises(Core0Error):
            validate_unit(value, "user", configuration="service-normal", image_key="server")

    def test_source_closure_allows_shared_protocol_but_rejects_executable_and_privileged_imports(self):
        image = image_specs("service-normal")[0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source(root, "Lemma.Services.Buffer.Protocol")
            source(root, image["module"], "import Lemma.Services.Buffer.Protocol")
            self.assertEqual(len(user_module_closure(root, image, "service-normal")), 2)
            for foreign in ("Lemma.Applications.BufferPeer", "Lemma.Kernel.Directory", "Lemma.Compiler.Frontend", "Lemma.User.Development.BufferFault"):
                source(root, foreign)
                source(root, image["module"], "import " + foreign)
                with self.assertRaises(Core0Error):
                    user_module_closure(root, image, "service-normal")
            source(root, "Lemma.Kernel.ServiceEntry", "import Lemma.Services.Buffer.Server")
            with self.assertRaises(Core0Error):
                module_closure(root, "Lemma.Kernel.ServiceEntry", selected_executable_module="")

    def test_development_fault_closure_does_not_admit_other_development_or_application_images(self):
        image = image_specs("service-development")[-1]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source(root, image["module"])
            self.assertEqual(len(user_module_closure(root, image, "service-development")), 1)
            for foreign in ("Lemma.User.Development.IPCFault", "Lemma.Applications.BufferCLI"):
                source(root, foreign); source(root, image["module"], "import " + foreign)
                with self.assertRaises(Core0Error):
                    user_module_closure(root, image, "service-development")

    def test_server_reserves_four_pages_with_owned_base18_and_separate_global_descriptor(self):
        layout = {"configuration": "service-normal", "frame_bytes": 4096}
        image = image_specs("service-normal")[0]
        budget = validate_service_user_quota(layout, image, 10 * 4096)
        self.assertEqual(budget, {"base_owned_task_frames": 18, "base_global_task_frames": 19,
                                 "text_pages": 10, "reserved_arena_pages": 4, "owner_quota": 32})
        with self.assertRaises(Core0Error):
            validate_service_user_quota(layout, image, 10 * 4096 + 1)
        with self.assertRaises(Core0Error):
            validate_service_user_quota(layout, image, 0)
        self.assertIsNone(validate_service_user_quota({"configuration": "ipc-development"}, {"key": "server"}, 13 * 4096))


if __name__ == "__main__":
    unittest.main()
