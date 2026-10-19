"""New native schema never grants arbitrary hardware/workload authority."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from multimodal_native_bundle import prepared_archive,pack,PROFILE,SCHEMA,SCHOOL,CONFIGURATIONS

class ArchiveAdmission(unittest.TestCase):
    def test_other_profiles_and_backends_reject_before_inventory(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'bundle.json').write_text(json.dumps(dict(schema=SCHEMA,profile=PROFILE)))
            for backend,workload,profile in [('rtl','notebook',PROFILE),('qemu','devices',PROFILE),('qemu','notebook','lemma-silicon-dev/0.15.0')]:
                with self.subTest(backend=backend,workload=workload,profile=profile):
                    with self.assertRaisesRegex(ValueError,'exact0.14'):prepared_archive(root,backend,workload,profile)
            with self.assertRaisesRegex(ValueError,'deployment pair'):prepared_archive(root,'qemu','notebook',PROFILE)

    def test_school_requires_explicit_pair_and_original_source(self):
        for present in ({},{'notebook_build':Path('/missing')},
                        {'notebook_build':Path('/missing'),'initializer_build':Path('/missing')}):
            with self.subTest(present=present):
                args=SimpleNamespace(profile=PROFILE,school_deployment=True,**present)
                with self.assertRaisesRegex(ValueError,'explicit audited'):
                    pack(args)

    def test_school_pair_cannot_mix_legacy_or_parameterized_root(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            for role in SCHOOL:
                configs={**SCHOOL,role:CONFIGURATIONS[role]}
                (root/'bundle.json').write_text(json.dumps(dict(schema=SCHEMA,profile=PROFILE,configurations=configs)))
                with self.subTest(role=role):
                    with self.assertRaisesRegex(ValueError,'deployment pair'):
                        prepared_archive(root,'qemu','notebook',PROFILE)

    def test_school_contract_is_required_after_real_inventory_boundary(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name)
            (root/'bundle.json').write_text(json.dumps(dict(schema=SCHEMA,profile=PROFILE,configurations=SCHOOL)))
            with patch('silicon_guest_bundle.inventory') as inventory:
                with self.assertRaisesRegex(ValueError,'software/service contract'):
                    prepared_archive(root,'qemu','notebook',PROFILE)
                inventory.assert_called_once()
