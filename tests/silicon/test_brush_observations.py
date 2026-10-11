# SPDX-License-Identifier: Apache-2.0
"""Literal host-unit records reject false brush-edit and Save observations.

These bytes are test fixtures only. They are never supplied to RTL or a guest.
"""
from pathlib import Path
import copy
from dataclasses import replace
import json
import struct
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'conformance/silicon'))
from notebook_observations import (fixture,validate_fixture,document_payloads,
                                  explicit_save,reset_identity)
from store_oracle import Record

MAGIC=0x314b4e49414d454c

class BrushObservationTests(unittest.TestCase):
    def test_explicit_brush_fixture_preserves_pressure_and_declares_only_width_save(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            data=fixture(directory,500000000,100000000,'brush-width')
            raw=validate_fixture(data,directory/'events.txt','brush-width')
            self.assertEqual(len(raw),11)
            self.assertEqual([row[4] for row in raw[1:7]],[1024,1216,1408,1600,1792,0])
            self.assertEqual([row['button'] for row in data['actions'][1:]],[6,7])
            self.assertEqual(data['actions'][0]['brush_q8'],512)
            self.assertNotIn('undo',str(data['actions']))
            self.assertNotIn('redo',str(data['actions']))
            with self.assertRaisesRegex(ValueError,'session differs'):
                validate_fixture(data,directory/'events.txt')

    def test_missing_selector_does_not_auto_admit_a_different_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            data=fixture(directory,500000000,100000000,'brush-width')
            del data['session']
            with self.assertRaisesRegex(ValueError,'session differs'):
                validate_fixture(data,directory/'events.txt','brush-width')
            with self.assertRaisesRegex(ValueError,'unknown notebook'):
                fixture(directory,500000000,100000000,'arbitrary-edit')

    def test_manifest_cannot_relabel_a_different_toolbar_or_stroke_slice(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            data=fixture(directory,500000000,100000000,'brush-width')
            for changes in ({'button':3},{'first_sequence':2}):
                changed=copy.deepcopy(data);changed['actions'][1].update(changes)
                with self.assertRaisesRegex(ValueError,'exact stroke/edit/save'):
                    validate_fixture(changed,directory/'events.txt','brush-width')

    @staticmethod
    def records():
        # Authored little-endian document-v1 and page-v2 literals, not Lean codecs.
        raw=[(index+2,50000001+index*50000,13082+index*385,23589+index*205,
              1024+index*192 if index<5 else 0,3 if index<5 else 2,1,0,1)
             for index in range(6)]
        chunk=struct.pack('<16Q',MAGIC,1,3,1,3,0,6,512,1,65535,65535,4095,512,640,3,0)
        chunk+=b''.join(struct.pack('<9Q',*row) for row in raw)
        page=struct.pack('<16Q',MAGIC,2,2,1,1,1,1,0,0,0,0,0,0,0,0,0)
        page+=struct.pack('<3Q',65540,3,1)+struct.pack('<2Q',1,3)
        root=struct.pack('<8Q',MAGIC,1,1,1,1024,0,0,0)
        return raw,{(1,65540):Record(1,65540,3,3,1,chunk,20),
                    (1,257):Record(1,257,4,4,1,page,24),
                    (1,1):Record(1,1,6,6,1,root,31)}

    def test_literal_six_sample_page_and_persisted_width_are_observed(self):
        raw,records=self.records()
        self.assertEqual(document_payloads(records,raw,'brush-width',6),
                         {'brush_q8':1024,'stroke_id':3,'chunk_object':65540})

    def test_missing_or_old_brush_root_cannot_claim_edit(self):
        raw,records=self.records()
        del records[(1,1)]
        with self.assertRaisesRegex(ValueError,'declared brush edit'):
            document_payloads(records,raw,'brush-width',6)
        raw,records=self.records()
        records[(1,1)]=replace(records[(1,1)],payload=struct.pack('<8Q',MAGIC,1,1,1,512,0,0,0))
        with self.assertRaisesRegex(ValueError,'declared brush edit'):
            document_payloads(records,raw,'brush-width',6)

    def test_page_cannot_point_to_another_chunk_or_edit_stroke(self):
        for offset,value in ((128,65541),(152,2),(160,4),(56,1)):
            raw,records=self.records();changed=bytearray(records[(1,257)].payload)
            struct.pack_into('<Q',changed,offset,value)
            records[(1,257)]=replace(records[(1,257)],payload=bytes(changed))
            with self.assertRaisesRegex(ValueError,'exact visible stroke identity'):
                document_payloads(records,raw,'brush-width',6)

    def test_all_nine_raw_words_remain_authoritative(self):
        for field in range(9):
            raw,records=self.records();changed=bytearray(records[(1,65540)].payload)
            struct.pack_into('<Q',changed,128+field*8,raw[0][field]+1)
            records[(1,65540)]=replace(records[(1,65540)],payload=bytes(changed))
            with self.assertRaises(ValueError):document_payloads(records,raw,'brush-width',6)

    def test_root_must_follow_the_chunk_and_page_commit(self):
        raw,records=self.records();records[(1,1)]=replace(records[(1,1)],sequence=2)
        with self.assertRaisesRegex(ValueError,'ordering differs'):
            document_payloads(records,raw,'brush-width',6)
        raw,records=self.records();records[(2,1)]=replace(records[(1,1)],namespace=2)
        with self.assertRaisesRegex(ValueError,'unexpected document objects'):
            document_payloads(records,raw,'brush-width',6)

    def test_prior_stroke_saved_cannot_confirm_explicit_save(self):
        with self.assertRaisesRegex(ValueError,'final explicit Save'):
            explicit_save([(0x421,6,1,1,3)],6)
        with self.assertRaisesRegex(ValueError,'stale or regressed'):
            explicit_save([(0x421,6,1,1,0)],6)

    def test_actual_pending_save_confirmed_but_failure_or_regression_rejected(self):
        self.assertEqual(explicit_save([(0x421,2,1,1,0),(0x421,6,1,1,3),
                                       (0x423,6,1,1,0),(0x421,6,1,1,0)],6),
                         (0x421,6,1,1,0))
        for states in ([(0x423,7,1,1,0),(0x421,6,1,1,0)],
                       [(0x423,6,1,1,0),(0x424,223,1,1,0),(0x421,6,1,1,0)],
                       [(0x423,6,1,2,0),(0x421,6,1,1,0)]):
            with self.assertRaisesRegex(ValueError,'stale or regressed'):explicit_save(states,6)
        with self.assertRaisesRegex(ValueError,'final explicit Save'):
            explicit_save([(0x423,6,1,1,0)],6)

if __name__=='__main__':unittest.main()
