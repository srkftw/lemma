"""Independent host transport checks; not ROM/circuit/execution evidence."""
import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import development_install as install
import lemmasim_auth as auth


class Client:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.requests = []

    def send(self, operation, **kw):
        self.requests.append((operation, kw))
        outcome = next(self.outcomes)
        if isinstance(outcome, BaseException):
            raise outcome
        status, value = outcome
        return {'transaction': len(self.requests), 'status': status, 'value': value}


class DevelopmentInstallTests(unittest.TestCase):
    package = {'identity': 0x1234}
    wire = bytes((i * 13 + 5) % 256 for i in range(1024))
    tag = bytes((i * 7 + 11) % 256 for i in range(512))

    def run_client(self, outcomes):
        client = Client(outcomes)
        result = install.resume(client, self.package, self.wire, self.tag, 1)
        return result, client

    def test_existing_receipt_never_rewrites_confirmed_or_trial(self):
        for value, state in ((1, 'reconciled-confirmed'), (2, 'reconciled-trial')):
            result, client = self.run_client([(0, value)])
            self.assertEqual(result['state'], state)
            self.assertEqual(result['sectors_sent'], 0)
            self.assertEqual(client.requests, [(4, {'slot': 1, 'identity': 0x1234})])

    def test_no_receipt_requires_real_payload_tag_publish_and_fresh_status(self):
        for initial in (215, 217):
            result, client = self.run_client([(initial, 0), (0, 8), (0, 9),
                                               (0, 10), (0, 1), (0, 2)])
            self.assertEqual(result['state'], 'installed-trial')
            self.assertEqual(result['sectors_sent'], 2)
            self.assertEqual([op for op, _ in client.requests], [4, 1, 1, 5, 2, 4])
            self.assertEqual(client.requests[1][1]['payload'], self.wire[:512])
            self.assertEqual(client.requests[2][1]['payload'], self.wire[512:])
            self.assertEqual([client.requests[i][1]['relative'] for i in (1, 2)], [0, 1])
            self.assertEqual(client.requests[3][1]['payload'], self.tag)

    def test_errors_and_unknown_status_never_authorize_staging(self):
        # Include failed real barriers, malformed/corrupt images, conflicting
        # peers, stale receipts and authentication denial. Every UInt8 is
        # accounted for, rather than testing only one injected flush failure.
        for status in range(256):
            if status in (215, 217):
                continue
            client = Client([(status, 0)])
            with self.assertRaises(RuntimeError):
                install.resume(client, self.package, self.wire, self.tag, 1)
            self.assertEqual([op for op, _ in client.requests], [4])
        for value in (0, 3, 1 << 64, True):
            with self.assertRaises(RuntimeError):
                self.run_client([(0, value)])

    def test_lost_reply_and_failed_final_barrier_cannot_be_success(self):
        for tail in (TimeoutError('publication reply lost'), (212, 0)):
            client = Client([(217, 0), (0, 8), (0, 9), (0, 10), tail])
            with self.assertRaises((TimeoutError, RuntimeError)):
                install.resume(client, self.package, self.wire, self.tag, 1)
            self.assertEqual([op for op, _ in client.requests], [4, 1, 1, 5, 2])
        client = Client([(217, 0), (0, 8), (0, 9), (0, 10), (0, 1), (212, 0)])
        with self.assertRaises(RuntimeError):
            install.resume(client, self.package, self.wire, self.tag, 1)
        self.assertEqual([op for op, _ in client.requests], [4, 1, 1, 5, 2, 4])

    def test_bounded_opaque_package_admission(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / 'image.bin').write_bytes(self.wire)
            (root / 'tag').write_bytes(self.tag)
            manifest = dict(self.package, schema='lemma-product-image/1', status='PASS',
                            image_sha256=hashlib.sha256(self.wire).hexdigest())
            (root / 'package.json').write_text(json.dumps(manifest))
            sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
            self.assertEqual(install.load_package(root, root / 'tag', sha),
                             (manifest, self.wire, self.tag))
            (root / 'image.bin').write_bytes(self.wire[:-1])
            with self.assertRaises(ValueError):
                install.load_package(root, root / 'tag', sha)
            (root / 'image.bin').write_bytes(self.wire)
            (root / 'tag').write_bytes(self.tag + b'x')
            with self.assertRaises(ValueError):
                install.load_package(root, root / 'tag', sha)

    def test_version2_exact_payload_and_independent_wire_crc(self):
        wire = auth.frame(73, 5, 1, 0, 0x1234, self.tag)
        self.assertEqual(struct.unpack('<10Q', wire[:80]),
                         (0x31564f4345524d4c, 2, 73, 5, 1, 0, 0x1234, 0,
                          zlib.crc32(self.tag), zlib.crc32(wire[:72])))
        self.assertEqual(wire[80:], self.tag)
        for operation in (1, 5):
            for payload in (b'', bytes(511), bytes(513)):
                with self.assertRaises(ValueError):
                    auth.frame(73, operation, payload=payload)
        for operation in (0, 2, 3, 4, 6):
            with self.assertRaises(ValueError):
                auth.frame(73, operation, payload=self.tag)
        for transaction, operation in ((0, 4), (73, 7), (True, 4)):
            with self.assertRaises(ValueError):
                auth.frame(transaction, operation)


if __name__ == '__main__':
    unittest.main()
