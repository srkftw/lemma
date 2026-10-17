"""Host selector checks only; these fixtures are not compiled target programs.

Actual169/171-function artifacts and valid LLVM mutants are qualified separately.
"""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import package_companion_target as target
from core0_common import Core0Error


class CourseIngressAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "authority.json"
        self.patch = mock.patch.object(target, "AUTHORITY", self.path)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.old = dict(role="user", image_key="course",
                        configuration=target.CONFIGURATIONS[0],
                        software_deployment=target.SOFTWARE_DEPLOYMENT,
                        used_loops=[dict(stable_id="action.loop",
                                        callback="Lemma.Courses.PackageInstaller.step")])
        self.new = {**self.old, "used_loops": [dict(stable_id="action.loop",
                    callback="Lemma.Courses.PackageInstaller.stepIdle")]}
        self.original = self.role(self.old, 169)
        self.authority = dict(schema=target.VERSION,
            roles={key: copy.deepcopy(self.original) for key in
                   ("firmware", "firmware-init", "kernel", "kernel-init", *target.USER_ROOTS)})
        self.authority["course_ingress_idle2"] = dict(
            schema=target.INGRESS_IDLE_VERSION, policy="lemma-course-ingress-idle/2",
            previous_role_sha256=target.digest(self.original), role=self.role(self.new, 171))
        self.write()

    def role(self, unit, count):
        return dict(catalog_sha256=target.digest(unit),
                    catalog_sha256_by_configuration={configuration:
                        target.digest({**unit, "configuration": configuration})
                        for configuration in target.CONFIGURATIONS},
                    function_count=count, pre_function_count=count, post_function_count=count,
                    pre_sha256="fixture-pre", post_sha256="fixture-post")

    def write(self):
        self.path.write_text(json.dumps(self.authority))

    def test_historical_catalogs_keep_the_original_authority(self):
        self.authority["course_ingress_idle2"]["schema"] = "corrupt-unused-successor"
        self.write()
        for configuration in target.CONFIGURATIONS:
            key, wanted = target.contract({**self.old, "configuration": configuration})
            self.assertEqual((key, wanted), ("course", self.original))

    def test_both_exact_successor_catalogs_select_the_new_version(self):
        for configuration in target.CONFIGURATIONS:
            key, wanted = target.contract({**self.new, "configuration": configuration})
            self.assertEqual(key, "course")
            self.assertEqual(wanted["artifact_contract_version"], target.INGRESS_IDLE_VERSION)
            self.assertEqual(wanted["function_count"], 171)

    def test_changed_catalog_effects_reject(self):
        with self.assertRaisesRegex(Core0Error, "complete typed/effect/root"):
            target.contract({**self.new, "extra_effect": "physical-write"})

    def test_unknown_version_and_changed_predecessor_reject(self):
        original = copy.deepcopy(self.authority)
        for field, value in (("schema", "unknown"), ("previous_role_sha256", "changed")):
            with self.subTest(field=field):
                self.authority = copy.deepcopy(original)
                self.authority["course_ingress_idle2"][field] = value
                self.write()
                with self.assertRaisesRegex(Core0Error, "version/previous authority"):
                    target.contract(self.new)

    def test_loop_and_function_count_guards_are_independent_of_catalog_pin(self):
        original = copy.deepcopy(self.authority)
        for unit, count in (({**self.new, "used_loops": self.old["used_loops"],
                              "fixture_nonce": "changed-successor"}, 171),
                            (self.new, 170)):
            self.authority = copy.deepcopy(original)
            # Deliberately matching fixture digest: the explicit shape guard
            # must reject even when the test authority pins the wrong shape.
            self.authority["course_ingress_idle2"]["role"] = self.role(unit, count)
            self.write()
            with self.assertRaisesRegex(Core0Error, "complete typed/effect/root"):
                target.contract(unit)

    def test_both_configuration_pins_are_required(self):
        del self.authority["course_ingress_idle2"]["role"][
            "catalog_sha256_by_configuration"][target.CONFIGURATIONS[1]]
        self.write()
        with self.assertRaisesRegex(Core0Error, "complete typed/effect/root"):
            target.contract(self.new)


if __name__ == "__main__":
    unittest.main()
