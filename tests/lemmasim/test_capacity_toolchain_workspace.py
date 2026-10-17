"""Host pin/copy boundary, separate from real LLVM or guest execution."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from capacity_toolchain_workspace import command
from kernel_source_workspace import FILES


class CapacityToolchainWorkspace(unittest.TestCase):
    def fixture(self, root):
        pins = {}
        for name in FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(('original fixture ' + name + '\n').encode())
            pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        output = root / 'build/private-session'
        output.mkdir(parents=True)
        (output / 'private-machine-state').write_bytes(b'must not enter tool realization')
        guest = root / 'guest'
        guest.mkdir()
        raw = json.dumps({'source_inputs': pins}).encode()
        (guest / 'provenance.json').write_bytes(raw)
        return output, {'provenance_sha256': hashlib.sha256(raw).hexdigest()}

    def test_only_three_original_pins_enter_explicit_path_flake(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out, build = self.fixture(root)
            argv = command(root, out, build, root / 'guest', out / 'capacity.json')
            flake = out / 'guest-capacity-toolchain'
            self.assertEqual({p.relative_to(flake).as_posix() for p in flake.rglob('*') if p.is_file()}, set(FILES))
            self.assertEqual(argv[:3], ['nix', 'develop', 'path:' + str(flake)])
            self.assertEqual(argv[6], str(root / 'scripts/audit_lemmasim_capacity.py'))
            receipt = json.loads((out / 'guest-capacity-toolchain.json').read_text())
            self.assertEqual(receipt['input_sha256'], json.loads((root / 'guest/provenance.json').read_text())['source_inputs'])
            self.assertEqual(receipt['input_bytes'], sum((root / n).stat().st_size for n in FILES))

    def test_changed_or_missing_pin_rejects_before_output_creation(self):
        for missing in (False, True):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                out, build = self.fixture(root)
                if missing:
                    path = root / 'guest/provenance.json'
                    value = json.loads(path.read_text())
                    del value['source_inputs']['flake.lock']
                    raw = json.dumps(value).encode()
                    path.write_bytes(raw)
                    build['provenance_sha256'] = hashlib.sha256(raw).hexdigest()
                else:
                    (root / 'flake.lock').write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    command(root, out, build, root / 'guest', out / 'capacity.json')
                self.assertFalse((out / 'guest-capacity-toolchain').exists())

    def test_changed_provenance_rejects_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            out, build = self.fixture(root)
            (root / 'guest/provenance.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):
                command(root, out, build, root / 'guest', out / 'capacity.json')
            self.assertFalse((out / 'guest-capacity-toolchain').exists())

    def test_symlinked_pin_or_output_rejects(self):
        for output_link in (False, True):
            with self.subTest(output_link=output_link), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                out, build = self.fixture(root)
                if output_link:
                    alias = root / 'alias'
                    alias.symlink_to(out, target_is_directory=True)
                    out = alias
                else:
                    original = root / 'flake.lock'
                    original.rename(root / 'actual-lock')
                    original.symlink_to(root / 'actual-lock')
                with self.assertRaises(ValueError):
                    command(root, out, build, root / 'guest', out / 'capacity.json')


if __name__ == '__main__':
    unittest.main()
