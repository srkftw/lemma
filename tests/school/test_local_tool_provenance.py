"""Protected school consumes actual maintained workspace/tool Actions.

This bounded RAM fixture is hosted validation, separate from target IPC/CPU
execution and actual panel visibility. No Python implementation supplies math.
"""
import copy
import json
import struct
import subprocess
import unittest

import test_authority as harness
import test_admission as admission
import test_delivery as delivery
import test_guest_submission as submission


class LocalToolProvenance(admission.Admission):
    start = delivery.Delivery.start
    stop = delivery.Delivery.stop
    client = delivery.Delivery.client
    test_two_principals_replay_revocation_and_path_separation = None
    test_same_credential_can_teach_only_with_scope_and_revoke_takes_effect = None
    test_lost_help_acknowledgement_reuses_exact_context_until_cancelled = None
    test_pair_uses_private_os_random_handoff_and_no_raw_token_in_stdout = None

    def setUp(self):
        super().setUp()
        # The package remains a synthetic test definition with its declared
        # fixture source anchors. This does not author a source-grounded unit.
        self.unit = copy.deepcopy(self.unit)
        self.unit['course']['nodes'][3]['kind'] = {'exercise': {'goal': 'fractionAddition'}}
        self.unit['activities'][3]['goal'] = 'fractionAddition'
        self.unit['activities'][3]['assessment']['checker'] = 'lemma-exact/1:fractionAddition'
        self.enroll('alice')
        self.token = self.issue('alice')
        self.teacher = self.issue('teacher')
        self.call('grant', subject='teacher', action='review', resource='alice')
        self.addCleanup(self.stop)
        self.start()

    def fixture(self, terminal=None):
        ask = harness.Authority.ask(self)
        ask.update(revision=2 if terminal == 2 else 1, object=0x504b000000000001)
        joined = self.client(self.token, 'join', course=1, revision=1, session='local-tool',
                             guestSession=41, lifetimeMs=10000, ask=ask)
        invitation = bytes.fromhex(joined['package_hex'])
        span = submission.word(invitation, 112)
        context = bytes.fromhex(invitation[span & 0xffffffff:(span & 0xffffffff)+(span >> 32)].decode())
        package = bytes.fromhex(self.client(self.token, 'client-course', course=1, revision=1)['package_hex'])
        crc = submission.word(package, 80)
        def event(scope, outcome):
            descriptor = 8 | (1 << 8) | (scope << 16) | (8 << 24) | (outcome << 32)
            return struct.pack('<16Q', 1, descriptor, 2 if scope == 2 else 0, 17,
                               0x0001000052444331, 1, 1, 4, crc, 0x504b000000000001,
                               10, 12, 5 if scope == 2 else 0, 6 if scope == 2 else 0, 0, 0)
        events = event(1, 0)
        if terminal:
            events += event(terminal, 1 if terminal == 2 else 3)
        paths = [self.base / name for name in ('package.bin', 'context.bin', 'tool-events.bin', 'tool-work.bin')]
        for path, data in zip(paths, (package, context, events)):
            path.write_bytes(data)
        run = subprocess.run(['lake', 'env', 'lean', '--run', 'tests/school/SubmissionFixture.lean',
                              str(paths[0]), str(paths[1]), str(paths[3]), '1', '4', str(paths[2]), 'local-tool'],
                             cwd=harness.REPO, capture_output=True, timeout=40)
        self.assertEqual(run.returncode, 0, (run.stdout + run.stderr).decode())
        decoded = json.loads(run.stdout)
        self.assertEqual(decoded['eventFormat'], 3)
        return decoded, paths[3].read_bytes()

    def review(self, terminal=None):
        decoded, artifact = self.fixture(terminal)
        receipt = self.client(self.token, 'guest-submit', hex=artifact.hex())
        review = self.client(self.teacher, 'review-work', attempt=receipt['attempt'])
        self.assertEqual(review['attempt']['data']['guestEnvelope'], decoded)
        self.assertEqual(self.client(self.teacher, 'review-artifact', attempt=receipt['attempt'])['hex'], artifact.hex())
        self.assertEqual(review['assistance'], [])
        self.assertEqual(review['localToolObservations'], review['attempt']['data']['localToolObservations'])
        self.assertTrue(self.client(self.token, 'guest-submit', hex=artifact.hex())['reused'])
        return decoded, receipt, review

    def test_applied_calculation_is_advisory_and_original_checker_is_invalidated(self):
        decoded, receipt, review = self.review(2)
        self.assertEqual(decoded['values'][:2], [5, 6])
        self.assertEqual(decoded['documentRevision'], 2)
        self.assertEqual(decoded['guestOutcome'], 0)
        self.assertEqual(receipt['outcome'], 1)  # Separate hosted exact check.
        data = review['attempt']['data']
        self.assertTrue(data['assisted'])
        self.assertTrue(review['localToolCurrentWorkExposure'])
        self.assertFalse(review['localToolApplicationUncertain'])
        self.assertEqual(len(review['localToolObservations']), 2)
        self.assertTrue(review['localToolObservations'][1]['deliveredLocalCalculation'])
        self.assertIn('hosted exact', data['checkingScope'])

    def test_interrupted_prepared_is_uncertain_and_cancelled_did_not_deliver(self):
        _, _, review = self.review()
        self.assertTrue(review['localToolCurrentWorkExposure'])
        self.assertTrue(review['localToolApplicationUncertain'])

    def test_exact_no_apply_terminal_retains_observations_without_delivered_exposure(self):
        decoded, _, review = self.review(3)
        self.assertEqual(decoded['documentRevision'], 1)
        self.assertEqual(decoded['values'][:2], [10, 12])
        self.assertFalse(review['localToolCurrentWorkExposure'])
        self.assertFalse(review['localToolApplicationUncertain'])
        self.assertFalse(review['attempt']['data']['assisted'])
        self.assertEqual(len(review['localToolObservations']), 2)


if __name__ == '__main__':
    unittest.main()
