"""Artifact authority from genuine source; no host execution substitutes for guest."""
from pathlib import Path
import copy
import json
import re
import sys
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
from core0_common import Core0Error
from lemmasim_readonly import validate_lookup,validate_devices

class BLEDiscovery(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture=json.loads((ROOT/'tests/kernel/fixtures/ble-discovery-generated.json').read_text())
        cls.unit=cls.fixture['unit'];cls.ir=cls.fixture['optimized_ir']
    def reject(self,text):
        with self.assertRaises(Core0Error):validate_lookup(text,self.unit)
    def test_actual_closed_tables_and_four_hardware_guards(self):
        tables=validate_lookup(self.ir,self.unit)[1]
        self.assertEqual(len(tables),35)
        self.assertEqual({r['literal_schema'] for r in tables},{'ble-packet-v1'})
        irq=next(r for r in tables if r['source'].endswith('.expectedIRQ'))
        self.assertEqual(irq['values'],[12,13,1,None,None,10,11,14,15])
        for optimized,key in [(False,'ir'),(True,'optimized_ir')]:
            self.assertEqual(len(validate_devices(self.fixture[key],self.unit,optimized)[1]),4)
    def test_ble_strings_bounds_and_selection_are_load_bearing(self):
        changes=[('i64 12336], align 8','i64 12337], align 8'),
                 ('icmp ult i64 %switch.tableidx, 76','icmp ult i64 %switch.tableidx, 77'),
                 ('i64 76, label %if.then.48','i64 77, label %if.then.48')]
        for old,new in changes:
            with self.subTest(old=old):
                changed=self.ir.replace(old,new,1);self.assertNotEqual(changed,self.ir);self.reject(changed)
    def test_poison_rows_irq_and_mixed_schema_rejected(self):
        for old,new in [('lshr i16 -16257','lshr i16 -16249'),
                        ('lshr i16 487','lshr i16 495'),
                        ('i64 14, i64 15], align 8','i64 14, i64 14], align 8'),
                        ('[16 x i64] [i64 1, i64 2','[15 x i64] [i64 1, i64 2')]:
            with self.subTest(old=old):
                changed=self.ir.replace(old,new,1);self.assertNotEqual(changed,self.ir);self.reject(changed)
    def test_kernel5_cannot_alias_historical_aperture_or_unchecked_pointer(self):
        old=copy.deepcopy(self.unit);old['contract_version']='core0-kernel-v0.4'
        with self.assertRaises(Core0Error):validate_devices(self.fixture['ir'],old,False)
        for text,optimized in [(self.fixture['ir'].replace('201326652','201326656'),False),
                               (self.ir.replace('load volatile i32','load i32',1),True)]:
            self.assertNotEqual(text,self.fixture['ir'] if not optimized else self.ir)
            with self.assertRaises(Core0Error):validate_devices(text,self.unit,optimized)
