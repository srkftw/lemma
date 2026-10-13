# SPDX-License-Identifier: Apache-2.0
"""Independent container-boundary fixtures; actual runtime has its own checks."""
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import lemmasim_session as runtime


class BoundaryMachine:
    identity = {'backend': 'rtl', 'profile':'lemma-silicon-dev/0.3.0',
                'implementation': 'boundary failure fixture'}
    checkpoint_identity = 'a' * 64
    preflight_checkpoint = runtime.RTL.preflight_checkpoint

    def __init__(self):
        self.cycle = 10
        self.commands = []

    def call(self, command):
        self.commands.append(command)
        if command.startswith('snapshot '):
            wrapper = struct.pack('<2Q', 0, self.cycle)
            header = b'LMSSRTL1' + struct.pack('<Q', 1) + self.checkpoint_identity.encode()
            header += struct.pack('<4Q', len(wrapper), 1, 0, 0)
            Path(command[9:]).write_bytes(header + wrapper + b'x')
        return {'cycle': self.cycle, 'finished': False}

    def close(self):
        pass


class RTLBoundaryFailures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.live = self.root / 'live'
        self.live.mkdir()
        self.machine = BoundaryMachine()
        self.session = runtime.Session(self.machine, self.live,
                                       SimpleNamespace(mode='laboratory', paused=True, quantum=1000))
        self.addCleanup(self.session.close)
        self.snapshot = self.root / 'saved'
        self.session.snapshot(self.snapshot)

    def reject_without_applying(self):
        before = list(self.machine.commands)
        with self.assertRaises(ValueError):
            self.session.restore(self.snapshot)
        self.assertEqual(self.machine.commands, before)
        self.assertEqual(self.machine.cycle, 10)

    def mutate_container(self, offset, payload):
        path = self.snapshot / 'machine.chk'
        content = bytearray(path.read_bytes())
        content[offset:offset + len(payload)] = payload
        path.write_bytes(content)
        manifest_path = self.snapshot / 'snapshot.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['files'][0].update(bytes=len(content), sha256=runtime.digest(path))
        manifest_path.write_text(json.dumps(manifest))

    def test_sidecar_cycle_mismatch_rejects_before_restore(self):
        manifest_path = self.snapshot / 'snapshot.json'
        manifest = json.loads(manifest_path.read_text())
        manifest['virtual_cycle'] += 1
        manifest_path.write_text(json.dumps(manifest))
        self.reject_without_applying()

    def test_changed_saved_cycle_with_recomputed_file_hash_rejects(self):
        self.mutate_container(120, struct.pack('<Q', 11))
        self.reject_without_applying()

    def test_unsupported_container_identity_or_version_rejects(self):
        # Canonical0.3 supports the historical1 and current2 containers.
        # A genuinely unsupported version must still reject before adoption.
        for offset, payload in ((8, struct.pack('<Q', 99)), (16, b'b' * 64)):
            with self.subTest(offset=offset):
                original = (self.snapshot / 'machine.chk').read_bytes()
                self.mutate_container(offset, payload)
                self.reject_without_applying()
                (self.snapshot / 'machine.chk').write_bytes(original)

    def test_inconsistent_component_lengths_rejects(self):
        self.mutate_container(80, struct.pack('<Q', 17))
        self.reject_without_applying()

    def test_matching_boundary_allows_backend_validation(self):
        self.session.restore(self.snapshot)
        self.assertEqual(self.machine.commands[-1], 'restore ' + str(self.snapshot / 'machine.chk'))


if __name__ == '__main__':
    unittest.main()
