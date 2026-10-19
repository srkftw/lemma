"""Actual authorized Lean preview of the immutable submitted ink layer.

The structural fixture executes maintained document/ink Actions. Rendering uses
the product's Rasterizer Action; this is hosted preview, separate from a guest.
"""
import hashlib
import json
import os
from pathlib import Path
import time
import unittest

import test_authority as harness
import test_admission as admission
import test_guest_submission as submission
from test_guest_submission import change, word


class ReviewRender(unittest.TestCase):
    setUpClass=classmethod(harness.Authority.setUpClass.__func__)
    setUp=harness.Authority.setUp
    command=harness.Authority.command
    call=harness.Authority.call
    publish=harness.Authority.publish
    enroll=harness.Authority.enroll
    issue=admission.Admission.issue
    client=admission.Admission.client
    fixture=submission.GuestSubmission.fixture

    def test_original_visibility_permission_and_actual_guest_rasterizer(self):
        self.enroll('alice');self.enroll('bob')
        token,artifact,_=self.fixture(kind=2)
        original=self.client(token,'guest-submit',hex=artifact.hex())
        teacher=self.issue('teacher');bob=self.issue('bob')
        self.client(teacher,'review-render',attempt=original['attempt'],error='grant denied')
        self.client(bob,'review-render',attempt=original['attempt'],error='grant denied')
        self.call('grant',subject='teacher',action='review',resource='alice')
        before=(self.root/'state.json').read_bytes()
        hidden=self.client(teacher,'review-render',attempt=original['attempt'])
        self.assertEqual(hidden['schema'],'lemma-school-review-ink/1')
        self.assertEqual((hidden['width'],hidden['height'],hidden['stride']),(1650,2200,825))
        self.assertEqual(hidden['gray4Hex'],'ff'*(825*2200))
        self.assertEqual((hidden['segments'],hidden['tiles'],hidden['changedPixels']),(0,0,0))
        self.assertEqual((self.root/'state.json').read_bytes(),before)
        self.assertEqual(hidden['digest'],hashlib.sha256(artifact).hexdigest())
        # An independently admitted immutable revision exposes the original
        # contact point. The hidden source artifact above is not changed.
        index=256+3712
        chunk=index+word(artifact,248)
        visible=change(change(artifact,24,word(artifact,24)+1),32,18)
        visible=change(visible,index+128+16,1)
        visible=change(visible,index+128+24,1) # stored visibility edit: show
        for offset,value in [(16,32767),(24,32767),(32,65535),(40,1)]:
            visible=change(visible,chunk+128+offset,value)
        shown=self.client(token,'guest-submit',hex=visible.hex())
        start=time.monotonic()
        rendered=self.client(teacher,'review-render',attempt=shown['attempt'])
        elapsed=time.monotonic()-start
        pixels=bytes.fromhex(rendered['gray4Hex'])
        self.assertEqual(rendered['segments'],1)
        self.assertGreater(rendered['changedPixels'],0)
        self.assertLess(rendered['changedPixels'],100)
        self.assertEqual(len(pixels),825*2200)
        self.assertTrue(any(byte != 255 for byte in pixels))
        self.assertEqual(self.client(token,'review-artifact',attempt=original['attempt'])['hex'],artifact.hex())
        self.assertIn('actual guest Rasterizer.segmentSurface',rendered['scope'])
        self.assertIn('no guest execution',rendered['scope'])
        if destination:=os.environ.get('LEMMA_SCHOOL_RENDER_EVIDENCE_DIR'):
            evidence=Path(destination);evidence.mkdir(parents=True,exist_ok=False)
            (evidence/'hidden-submission.bin').write_bytes(artifact)
            (evidence/'visible-submission.bin').write_bytes(visible)
            (evidence/'ink.gray4').write_bytes(pixels)
            (evidence/'render.json').write_text(json.dumps({key:value for key,value in rendered.items()
                if key!='gray4Hex'},indent=2)+'\n')
        invalid=change(change(visible,24,word(visible,24)+1),32,19)
        invalid=change(invalid,chunk+128+32,70000)
        retained=self.client(token,'guest-submit',hex=invalid.hex())
        self.client(teacher,'review-render',attempt=retained['attempt'],error='rasterizer rejected preview')
        self.assertEqual(self.client(teacher,'review-artifact',attempt=retained['attempt'])['hex'],invalid.hex())
        self.call('grant',subject='teacher',action='review',resource='alice',revoked=True)
        self.client(teacher,'review-render',attempt=shown['attempt'],error='grant denied')
        print(json.dumps({'reviewRenderSeconds':elapsed,'tiles':rendered['tiles'],
                          'changedPixels':rendered['changedPixels'],'bytes':len(pixels)}))


if __name__=='__main__':unittest.main()
