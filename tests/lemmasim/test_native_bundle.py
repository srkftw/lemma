"""Fail-closed package boundary fixtures; no guest-execution claim."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from silicon_guest_bundle import inventory, read_json, development_configuration, ARITHMETIC_LAB_CONFIGURATIONS

class NativeBundleBoundary(unittest.TestCase):
    def test_development_configuration_requires_exact_laboratory_admission(self):
        profile='lemma-silicon-dev/0.3.0'
        for configuration in ARITHMETIC_LAB_CONFIGURATIONS:
            self.assertEqual(development_configuration(profile,'notebook',configuration,'laboratory'),configuration)
            for mode in (None,'student','developer'):
                with self.assertRaises(ValueError):development_configuration(profile,'notebook',configuration,mode)
            with self.assertRaises(ValueError):development_configuration(profile,'initializer',configuration,'laboratory')
            with self.assertRaises(ValueError):development_configuration('lemma-silicon-dev/0.2.0','notebook',configuration,'laboratory')
        with self.assertRaises(ValueError):development_configuration(profile,'notebook','lemmasim-silicon-power-arithmetic-invented-development','laboratory')
        self.assertEqual(development_configuration(profile,'notebook','lemmasim-silicon-power-notebook','student'),'lemmasim-silicon-power-notebook')
    def test_inventory_rejects_missing_changed_unlisted_and_symlinked_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'opaque.bin';p.write_bytes(b'actual bytes')
            (root/'bundle.json').write_text('{}')
            m={'files':{'opaque.bin':{'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':12,'executable':False}}}
            inventory(root,m)
            p.write_bytes(b'changedbytes')
            with self.assertRaises(ValueError):inventory(root,m)
            p.unlink();p.symlink_to('/dev/null')
            with self.assertRaises(ValueError):inventory(root,m)
            p.unlink();p.write_bytes(b'actual bytes');(root/'surprise.bin').write_bytes(b'x')
            with self.assertRaises(ValueError):inventory(root,m)
            (root/'surprise.bin').unlink();p.unlink()
            with self.assertRaises(ValueError):inventory(root,m)
    def test_metadata_rejects_duplicate_keys_empty_and_escaping_inventory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'bundle.json';p.write_text('{"schema":1,"schema":2}')
            with self.assertRaises(ValueError):read_json(p)
            for m in ({'files':{}},{'files':{'../other':{}}},{'files':{'/absolute':{}}}):
                with self.assertRaises(ValueError):inventory(root,m)

if __name__=='__main__':unittest.main()
