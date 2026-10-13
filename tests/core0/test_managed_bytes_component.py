"""Fail-closed artifact observer boundaries; positive execution is not mocked."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from core0_common import Core0Error
import check_managed_bytes_component as component

class ManagedBytesComponentBoundary(unittest.TestCase):
    def test_empty_source_inventory_rejects(self):
        with self.assertRaises(Core0Error):
            component.names('')

    def test_missing_genuine_catalog_rejects(self):
        with self.assertRaises(Core0Error):
            component.validate_catalog({})

    def test_non_object_rejects(self):
        with self.assertRaises(Core0Error):
            component.validate_object(b'\0' * 64, {})

    def test_empty_llvm_definitions_rejects(self):
        with self.assertRaises(Core0Error):
            component.definitions('declare i64 @foreign_runtime()\n')

if __name__ == '__main__':
    unittest.main()
