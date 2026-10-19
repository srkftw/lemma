"""Full immutable guest-envelope admission with maintained guest Action fixture.

The bounded RAM fixture is not claimed as target execution; the product scenario
captures the same bytes from the actual guest separately.
"""
import hashlib
import json
import struct
import subprocess
import unittest
import test_authority as harness
import test_admission as admission


def word(data, offset):
    return struct.unpack_from('<Q', data, offset)[0]


def change(data, offset, value):
    result=bytearray(data)
    struct.pack_into('<Q', result, offset, value)
    return bytes(result)


class GuestSubmission(admission.Admission):
    # Keep inherited admission tests in their own class/module.
    test_two_principals_replay_revocation_and_path_separation=None
    test_same_credential_can_teach_only_with_scope_and_revoke_takes_effect=None
    test_lost_help_acknowledgement_reuses_exact_context_until_cancelled=None
    test_pair_uses_private_os_random_handoff_and_no_raw_token_in_stdout=None

    def fixture(self, kind=1, token=None, session='guest-one', review=None, node=None):
        token=token or self.issue('alice')
        node=node or (4 if kind==1 else 6)
        ask=harness.Authority.ask(self, task=node)
        fields=dict(course=1,revision=1,session=session,guestSession=41,lifetimeMs=10000,ask=ask)
        if review: fields['reviewId']=review
        joined=self.client(token,'join',**fields)
        invitation=bytes.fromhex(joined['package_hex'])
        span=word(invitation,112)
        context=bytes.fromhex(invitation[span & 0xffffffff:(span & 0xffffffff)+(span>>32)].decode())
        package=bytes.fromhex(self.client(token,'client-course',course=1,revision=1)['package_hex'])
        source=self.base/'package.bin';source.write_bytes(package)
        source_context=self.base/'context.bin';source_context.write_bytes(context)
        output=self.base/f'envelope-{kind}.bin'
        cmd=['lake','env','lean','--run','tests/school/SubmissionFixture.lean',str(source),str(source_context),str(output),str(kind),str(node)]
        result=subprocess.run(cmd,cwd=harness.REPO,capture_output=True,timeout=40)
        self.assertEqual(result.returncode,0,(result.stdout+result.stderr).decode())
        decoded=json.loads(result.stdout)
        self.assertEqual(decoded['guestOutcome'],1)
        self.assertEqual(decoded['executionOrigin'],7)
        self.assertEqual(decoded['chunks'][0]['samples'],1)
        self.assertFalse(decoded['chunks'][0]['visible'])
        self.assertEqual(decoded['inkEditCount'],1)
        return token,output.read_bytes(),joined

    def test_exact_origin_immutable_retry_and_retarget_rejected(self):
        self.enroll('alice');self.enroll('bob')
        token,artifact,joined=self.fixture()
        bob=self.issue('bob')
        self.client(bob,'guest-submit',hex=artifact.hex(),error='actor/publication')
        receipt=self.client(token,'guest-submit',hex=artifact.hex())
        self.assertEqual(receipt['outcome'],1)
        self.assertEqual(receipt['artifact'],hashlib.sha256(artifact).hexdigest())
        replay=self.client(token,'guest-submit',hex=artifact.hex())
        self.assertTrue(replay['reused'])
        self.assertEqual(receipt['commitSequence'],replay['commitSequence'])
        self.assertEqual(len(self.client(token,'progress')['attempts']),1)
        # An actual independently valid Doc8 is retained; change only capture
        # time to test same durable queue identity/different original bytes.
        self.client(token,'guest-submit',hex=change(artifact,112,121).hex(),error='different immutable work')
        self.client(token,'guest-submit',hex=change(artifact,88,0).hex(),error='selection is stale')
        self.client(token,'cancel-session',session='guest-one')
        self.assertTrue(self.client(token,'guest-submit',hex=artifact.hex())['reused'])
        self.client(token,'guest-submit',hex=change(change(artifact,24,word(artifact,24)+1),32,18).hex(),error='cancelled')
        self.assertEqual(len(self.client(token,'progress')['attempts']),1)
        attempt=self.client(token,'review-work',attempt=receipt['attempt'])['attempt']['data']
        self.assertEqual(attempt['guestEnvelope']['executionOrigin'],7)
        self.assertIn('hosted exact',attempt['checkingScope'])

    def test_opaque_work_stays_reviewable_and_revoked_new_work_is_rejected(self):
        self.enroll('alice')
        token,artifact,_=self.fixture(kind=2)
        receipt=self.client(token,'guest-submit',hex=artifact.hex())
        self.assertEqual(receipt['outcome'],4) # old typed success is not proof
        attempt=self.client(token,'review-work',attempt=receipt['attempt'])
        self.assertEqual(attempt['attempt']['data']['guestEnvelope']['guestOutcome'],1)
        self.assertIn('opaque',attempt['attempt']['data']['checkingScope'])
        self.assertEqual(self.client(token,'review-artifact',attempt=receipt['attempt'])['hex'],artifact.hex())
        self.call('enrollment-revoke',learner='alice',course=1,revision=1)
        fresh=change(change(artifact,24,word(artifact,24)+1),32,18)
        self.client(token,'guest-submit',hex=fresh.hex(),error='enrollment revoked')
        self.assertTrue(self.client(token,'guest-submit',hex=artifact.hex())['reused'])
        self.client(token,'guest-submit',hex=artifact[:-8].hex(),error='header/version/length')
        self.call('admission-revoke',tokenHash=hashlib.sha256(token.encode()).hexdigest())
        self.client(token,'guest-submit',hex=artifact.hex(),error='revoked')


    def test_unselected_exact_activity_retains_opaque_work_for_review(self):
        self.enroll('alice')
        token,artifact,_=self.fixture(kind=2,node=4)
        receipt=self.client(token,'guest-submit',hex=artifact.hex())
        self.assertEqual(receipt['outcome'],4)
        attempt=self.client(token,'review-work',attempt=receipt['attempt'])['attempt']['data']
        self.assertEqual(attempt['activity'],'coefficients')
        self.assertEqual(attempt['guestEnvelope']['guestOutcome'],1)
        self.assertIn('opaque',attempt['checkingScope'])

    def test_original_review_is_bound_before_capture_and_completed_by_human_response(self):
        self.enroll('alice')
        token,artifact,_=self.fixture(kind=2)
        original=self.client(token,'guest-submit',hex=artifact.hex())
        review=original['attempt']
        self.call('grant',subject='teacher',action='review',resource='alice',now=86400001)
        token=self.issue('alice') # the original one-day admission expired
        opened=self.client(token,'review-open',id=review)
        self.assertEqual((opened['identity'],opened['edition'],opened['node']),(1,1,7))
        second,work,_=self.fixture(kind=2,token=token,session='guest-review',review=review,node=8)
        response=self.client(second,'guest-submit',hex=work.hex())
        progress=self.client(token,'progress')
        self.assertFalse(any(item['key']==review for item in progress['due']))
        self.call('human-assess',actor='teacher',attempt=response['attempt'],version=1,
                  previousSequence=0,disposition='accepted',criteria=['met','met'],comment='Independent written reconstruction reviewed.')
        state=json.loads((self.root/'state.json').read_text())['payload']
        original_reviews=[r for r in state['records'] if r['kind']=='review' and r['key']==review]
        self.assertEqual(original_reviews[-1]['data']['status'],'completed')
        attempts=self.client(token,'progress')['attempts']
        self.assertEqual([r['data']['outcome'] for r in attempts],[4,4])
        self.assertEqual(attempts[-1]['data']['request']['reviewId'],review)
        self.assertIn('human-review',self.client(token,'feedback')['feedback'][0]['data']['scope'])


if __name__=='__main__':unittest.main()
