# SPDX-License-Identifier: Apache-2.0
"""Literal optical observer tests; no bytes here are supplied to RTL/guest."""
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'conformance/silicon'))
from notebook_observations import contact_ink

class ContactObservationTests(unittest.TestCase):
    SAMPLE=(2,70050000,13082,23589,1024,3,1,0,1)
    @staticmethod
    def pixels(point=None):
        pixels=bytearray([255])*512*640
        if point is not None:pixels[point[1]*512+point[0]]=0
        return bytes(pixels)
    @staticmethod
    def events(path,phases,point=(102,229),trailing=None):
        rows=['cycle,event,sequence,x,y,gray\n']
        for sequence,gray in enumerate(phases,1):
            rows.extend([f'{sequence*10},pixel,{sequence},{point[0]},{point[1]},{gray}\n',
                         f'{sequence*10+1},complete,{sequence},0,0,0\n'])
        if trailing is not None:rows.append(trailing)
        path.write_text(''.join(rows))
    def test_quantized_contact_neighbor_has_actual_completed_ink(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events';self.events(path,[0])
            pixels=self.pixels((102,229))
            self.assertEqual(pixels[230*512+102],255)
            self.assertEqual(contact_ink(path,self.SAMPLE,512,640,pixels),
                             (102,229,[(11,1,0)],['ink']))
    def test_same_point_undo_and_redo_remain_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events';self.events(path,[0,15,0])
            self.assertEqual(contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)),'undo-redo')[3],
                             ['ink','white','ink'])
            for phases in ([0],[15,0],[0,15],[15,0,15]):
                self.events(path,phases)
                with self.assertRaisesRegex(ValueError,'same-point stroke/undo/redo|retained stroke'):
                    contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)),'undo-redo')
    def test_all_white_and_distant_dark_pixels_cannot_claim_retained_ink(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events';self.events(path,[0],point=(102,227))
            for pixels in (self.pixels(),self.pixels((102,227))):
                with self.assertRaisesRegex(ValueError,'retained stroke'):
                    contact_ink(path,self.SAMPLE,512,640,pixels)
    def test_final_pgm_cannot_substitute_for_actual_completed_ink(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events';self.events(path,[15])
            with self.assertRaisesRegex(ValueError,'retained stroke'):
                contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)))
            self.events(path,[0,15])
            with self.assertRaisesRegex(ValueError,'retained stroke'):
                contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)))
    def test_pending_only_or_trailing_pixels_cannot_be_hidden_by_final_pgm(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events'
            path.write_text('cycle,event,sequence,x,y,gray\n10,pixel,1,102,229,0\n')
            with self.assertRaisesRegex(ValueError,'no actual controller completion'):
                contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)))
            self.events(path,[0],trailing='20,pixel,2,102,229,0\n')
            with self.assertRaisesRegex(ValueError,'incomplete accepted update'):
                contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)))
    def test_two_dark_values_cannot_hide_final_pgm_controller_contradiction(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events';self.events(path,[0])
            pixels=bytearray(self.pixels((102,229)));pixels[229*512+102]=17
            with self.assertRaisesRegex(ValueError,'retained stroke'):
                contact_ink(path,self.SAMPLE,512,640,bytes(pixels))
    def test_undo_redo_cannot_combine_different_points(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events'
            path.write_text('cycle,event,sequence,x,y,gray\n10,pixel,1,102,229,0\n11,complete,1,0,0,0\n'
                            '20,pixel,2,103,230,15\n21,complete,2,0,0,0\n'
                            '30,pixel,3,103,230,0\n31,complete,3,0,0,0\n')
            pixels=bytearray(self.pixels((102,229)));pixels[230*512+103]=0
            with self.assertRaisesRegex(ValueError,'same-point stroke/undo/redo'):
                contact_ink(path,self.SAMPLE,512,640,bytes(pixels),'undo-redo')
    def test_unknown_session_is_not_an_optical_admission(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events';self.events(path,[0])
            with self.assertRaisesRegex(ValueError,'unknown notebook'):
                contact_ink(path,self.SAMPLE,512,640,self.pixels((102,229)),'arbitrary')

if __name__=='__main__':unittest.main()
