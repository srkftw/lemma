"""Source admission negatives; these do not execute a guest or fabricate IR.

The separate actual Lean Action mutation campaign and genuine whole-image
LLVM catalogs remain required. These checks protect the reviewed source/layout
conditions rather than treating a matching catalog as semantic justification.
"""
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from core0_common import Core0Error
from multimodal_target import notebook_safety_sources


class SchoolWarmSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = tuple((ROOT / path).read_text() for path in (
            'Lemma/User/Multimodal.lean', 'Lemma/Applications/Notebook.lean',
            'Lemma/Notebook/ControlBacklog.lean'))

    def reject(self, before, after, message='source warm', function=None):
        source = self.sources[1]
        if function:
            start = source.index('private def ' + function + ' ')
            end = source.find('\nprivate def ', start + 1)
            if end < 0:
                end = len(source)
            self.assertIn(before, source[start:end], 'missing scoped mutation anchor')
            changed = source[:start] + source[start:end].replace(before, after, 1) + source[end:]
        else:
            self.assertIn(before, source, 'missing mutation anchor')
            changed = source.replace(before, after, 1)
        with self.assertRaisesRegex(Core0Error, message):
            notebook_safety_sources(self.sources[0], changed, self.sources[2])

    def test_current_warm_context_is_120_bytes_and_disjoint(self):
        result = notebook_safety_sources(*self.sources)
        self.assertTrue(result['warm_submission'])
        windows = {name: (start, length) for name, start, length in result['disjoint_windows']}
        self.assertEqual(windows['tutor context'], (1024, 120))
        self.assertEqual(windows['school context'], (1152, 104))
        self.assertLessEqual(sum(windows['tutor context']), windows['school context'][0])

    def test_legacy_without_warm_helpers_keeps_88_byte_context(self):
        # Deliberately legacy source-gate scope, not a target install candidate:
        # remove the new helpers and wrapper while leaving older safety routes.
        notebook = re.sub(r'^private def schoolSendSource\b.*?(?=^private def schoolSendAttempt\b)',
                          '', self.sources[1], flags=re.M | re.S)
        notebook = re.sub(r'^private def schoolSendAttempt\b.*?(?=^private def schoolCancel\b)',
                          '', notebook, flags=re.M | re.S)
        notebook = re.sub(r'^  \.bind \(tutorPut (?:88|96|104|112) [^\n]+\n',
                          '', notebook, flags=re.M)
        result = notebook_safety_sources(self.sources[0], notebook, self.sources[2])
        self.assertFalse(result['warm_submission'])
        self.assertIn(('tutor context', 1024, 88), result['disjoint_windows'])

    def test_partial_removal_cannot_downgrade_warm_context_to_legacy(self):
        changed = self.sources[1].replace('private def schoolSendSource :', 'private def renamedSendSource :')
        changed = changed.replace('private def schoolSendAttempt :', 'private def renamedSendAttempt :')
        for source in (changed, re.sub(r'^  \.bind \(tutorPut 112 [^\n]+\n', '', changed, flags=re.M)):
            with self.subTest(snapshot_ready='tutorPut 112' in source):
                with self.assertRaisesRegex(Core0Error, '(?:source warm|definition absent/duplicate: schoolSendSource)'):
                    notebook_safety_sources(self.sources[0], source, self.sources[2])

    def test_ask_invalidates_first_and_publishes_complete_snapshot_last(self):
        for before, after in (
            ('(tutorPut 112 0)', '(tutorPut 112 1)'),
            ('(tutorPut 88 crc)', '(tutorPut 88 0)'),
            ('(tutorPut 96 ns)', '(tutorPut 96 0)'),
            ('(tutorPut 104 page)', '(tutorPut 104 0)'),
            ('(tutorPut 112 1)', '(tutorPut 112 0)'),
            ('(tutorPut 24 (Lemma.Courses.PackageWorkspace.object page))', '(tutorPut 24 1)')):
            with self.subTest(before=before):
                self.reject(before, after, function='multimodalAsk')

    def test_reserved_help_or_binding_cannot_become_original_ask(self):
        for before, after in (
            ('if identity = 60000 then .done 244 0 else', 'if identity = 60002 then .done 244 0 else'),
            ('if identity = 60001 then .done 244 0 else', 'if identity = 60002 then .done 244 0 else')):
            with self.subTest(before=before):
                self.reject(before, after, function='multimodalAskLocation')

    def test_ask_cannot_substitute_history_or_another_binding_field(self):
        for before, after, function in (
            ('(Memory.read64 (packageBytes + 80)) fun s crc', '(Memory.read64 (packageBytes + 32)) fun s crc', 'multimodalAskLocation'),
            ('(Memory.read64 entry) fun s node', '(Memory.read64 packageBytes) fun s node', 'multimodalAskLocation'),
            ('(Memory.read64 (binding + 32)) fun s crc', '(Memory.read64 (binding + 24)) fun s crc', 'multimodalAsk'),
            ('(multimodalAskLocation ns page) fun s binding', '(Lemma.Courses.BrowseHistory.location packageWorkspace ns page) fun s binding', 'multimodalAsk')):
            with self.subTest(before=before):
                self.reject(before, after, function=function)

    def test_overlay_requires_exact_work_revision_and_admission(self):
        for before, after in (
            ('if loaded = 60001 then', 'if loaded = 60002 then'),
            ('if ready = 1 then if ns = expectedNS', 'if ready = 0 then if ns = expectedNS'),
            ('if ns = expectedNS then if page = expectedPage', 'if ns = ns then if page = expectedPage'),
            ('if page = expectedPage then', 'if page = page then'),
            ('if object = Lemma.Courses.PackageWorkspace.object page then', 'if object = object then'),
            ('if 0 < previousRevision then if previousRevision ≤ revision', 'if 0 ≤ previousRevision then if previousRevision ≤ revision'),
            ('if previousRevision ≤ revision then if session = joinedSession', 'if previousRevision ≤ previousRevision then if session = joinedSession'),
            ('if session = joinedSession then', 'if session = session then'),
            ('if identity = joinedSource then if edition = joinedEdition', 'if identity = identity then if edition = joinedEdition'),
            ('if edition = joinedEdition then', 'if edition = edition then'),
            ('if identity = 60000 then .done 240 0 else', 'if identity = 60002 then .done 240 0 else'),
            ('if identity = 60001 then .done 240 0 else', 'if identity = 60002 then .done 240 0 else')):
            with self.subTest(before=before):
                self.reject(before, after, function='schoolSendSource')

    def test_known_workspace_and_local_scratch_cannot_retarget(self):
        for before, after in (
            ('if (mask >>> 8) &&& 1 = 1 then', 'if (mask >>> 8) &&& 1 = 0 then'),
            ('if identity = selectedSource then', 'if identity = identity then'),
            ('if edition = selectedEdition then', 'if edition = edition then'),
            ('if crc = selectedCRC then', 'if crc = crc then'),
            ('store identity edition node crc', 'store loaded edition node crc'),
            ('(packageBindingScratch+16) identity', '(packageWorkspace+16) identity'),
            ('(packageBindingScratch+40) node', '(packageBindingScratch+40) 1')):
            with self.subTest(before=before):
                self.reject(before, after, function='schoolSendSource')

    def test_typed_selection_remains_exact_and_retry_precedes_validation(self):
        for before, after in (
            ('if boundRevision = revision then 1 else 2', 'if boundRevision = boundRevision then 1 else 2'),
            ('if checksum = crc then', 'if checksum = checksum then'),
            ('if phase = 26 then Lemma.Courses.SchoolSubmission.retry', 'if phase = 26 then schoolSendSource'),
            ('if phase = 45 then Lemma.Courses.SchoolSubmission.retry', 'if phase = 45 then schoolSendSource'),
            ('(schoolHeaderPut 64 identity)', '(schoolHeaderPut 64 60001)'),
            ('(schoolHeaderPut 104 kind)', '(schoolHeaderPut 104 1)')):
            with self.subTest(before=before):
                self.reject(before, after, function='schoolWorkKind' if 'boundRevision' in before or 'checksum' in before else 'schoolSendAttempt')

    def test_rejection_is_visible_and_exact_status_survives(self):
        for before, after in (
            ('.bind (schoolQueueFailure result) fun s _ =>', '.bind (.done 0 0) fun s _ =>'),
            ('then .done s 0 else .done result value\n  else .bind (Memory.write64 schoolQueueError 0)',
             'then .done s 0 else .done 0 value\n  else .bind (Memory.write64 schoolQueueError 0)'),
            ('else .bind (Memory.write64 schoolQueueError 0)', 'else .bind (.done 0 0)')):
            with self.subTest(before=before):
                self.reject(before, after, function='schoolSend')


if __name__ == '__main__':
    unittest.main()
