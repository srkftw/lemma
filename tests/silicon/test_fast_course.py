"""Host transport admission guards; no guest execution or package authority."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'scripts'))
import lemmasim_course_fast as course


class FastCourseAdmission(unittest.TestCase):
    def test_mode_and_old_backend_reject_before_external_control(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for mode, adapter in [('student', 'lemmasim-fast-adapter/5'),
                                  ('developer', 'lemmasim-fast-adapter/4')]:
                (root/'session.json').write_text(json.dumps(dict(schema='lemmasim-live/1',
                    mode=mode, backend='qemu', identity=dict(profile='lemma-silicon-dev/0.3.0',
                    adapter=adapter))))
                with self.subTest(mode=mode, adapter=adapter), mock.patch.object(course, 'request') as request:
                    with self.assertRaises(ValueError):
                        course.send(SimpleNamespace(session_dir=root))
                    request.assert_not_called()

    def test_running_or_insufficient_capacity_admits_no_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root/'image.elf'
            image.write_bytes(b'literal host fixture; not a guest')
            (root/'build.json').write_text(json.dumps({'configuration':course.CANONICAL_CONFIGURATIONS[0]}))
            identity = dict(profile='lemma-silicon-dev/0.3.0', adapter='lemmasim-fast-adapter/5',
                            guest=hashlib.sha256(image.read_bytes()).hexdigest())
            (root/'session.json').write_text(json.dumps(dict(schema='lemmasim-live/1',
                mode='developer', backend='qemu', identity=identity, argv=['-kernel', str(image)])))
            package = root/'untrusted.bin'
            payload = bytearray(128)
            struct.pack_into('<2Q', payload, 24, 1, 1)
            package.write_bytes(payload)
            args = SimpleNamespace(session_dir=root, command='course-install', package=package,
                                   transaction=1, cycle=None)
            for running, pending, message in [(True, 0, 'Pause'), (False, 65535, 'capacity')]:
                reply = dict(identity=identity, running=running, machine=dict(cycle=0,
                    devices=dict(uart_ingress=dict(enabled=True, pending=pending))))
                with self.subTest(running=running, pending=pending), \
                        mock.patch.object(course, 'request', return_value=reply) as request:
                    with self.assertRaisesRegex(ValueError, message):
                        course.send(args)
                    request.assert_called_once_with(root, {'action':'inspect'}, timeout=120)
