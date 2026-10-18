"""New native schema never grants arbitrary hardware/workload authority."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from multimodal_native_bundle import prepared_archive,PROFILE,SCHEMA

class ArchiveAdmission(unittest.TestCase):
    def test_other_profiles_and_backends_reject_before_inventory(self):
        with tempfile.TemporaryDirectory() as name:
            root=Path(name);(root/'bundle.json').write_text(json.dumps(dict(schema=SCHEMA,profile=PROFILE)))
            for backend,workload,profile in [('rtl','notebook',PROFILE),('qemu','devices',PROFILE),('qemu','notebook','lemma-silicon-dev/0.15.0')]:
                with self.subTest(backend=backend,workload=workload,profile=profile):
                    with self.assertRaisesRegex(ValueError,'exact0.14'):prepared_archive(root,backend,workload,profile)
            with self.assertRaisesRegex(ValueError,'deployment pair'):prepared_archive(root,'qemu','notebook',PROFILE)
