"""Host-only exact raw UART launch fixtures; no guest installation or CPU."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import lemmasim_course as transport
from course_deployment import CONFIGURATIONS as LEGACY
from course_await_deployment import CONFIGURATIONS as AWAIT
from package_notebook_target import CONFIGURATIONS as PACKAGE


class RawRegistry(unittest.TestCase):
    def test_exact_old_and_new_configuration_registry(self):
        expected = set(LEGACY) | set(AWAIT) | set(PACKAGE)
        self.assertEqual(set(transport.CONFIGURATIONS), expected)
        self.assertEqual(len(transport.CONFIGURATIONS), len(expected))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            image = directory / 'image.elf'
            image.write_bytes(b'host-admission-fixture-no-cpu')
            good = {'schema': 'lemmasim-live/1', 'mode': 'developer', 'backend': 'rtl',
                    'identity': {'profile': 'lemma-silicon-dev/0.3.0',
                                 'guest': hashlib.sha256(image.read_bytes()).hexdigest()},
                    'argv': ['fixture', '--image', str(image)]}
            (directory / 'session.json').write_text(json.dumps(good))
            args = SimpleNamespace(command='course-load', session_dir=directory,
                                   identity=1, edition=1, crc=0, node=2,
                                   transaction=0, cycle=None)
            with patch.object(transport, 'request', return_value={'fixture': 'raw-admission'}) as request:
                for configuration in sorted(expected):
                    (directory / 'build.json').write_text(json.dumps({'configuration': configuration}))
                    self.assertEqual(transport.send(args)['status'], 'RAW_COMMAND_ADMITTED')
                    sent = request.call_args.args[1]
                    self.assertEqual((sent['action'], sent['kind']), ('inject', 'uart'))
                    self.assertEqual(bytes.fromhex(sent['hex']), transport.frame(2, 1, 1, 0, 2, 0))
                lookalikes = {name + suffix for name in PACKAGE for suffix in ('-extra', '-teacher', '-cold')}
                lookalikes |= {'lemmasim-silicon-closure-entry2-bulk-notebook',
                               'lemmasim-silicon-package-closure-entry2-notebook'}
                for configuration in sorted(lookalikes):
                    (directory / 'build.json').write_text(json.dumps({'configuration': configuration}))
                    before = request.call_count
                    with self.assertRaises(ValueError):
                        transport.send(args)
                    self.assertEqual(request.call_count, before)
                (directory / 'build.json').write_text(json.dumps({'configuration': sorted(PACKAGE)[0]}))
                for field, value in [('mode', 'student'), ('backend', 'fast'), ('schema', 'lemmasim-live/0')]:
                    (directory / 'session.json').write_text(json.dumps({**good, field: value}))
                    before = request.call_count
                    with self.assertRaises(ValueError):
                        transport.send(args)
                    self.assertEqual(request.call_count, before)
                for field, value in [('profile', 'lemma-silicon-dev/0.2.0'), ('guest', '0' * 64)]:
                    wrong = {**good, 'identity': {**good['identity'], field: value}}
                    (directory / 'session.json').write_text(json.dumps(wrong))
                    before = request.call_count
                    with self.assertRaises(ValueError):
                        transport.send(args)
                    self.assertEqual(request.call_count, before)


if __name__ == '__main__':
    unittest.main()
