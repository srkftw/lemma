"""Actual protected consumer of maintained guest write-ahead workspace Actions.

The RAM fixture is hosted validation, not CPU or panel-presentation evidence.
"""
import copy
import json
import struct
import subprocess
import unittest

import test_authority as harness
import test_delivery as delivery
import test_guest_submission as submission


class RemoteProvenance(delivery.Delivery):
    test_original_context_partial_cancel_raw_records_and_lost_ack_restart = None
    test_replaced_join_and_unrelated_page_publication_generation_do_not_taint_work = None

    def join(self, token, ask, session):
        joined = self.client(token, 'join', course=1, revision=1, session=session,
                             guestSession=ask['session'], lifetimeMs=10000, ask=ask)
        invitation = bytes.fromhex(joined['package_hex'])
        span = submission.word(invitation, 112)
        return bytes.fromhex(invitation[span & 0xffffffff:(span & 0xffffffff)+(span >> 32)].decode())

    def fixture(self, token, context, events, *, edit=False, node=4):
        package = bytes.fromhex(self.client(token, 'client-course', course=1, revision=1)['package_hex'])
        paths = [self.base/name for name in ('package.bin', 'context.bin', 'remote.bin', 'work.bin')]
        for path, data in zip(paths, (package, context, events)):
            path.write_bytes(data)
        result = subprocess.run(['lake', 'env', 'lean', '--run', 'tests/school/SubmissionFixture.lean',
            str(paths[0]), str(paths[1]), str(paths[3]), '2', str(node), str(paths[2]),
            'edit' if edit else 'same'], cwd=harness.REPO, capture_output=True, timeout=40)
        self.assertEqual(result.returncode, 0, (result.stdout+result.stderr).decode())
        decoded = json.loads(result.stdout.decode().splitlines()[-1])
        self.assertEqual(decoded['eventFormat'], 2)
        self.assertEqual(decoded['documentRevision'], 2 if edit else 1)
        return paths[3].read_bytes()

    @staticmethod
    def event(context, ask, scope=1):
        tag = 7 | (2 << 8) | (scope << 16) | (4 << 24) | (ask['sequence'] << 32)
        return struct.pack('<QQQQ', ask['revision'], tag, ask['object'],
                           submission.word(context, 48)) + context[16:48]

    def test_old_help_survives_edited_work_new_binding_and_execution_generation(self):
        self.enroll('alice'); alice = self.issue('alice'); teacher = self.issue('teacher')
        self.call('grant', subject='teacher', action='review', resource='alice')
        self.addCleanup(self.stop); self.start()
        ask = harness.Authority.ask(self); ask.update(revision=1, object=0x504b000000000001)
        context = self.join(alice, ask, 'before-cold')
        help_result = self.client(alice, 'assist', session='before-cold', ask=ask)
        self.client(alice, 'delivery-observe', decision=help_result['decision'], sequence=1,
            observer='fixture-original-guest-raster', kind='guest-raster',
            observation=dict(record=[0x725,1,1,0,0], uartSHA256='a'*64))
        before = copy.deepcopy(json.loads((self.root/'state.json').read_text())['payload'])
        self.stop(); self.start()
        current = dict(ask, session=42, sequence=2, revision=2)
        new_context = self.join(alice, current, 'after-cold')
        self.assertNotEqual(submission.word(context,48), submission.word(new_context,48))
        events = self.event(context, ask) + self.event(context, ask, 2)
        artifact = self.fixture(alice, new_context, events, edit=True)
        receipt = self.client(alice, 'guest-submit', hex=artifact.hex())
        self.assertEqual(receipt['outcome'], 4)
        review = self.client(teacher, 'review-work', attempt=receipt['attempt'])
        data = review['attempt']['data']
        self.assertTrue(data['assisted']); self.assertTrue(data['remoteCurrentWorkExposure'])
        self.assertTrue(data['remotePresentationUncertain'])
        self.assertEqual([r['key'] for r in data['assistanceDecisions']], [help_result['decision']])
        self.assertEqual([r['key'] for r in review['assistance']], [help_result['decision']])
        self.assertEqual(len(data['deliveryObservations']), 1)
        self.assertEqual(len(data['remoteAssistance']), 2)
        self.assertTrue(all(r['contextMatched'] and r['appliesToCurrentWork'] for r in data['remoteAssistance']))
        self.assertIn('panel visibility unestablished', data['remoteAssistance'][1]['presentation'])
        self.assertEqual(review['assistanceScope'], 'exact immutable guest-work attribution')
        after = json.loads((self.root/'state.json').read_text())['payload']
        self.assertEqual(after['generation'], before['generation']+1)
        self.assertEqual(after['records'][:len(before['records'])], before['records'])
        self.assertTrue(self.client(alice, 'guest-submit', hex=artifact.hex())['reused'])
        print(json.dumps(dict(oldDecision=help_result['decision'], laterRevision=2,
            originalGeneration=before['generation'], newGeneration=after['generation'],
            exposureSurvivesReconnect=True, uncertainPanelPresentation=True, exactRetry=True)))

    def test_unresolved_identity_is_uncertain_and_does_not_link_other_principal_history(self):
        self.enroll('alice'); self.enroll('bob')
        alice = self.issue('alice'); bob = self.issue('bob')
        self.addCleanup(self.stop); self.start()
        ask = harness.Authority.ask(self); ask.update(revision=1, object=0x504b000000000001)
        bob_context = self.join(bob, ask, 'bob-original')
        bob_help = self.client(bob, 'assist', session='bob-original', ask=ask)
        context = self.join(alice, dict(ask,session=42), 'alice-current')
        artifact = self.fixture(alice, context, self.event(bob_context, ask))
        receipt = self.client(alice, 'guest-submit', hex=artifact.hex())
        review = self.client(alice, 'review-work', attempt=receipt['attempt'])
        data = review['attempt']['data']
        self.assertTrue(data['assisted']); self.assertTrue(data['remotePresentationUncertain'])
        self.assertFalse(data['remoteAssistance'][0]['contextMatched'])
        self.assertEqual(data['assistanceDecisions'], []); self.assertEqual(review['assistance'], [])
        self.assertEqual(data['deliveryObservations'], [])
        self.assertNotIn(bob_help['decision'], json.dumps(review))

    def test_known_other_activity_does_not_taint_an_independent_response(self):
        self.enroll('alice'); alice = self.issue('alice')
        self.addCleanup(self.stop); self.start()
        ask = harness.Authority.ask(self); ask.update(revision=1, object=0x504b000000000001)
        old_context = self.join(alice, ask, 'previous-activity')
        old_help = self.client(alice, 'assist', session='previous-activity', ask=ask)
        context = self.join(alice, dict(ask,session=42,task_id=6), 'independent-current')
        artifact = self.fixture(alice, context, self.event(old_context, ask), node=6)
        receipt = self.client(alice, 'guest-submit', hex=artifact.hex())
        review = self.client(alice, 'review-work', attempt=receipt['attempt'])
        data = review['attempt']['data']
        self.assertTrue(data['independent']); self.assertFalse(data['assisted'])
        self.assertTrue(data['remoteAssistance'][0]['contextMatched'])
        self.assertFalse(data['remoteAssistance'][0]['appliesToCurrentWork'])
        self.assertEqual(data['assistanceDecisions'], []); self.assertEqual(review['assistance'], [])
        self.assertNotIn(old_help['decision'], json.dumps(review['assistance']))


if __name__ == '__main__':
    unittest.main()
