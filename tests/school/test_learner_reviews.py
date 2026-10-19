"""Actual own-learner due pagination; teacher review authority is separate."""
import unittest
import test_authority as harness
import test_admission as admission


class LearnerReviews(unittest.TestCase):
    setUpClass=classmethod(harness.Authority.setUpClass.__func__)
    setUp=harness.Authority.setUp
    command=harness.Authority.command
    call=harness.Authority.call
    publish=harness.Authority.publish
    enroll=harness.Authority.enroll
    issue=admission.Admission.issue
    client=admission.Admission.client

    def attempt(self, learner, identity, **extra):
        return self.call('attempt',actor=learner,course=1,revision=1,activity='coefficients',
                         id=identity,values=[0,1,1,2,1],**extra)

    def test_own_due_pages_keep_original_publication_and_latest_disposition(self):
        self.enroll('alice');self.enroll('bob')
        for name in ['defer','withdraw','page-one','page-two']:self.attempt('alice',name)
        self.attempt('bob','bob-original')
        self.call('grant',subject='teacher',action='review',resource='alice',now=86400001)
        alice=self.issue('alice');bob=self.issue('bob')
        self.client(alice,'review-state',id='defer',status='deferred',due=86401001,reason='After the current exercise')
        self.client(alice,'review-state',id='withdraw',status='withdrawn',reason='Teacher replaced this review')
        first=self.client(alice,'reviews',limit=1)
        self.assertEqual([r['id'] for r in first['reviews']],['page-one'])
        self.assertTrue(first['more'])
        second=self.client(alice,'reviews',limit=1,after=first['next'])
        self.assertEqual([r['id'] for r in second['reviews']],['page-two'])
        self.assertFalse(second['more'])
        row=first['reviews'][0]
        self.assertEqual((row['course'],row['revision'],row['node'],row['ordinal']),(1,1,7,8))
        self.assertEqual(row['courseTitle'],self.unit['course']['title'])
        self.assertEqual(row['title'],self.unit['course']['nodes'][7]['title'])
        self.assertEqual([r['id'] for r in self.client(bob,'reviews')['reviews']],['bob-original'])
        self.client(alice,'reviews',learner='bob',error='admitted learner')
        self.client(alice,'reviews',limit=51,error='page limit')
        self.client(alice,'review-queue',learner='alice',error='grant denied')
        self.client(alice,'review-open',id='page-one')
        self.assertEqual(len(self.client(alice,'reviews')['reviews']),2) # opening is not completion
        self.call('attempt',actor='alice',course=1,revision=1,activity='later-review',id='actual-response',
                  values=[0,0,0,0,0],reviewId='page-one')
        self.call('human-assess',actor='teacher',attempt='actual-response',version=1,previousSequence=0,
                  disposition='accepted',comment='Original written review response assessed.',criteria=['met','met'])
        self.assertEqual([r['id'] for r in self.client(alice,'reviews')['reviews']],['page-two'])
        self.call('grant',subject='teacher',action='review',resource='alice',now=86402001)
        last=self.client(alice,'reviews')['reviews']
        self.assertEqual([r['id'] for r in last],['page-two','defer'])
        self.assertEqual(last[-1]['status'],'deferred')


if __name__=='__main__':unittest.main()
