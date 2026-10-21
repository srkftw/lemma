"""Actual protected Lean publication activity choices and selected-node metadata.

The synthetic authoring fixture exercises domain semantics. Its returned package
is passed to the existing selection-frame encoder, not installed by this test;
guest selection/rendering needs a separate ordinary execution observation.
"""
import copy
import hashlib
import json
import struct
import sys
import unittest

import test_authority as harness
import test_admission as admission
import test_delivery as delivery

sys.path.insert(0, str(harness.REPO / 'scripts'))
from lemmasim_course import selection_frame


class ActivitySelection(unittest.TestCase):
    setUpClass = classmethod(harness.Authority.setUpClass.__func__)
    command = harness.Authority.command
    call = harness.Authority.call
    issue = admission.Admission.issue
    start = delivery.Delivery.start
    stop = delivery.Delivery.stop
    client = delivery.Delivery.client

    def setUp(self):
        harness.Authority.setUp(self)
        self.original = copy.deepcopy(self.unit)
        self.revised = copy.deepcopy(self.unit)
        self.revised['course']['edition'] = '2'
        self.revised['course']['title'] += ' edition two'
        self.revised['course']['nodes'][3]['title'] += ' revised activity'
        for activity in self.revised['activities']:
            if activity['id'] == 'coefficients':
                activity['id'] = 'revised-coefficients'
        for relation in self.revised['relations']:
            for name in ('fromActivity', 'toActivity'):
                if relation[name] == 'coefficients':
                    relation[name] = 'revised-coefficients'
        self.publications = {}
        for revision, unit in ((1, self.original), (2, self.revised)):
            self.publications[revision] = self.call('publish', definition=unit, policy=revision)['sequence']
            self.call('enroll', learner='alice', course=1, revision=revision)
        self.alice = self.issue('alice')
        self.bob = self.issue('bob')
        self.addCleanup(self.stop)
        self.start()

    def records(self):
        return json.loads((self.root / 'state.json').read_text())['payload']['records']

    def expected_choices(self, unit):
        return [dict(id=a['id'], title=unit['course']['nodes'][a['node']]['title'], node=a['node'],
                     kind=a['kind'], goal=a['goal'], independent=a['assessment']['independent'],
                     assistance=a['assistance']) for a in unit['activities']]

    def test_catalogue_keeps_exact_publication_activity_titles_and_pagination(self):
        before = self.records()
        first = self.client(self.alice, 'course-catalogue', limit=1)
        self.assertTrue(first['more'])
        old = first['courses'][0]
        self.assertEqual(old['revision'], 1)
        self.assertEqual(old['publicationSequence'], self.publications[1])
        self.assertEqual(old['activities'], self.expected_choices(self.original))
        self.assertEqual(len(old['activities']), len(self.original['activities']))
        self.assertTrue(all(set(a) == {'id', 'title', 'node', 'kind', 'goal', 'independent', 'assistance'}
                            for a in old['activities']))
        second = self.client(self.alice, 'course-catalogue', after=first['next'], limit=1)
        self.assertFalse(second['more'])
        new = second['courses'][0]
        self.assertEqual((new['revision'], new['policy']), (2, 2))
        self.assertEqual(new['activities'], self.expected_choices(self.revised))
        self.assertNotEqual(new['activities'][3]['title'], old['activities'][3]['title'])
        self.assertEqual(self.client(self.bob, 'course-catalogue')['courses'], [])
        self.assertEqual(self.records(), before)  # browsing does not publish, assess or retarget work

    def test_selected_activity_resolves_only_in_original_immutable_publication(self):
        before = self.records()
        default = self.client(self.alice, 'client-course', course=1, revision=1)
        selected = self.client(self.alice, 'client-course', course=1, revision=1, activity='coefficients')
        repeated = self.client(self.alice, 'client-course', course=1, revision=1, activity='coefficients')
        self.assertEqual(selected, repeated)
        self.assertEqual((default['node'], default['activity']), (0, ''))
        self.assertEqual((selected['identity'], selected['edition'], selected['node'], selected['activity'],
                          selected['publicationSequence'], selected['policy']),
                         (1, 1, 3, 'coefficients', self.publications[1], 1))
        self.assertEqual(default['package_hex'], selected['package_hex'])
        payload = bytes.fromhex(selected['package_hex'])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), selected['artifact'])
        identity, edition = struct.unpack_from('<2Q', payload, 24)
        crc, = struct.unpack_from('<Q', payload, 80)
        words = struct.unpack('<8Q', selection_frame(identity, edition, 17, crc, selected['node']))
        self.assertEqual(words, (0x31504B43414D454C, 4, 9, 1, 1, 3, 17, crc))
        revised = self.client(self.alice, 'client-course', course=1, revision=2, activity='revised-coefficients')
        self.assertEqual((revised['node'], revised['activity'], revised['publicationSequence'], revised['policy']),
                         (3, 'revised-coefficients', self.publications[2], 2))
        self.assertNotEqual(revised['artifact'], selected['artifact'])
        for revision, activity in ((1, 'revised-coefficients'), (2, 'coefficients'), (1, ''), (1, 'absent')):
            self.client(self.alice, 'client-course', course=1, revision=revision, activity=activity,
                        error='activity absent from selected publication')
        for malformed in (0, None, [], {}):
            self.client(self.alice, 'client-course', course=1, revision=1, activity=malformed,
                        error='String expected')
        for forged in ({'node': 3}, {'ordinal': 3}):
            self.client(self.alice, 'client-course', course=1, revision=1, **forged,
                        error='caller node ordinals')
        self.assertEqual(self.records(), before)

    def test_enrollment_and_principal_revocation_apply_before_activity_selection(self):
        self.client(self.bob, 'client-course', actor='owner', school='wrong', course=1, revision=1,
                    activity='coefficients', error='not enrolled')
        self.stop()
        self.call('enrollment-revoke', learner='alice', course=1, revision=1)
        self.start()
        rows = self.client(self.alice, 'course-catalogue')['courses']
        self.assertEqual([row['revision'] for row in rows], [2])
        self.client(self.alice, 'client-course', course=1, revision=1, activity='coefficients',
                    error='enrollment revoked')
        self.assertEqual(self.client(self.alice, 'client-course', course=1, revision=2,
                                     activity='revised-coefficients')['node'], 3)
        self.stop()
        self.call('admission-revoke', tokenHash=hashlib.sha256(self.alice.encode()).hexdigest())
        self.start()
        self.client(self.alice, 'course-catalogue', error='revoked')
        self.client(self.alice, 'client-course', course=1, revision=2, activity='revised-coefficients',
                    error='revoked')
        self.assertEqual(self.client(self.bob, 'course-catalogue')['courses'], [])


if __name__ == '__main__':
    unittest.main()
